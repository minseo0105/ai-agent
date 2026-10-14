"""Bounded official HTTP acquisition. No access-control bypass or guessed URLs."""
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit, parse_qs

import requests
from bs4 import BeautifulSoup

PORTAL = 'https://data.seoul.go.kr/dataList/OA-22712/S/1/datasetView.do'
HOSTS = {'cleanup.seoul.go.kr', 'news.seoul.go.kr', 'data.seoul.go.kr',
         'datafile.seoul.go.kr', 'urban.seoul.go.kr'}
MAX_BYTES = 150 * 1024 * 1024


class SourceError(Exception):
    """Only fixed safe codes escape network operations."""
    @property
    def safe_code(self):
        return str(self)


def official_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in HOSTS
            and parsed.port in (None, 443) and not parsed.username and not parsed.password)


def decode(body):
    options = [body.decode(e, 'replace') for e in ('utf-8', 'cp949')]
    return max(options, key=lambda t: sum('가' <= c <= '힣' for c in t) - t.count('�') * 5)


class OfficialHTTP:
    def __init__(self, directory, session=None, sleeper=time.sleep):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.sleeper = sleeper
        self.objects = []
        self.pages = {}
        self.unavailable = set()

    def request(self, method, url, **kwargs):
        for redirect in range(4):
            if not official_url(url):
                raise SourceError('UNTRUSTED_OFFICIAL_URL')
            if urlsplit(url).hostname in self.unavailable:
                raise SourceError('SOURCE_HOST_UNAVAILABLE')
            response = None
            for attempt in range(3):
                try:
                    response = self.session.request(method, url, timeout=(10, 40),
                                                    allow_redirects=False, stream=True, **kwargs)
                    if response.status_code not in (429, 500, 502, 503, 504):
                        break
                except (requests.Timeout, requests.ConnectionError):
                    if attempt == 2:
                        self.unavailable.add(urlsplit(url).hostname)
                        raise SourceError('SOURCE_NETWORK_FAILURE') from None
                if response is not None:
                    response.close()
                if attempt < 2:
                    self.sleeper(2 ** attempt)
            if response is None:
                raise SourceError('SOURCE_UNAVAILABLE')
            if response.status_code in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers.get('Location', ''))
                if urlsplit(target).hostname=='www.seoul.go.kr' and urlsplit(target).path=='/common/errorAccess.html':
                    response.close()
                    raise SourceError('SOURCE_ACCESS_DENIED')
                parsed=urlsplit(target)
                # Seoul's canonical page redirects to its own http://...?refresh.
                # Upgrade that exact official host to TLS; never send plain HTTP.
                if parsed.scheme=='http' and parsed.hostname in HOSTS and parsed.port in (None,80):
                    target=parsed._replace(scheme='https',netloc=parsed.hostname).geturl()
                response.close()
                url = target
                if response.status_code in (301, 302, 303):
                    method, kwargs = 'GET', {}
                continue
            if response.status_code != 200:
                response.close()
                if response.status_code in (401,403,429,500,502,503,504):
                    self.unavailable.add(urlsplit(url).hostname)
                raise SourceError('SOURCE_HTTP_' + str(response.status_code))
            body = bytearray()
            try:
                for chunk in response.iter_content(65536):
                    if len(body) + len(chunk) > MAX_BYTES:
                        raise SourceError('SOURCE_TOO_LARGE')
                    body.extend(chunk)
            finally:
                response.close()
            response._content = bytes(body)
            response.url = url
            sha = hashlib.sha256(body).hexdigest()
            path = self.directory / sha
            if not path.exists():
                path.write_bytes(body)
            self.objects.append({'sha256': sha, 'path': str(path), 'source_url': url,
                                 'bytes': len(body), 'content_type': response.headers.get('Content-Type')})
            return response
        raise SourceError('TOO_MANY_REDIRECTS')

    def get(self, url, **_):
        return self.request('GET', url)

    def text(self, url):
        if url not in self.pages:
            self.pages[url] = decode(self.get(url).content)
        return self.pages[url]


def discover_archive(html, page_url=PORTAL):
    """Extract posted filename + sequence + actual frmFile action, never invent a date."""
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.find('form', attrs={'name': 'frmFile'})
    if form is None:
        raise SourceError('DOWNLOAD_FORM_CHANGED')
    fields = {x['name']: x.get('value', '') for x in form.select('input[name]')}
    if fields.get('infId') != 'OA-22712':
        raise SourceError('DATASET_ID_MISMATCH')
    action = form.get('action')
    if not action or action == '#':
        match = re.search(r'document\.frmFile\.action\s*=\s*[\'"]([^\'"]+)', html)
        action = match.group(1) if match else None
    url = urljoin(page_url, action or '')
    if not action or not official_url(url) or urlsplit(url).hostname != 'datafile.seoul.go.kr':
        raise SourceError('OFFICIAL_DOWNLOAD_URL_UNAVAILABLE')
    files = []
    for anchor in soup.select('a[title]'):
        name = anchor['title']
        if 'UQ120' not in name.upper() or not name.lower().endswith('.zip'):
            continue
        seq = re.search(r'downloadFile\([\'"](\d+)[\'"]\)', anchor.get('href', ''))
        version = re.search(r'_(\d{6})\.zip$', name, re.I)
        if seq and version and name == PurePosixPath(name).name:
            files.append({'filename': name, 'version': version.group(1), 'download_url': url,
                          'form': dict(fields, seq=seq.group(1)), 'seq': seq.group(1)})
    if not files:
        raise SourceError('OFFICIAL_ARCHIVE_NOT_DISCOVERED')
    latest = max(x['version'] for x in files)
    candidates = [x for x in files if x['version'] == latest]
    if len(candidates) != 1:
        raise SourceError('AMBIGUOUS_LATEST_ARCHIVE')
    return candidates[0]


def validate_zip(body):
    if not body.startswith(b'PK'):
        raise SourceError('NOT_A_ZIP')
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as bundle:
            infos = bundle.infolist()
            if len(infos) > 200 or sum(x.file_size for x in infos) > MAX_BYTES * 5:
                raise SourceError('ARCHIVE_EXPANSION_LIMIT')
            for x in infos:
                p = PurePosixPath(x.filename.replace('\\', '/'))
                if p.is_absolute() or '..' in p.parts or x.flag_bits & 1:
                    raise SourceError('UNSAFE_ARCHIVE')
            names = {x.filename.lower() for x in infos}
            stems = [n[:-4] for n in names if n.endswith('.shp') and 'uq120' in n]
            if len(stems) != 1:
                raise SourceError('AMBIGUOUS_UQ120_LAYER')
            if any(stems[0] + '.' + e not in names for e in ('shp', 'dbf', 'shx', 'prj')):
                raise SourceError('SHP_COMPONENT_MISSING')
            if bundle.testzip():
                raise SourceError('ZIP_CRC_FAILURE')
    except (zipfile.BadZipFile, RuntimeError):
        raise SourceError('CORRUPT_ZIP') from None


def acquire_archive(http, directory, previous=None, force=False):
    file = discover_archive(http.text(PORTAL))
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if previous and not force and all(previous.get(k)==file[k] for k in ('version','seq','download_url')):
        existing=directory/(previous['sha256']+'.zip')
        if existing.is_file() and hashlib.sha256(existing.read_bytes()).hexdigest()==previous['sha256']:
            validate_zip(existing.read_bytes())
            return dict(previous,path=str(existing),unchanged=True,downloaded=False)
    # Monthly full revalidation catches replacement under the same advertised filename.
    response = http.request('POST', file['download_url'], data=file['form'])
    validate_zip(response.content)
    sha = hashlib.sha256(response.content).hexdigest()
    path = directory / (sha + '.zip')
    if not path.exists():
        path.write_bytes(response.content)
    manifest = dict(file, sha256=sha, bytes=len(response.content), path=str(path))
    manifest.pop('form')
    manifest['unchanged'] = bool(previous and previous.get('sha256') == sha)
    manifest['downloaded'] = True
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    return manifest


def labeled_dates(html):
    """Only exact official labels and unambiguous four-digit dates have meaning."""
    labels={'자료기준일':'source_date','데이터기준일':'source_date','기준일':'source_date',
            '고시일':'notice_date','고시일자':'notice_date','효력발생일':'effective_date',
            '시행일':'effective_date','공고일':'publication_date'}
    soup=BeautifulSoup(html,'html.parser')
    values={}
    for cell in soup.select('th,dt'):
        field=labels.get(''.join(cell.get_text().split()))
        if not field:
            continue
        value=cell.find_next_sibling('td' if cell.name=='th' else 'dd')
        text=value.get_text(' ',strip=True) if value else ''
        match=re.fullmatch(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\.?',text)
        if not match:
            values[field]=None
            continue
        try:
            stamp=datetime(*map(int,match.groups())).date().isoformat()
        except ValueError:
            values[field]=None
            continue
        if field in values and values[field]!=stamp:
            raise SourceError('CONFLICTING_OFFICIAL_DATES')
        values[field]=stamp
    return values


NOTICE_BOARD='https://cleanup.seoul.go.kr/cleanup/bbs/lscr.do?bbsClCode=100&ctgryClCode=100'


def collect_notices(http, seen=(), max_pages=5):
    """Official 게시일/등록일 is an observation date, never an inferred notice date.

    Incremental scope covers the most recent 30 days, including changed existing IDs. A
    bounded initial backlog that cannot reach either boundary is PARTIAL.
    """
    from datetime import timedelta
    cutoff=datetime.now(timezone.utc).date()-timedelta(days=30)
    known=set(seen);items=[];documents=set();complete=False;ids=set();target_ids=set()
    for page in range(1,max_pages+1):
        url=NOTICE_BOARD+'&cpage='+str(page)
        html=http.text(url);sha=hashlib.sha256(html.encode()).hexdigest()
        if sha in documents:raise SourceError('NOTICE_DUPLICATE_PAGE')
        documents.add(sha);soup=BeautifulSoup(html,'html.parser');links=[]
        for anchor in soup.select('a[href]'):
            href=urljoin(url,anchor['href']);params=parse_qs(urlsplit(href).query)
            sn=(params.get('bbs.bbsSn') or [None])[0]
            if sn and sn.isdigit() and urlsplit(href).path=='/cleanup/bbs/vscr.do':
                links.append((sn,href,anchor.get_text(' ',strip=True)))
        if not links:
            raise SourceError('NOTICE_LAYOUT_CHANGED_OR_EMPTY')
        recent_on_page=False
        unknown_date=False
        for sn,href,title in links:
            if sn in ids:continue
            ids.add(sn)
            date=re.search(r'(?:등록일|게시일)\s*:?\s*(\d{4}-\d{2}-\d{2})',title)
            if date and datetime.fromisoformat(date.group(1)).date()<cutoff:
                continue
            recent_on_page=True
            unknown_date=unknown_date or date is None
            if not official_url(href):raise SourceError('UNTRUSTED_NOTICE_URL')
            detail=http.text(href)
            ds=BeautifulSoup(detail,'html.parser')
            text=ds.get_text(' ',strip=True)
            semantic=re.sub(r'조회수\s*:?\s*[\d,]+','조회수',text)
            raw_hash=hashlib.sha256(semantic.encode()).hexdigest()
            aliases=[]
            for a in ds.select('a[href]'):
                p=urlsplit(urljoin(href,a['href']));q=parse_qs(p.query)
                if p.hostname=='cleanup.seoul.go.kr' and p.path=='/cafe/mainIndx.do':
                    aliases.extend(q.get('cafeUrl',[]))
            target_ids.update(aliases)
            items.append({'notice_id':sn,'title':title[:500],'source_url':href,'content_hash':raw_hash,
                          'registered_at':date.group(1) if date else None,
                          'date_meaning':'BOARD_REGISTRATION_ONLY','official_project_aliases':sorted(set(aliases)),
                          'raw_snapshot':{'text':text[:30000],'raw_sha256':hashlib.sha256(detail.encode()).hexdigest()}})
        next_pages=[int(v) for a in soup.select('a[href]')
                    for v in parse_qs(urlsplit(a['href']).query).get('cpage',[]) if v.isdigit()]
        if (not recent_on_page and not unknown_date) or not any(p>page for p in next_pages):
            complete=True
            break
    return {'items':items,'seen':sorted(known|ids),'target_aliases':sorted(target_ids),
            'source':'official_notices','source_url':NOTICE_BOARD,'source_complete':complete,
            'status':'SUCCEEDED' if complete else 'PARTIAL','pages_fetched':page,
            'scope':'NEW_IDS_OR_LAST_30_DAYS','errors':[] if complete else ['NOTICE_PAGE_LIMIT']}


MOA_CANCELLATIONS='https://cleanup.seoul.go.kr/cleanup/view/moaTown.do'


def collect_moa_cancellations(http):
    """Official supplemental source, NOT a substitute for the active town list."""
    soup=BeautifulSoup(http.text(MOA_CANCELLATIONS),'html.parser')
    items=[]
    for title in soup.select('li > .title'):
        text=title.get_text(' ',strip=True)
        date=re.search(r'취소일자\s*:\s*(\d{4}-\d{2}-\d{2})',text)
        if not date:continue
        body=title.parent.get_text(' ',strip=True)
        district=re.search(r'자치구\s*:\s*([가-힣]+구)',body)
        if not district:raise SourceError('MOA_CANCELLATION_DISTRICT_MISSING')
        item={'official_name':text.split('(취소일자')[0].strip(),'sigungu':district.group(1),
              'cancellation_date':datetime.fromisoformat(date.group(1)).date().isoformat(),
              'status_candidate':'CANCELLED','source_url':MOA_CANCELLATIONS}
        item['content_hash']=hashlib.sha256(json.dumps(item,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        items.append(item)
    if not items:raise SourceError('MOA_CANCELLATION_LAYOUT_CHANGED_OR_EMPTY')
    return items

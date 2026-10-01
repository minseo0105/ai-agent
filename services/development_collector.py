"""Official Seoul collector. Collect locally first; explicit isolated importer only.

Official publication is evidence, not automatic proof of current business status.
No missing-from-list deletion and no inferred polygons or dong-centroid geocoding.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup

from services.development_official import dong_from_address
from services.realestate_monitor import REGION_LAWD

# The identity seed is frozen: the pilot records and the canary rows already in
# the database were derived from the project name verbatim. Parser fixes must not
# silently re-identify an existing project, so a change here needs a new version
# and a mapping migration.
IDENTITY_NORMALIZER_VERSION = 'seoul-identity-v1'

# 자치구 코드는 새로 만들지 않는다. 실거래 조회가 쓰는 REGION_LAWD의 서울 25개 항목이
# 그대로 정보몽땅 signguCode다. 두 값이 같은 체계라는 근거는 이미 적재된 세 구에서
# 확인했다: 강동구 11740 / 송파구 11710 / 서초구 11650이 LAWD_CD와 정보몽땅
# scupBsnsSttus.signguCode 양쪽에서 동일하고, 25개 모두 행정표준코드 시군구코드
# 5자리(11xxx)이며 중복이 없다. 나머지 22개 구는 코드 체계가 같다는 것까지만
# 확인된 상태이고 정보몽땅 응답으로 실측되지는 않았으므로, 실제 수집 실행에서
# 구별 응답 건수를 확인해야 한다.
SIGNGU_CODE_SYSTEM = '행정표준코드 시군구코드(5)'
SIGNGU_CODE_SOURCE = 'services.realestate_monitor.REGION_LAWD'
SEOUL_SIGNGU_CODE = {label.split(' > ', 1)[1]: code
                     for label, code in REGION_LAWD.items() if label.startswith('서울 > ')}
SEOUL_DISTRICTS = tuple(SEOUL_SIGNGU_CODE)

# 이미 적재/검증된 세 구. 인자 없이 호출하면 동작이 바뀌지 않도록 기본값으로 둔다.
# 서울 전체 수집은 --all-seoul처럼 호출자가 명시적으로 요청할 때만 일어난다.
PILOT_DISTRICTS = ('강동구', '송파구', '서초구')
DISTRICTS = {district: SEOUL_SIGNGU_CODE[district] for district in PILOT_DISTRICTS}

CITYWIDE_SOURCES = (
 {'id': 'seoul_moa', 'name': '서울시 모아타운 추진현황', 'kind': 'moa',
  'url': 'https://news.seoul.go.kr/citybuild/moa-housing-town/policy/status'},
 {'id': 'seoul_shintong_redevelopment', 'name': '정보몽땅 신속통합기획 재개발', 'kind': 'shintong',
  'url': 'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn.do'},
 {'id': 'seoul_shintong_reconstruction', 'name': '정보몽땅 신속통합기획 재건축', 'kind': 'reconstruction',
  'url': 'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn2.do'},
)
DIRECTORY_URL = ('https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do'
                 '?cpage=1&pageSize=100&scupBsnsSttus.signguCode=')
# 정보몽땅 사업장 목록은 cpage로 페이지를 넘긴다. pageSize=100 한 장만 받으면
# 100건이 넘는 자치구가 조용히 잘린다. 상한은 100 x 40 = 4,000행으로, 자치구 하나가
# 그보다 많을 가능성보다 응답이 cpage를 무시해 같은 장을 계속 주는 쪽이 현실적이다.
DIRECTORY_PAGE_PARAM = 'cpage'
DIRECTORY_PAGE_SIZE = 100
MAX_DIRECTORY_PAGES = 40


class UnknownDistrict(ValueError):
    """Names a district the region master does not contain. No code is guessed."""


def normalize_districts(districts=None):
    """요청한 자치구 이름을 지역 마스터로 검증해 중복 없는 순서대로 돌려준다.

    모르는 이름은 조용히 버리지 않고 거부한다. 오타 하나가 '그 구는 수집된 게
    없다'로 보이는 것이 가장 나쁜 실패 방식이기 때문이다.
    """
    if districts is None:
        districts = PILOT_DISTRICTS
    if isinstance(districts, str):
        districts = [districts]
    names, unknown = [], []
    for raw in districts:
        name = (raw or '').strip()
        if not name:
            continue
        # '서울 > 성동구'와 '성동구'를 모두 받는다. 지역 라벨 형식이 하나뿐이라고 가정하지 않는다.
        name = name.split('>')[-1].strip()
        if name not in SEOUL_SIGNGU_CODE:
            unknown.append(name)
        elif name not in names:
            names.append(name)
    if unknown:
        raise UnknownDistrict('UNKNOWN_SEOUL_DISTRICT:' + ','.join(sorted(set(unknown))))
    if not names:
        raise UnknownDistrict('NO_DISTRICT_SELECTED')
    return tuple(names)


def build_sources(districts=None):
    """선택한 자치구만 대상으로 하는 수집 source 목록.

    시 전체 페이지(모아타운·신속통합기획)는 25개 구 행을 모두 돌려주므로 URL은
    그대로 두고 source에 담긴 자치구 범위로 행을 고른다. 사업장 목록은 구별
    signguCode URL이라 선택한 구만큼만 만든다.
    """
    names = normalize_districts(districts)
    scope = {name: SEOUL_SIGNGU_CODE[name] for name in names}
    sources = [dict(source, districts=dict(scope)) for source in CITYWIDE_SOURCES]
    sources += [{'id': 'cleanup_' + code, 'name': '정보몽땅 사업장 목록 ' + district,
                 'kind': 'directory', 'url': DIRECTORY_URL + code,
                 'district': district, 'signgu_code': code, 'districts': {district: code},
                 'page_param': DIRECTORY_PAGE_PARAM, 'page_size': DIRECTORY_PAGE_SIZE,
                 'max_pages': MAX_DIRECTORY_PAGES}
                for district, code in scope.items()]
    return sources


# 기본 SOURCES는 지금까지와 같은 세 구다. 테스트와 기존 스크립트가 보는 모양을 바꾸지 않는다.
SOURCES = build_sources(PILOT_DISTRICTS)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def decode_page(content):
    candidates = []
    for encoding in ('utf-8', 'cp949'):
        try:
            text = content.decode(encoding)
            candidates.append((sum(text.count(k) for k in ('사업', '자치구', '정비', '모아')), text))
        except UnicodeError:
            pass
    if not candidates:
        raise ValueError('Unsupported official page encoding')
    return max(candidates, key=lambda item: item[0])[1]

def table_rows(table):
    """Expand rowspan/colspan so district names remain associated with their rows."""
    spans = {}
    for tr in table.select('tr'):
        row, col = [], 0
        def inherited():
            nonlocal col
            while col in spans:
                text, remaining = spans[col];row.append(text)
                if remaining <= 1: del spans[col]
                else: spans[col] = (text, remaining - 1)
                col += 1
        for cell in tr.find_all(['th', 'td'], recursive=False):
            inherited()
            value = ' '.join(cell.get_text(' ', strip=True).split())
            width, height = int(cell.get('colspan', 1)), int(cell.get('rowspan', 1))
            for _ in range(width):
                row.append(value)
                if height > 1: spans[col] = (value, height - 1)
                col += 1
        inherited()
        yield row, str(tr)

def number(raw):
    try: return float(raw.replace(',', '').replace('㎡', '').strip())
    except (ValueError, AttributeError): return None

def parse_page(content, source, collected_at=None, districts=None):
    """source가 담고 있는 자치구 범위의 행만 기록으로 바꾼다.

    districts를 주면 그것이 범위이고, 없으면 source['districts'], 그것도 없으면
    기존 세 구(DISTRICTS)다. 범위를 명시하지 않은 호출의 동작은 바뀌지 않는다.
    """
    text = decode_page(content) if isinstance(content, bytes) else content
    soup = BeautifulSoup(text, 'html.parser')
    stamp = collected_at or datetime.now(timezone.utc).isoformat()
    scope = districts or source.get('districts') or DISTRICTS
    if not isinstance(scope, dict): scope = {name: SEOUL_SIGNGU_CODE.get(name) for name in scope}
    records = []
    for table in soup.select('table'):
        for cells, markup in table_rows(table):
            district = next((c for c in cells if c in scope), None)
            if not district: continue
            pos = cells.index(district)
            if len(cells) <= pos + 2: continue
            external_id = None; address = None; stage_raw = None; area = None; units = None
            dates = re.findall(r'\d{4}-\d{2}-\d{2}', ' '.join(cells))
            if source['kind'] == 'directory':
                category, name = cells[pos+1:pos+3]
                kind = 'REDEVELOPMENT' if '재개발' in category else 'RECONSTRUCTION' if '재건축' in category else None
                if not kind or len(cells) < pos+5: continue
                address, stage_raw = cells[pos+3:pos+5]
                match = re.search(r"cafeOpenPopup[(]['\"]([^'\"]+)['\"]", markup)
                if match: external_id = match.group(1)
            else:
                name = cells[pos+1]
                kind = {'moa': 'MOATOWN', 'shintong': 'SHINTONG', 'reconstruction': 'RECONSTRUCTION'}[source['kind']]
                area = number(cells[pos+2])
                if source['kind'] != 'moa' and len(cells) > pos+4:
                    units = number(cells[pos+3]); stage_raw = cells[pos+4]
                # A 신속통합기획 row whose 구역명 is itself a lot ("천호동 392-9") is
                # an official representative address, not an inferred one.
                if re.search(r'[동리가]\s*\d', name): address = name
            if not name or name in ('사업장명','대표 지번','구역명'): continue
            address = ('서울특별시 ' + district + ' ' + address) if address else None
            identity = 'cleanup:' + external_id if external_id else f"{source['id']}:{district}:{name}"
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
            evidence = {'cells': cells, 'source_url': source['url'], 'parser_version': 'seoul-tables-v1',
                        'identity_normalizer': IDENTITY_NORMALIZER_VERSION, 'observed_dates': dates}
            content_hash = digest(evidence)
            record = {'project_id': pid, 'project_name': name, 'project_type': kind,
              'official_authority': 'cleanup.seoul.go.kr' if external_id else None,
              'external_id': external_id, 'sido': '서울특별시', 'sigungu': district,
              'dong': dong_from_address(address, district),
              'address': address, 'stage': None, 'stage_raw': stage_raw,
              'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW',
              'area_m2': area, 'planned_units': int(units) if units is not None else None,
              'source_date': None,
              'location': None, 'geometry': None, 'geometry_verified': False,
              'revision': 1, 'field_evidence': evidence,
              'source': {'source_name': source['name'], 'source_type': 'OFFICIAL_WEBSITE',
                 'source_url': source['url'], 'is_official': True, 'external_id': external_id,
                 'published_at': None, 'collected_at': stamp, 'verified_at': None,
                 'validation_status': 'UNVERIFIED', 'content_hash': content_hash, 'raw_snapshot': evidence}}
            records.append(record)
    return records

# 좌표 축이 뒤집혔는지 보기 위한 한반도 범위. 자치구 판정용이 아니다.
KOREA_LONGITUDE = (124.0, 132.0)
KOREA_LATITUDE = (33.0, 39.0)
# 서울 bbox. services.development_geocode.SEOUL_BOUNDS와 같은 값을 쓴다.
SEOUL_LONGITUDE = (126.734, 127.270)
SEOUL_LATITUDE = (37.413, 37.715)
DISTRICT_PATTERN = re.compile(r'([가-힣]{2,5}구)(?=\s|$|,)')


def result_district(result):
    """지오코딩 결과가 말하는 자치구. 못 읽으면 None이고, 추측하지 않는다."""
    elements = (result or {}).get('address_elements') or {}
    if elements.get('SIGUGUN'):
        return elements['SIGUGUN'].strip()
    for key in ('matched_address', 'jibun_address', 'road_address', 'address', 'returned_address'):
        text = (result or {}).get(key)
        if isinstance(text, str):
            found = DISTRICT_PATTERN.search(text)
            if found: return found.group(1)
    return None


def location_rejections(record, result):
    """이 결과를 좌표로 채택하면 안 되는 이유를 전부 모아 돌려준다.

    서울 bbox 안에 있다는 것만으로는 부족하다. 사업의 sigungu와 지오코딩이 답한
    자치구가 같은지까지 봐야, 성동구 사업이 마포구 좌표를 들고 지도에 꽂히는 일을
    막을 수 있다. 자치구를 읽을 수 없는 응답은 통과가 아니라 검토 대상이다.
    """
    reasons = []
    if not result: return ['NO_GEOCODE_RESULT']
    if result.get('result_status') != 'MATCHED': reasons.append('NOT_MATCHED')
    if result.get('accuracy') not in ('BUILDING', 'PARCEL'): reasons.append('ACCURACY_NOT_EXACT')
    if not result.get('source_url'): reasons.append('NO_SOURCE_URL')
    lon, lat = result.get('longitude'), result.get('latitude')
    if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float))):
        reasons.append('COORDINATE_NOT_NUMERIC')
    else:
        if not (KOREA_LONGITUDE[0] <= lon <= KOREA_LONGITUDE[1]
                and KOREA_LATITUDE[0] <= lat <= KOREA_LATITUDE[1]):
            reasons.append('OUTSIDE_KOREA_BBOX')
        elif not (SEOUL_LONGITUDE[0] <= lon <= SEOUL_LONGITUDE[1]
                  and SEOUL_LATITUDE[0] <= lat <= SEOUL_LATITUDE[1]):
            reasons.append('OUTSIDE_SEOUL_BBOX')
    wanted = record.get('sigungu')
    answered = result_district(result)
    if not wanted: reasons.append('PROJECT_SIGUNGU_MISSING')
    elif answered is None: reasons.append('GEOCODE_SIGUNGU_UNVERIFIABLE')
    elif answered != wanted: reasons.append('GEOCODE_SIGUNGU_MISMATCH')
    return reasons


def geocode(record, cache, provider=None):
    """Exact address cache/provider contract; no provider configured means no guess.

    채택하지 못한 이유는 버리지 않고 location_review에 남긴다. 좌표가 없는 것과
    좌표가 틀려서 뺀 것은 다른 사건이고, 보고서에서 구분되어야 한다.
    """
    address = record.get('address')
    if not address: return record
    key = digest({'address': ' '.join(address.split()), 'normalizer': 'v1'})
    result = cache.get(key)
    if result is None and provider:
        result = provider(address)
        cache[key] = result
    if result is None: return record
    reasons = location_rejections(record, result)
    if reasons:
        return dict(record, location_review=reasons)
    return dict(record, location=f"SRID=4326;POINT({result['longitude']} {result['latitude']})",
                location_source=result['source_url'], location_sigungu=result_district(result))

def page_url(url, param, page):
    """같은 URL의 page 번호만 바꾼다. 쿼리를 새로 짜지 않는다."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, str(page) if k == param else v) for k, v in query]
    if not any(k == param for k, _ in query): query.append((param, str(page)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def fetch_source_pages(source, fetch):
    """이 source의 모든 페이지를 돌려준다. 종료조건은 네 가지이고 전부 명시적이다.

      * 응답이 pageSize보다 적은 행을 준다 -> 마지막 장이다 (정상 종료)
      * 이 source에서 이미 본 문서와 같다 -> cpage를 무시하는 응답이다 (DUPLICATE_PAGE)
      * 새 project_id가 하나도 늘지 않는다 -> 더 받을 것이 없다 (NO_NEW_ROWS)
      * max_pages에 닿는다 -> 잘렸다는 사실을 오류로 남긴다 (PAGE_LIMIT_REACHED)

    페이지 없는 source는 지금까지처럼 한 번만 받는다.
    """
    param, size = source.get('page_param'), source.get('page_size')
    limit = source.get('max_pages') or 1
    if not param or not size:
        yield source['url'], fetch(source['url'], timeout=25), None
        return
    seen_documents, seen_ids, page = set(), set(), 1
    while page <= limit:
        url = page_url(source['url'], param, page)
        response = fetch(url, timeout=25)
        response.raise_for_status()
        document = hashlib.sha256(response.content).hexdigest()
        if document in seen_documents:
            yield url, response, 'DUPLICATE_PAGE'
            return
        seen_documents.add(document)
        rows = parse_page(response.content, source)
        ids = {row['project_id'] for row in rows}
        if page > 1 and not (ids - seen_ids):
            yield url, response, 'NO_NEW_ROWS'
            return
        seen_ids |= ids
        last = len(rows) < size
        yield url, response, None if last else 'CONTINUE'
        if last: return
        page += 1
    yield None, None, 'PAGE_LIMIT_REACHED'


def collect(fetch=None, *, geocode_provider=None, geocode_cache=None, districts=None, sources=None):
    """선택한 자치구만 수집한다. 인자가 없으면 지금까지와 같은 세 구다.

    districts=SEOUL_DISTRICTS로 서울 전체를, districts=['성동구']로 한 구만 돌릴 수
    있다. 25개를 매번 무조건 도는 경로는 만들지 않는다.
    """
    fetch = fetch or requests.get
    records, runs = {}, []
    cache = geocode_cache if geocode_cache is not None else {}
    if sources is None:
        sources = SOURCES if districts is None else build_sources(districts)
    for source in sources:
        run = {'source': source['id'], 'source_url': source['url'], 'started_at': datetime.now(timezone.utc).isoformat(),
               'dry_run': True, 'source_complete': False, 'new_count': 0, 'changed_count': 0,
               'unchanged_count': 0, 'validation_failed_count': 0, 'errors': []}
        try:
            hashes, found, truncated, pages = [], [], False, 0
            for url, response, note in fetch_source_pages(source, fetch):
                if note == 'PAGE_LIMIT_REACHED':
                    run['errors'].append(note);truncated = True;break
                response.raise_for_status()
                if urlsplit(response.url).hostname not in ('cleanup.seoul.go.kr','news.seoul.go.kr'):
                    raise ValueError('Unexpected official source redirect')
                pages += 1
                hashes.append(hashlib.sha256(response.content).hexdigest())
                if note not in ('DUPLICATE_PAGE', 'NO_NEW_ROWS'):
                    found += parse_page(response.content, source)
                if note in ('DUPLICATE_PAGE', 'NO_NEW_ROWS'):
                    # 페이지가 더 있다고 주장하는데 내용이 늘지 않는다. 받은 것만 쓴다.
                    run['errors'].append(note);truncated = True
            run['pages_fetched'] = pages
            run['document_hash'] = hashes[0] if len(hashes) == 1 else digest(hashes)
            if not found: run['errors'].append('NO_PILOT_ROWS_OR_LAYOUT_CHANGED')
            for record in found:
                if record['project_id'] in records:
                    run['unchanged_count'] += 1
                else:
                    records[record['project_id']] = geocode(record, cache, geocode_provider)
                    run['new_count'] += 1
            # 끝까지 받았다고 말할 수 있을 때만 완전수집이다. 잘림은 누락이지 폐지가 아니다.
            run['source_complete'] = bool(found) and not truncated and not run['errors']
            run['status'] = 'SUCCEEDED' if run['source_complete'] else 'PARTIAL'
        except Exception as exc:
            run['status'] = 'FAILED';run['errors'].append(type(exc).__name__)
        run['finished_at'] = datetime.now(timezone.utc).isoformat();runs.append(run)
    scope = sorted({d for source in sources for d in (source.get('districts') or {})})
    return {'collected_at': datetime.now(timezone.utc).isoformat(), 'records': list(records.values()), 'runs': runs,
            'districts': scope, 'signgu_code_system': SIGNGU_CODE_SYSTEM,
            'signgu_code_source': SIGNGU_CODE_SOURCE,
            'policy': 'LOCAL_CANDIDATES_ONLY; no business status inferred; no missing-record deletion'}

def import_candidate(record, request, run_id=None):
    """Atomic REST/RPC import; never directly PATCH master then append history."""
    current = request('GET','development_projects',params={'project_id':'eq.'+record['project_id'],'select':'revision'})
    project = {k:v for k,v in record.items() if k not in ('source','revision') and v is not None}
    return request('POST','rpc/zipon_ingest_candidate',payload={'p_project':project,
        'p_source':record['source'], 'p_run_id':run_id, 'p_expected_revision':current[0]['revision'] if current else 0})


MAX_IMPORT_BATCH = 10


def import_batch(records, request):
    """Explicit caller-supplied transport. Each candidate+history is atomic in RPC.

    An interrupted run remains RUNNING for operator review, not silently successful.
    The batch ceiling is enforced here as well as in the CLI, before any request is
    issued, so no code path can write more than a reviewed batch.
    """
    if not 1 <= len(records) <= MAX_IMPORT_BATCH:
        raise ValueError(f'IMPORT_BATCH_LIMIT_1_TO_{MAX_IMPORT_BATCH}')
    run_id = str(uuid.uuid4())
    request('POST', 'development_collection_runs', payload={
        'run_id': run_id, 'source_name': 'Seoul pilot reviewed import',
        'source_type': 'OFFICIAL_WEBSITE', 'collector_version': 'seoul-tables-v1',
        'dry_run': False, 'source_complete': False})
    counts = {'new': 0, 'changed': 0, 'unchanged': 0}
    errors = []
    for record in records:
        try:
            result = import_candidate(record, request, run_id)
            counts[result['result']] += 1
        except Exception as exc:
            errors.append({'project_id': record['project_id'], 'error_type': type(exc).__name__,
                'stage': getattr(exc, 'failure_stage', 'CANDIDATE_IMPORT'),
                'reason': getattr(exc, 'safe_reason', 'DETAILS_SUPPRESSED')})
    request('PATCH', 'development_collection_runs', params={'run_id': 'eq.' + run_id}, payload={
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'status': 'PARTIAL' if errors else 'SUCCEEDED', 'errors': errors,
        'new_count': counts['new'], 'changed_count': counts['changed'],
        'unchanged_count': counts['unchanged'], 'validation_failed_count': len(errors)})
    return {'run_id': run_id, **counts, 'errors': errors}

"""Official-source verification for ZIP:ON development candidates.

Read-only by construction. Every value is either parsed from stored official
evidence or from a single cached GET against an official host. No database
write, no secret or cookie is cached, and nothing is promoted to verified
without an official basis that is recorded next to it.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DETAIL_PARSER_VERSION = 'cleanup-detail-v1'
OFFICIAL_HOSTS = ('cleanup.seoul.go.kr', 'news.seoul.go.kr', 'data.seoul.go.kr')

# Base taxonomy required by the sprint plus values the official pilot data
# actually uses. Raw official wording is always preserved beside the mapping.
STAGE_TAXONOMY = ('CANDIDATE', 'PLANNING', 'PLAN_DELIBERATION', 'PLAN_NOTICED', 'DESIGNATED',
                  'IMPLEMENTER_DESIGNATED', 'SAFETY_DIAGNOSIS', 'COMMITTEE', 'ASSOCIATION_APPROVED',
                  'IMPLEMENTATION_APPROVED', 'MANAGEMENT_DISPOSITION', 'SALES', 'DEMOLITION',
                  'CONSTRUCTION', 'PARTIAL_COMPLETION', 'COMPLETED', 'TRANSFER_NOTICE',
                  'ASSOCIATION_DISSOLVED', 'ASSOCIATION_LIQUIDATION', 'CANCELLED', 'UNKNOWN')
STAGE_MAP = {
    '기본계획수립': 'PLANNING', '조합설립추진위원회승인': 'COMMITTEE',
    '철거신고': 'DEMOLITION', '착공신고': 'CONSTRUCTION', '일반분양승인': 'SALES',
    '후보지선정': 'CANDIDATE',
    '정비계획제안': 'PLANNING', '정비계획수립': 'PLANNING', '주민공람': 'PLANNING',
    '재공람': 'PLANNING', '구의회의견청취': 'PLANNING',
    '심의요청': 'PLAN_DELIBERATION', '심의': 'PLAN_DELIBERATION', '통합심의': 'PLAN_DELIBERATION',
    '통심완료': 'PLAN_DELIBERATION', '자문중': 'PLAN_DELIBERATION',
    '정비계획고시': 'PLAN_NOTICED',
    '구역지정': 'DESIGNATED', '정비구역지정': 'DESIGNATED', '정비구역지정고시': 'DESIGNATED',
    '시행자지정(조합)': 'IMPLEMENTER_DESIGNATED', '시행자지정': 'IMPLEMENTER_DESIGNATED',
    '안전진단': 'SAFETY_DIAGNOSIS',
    '추진위원회승인': 'COMMITTEE', '추진위승인': 'COMMITTEE',
    '조합설립인가': 'ASSOCIATION_APPROVED',
    '사업시행인가': 'IMPLEMENTATION_APPROVED',
    '관리처분인가': 'MANAGEMENT_DISPOSITION',
    '분양': 'SALES', '철거': 'DEMOLITION', '착공': 'CONSTRUCTION',
    '준공인가': 'COMPLETED', '부분준공인가': 'PARTIAL_COMPLETION', '이전고시': 'TRANSFER_NOTICE',
    '조합해산': 'ASSOCIATION_DISSOLVED', '조합청산': 'ASSOCIATION_LIQUIDATION',
}
# Official source typos are mapped but flagged; the raw string is never rewritten.
STAGE_TYPOS = {'정비계회고시': '정비계획고시'}
# Only an unambiguous official terminal step sets a status. Everything else stays
# UNKNOWN with a recorded hypothesis: a listed approval does not prove the
# business is still running, and absence from a list is never a cancellation.
STATUS_FROM_STAGE = {'COMPLETED': 'COMPLETED', 'TRANSFER_NOTICE': 'COMPLETED'}
STATUS_HYPOTHESIS = {
    'ASSOCIATION_LIQUIDATION': 'COMPLETED_PROBABLE_POST_TRANSFER',
    'ASSOCIATION_DISSOLVED': 'AMBIGUOUS_COMPLETED_OR_CANCELLED',
    'PARTIAL_COMPLETION': 'ACTIVE_PROBABLE_REMAINING_WORK',
}
STATUS_TAXONOMY = ('ACTIVE', 'COMPLETED', 'CANCELLED', 'SUSPENDED', 'UNKNOWN')

# Program membership is a property of the official source, not of the name.
SOURCE_PROGRAMS = {
    'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn.do':
        {'program': 'FAST_TRACK', 'program_name': '신속통합기획 재개발', 'registry': False,
         'canonical_project_type': 'REDEVELOPMENT'},
    'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn2.do':
        {'program': 'FAST_TRACK', 'program_name': '신속통합기획 재건축', 'registry': False,
         'canonical_project_type': 'RECONSTRUCTION'},
    'https://news.seoul.go.kr/citybuild/moa-housing-town/policy/status':
        {'program': 'MOATOWN', 'program_name': '모아타운', 'registry': False,
         'canonical_project_type': 'MOATOWN'},
}
REGISTRY_PROGRAM = {'program': None, 'program_name': None, 'registry': True,
                    'canonical_project_type': None}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def compact(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or ''))


def normalize_stage(raw):
    """Map an official stage string. Never guess a stage from a project name."""
    text = compact(raw)
    note = None
    if text in STAGE_TYPOS:
        text, note = STAGE_TYPOS[text], 'SOURCE_TYPO_NORMALIZED'
    stage = STAGE_MAP.get(text)
    if stage is None:
        return {'normalized_stage': 'UNKNOWN', 'stage_confidence': 'UNRESOLVED',
                'normalization_note': 'UNMAPPED_OFFICIAL_TERM' if text else 'NO_OFFICIAL_STAGE'}
    return {'normalized_stage': stage, 'stage_confidence': 'OFFICIAL_TERM',
            'normalization_note': note}


def normalize_status(normalized_stage):
    """status is separate from stage and only an official terminal step sets it."""
    status = STATUS_FROM_STAGE.get(normalized_stage)
    if status:
        return {'normalized_status': status, 'status_confidence': 'OFFICIAL_TERMINAL_STAGE',
                'status_hypothesis': None}
    return {'normalized_status': 'UNKNOWN', 'status_confidence': 'UNRESOLVED',
            'status_hypothesis': STATUS_HYPOTHESIS.get(normalized_stage, 'ACTIVE_LISTED_UNCONFIRMED')}


def dong_from_address(address, district):
    """The pilot collector matched the 구 prefix ("강동구" -> "강동"); skip the
    sido/sigungu tokens and read the administrative dong from the remainder."""
    skip = {compact(district), '서울특별시', '서울시', '서울'}
    for token in (address or '').split():
        if compact(token) in skip or token.endswith('구'):
            continue
        if re.fullmatch(r'[가-힣0-9]+(동|가|리)', token):
            return token
    return None


def lot_number(address):
    match = re.search(r'(\d+(?:-\d+)?)\s*(?:번지)?\s*$', (address or '').strip())
    return match.group(1) if match else None


def normalize_url(url):
    parts = urlsplit(url or '')
    query = urlencode(sorted(parse_qsl(parts.query)))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ''))


def cache_key(source_system=None, external_id=None, url=None, identity=None):
    """Prefer the official identity; fall back to a normalized URL hash.

    A list row without an official identifier gets the candidate identity mixed
    into the key, so two different projects on one list page can never share a
    cached detail entry.
    """
    if source_system and external_id:
        return 'id-' + hashlib.sha256(f'{source_system}|{external_id}'.encode()).hexdigest()[:32]
    if url:
        seed = normalize_url(url) + (f'|{identity}' if identity else '')
        return 'url-' + hashlib.sha256(seed.encode()).hexdigest()[:32]
    raise ValueError('cache key needs an official identity or a URL')


class DetailCache:
    """File-backed official-detail cache. Secrets and cookies are never stored."""

    FORBIDDEN = ('cookie', 'set-cookie', 'authorization', 'apikey', 'api_key', 'key',
                 'token', 'secret', 'password')

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.writes = 0
        self.requests_avoided = 0

    def path(self, key):
        return self.directory / (key + '.json')

    def get(self, key):
        path = self.path(key)
        if not path.exists():
            return None
        self.hits += 1
        return json.loads(path.read_text(encoding='utf-8'))

    def put(self, key, entry):
        clean = {k: v for k, v in entry.items() if k.lower() not in self.FORBIDDEN}
        clean['cache_key'] = key
        self.path(key).write_text(json.dumps(clean, ensure_ascii=False, indent=2) + '\n',
                                  encoding='utf-8')
        self.writes += 1
        return clean


def detail_target(record):
    """What would have to be read to verify this candidate's identity officially.

    The district list exposes the identity through cafeOpenPopup(external_id);
    the detail endpoint itself is not present in the stored evidence, so it is
    reported as unconfirmed instead of being invented.
    """
    source = record.get('source') or {}
    system = record.get('official_authority') or urlsplit(source.get('source_url') or '').hostname
    external = record.get('external_id')
    return {'project_id': record['project_id'], 'source_system': system, 'external_id': external,
            'list_source_url': source.get('source_url'),
            'detail_url': None,
            'detail_lookup': {
                'method': 'cafeOpenPopup(external_id) on the official district list page'
                          if external else 'no official identifier on this list row',
                'endpoint_confirmed': False,
                'resolvable_offline': False},
            'cache_key': cache_key(system, external, source.get('source_url'),
                                   identity=None if external else record['project_id'])}


def parse_detail_page(html):
    """Label/value parser for the official detail layout (th/td and dl/dt/dd).

    Returns parsed fields plus the labels it saw, so a layout change is visible
    instead of silently producing empty fields.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    pairs = {}
    for row in soup.select('tr'):
        cells = row.find_all(['th', 'td'], recursive=False)
        for i in range(0, len(cells) - 1, 2):
            label = ' '.join(cells[i].get_text(' ', strip=True).split())
            value = ' '.join(cells[i + 1].get_text(' ', strip=True).split())
            if label and cells[i].name == 'th':
                pairs.setdefault(label, value)
    for block in soup.select('dl'):
        terms = block.find_all('dt')
        definitions = block.find_all('dd')
        for term, definition in zip(terms, definitions):
            pairs.setdefault(' '.join(term.get_text(' ', strip=True).split()),
                             ' '.join(definition.get_text(' ', strip=True).split()))
    labels = {'official_project_name': ('사업장명', '사업명', '구역명'),
              'official_project_type': ('사업구분', '사업유형', '구분'),
              'raw_stage': ('진행단계', '추진단계', '단계'),
              'representative_address': ('대표지번', '대표 지번', '위치', '소재지'),
              'road_address': ('도로명주소', '도로명 주소'),
              'designation_date': ('구역지정일', '정비구역지정일', '지정일'),
              'approval_date': ('조합설립인가일', '설립인가일'),
              'implementation_date': ('사업시행인가일',),
              'management_disposition_date': ('관리처분인가일',),
              'completion_date': ('준공일', '준공인가일', '이전고시일')}
    parsed = {}
    for field, candidates in labels.items():
        for label in candidates:
            for seen, value in pairs.items():
                if compact(seen) == compact(label) and value and value not in ('-', ''):
                    parsed[field] = value
                    break
            if field in parsed:
                break
    return {'parsed_fields': parsed, 'observed_labels': sorted(pairs),
            'parser_version': DETAIL_PARSER_VERSION,
            'layout_confirmed': bool(parsed)}


def fetch_details(targets, transport, cache, *, host_state=None):
    """One request per cache key, at most. A host that denies or drops the first
    connection is not retried for the remaining targets of the same run."""
    host_state = {} if host_state is None else host_state
    results, log = {}, []
    for target in targets:
        key = target['cache_key']
        if key in results:
            cache.requests_avoided += 1
            log.append({'cache_key': key, 'result_status': 'DEDUPED_IN_RUN',
                        'project_id': target['project_id']})
            continue
        cached = cache.get(key)
        if cached is not None:
            results[key] = cached
            log.append({'cache_key': key, 'result_status': 'CACHE_HIT',
                        'project_id': target['project_id']})
            continue
        url = target.get('detail_url')
        if not url:
            entry = {'fetched_at': None, 'source_system': target['source_system'],
                     'source_url': target.get('list_source_url'), 'external_id': target['external_id'],
                     'result_status': 'NO_CONFIRMED_DETAIL_ENDPOINT', 'http_status': None,
                     'content_hash': None, 'parsed_fields': {}, 'evidence': target['detail_lookup'],
                     'parser_version': DETAIL_PARSER_VERSION}
            results[key] = entry
            log.append({'cache_key': key, 'result_status': entry['result_status'],
                        'project_id': target['project_id']})
            continue
        host = urlsplit(url).hostname
        if host not in OFFICIAL_HOSTS:
            results[key] = {'result_status': 'NON_OFFICIAL_HOST_REFUSED', 'source_url': url,
                            'parsed_fields': {}, 'parser_version': DETAIL_PARSER_VERSION}
            log.append({'cache_key': key, 'result_status': 'NON_OFFICIAL_HOST_REFUSED'})
            continue
        if host_state.get(host, {}).get('unavailable'):
            cache.requests_avoided += 1
            log.append({'cache_key': key, 'result_status': 'SKIPPED_HOST_UNAVAILABLE', 'host': host,
                        'reason': host_state[host]['reason'], 'project_id': target['project_id']})
            continue
        entry = {'fetched_at': now(), 'source_system': target['source_system'], 'source_url': url,
                 'external_id': target['external_id'], 'parser_version': DETAIL_PARSER_VERSION}
        try:
            response = transport(url, timeout=25)
            entry['http_status'] = getattr(response, 'status_code', None)
            body = response.content if isinstance(response.content, bytes) else response.content.encode()
            entry['content_hash'] = hashlib.sha256(body).hexdigest()
            if entry['http_status'] != 200:
                entry.update(result_status='HTTP_ERROR', parsed_fields={}, evidence={})
            else:
                parsed = parse_detail_page(body.decode('utf-8', 'replace'))
                entry.update(result_status='FETCHED' if parsed['layout_confirmed'] else 'LAYOUT_UNRECOGNIZED',
                             parsed_fields=parsed['parsed_fields'],
                             evidence={'observed_labels': parsed['observed_labels']})
        except Exception as exc:  # network/policy failures are recorded, never retried blindly
            reason = type(exc).__name__
            entry.update(result_status='FETCH_FAILED', http_status=None, content_hash=None,
                         parsed_fields={}, evidence={'error_type': reason})
            host_state[host] = {'unavailable': True, 'reason': reason, 'observed_at': entry['fetched_at']}
        results[key] = cache.put(key, entry)
        log.append({'cache_key': key, 'result_status': entry['result_status'],
                    'project_id': target['project_id']})
    return {'details': results, 'log': log, 'host_state': host_state,
            'stats': {'requests': sum(1 for e in log if e['result_status'] not in
                                      ('CACHE_HIT', 'DEDUPED_IN_RUN', 'SKIPPED_HOST_UNAVAILABLE',
                                       'NO_CONFIRMED_DETAIL_ENDPOINT')),
                      'cache_hits': sum(1 for e in log if e['result_status'] == 'CACHE_HIT'),
                      'duplicates_avoided': sum(1 for e in log if e['result_status'] in
                                                ('DEDUPED_IN_RUN', 'SKIPPED_HOST_UNAVAILABLE'))}}


def discover_detail_endpoint(html):
    """Read the detail endpoint out of the official list markup rather than guessing.

    The district list opens a business detail through cafeOpenPopup(external_id);
    the endpoint it calls is only knowable from the page itself.
    """
    for match in re.finditer(r'function\s+cafeOpenPopup[^{]*\{(.{0,600}?)\}', html, re.S):
        body = match.group(1)
        path = re.search(r"""['"](/?[^'"\s]+\.do)""", body)
        parameter = re.search(r'[?&]([A-Za-z_.]+)=', body)
        if path:
            return {'confirmed': True, 'path': path.group(1),
                    'parameter': parameter.group(1) if parameter else None,
                    'evidence': ' '.join(body.split())[:200]}
    anchor = re.search(r'href=["\']([^"\']*(?:lscrMainDetail|bsnsSttusDetail|cafeMain)[^"\']*)["\']', html)
    if anchor:
        return {'confirmed': True, 'path': anchor.group(1), 'parameter': None,
                'evidence': anchor.group(0)[:200]}
    return {'confirmed': False, 'path': None, 'parameter': None,
            'evidence': 'no detail endpoint present in the official list markup'}


def official_read(records, transport, cache):
    """One GET per official list page to learn the detail endpoint, then one GET
    per official identity. A host that fails once is not asked again this run."""
    from urllib.parse import urljoin
    targets = [detail_target(record) for record in records]
    host_state, discovery = {}, {}
    for url in sorted({t['list_source_url'] for t in targets if t['list_source_url']}):
        host = urlsplit(url).hostname
        key = cache_key(url=url, identity='list-page-endpoint-discovery')
        entry = cache.get(key)
        if entry is None:
            entry = {'fetched_at': now(), 'source_system': host, 'source_url': url,
                     'external_id': None, 'parser_version': DETAIL_PARSER_VERSION}
            if host_state.get(host, {}).get('unavailable'):
                entry.update(result_status='SKIPPED_HOST_UNAVAILABLE', http_status=None,
                             content_hash=None, parsed_fields={},
                             evidence={'error_type': host_state[host]['reason']})
            else:
                try:
                    response = transport(url, timeout=25)
                    body = response.content
                    entry.update(http_status=getattr(response, 'status_code', None),
                                 content_hash=hashlib.sha256(body).hexdigest(),
                                 result_status='FETCHED', parsed_fields={},
                                 detail_endpoint=discover_detail_endpoint(
                                     body.decode('utf-8', 'replace')))
                except Exception as exc:
                    entry.update(result_status='FETCH_FAILED', http_status=None, content_hash=None,
                                 parsed_fields={}, evidence={'error_type': type(exc).__name__})
                    host_state[host] = {'unavailable': True, 'reason': type(exc).__name__,
                                        'observed_at': entry['fetched_at']}
                cache.put(key, entry)
        discovery[url] = entry
    for target in targets:
        endpoint = (discovery.get(target['list_source_url']) or {}).get('detail_endpoint') or {}
        if endpoint.get('confirmed') and target['external_id']:
            url = urljoin(target['list_source_url'], endpoint['path'])
            if endpoint.get('parameter'):
                url = f"{url}?{endpoint['parameter']}={target['external_id']}"
            target['detail_url'] = url
            target['detail_lookup'] = dict(target['detail_lookup'], endpoint_confirmed=True,
                                           discovered_from=target['list_source_url'],
                                           evidence=endpoint['evidence'])
    result = fetch_details(targets, transport, cache, host_state=host_state)
    result['discovery'] = {url: {k: v for k, v in entry.items() if k != 'parsed_fields'}
                           for url, entry in discovery.items()}
    return result

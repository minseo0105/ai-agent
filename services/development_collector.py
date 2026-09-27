"""Official Seoul collector. Collect locally first; explicit isolated importer only.

Official publication is evidence, not automatic proof of current business status.
No missing-from-list deletion and no inferred polygons or dong-centroid geocoding.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup

from services.development_official import dong_from_address

# The identity seed is frozen: the pilot records and the canary rows already in
# the database were derived from the project name verbatim. Parser fixes must not
# silently re-identify an existing project, so a change here needs a new version
# and a mapping migration.
IDENTITY_NORMALIZER_VERSION = 'seoul-identity-v1'

DISTRICTS = {'강동구': '11740', '송파구': '11710', '서초구': '11650'}
SOURCES = [
 {'id': 'seoul_moa', 'name': '서울시 모아타운 추진현황', 'kind': 'moa',
  'url': 'https://news.seoul.go.kr/citybuild/moa-housing-town/policy/status'},
 {'id': 'seoul_shintong_redevelopment', 'name': '정보몽땅 신속통합기획 재개발', 'kind': 'shintong',
  'url': 'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn.do'},
 {'id': 'seoul_shintong_reconstruction', 'name': '정보몽땅 신속통합기획 재건축', 'kind': 'reconstruction',
  'url': 'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn2.do'},
] + [{'id': 'cleanup_' + code, 'name': '정보몽땅 사업장 목록 ' + district, 'kind': 'directory',
       'url': 'https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do?cpage=1&pageSize=100&scupBsnsSttus.signguCode=' + code}
      for district, code in DISTRICTS.items()]

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

def parse_page(content, source, collected_at=None):
    text = decode_page(content) if isinstance(content, bytes) else content
    soup = BeautifulSoup(text, 'html.parser')
    stamp = collected_at or datetime.now(timezone.utc).isoformat()
    records = []
    for table in soup.select('table'):
        for cells, markup in table_rows(table):
            district = next((c for c in cells if c in DISTRICTS), None)
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

def geocode(record, cache, provider=None):
    """Exact address cache/provider contract; no provider configured means no guess."""
    address = record.get('address')
    if not address: return record
    key = digest({'address': ' '.join(address.split()), 'normalizer': 'v1'})
    result = cache.get(key)
    if result is None and provider:
        result = provider(address)
        cache[key] = result
    if result and result.get('result_status') == 'MATCHED' and result.get('accuracy') in ('BUILDING','PARCEL') and result.get('source_url'):
        lon, lat = result.get('longitude'), result.get('latitude')
        if isinstance(lon,(int,float)) and isinstance(lat,(int,float)) and 124 <= lon <= 132 and 33 <= lat <= 39:
            record = dict(record, location=f'SRID=4326;POINT({lon} {lat})', location_source=result['source_url'])
    return record

def collect(fetch=None, *, geocode_provider=None, geocode_cache=None):
    fetch = fetch or requests.get
    records, runs = {}, []
    cache = geocode_cache if geocode_cache is not None else {}
    for source in SOURCES:
        run = {'source': source['id'], 'source_url': source['url'], 'started_at': datetime.now(timezone.utc).isoformat(),
               'dry_run': True, 'source_complete': False, 'new_count': 0, 'changed_count': 0,
               'unchanged_count': 0, 'validation_failed_count': 0, 'errors': []}
        try:
            response = fetch(source['url'], timeout=25)
            response.raise_for_status()
            if urlsplit(response.url).hostname not in ('cleanup.seoul.go.kr','news.seoul.go.kr'):
                raise ValueError('Unexpected official source redirect')
            run['document_hash'] = hashlib.sha256(response.content).hexdigest()
            found = parse_page(response.content, source)
            if not found: run['errors'].append('NO_PILOT_ROWS_OR_LAYOUT_CHANGED')
            for record in found:
                if record['project_id'] in records:
                    run['unchanged_count'] += 1
                else:
                    records[record['project_id']] = geocode(record, cache, geocode_provider)
                    run['new_count'] += 1
            # Directory may paginate: incomplete coverage is explicit, never disappearance/cancellation.
            run['status'] = 'PARTIAL' if run['errors'] or source['kind']=='directory' else 'SUCCEEDED'
        except Exception as exc:
            run['status'] = 'FAILED';run['errors'].append(type(exc).__name__)
        run['finished_at'] = datetime.now(timezone.utc).isoformat();runs.append(run)
    return {'collected_at': datetime.now(timezone.utc).isoformat(), 'records': list(records.values()), 'runs': runs,
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

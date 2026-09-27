"""Write accepted ZIP:ON geocode results onto existing development projects.

This is the separate database step. scripts/geocode_zipon_development.py produces the
queue and never writes; this script writes nothing until --apply is given, and even
then only through the reviewed RPC public.zipon_set_project_location, which sets
location, location_source, location_verified_at and the field_evidence entry and
touches no boundary, status, stage or validation column.

  python scripts/apply_zipon_geocode.py --check-config   # credentials and queue only, no HTTP
  python scripts/apply_zipon_geocode.py --dry-run        # plan, read-only preflight, 0 writes
  python scripts/apply_zipon_geocode.py --apply          # batches of ten, then reconcile

Protections, every one of which skips the row instead of correcting it:
  * only ACCEPTED rows with coordinate_verified and confidence EXACT are eligible
  * project_id must match one existing row exactly; no name or address matching
  * a project that already has a coordinate is skipped, never overwritten
  * a project with a verified boundary keeps the boundary and is skipped
  * the queue's 자치구 must equal the stored sigungu
  * the point must sit inside the Seoul bounding box with x=longitude, y=latitude
  * batches never exceed ten and one failing row never stops the run
No credential value is printed or stored, and no row is ever deleted.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_geocode as geo
from services.development_collector import MAX_IMPORT_BATCH
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
QUEUE_FILE = DATA / 'geocode_queue_20260927.json'
RESULT_FILE = DATA / 'geocode_apply_result_20260927.json'
PROJECT_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'
RPC = 'rpc/zipon_set_project_location'
SOURCE_BY_PROVIDER = {'naver:geocode': 'NAVER_MAP_GEOCODE', 'kakao:address': 'KAKAO_ADDRESS',
                      'vworld:address': 'VWORLD_ADDRESS'}
SELECT = 'project_id,sigungu,revision,location,geometry_verified,validation_status,address'


class ApplyBlocked(Exception):
    """Carries a reason code only. No value, no response body, no URL."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def configuration():
    """Write credentials are their own pair; they never fall back to the read settings."""
    url = os.environ.get('ZIPON_IMPORT_SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('ZIPON_IMPORT_SUPABASE_KEY', '').strip()
    if not url:
        raise ApplyBlocked('MISSING_ZIPON_IMPORT_SUPABASE_URL')
    if not key:
        raise ApplyBlocked('MISSING_ZIPON_IMPORT_SUPABASE_KEY')
    if '/rest/v1' in url:
        raise ApplyBlocked('PROJECT_URL_MUST_NOT_INCLUDE_REST_V1')
    if url != PROJECT_URL:
        raise ApplyBlocked('PROJECT_URL_MISMATCH')
    if key.startswith('sb_publishable_'):
        raise ApplyBlocked('SERVER_SECRET_KEY_REQUIRED')
    if any(c.isspace() for c in key):
        raise ApplyBlocked('KEY_CONTAINS_WHITESPACE')
    return url, {'apikey': key, 'Authorization': 'Bearer ' + key,
                 'Content-Type': 'application/json', 'Accept': 'application/json'}


def eligible(queue):
    """The rows the queue itself marks as accepted, with the checks re-read here."""
    rows, rejected = [], []
    for item in queue.get('items') or []:
        reasons = []
        if item.get('geocode_status') != 'ACCEPTED':
            reasons.append('NOT_ACCEPTED_' + str(item.get('geocode_status')))
        if not item.get('coordinate_verified'):
            reasons.append('COORDINATE_NOT_VERIFIED')
        if item.get('geocode_confidence') != 'EXACT':
            reasons.append('CONFIDENCE_NOT_EXACT')
        if item.get('coordinate_orientation') not in (None, 'X_IS_LONGITUDE'):
            reasons.append('AXIS_ORDER_NOT_VERIFIED')
        if not geo.in_bounds(item.get('longitude'), item.get('latitude')):
            reasons.append('COORDINATE_OUTSIDE_SEOUL')
        if SOURCE_BY_PROVIDER.get(item.get('geocode_source') or '') is None:
            reasons.append('UNKNOWN_GEOCODE_SOURCE')
        if not item.get('district'):
            reasons.append('NO_DISTRICT_TO_COMPARE')
        (rejected if reasons else rows).append(
            dict(item, skip_reasons=reasons) if reasons else item)
    return rows, [{'project_id': r['project_id'], 'skip_reasons': r['skip_reasons']}
                  for r in rejected]


def batches(rows, size=MAX_IMPORT_BATCH):
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def payload_for(row, stored):
    """RPC arguments. The evidence keeps the provider's own strings and the checks."""
    return {'p_project_id': row['project_id'], 'p_longitude': row['longitude'],
            'p_latitude': row['latitude'], 'p_expected_sigungu': stored['sigungu'],
            'p_geocode_source': SOURCE_BY_PROVIDER[row['geocode_source']],
            'p_confidence': 'EXACT', 'p_expected_revision': stored['revision'],
            'p_evidence': {'address_used': row.get('canonical_address'),
                           'matched_address': row.get('matched_address'),
                           'road_address': row.get('road_address'),
                           'jibun_address': row.get('jibun_address'),
                           'english_address': row.get('english_address'),
                           'address_elements': row.get('address_elements'),
                           'checks': (row.get('checks')
                                      or {'axis_order': row.get('coordinate_orientation')
                                          == 'X_IS_LONGITUDE'}),
                           'geocoded_at': row.get('geocoded_at')}}


def preflight(row, stored):
    """Reasons to leave this project alone. Returned, never worked around."""
    reasons = []
    if stored is None:
        return ['PROJECT_NOT_IN_DATABASE']
    if stored.get('location') is not None:
        reasons.append('LOCATION_ALREADY_SET')
    if stored.get('geometry_verified'):
        reasons.append('VERIFIED_BOUNDARY_PRESENT')
    if (stored.get('sigungu') or '').strip() != (row.get('district') or '').strip():
        reasons.append('DISTRICT_MISMATCH')
    if not isinstance(stored.get('revision'), int) or stored['revision'] <= 0:
        reasons.append('REVISION_UNREADABLE')
    return reasons


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check-config', action='store_true',
                      help='validate the queue and the write credentials; no HTTP request')
    mode.add_argument('--dry-run', action='store_true',
                      help='plan and read-only preflight; zero database writes (default)')
    mode.add_argument('--apply', action='store_true',
                      help='call the RPC in batches of ten, then reconcile')
    ap.add_argument('--queue', type=Path, default=QUEUE_FILE,
                    help='queue file to apply (default: the geocode queue; use the '
                         'apply-ready artifact from the bulk run)')
    args = ap.parse_args()

    queue = json.loads(args.queue.read_text(encoding='utf-8'))
    rows, rejected = eligible(queue)
    plan = batches(rows)
    summary = {'format': 'zipon-geocode-apply-v1', 'generated_at': now(),
               'mode': 'APPLY' if args.apply else ('CHECK_CONFIG' if args.check_config else 'DRY_RUN'),
               'db_write': bool(args.apply), 'rpc': RPC, 'batch_size': MAX_IMPORT_BATCH,
               'queue_file': str(args.queue),
               'queue_generated_at': queue.get('generated_at'),
               'queue_provider': queue.get('provider'),
               'totals': {'queue_items': len(queue.get('items') or []), 'eligible': len(rows),
                          'not_eligible': len(rejected), 'batches': len(plan),
                          'applied': 0, 'skipped': 0, 'refused': 0, 'failed': 0},
               'not_eligible': rejected, 'batch_plan': [[r['project_id'] for r in b] for b in plan],
               'results': [], 'blocker': None, 'reconciliation': None}

    try:
        url, headers = configuration()
    except ApplyBlocked as blocked:
        summary['blocker'] = blocked.reason
        RESULT_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print(json.dumps({'mode': summary['mode'], 'db_write': summary['db_write'],
                          'blocker': blocked.reason, 'totals': summary['totals'],
                          'file': str(RESULT_FILE.relative_to(ROOT))}, ensure_ascii=False))
        return 0

    if args.check_config:
        summary['blocker'] = None
        RESULT_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print(json.dumps({'mode': 'CHECK_CONFIG', 'configuration': 'PASS', 'db_write': False,
                          'totals': summary['totals']}, ensure_ascii=False))
        return 0

    import requests

    def get(project_id):
        response = requests.get(f'{url}/rest/v1/development_projects', headers=headers,
                                params={'project_id': 'eq.' + project_id, 'select': SELECT},
                                timeout=20)
        response.raise_for_status()
        found = response.json()
        return found[0] if found else None

    for batch in plan:
        for row in batch:
            entry = {'project_id': row['project_id'], 'canonical_address': row.get('canonical_address'),
                     'latitude': row.get('latitude'), 'longitude': row.get('longitude'),
                     'matched_address': row.get('matched_address')}
            try:
                stored = get(row['project_id'])
                reasons = preflight(row, stored)
                if reasons:
                    summary['results'].append(dict(entry, outcome='SKIPPED', reasons=reasons))
                    summary['totals']['skipped'] += 1
                    continue
                if not args.apply:
                    summary['results'].append(dict(entry, outcome='WOULD_APPLY',
                                                   stored_revision=stored['revision']))
                    continue
                response = requests.post(f'{url}/rest/v1/{RPC}', headers=headers, timeout=20,
                                         json=payload_for(row, stored))
                response.raise_for_status()
                answer = response.json()
                answer = answer[0] if isinstance(answer, list) and answer else answer
                result = (answer or {}).get('result')
                summary['results'].append(dict(entry, outcome=result or 'UNKNOWN',
                                               reason=(answer or {}).get('reason'),
                                               revision=(answer or {}).get('revision')))
                if result == 'location_set':
                    summary['totals']['applied'] += 1
                elif result == 'skipped':
                    summary['totals']['skipped'] += 1
                else:
                    summary['totals']['refused'] += 1
            except Exception as exc:
                # One candidate never stops the run, and the error body is never kept.
                summary['results'].append(dict(entry, outcome='FAILED',
                                               error_type=type(exc).__name__))
                summary['totals']['failed'] += 1

    if args.apply:
        try:
            response = requests.get(f'{url}/rest/v1/development_projects', timeout=20,
                                    headers=dict(headers, Prefer='count=exact'),
                                    params={'select': 'project_id', 'location': 'not.is.null',
                                            'limit': 1})
            response.raise_for_status()
            located = response.headers.get('content-range', '').split('/')[-1]
            summary['reconciliation'] = {
                'rows_with_location': int(located) if located.isdigit() else None,
                'applied_this_run': summary['totals']['applied'],
                'matches': (located.isdigit()
                            and int(located) >= summary['totals']['applied'])}
        except Exception as exc:
            summary['reconciliation'] = {'error_type': type(exc).__name__}

    RESULT_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
    print(json.dumps({'mode': summary['mode'], 'db_write': summary['db_write'],
                      'totals': summary['totals'], 'reconciliation': summary['reconciliation'],
                      'file': str(RESULT_FILE.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

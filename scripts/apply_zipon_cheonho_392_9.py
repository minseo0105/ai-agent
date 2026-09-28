"""천호동 392-9 한 건만 주소와 좌표를 반영한다. 다른 사업은 건드리지 않는다.

왜 이 한 건만인가: 공식 목록 행의 사업명 칸 자체가 지번("천호동 392-9")이고 자치구가
강동구다. 즉 추정 없이 공식 텍스트만으로 주소가 나온다. 나머지 7건은 근거가 후보를
하나로 좁히지 못해 검토로 남겨 둔 상태이며 이 스크립트는 그것들을 건드리지 않는다.

  python scripts/apply_zipon_cheonho_392_9.py --check-config  # 자격증명·근거만 확인
  python scripts/apply_zipon_cheonho_392_9.py --dry-run       # 계획만, 쓰기 없음 (기본)
  python scripts/apply_zipon_cheonho_392_9.py --apply         # 주소 -> 지오코딩 -> 좌표

순서와 안전장치:
  1) 주소는 기존 zipon_ingest_candidate_v2로 넣는다. 이 RPC는 비어 있는 칸만 채우고
     이미 값이 있는 칸은 덮어쓰지 않는다. stage/status/validation_status/geometry는
     payload에 담지 않는다.
  2) 그 주소 하나만 NAVER로 조회한다. 기존 판정 규칙 그대로: 자치구·동·지번이 정확히
     일치하고 축이 x=경도인 단일 후보만 EXACT다.
  3) EXACT일 때만 zipon_set_project_location으로 좌표를 넣는다. 그 RPC는 기존 좌표를
     덮어쓰지 않고, 자치구가 다르면 거부하고, 서울 범위를 벗어나면 거부한다.
  EXACT가 아니면 주소까지만 두고 좌표는 MANUAL_REVIEW로 남긴다.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_geocode as geo
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
RESULT_FILE = DATA / 'cheonho_392_9_apply_result_20260928.json'
PROJECT_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'
PROJECT_ID = '429dc953-a406-56ff-871d-0ced658be69f'
PROJECT_NAME = '천호동 392-9'
DISTRICT, DONG, LOT = '강동구', '천호동', '392-9'
ADDRESS = f'서울특별시 {DISTRICT} {DONG} {LOT}'
INGEST_RPC = 'rpc/zipon_ingest_candidate_v2'
LOCATION_RPC = 'rpc/zipon_set_project_location'


class Blocked(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def evidence():
    """공식 목록 행에서 주소가 그대로 나오는지 다시 확인한다. 추정하지 않는다."""
    fast = json.loads((DATA / 'fast_track_location_20260927.json').read_text(encoding='utf-8'))
    row = next((r for r in fast['items'] if r['project_id'] == PROJECT_ID), None)
    if row is None:
        raise Blocked('PROJECT_NOT_IN_FAST_TRACK_ANALYSIS')
    if row['project_name'] != PROJECT_NAME or row['district'] != DISTRICT:
        raise Blocked('OFFICIAL_ROW_DOES_NOT_MATCH_EXPECTED_IDENTITY')
    if row['lot_in_name'] != f'{DONG} {LOT}':
        raise Blocked('PROJECT_NAME_DOES_NOT_CARRY_THE_EXPECTED_LOT')
    if row['address_in_source'] is not None:
        raise Blocked('PROJECT_ALREADY_HAS_AN_ADDRESS')
    if not str(row['source_url']).startswith('https://cleanup.seoul.go.kr/'):
        raise Blocked('SOURCE_IS_NOT_THE_OFFICIAL_HOST')
    if len(str(row['content_hash'])) != 64:
        raise Blocked('SOURCE_SNAPSHOT_HASH_MISSING')
    return row


def configuration():
    url = os.environ.get('ZIPON_IMPORT_SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('ZIPON_IMPORT_SUPABASE_KEY', '').strip()
    if not url:
        raise Blocked('MISSING_ZIPON_IMPORT_SUPABASE_URL')
    if not key:
        raise Blocked('MISSING_ZIPON_IMPORT_SUPABASE_KEY')
    if url != PROJECT_URL:
        raise Blocked('PROJECT_URL_MISMATCH')
    if key.startswith('sb_publishable_'):
        raise Blocked('SERVER_SECRET_KEY_REQUIRED')
    return url, {'apikey': key, 'Authorization': 'Bearer ' + key,
                 'Content-Type': 'application/json', 'Accept': 'application/json'}


def address_payload(row, revision):
    """주소와 동만 담는다. 단계·상태·검증상태·도형은 담지 않는다."""
    return {'p_project': {'project_id': PROJECT_ID, 'project_name': PROJECT_NAME,
                          'sido': '서울특별시', 'sigungu': DISTRICT, 'dong': DONG,
                          'address': ADDRESS},
            'p_source': {'source_name': row['official_source'],
                         'source_type': 'OFFICIAL_WEBSITE', 'source_url': row['source_url'],
                         'is_official': True, 'collected_at': now(),
                         'content_hash': row['content_hash'],
                         'raw_snapshot': {'cells': row['raw_source_text'],
                                          'source_url': row['source_url'],
                                          'address_basis': 'OFFICIAL_LIST_ROW_PROJECT_NAME_IS_LOT'}},
            'p_expected_revision': revision,
            'p_change': {'kind': 'DETAIL', 'note': 'ADDRESS_FROM_OFFICIAL_LIST_ROW'},
            'p_run_id': None}


def geocode_once(get_secret, http_get):
    """이 주소 하나만 조회한다. 기존 판정 규칙을 그대로 쓴다."""
    selected = geo.select_provider(get_secret, http_get)
    if selected['provider'] is None:
        raise Blocked(selected['blocker'])
    response = selected['provider'](geo.normalize_address(ADDRESS))
    return geo.evaluate(ADDRESS, response), selected['name']


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check-config', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    report = {'format': 'zipon-cheonho-apply-v1', 'generated_at': now(),
              'project_id': PROJECT_ID, 'project_name': PROJECT_NAME, 'address': ADDRESS,
              'db_write': bool(args.apply), 'scope': 'ONE_PROJECT_ONLY',
              'address_applied': False, 'coordinate_applied': False,
              'blocker': None, 'steps': []}
    try:
        row = evidence()
        report['steps'].append({'step': 'OFFICIAL_EVIDENCE', 'result': 'CONFIRMED',
                                'basis': 'OFFICIAL_LIST_ROW_PROJECT_NAME_IS_LOT',
                                'source_url': row['source_url'],
                                'content_hash': row['content_hash'],
                                'raw_row': row['raw_source_text']})
        url, headers = configuration()
        report['steps'].append({'step': 'CONFIGURATION', 'result': 'PASS'})
    except Blocked as blocked:
        report['blocker'] = blocked.reason
        report['steps'].append({'step': 'BLOCKED', 'reason': blocked.reason})
        RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print(json.dumps({'blocker': blocked.reason, 'db_write': False,
                          'address_applied': False, 'coordinate_applied': False},
                         ensure_ascii=False))
        return 0

    if args.check_config:
        print(json.dumps({'configuration': 'PASS', 'db_write': False}, ensure_ascii=False))
        return 0

    import requests
    from services.config import get_secret

    def http_get(target, params=None, headers_=None, timeout=10):
        return geo.requests_get(target, params=params, headers=headers_, timeout=timeout)

    current = requests.get(f'{url}/rest/v1/development_projects', headers=headers, timeout=20,
                           params={'project_id': 'eq.' + PROJECT_ID,
                                   'select': 'project_id,sigungu,dong,address,revision,'
                                             'location,geometry_verified'}).json()
    stored = current[0] if current else None
    if stored is None:
        report['blocker'] = 'PROJECT_NOT_IN_DATABASE'
    elif stored.get('address'):
        report['blocker'] = 'ADDRESS_ALREADY_SET'
    elif stored.get('sigungu') != DISTRICT:
        report['blocker'] = 'DISTRICT_MISMATCH'
    report['steps'].append({'step': 'PREFLIGHT', 'stored': stored, 'blocker': report['blocker']})

    if report['blocker'] or not args.apply:
        RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print(json.dumps({'mode': 'APPLY' if args.apply else 'DRY_RUN',
                          'db_write': False, 'blocker': report['blocker'],
                          'would_write_address': ADDRESS}, ensure_ascii=False))
        return 0

    answer = requests.post(f'{url}/rest/v1/{INGEST_RPC}', headers=headers, timeout=20,
                           json=address_payload(row, stored['revision'])).json()
    answer = answer[0] if isinstance(answer, list) and answer else answer
    filled = (answer or {}).get('filled_fields') or []
    report['address_applied'] = 'address' in filled
    report['steps'].append({'step': 'ADDRESS', 'result': (answer or {}).get('result'),
                            'filled_fields': filled})

    evaluation, provider = geocode_once(get_secret, http_get)
    report['steps'].append({'step': 'GEOCODE', 'provider': provider,
                            'confidence': evaluation.get('geocode_confidence'),
                            'candidate_count': evaluation.get('provider_candidate_count'),
                            'matched_address': evaluation.get('matched_address'),
                            'checks': evaluation.get('checks'),
                            'review_reason': evaluation.get('review_reason')})
    if evaluation.get('geocode_confidence') != 'EXACT' or not evaluation.get('coordinate_verified'):
        report['coordinate_status'] = 'MANUAL_REVIEW'
        RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        print(json.dumps({'address_applied': report['address_applied'],
                          'coordinate_applied': False, 'coordinate_status': 'MANUAL_REVIEW'},
                         ensure_ascii=False))
        return 0

    after = requests.get(f'{url}/rest/v1/development_projects', headers=headers, timeout=20,
                         params={'project_id': 'eq.' + PROJECT_ID,
                                 'select': 'revision,sigungu,location'}).json()[0]
    located = requests.post(f'{url}/rest/v1/{LOCATION_RPC}', headers=headers, timeout=20, json={
        'p_project_id': PROJECT_ID, 'p_longitude': evaluation['longitude'],
        'p_latitude': evaluation['latitude'], 'p_expected_sigungu': after['sigungu'],
        'p_geocode_source': 'NAVER_MAP_GEOCODE', 'p_confidence': 'EXACT',
        'p_expected_revision': after['revision'],
        'p_evidence': {'address_used': evaluation.get('address_used'),
                       'matched_address': evaluation.get('matched_address'),
                       'road_address': evaluation.get('road_address'),
                       'jibun_address': evaluation.get('jibun_address'),
                       'english_address': evaluation.get('english_address'),
                       'address_elements': evaluation.get('address_elements'),
                       'checks': evaluation.get('checks'),
                       'geocoded_at': evaluation.get('geocoded_at')}}).json()
    located = located[0] if isinstance(located, list) and located else located
    report['coordinate_applied'] = (located or {}).get('result') == 'location_set'
    report['steps'].append({'step': 'COORDINATE', 'result': (located or {}).get('result'),
                            'reason': (located or {}).get('reason')})
    RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')
    print(json.dumps({'address_applied': report['address_applied'],
                      'coordinate_applied': report['coordinate_applied'],
                      'file': str(RESULT_FILE.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

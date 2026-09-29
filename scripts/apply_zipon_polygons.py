"""검토를 통과한 공식 사업구역 polygon만 반영한다. 다른 칸은 건드리지 않는다.

  python scripts/apply_zipon_polygons.py --check-config   # 자격증명·산출물만 확인
  python scripts/apply_zipon_polygons.py --dry-run        # 계획만, 쓰기 없음 (기본)
  python scripts/apply_zipon_polygons.py --apply          # 한 건씩 RPC로 반영
  python scripts/apply_zipon_polygons.py --apply --only <project_id>  # 한 건만

무엇을 넣는가: `polygon_match_review_20260928.json`에서 `auto_apply_candidate`인 건,
즉 등급이 EXACT이고 geometry가 유효하며 대표좌표가 그 polygon 안에 있는 건만이다.
`polygon_match_exact_20260928.geojson`에 같은 project_id의 feature가 있어야 한다.
둘이 어긋나면 그 건은 건너뛴다.

무엇을 넣지 않는가: PROBABLE / AMBIGUOUS / NO_MATCH, geometry가 유효하지 않은 건,
대표좌표가 polygon 밖인 건, identity conflict·duplicate risk로 보호 중인 건.

안전장치(스크립트가 먼저 보고, 데이터베이스가 다시 본다):
  * 산출물의 원천 판과 해시가 source_registry.json과 같아야 한다
  * 한 건씩 revision을 읽고 그 revision으로만 쓴다(낙관적 잠금)
  * 이미 verified 경계가 있으면 건너뛴다. 덮어쓰지 않는다
  * 저장된 자치구가 산출물의 자치구와 달라도 쓰지 않는다
  * polygon이 서울 범위를 벗어나거나 면적이 정비사업 구역으로 볼 수 없으면 쓰지 않는다
  * 저장된 대표좌표가 polygon 안에 없으면 쓰지 않는다
  * RPC는 geometry 계열과 field_evidence.boundary, revision만 바꾼다.
    location / stage / status / validation_status / identity는 그대로다
반영 뒤에는 한 건씩 다시 읽어 geometry_verified와 면적, 그리고 좌표·단계·identity가
그대로인지 확인하고 journal에 남긴다.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
REFERENCE = ROOT / 'data/reference'
REVIEW_FILE = DATA / 'polygon_match_review_20260928.json'
GEOJSON_FILE = DATA / 'polygon_match_exact_20260928.geojson'
REGISTRY_FILE = REFERENCE / 'source_registry.json'
JOURNAL_FILE = DATA / 'polygon_apply_journal_20260929.json'
PROJECT_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'
BOUNDARY_RPC = 'rpc/zipon_set_project_boundary'
GEOMETRY_SOURCE = '서울특별시 도시계획사업 현황(서울플랜+) 공간정보'
PORTAL_URL = 'https://data.seoul.go.kr/dataList/OA-22712/S/1/datasetView.do'
# 확인된 경계가 아니면 화면이 구역으로 그리지 않는다. 여기서도 같은 범위를 쓴다.
SEOUL_LON = (126.734, 127.270)
SEOUL_LAT = (37.413, 37.715)
MIN_AREA_M2, MAX_AREA_M2 = 100.0, 5_000_000.0
# RPC가 바꾸지 않아야 하는 칸. 반영 뒤에 그대로인지 확인한다.
UNTOUCHED = ('sigungu', 'dong', 'address', 'stage', 'stage_raw', 'status', 'validation_status',
             'external_id', 'official_authority', 'location_source', 'canonical_source_id')


class Blocked(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def artifacts():
    """검토 산출물과 원천 등록부를 읽고 서로 맞는지 확인한다."""
    if not REVIEW_FILE.exists():
        raise Blocked('REVIEW_ARTIFACT_MISSING')
    if not GEOJSON_FILE.exists():
        raise Blocked('REVIEW_GEOJSON_MISSING')
    review = json.loads(REVIEW_FILE.read_text(encoding='utf-8'))
    geojson = json.loads(GEOJSON_FILE.read_text(encoding='utf-8'))
    if review.get('format') != 'zipon-polygon-match-review-v1':
        raise Blocked('REVIEW_FORMAT_UNKNOWN')
    if review.get('db_write') is not False:
        raise Blocked('REVIEW_ARTIFACT_CLAIMS_A_WRITE')
    source = review.get('source') or {}
    for field in ('dataset_id', 'version', 'source_sha256', 'archive'):
        if not source.get(field):
            raise Blocked('REVIEW_SOURCE_PROVENANCE_INCOMPLETE')
    if not REGISTRY_FILE.exists():
        raise Blocked('SOURCE_REGISTRY_MISSING')
    registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    entry = next((s for s in registry.get('sources', [])
                  if s.get('dataset_id') == source['dataset_id']), None)
    if entry is None:
        raise Blocked('SOURCE_NOT_IN_REGISTRY')
    if entry.get('source_sha256') != source['source_sha256']:
        # 등록된 원천과 산출물의 원천이 다르다. 어느 판으로 만든 결과인지 알 수 없다.
        raise Blocked('SOURCE_HASH_DOES_NOT_MATCH_REGISTRY')
    if entry.get('version') != source['version']:
        raise Blocked('SOURCE_VERSION_DOES_NOT_MATCH_REGISTRY')
    return review, geojson, source


def ring_points(geometry):
    """GeoJSON Polygon / MultiPolygon의 모든 점. 다른 형태는 받지 않는다."""
    kind = (geometry or {}).get('type')
    coordinates = (geometry or {}).get('coordinates')
    if kind == 'Polygon':
        rings = coordinates or []
    elif kind == 'MultiPolygon':
        rings = [ring for part in (coordinates or []) for ring in part]
    else:
        return None
    points = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            return None
        if ring[0] != ring[-1]:
            return None
        for point in ring:
            if not isinstance(point, list) or len(point) < 2:
                return None
            longitude, latitude = point[0], point[1]
            if not isinstance(longitude, (int, float)) or not isinstance(latitude, (int, float)):
                return None
            points.append((float(longitude), float(latitude)))
    return points or None


def ring_area_m2(geometry):
    """대략적인 면적(제곱미터). 터무니없는 크기를 걸러내기 위한 어림값이다.

    정확한 면적은 PostGIS가 다시 계산한다. 여기서는 자치구 단위 도형 같은 것을 미리 잡는다.
    """
    import math
    kind = geometry.get('type')
    parts = [geometry['coordinates']] if kind == 'Polygon' else geometry['coordinates']
    total = 0.0
    for part in parts:
        outer = part[0]
        latitudes = [point[1] for point in outer]
        middle = math.radians(sum(latitudes) / len(latitudes))
        metres_per_degree_lat = 111_132.0
        metres_per_degree_lon = 111_320.0 * math.cos(middle)
        shoelace = 0.0
        for index in range(len(outer) - 1):
            x1 = outer[index][0] * metres_per_degree_lon
            y1 = outer[index][1] * metres_per_degree_lat
            x2 = outer[index + 1][0] * metres_per_degree_lon
            y2 = outer[index + 1][1] * metres_per_degree_lat
            shoelace += x1 * y2 - x2 * y1
        total += abs(shoelace) / 2
    return total


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[index + 1][0], ring[index + 1][1]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < crossing:
                inside = not inside
    return inside


def point_inside(geometry, longitude, latitude):
    """외곽 ring 안에 있고 그 구멍에는 들어 있지 않을 때만 True."""
    kind = geometry.get('type')
    parts = [geometry['coordinates']] if kind == 'Polygon' else geometry['coordinates']
    for part in parts:
        if not point_in_ring((longitude, latitude), part[0]):
            continue
        if any(point_in_ring((longitude, latitude), hole) for hole in part[1:]):
            continue
        return True
    return False


def plan(review, geojson, source):
    """반영할 건과 건너뛸 건을 나눈다. 여기서 쓰지는 않는다."""
    features = {}
    for feature in geojson.get('features') or []:
        properties = feature.get('properties') or {}
        project_id = properties.get('zipon_project_id')
        if project_id:
            features.setdefault(project_id, feature)
    selected, skipped = [], []
    for row in review.get('items') or []:
        project_id = row.get('zipon_project_id')
        if not row.get('auto_apply_candidate'):
            skipped.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                            'reason': row.get('excluded_reason') or f"NOT_AUTO_APPLY_{row.get('match_status')}"})
            continue
        feature = features.get(project_id)
        if feature is None:
            skipped.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                            'reason': 'NOT_IN_REVIEW_GEOJSON'})
            continue
        geometry = feature.get('geometry') or {}
        points = ring_points(geometry)
        if points is None:
            skipped.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                            'reason': 'GEOMETRY_NOT_A_CLOSED_POLYGON'})
            continue
        if any(not (SEOUL_LON[0] <= lon <= SEOUL_LON[1]) or not (SEOUL_LAT[0] <= lat <= SEOUL_LAT[1])
               for lon, lat in points):
            skipped.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                            'reason': 'BOUNDARY_OUTSIDE_SEOUL'})
            continue
        area = ring_area_m2(geometry)
        if not MIN_AREA_M2 <= area <= MAX_AREA_M2:
            skipped.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                            'reason': 'BOUNDARY_AREA_IMPLAUSIBLE', 'area_m2': round(area, 1)})
            continue
        if row.get('match_status') != 'EXACT' or not row.get('geometry_valid') \
                or row.get('representative_point_inside_polygon') is not True:
            skipped.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                            'reason': 'REVIEW_ROW_DOES_NOT_SUPPORT_AN_APPLY'})
            continue
        selected.append({'project_id': project_id, 'project_name': row.get('zipon_project_name'),
                         'district': row.get('district'), 'geometry': geometry,
                         'geometry_type': geometry.get('type'), 'area_m2': round(area, 1),
                         'official_name': row.get('official_name'),
                         'official_source_record_id': row.get('official_source_record_id'),
                         'normalized_name': row.get('official_normalized_name'),
                         'match_signals': row.get('match_signals'),
                         'evidence': evidence_for(row, source)})
    return selected, skipped


def evidence_for(row, source):
    """RPC가 요구하는 근거. 없는 값을 만들지 않는다."""
    return {'match_status': row.get('match_status'),
            'auto_apply_candidate': True,
            'representative_point_inside_polygon': True,
            'source_dataset': source.get('dataset'), 'source_version': source.get('version'),
            'source_sha256': source.get('source_sha256'),
            'official_name': row.get('official_name'),
            'official_source_record_id': row.get('official_source_record_id'),
            'normalized_name': row.get('official_normalized_name'),
            'match_signals': row.get('match_signals'),
            'legal_note': source.get('legal_note'),
            'checks': {'geometry_valid': bool(row.get('geometry_valid')),
                       'ring_closed': row.get('geometry_validity') == 'VALID',
                       'crs_converted': row.get('converted_crs') == 'EPSG:4326',
                       'normalized_name_match': bool(row.get('official_normalized_name'))
                       and row.get('official_normalized_name') == row.get('zipon_normalized_name'),
                       'district_match': 'DISTRICT' in (row.get('match_signals') or []),
                       'single_candidate': row.get('match_status') == 'EXACT',
                       'not_identity_protected': row.get('match_status') == 'EXACT',
                       'point_in_polygon': row.get('representative_point_inside_polygon') is True}}


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


def stored_row(session, url, headers, project_id):
    select = ('project_id,revision,geometry_verified,geometry_source,geometry_verified_at,'
              'location,' + ','.join(UNTOUCHED))
    answer = session.get(f'{url}/rest/v1/development_projects', headers=headers, timeout=20,
                         params={'project_id': 'eq.' + project_id, 'select': select}).json()
    return answer[0] if answer else None


def apply_one(session, url, headers, item, stored):
    """한 건을 반영한다. 쓰기 전 확인은 여기서, 다시 한 번은 RPC 안에서 한다."""
    from services.development import _point
    if stored is None:
        return {'result': 'skipped', 'reason': 'PROJECT_NOT_IN_DATABASE'}
    if stored.get('geometry_verified'):
        return {'result': 'skipped', 'reason': 'BOUNDARY_ALREADY_VERIFIED'}
    if (stored.get('sigungu') or '') != (item.get('district') or ''):
        return {'result': 'refused', 'reason': 'DISTRICT_MISMATCH',
                'stored_sigungu': stored.get('sigungu')}
    longitude, latitude = _point(stored.get('location'))
    if longitude is not None and not point_inside(item['geometry'], longitude, latitude):
        return {'result': 'refused', 'reason': 'STORED_POINT_OUTSIDE_BOUNDARY'}
    answer = session.post(f'{url}/rest/v1/{BOUNDARY_RPC}', headers=headers, timeout=30, json={
        'p_project_id': item['project_id'], 'p_geometry': item['geometry'],
        'p_geometry_source': GEOMETRY_SOURCE, 'p_source_url': PORTAL_URL,
        'p_expected_sigungu': item['district'], 'p_expected_revision': stored['revision'],
        'p_evidence': item['evidence']}).json()
    return answer[0] if isinstance(answer, list) and answer else answer


def verify_one(session, url, headers, item, before):
    """반영 뒤 한 건을 다시 읽는다. 바뀌어서는 안 되는 칸이 그대로인지 본다."""
    after = stored_row(session, url, headers, item['project_id'])
    if after is None:
        return {'verified': False, 'reason': 'PROJECT_DISAPPEARED'}
    changed = [field for field in UNTOUCHED if before.get(field) != after.get(field)]
    return {'verified': bool(after.get('geometry_verified')),
            'geometry_source': after.get('geometry_source'),
            'geometry_verified_at': after.get('geometry_verified_at'),
            'revision': after.get('revision'),
            'location_untouched': before.get('location') == after.get('location'),
            'unexpected_changes': changed}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check-config', action='store_true')
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    ap.add_argument('--only', help='이 project_id 한 건만')
    ap.add_argument('--limit', type=int, default=0, help='0이면 전부')
    args = ap.parse_args()

    journal = {'format': 'zipon-polygon-apply-journal-v1', 'generated_at': now(),
               'mode': 'APPLY' if args.apply else 'DRY_RUN',
               'db_write': bool(args.apply), 'scope': 'REVIEWED_AUTO_APPLY_CANDIDATES_ONLY',
               'applied': 0, 'skipped_in_database': 0, 'refused': 0,
               'blocker': None, 'source': None, 'selected': [], 'not_selected': [],
               'results': []}
    try:
        review, geojson, source = artifacts()
        selected, skipped = plan(review, geojson, source)
        journal['source'] = {k: source.get(k) for k in
                             ('dataset', 'dataset_id', 'version', 'archive', 'source_sha256',
                              'legal_note')}
        journal['not_selected'] = skipped
        if args.only:
            selected = [item for item in selected if item['project_id'] == args.only]
        if args.limit:
            selected = selected[:args.limit]
        journal['selected'] = [{k: item[k] for k in
                                ('project_id', 'project_name', 'district', 'geometry_type',
                                 'area_m2', 'official_name', 'official_source_record_id')}
                               for item in selected]
        if args.check_config or args.apply:
            url, headers = configuration()
    except Blocked as blocked:
        journal['blocker'] = blocked.reason
        JOURNAL_FILE.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
        print(json.dumps({'blocker': blocked.reason, 'db_write': False, 'applied': 0},
                         ensure_ascii=False))
        return 1

    if args.check_config:
        print(json.dumps({'configuration': 'PASS', 'db_write': False,
                          'selected': len(journal['selected']),
                          'not_selected': len(skipped)}, ensure_ascii=False))
        return 0
    if not args.apply:
        JOURNAL_FILE.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + '\n',
                                encoding='utf-8')
        print(json.dumps({'mode': 'DRY_RUN', 'db_write': False,
                          'would_apply': len(selected), 'not_selected': len(skipped),
                          'journal': str(JOURNAL_FILE.relative_to(ROOT))}, ensure_ascii=False))
        return 0

    import requests
    session = requests.Session()
    for item in selected:
        before = stored_row(session, url, headers, item['project_id'])
        answer = apply_one(session, url, headers, item, before) or {}
        record = {'project_id': item['project_id'], 'project_name': item['project_name'],
                  'district': item['district'], 'geometry_type': item['geometry_type'],
                  'area_m2': item['area_m2'], 'result': answer.get('result'),
                  'reason': answer.get('reason'), 'rpc': answer}
        if answer.get('result') == 'boundary_set':
            journal['applied'] += 1
            record['verification'] = verify_one(session, url, headers, item, before)
        elif answer.get('result') == 'skipped':
            journal['skipped_in_database'] += 1
        else:
            journal['refused'] += 1
        journal['results'].append(record)

    JOURNAL_FILE.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')
    print(json.dumps({'mode': 'APPLY', 'db_write': True, 'applied': journal['applied'],
                      'skipped_in_database': journal['skipped_in_database'],
                      'refused': journal['refused'],
                      'journal': str(JOURNAL_FILE.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

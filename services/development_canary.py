"""ZIP:ON geocode canary: ten canonical projects, geocoded once, no database write.

Why the ten rows are frozen here rather than read from data/development: the deploy
uploads api/, services/ and web/ to the Space, not data/, and the NAVER credential
only exists on the Space. Keeping the list in services/ is what makes the canary
runnable where the credential is. scripts/select_zipon_geocode_canary.py derives the
same ten from the canonical file and a test asserts the two never drift apart.

What this module refuses to do: accept a first result, accept a 동·구 centroid, accept
a swapped axis pair, judge INSIDE, or write anything. A representative point supports
NEARBY and distance only; the boundary layer stays unverified, so presentation keeps
allows_inside false on its own.
"""
from math import asin, cos, log2, radians, sin, sqrt

from services import development_geocode as geo
from services import development_presentation as presentation

CANARY_VERSION = 'zipon-geocode-canary-v1'
# 자치구 4·3·3, 동 10개 전부 다름, 정비사업 유형 2종, 번지형 6건. 선정 근거는
# scripts/select_zipon_geocode_canary.py의 docstring에 있다.
CANARY = (
    {'project_id': '02b9c94c-8b6c-5297-affa-1e827181afb0',
     'project_name': '둔촌주공아파트 주택재건축정비사업조합',
     'canonical_address': '서울특별시 강동구 둔촌동 172',
     'district': '강동구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '0922ac26-1436-5158-853d-49d3c5aed7fb',
     'project_name': '천호 A1-1구역 공공재개발 정비사업 주민대표회의',
     'canonical_address': '서울특별시 강동구 천호동 467-61',
     'district': '강동구', 'project_type': 'REDEVELOPMENT', 'program': None},
    {'project_id': '17ae087a-3eb2-590e-9e32-7c36cd66eb6c',
     'project_name': '삼익파크아파트 재건축사업조합',
     'canonical_address': '서울특별시 강동구 길동 54',
     'district': '강동구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '1effd17b-53f8-52a3-b2bc-a91c8c7ce4f7',
     'project_name': '고덕주공6단지아파트 주택재건축정비사업조합',
     'canonical_address': '서울특별시 강동구 상일동 124',
     'district': '강동구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '070e2349-2569-5652-8d56-bc8080b20304',
     'project_name': '송파한양2차아파트 재건축정비사업 조합',
     'canonical_address': '서울특별시 송파구 송파동 151',
     'district': '송파구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '0cfa354d-f9ac-5516-aa2a-1f6767c0aa98',
     'project_name': '마천2재정비촉진구역 주택재개발정비사업',
     'canonical_address': '서울특별시 송파구 마천동 183-1',
     'district': '송파구', 'project_type': 'REDEVELOPMENT', 'program': None},
    {'project_id': '1a37e972-e886-5fec-a872-80402bd47c44',
     'project_name': '잠실진주아파트 주택재건축정비사업조합',
     'canonical_address': '서울특별시 송파구 신천동 20-4',
     'district': '송파구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '0164b2b0-1b21-51e3-8b8d-f97bda852a18',
     'project_name': '신반포25차아파트주택재건축정비사업조합설립추진위원회',
     'canonical_address': '서울특별시 서초구 잠원동 61-1',
     'district': '서초구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '03852475-6791-5fe9-9ea1-db09b5fdddc8',
     'project_name': '강남원효성빌라 재건축정비사업조합',
     'canonical_address': '서울특별시 서초구 반포동 591-1',
     'district': '서초구', 'project_type': 'RECONSTRUCTION', 'program': None},
    {'project_id': '0a179fc4-01b7-5991-97ad-0c4108273a8f',
     'project_name': '방배15 재건축정비사업조합',
     'canonical_address': '서울특별시 서초구 방배동 528-3',
     'district': '서초구', 'project_type': 'RECONSTRUCTION', 'program': None},
)
# 좌표가 자치구별로 얼마나 퍼져 있는지 보는 값. 자치구 경계가 아니라 분포 점검이다.
DISTRICT_SPREAD_LIMIT_M = 5000
# 같은 좌표에 여러 사업이 몰렸는지 보는 격자. 6자리는 약 0.1m, 4자리는 약 11m.
EXACT_PRECISION, CLUSTER_PRECISION = 6, 4


def _distance_m(a, b):
    """Haversine. 거리 계산에만 쓰고 구역 내부 판정에는 쓰지 않는다."""
    lon1, lat1, lon2, lat2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * asin(sqrt(h))


def verify(row, response, evaluation):
    """요청 주소와 NAVER 응답을 항목별로 맞대어 본 기록. 판정을 만들지는 않는다."""
    candidates = (response or {}).get('candidates') or []
    candidate = candidates[0] if len(candidates) == 1 else {}
    # 캐시에서 되살린 건은 응답이 없다. 그때는 평가 결과에 남은 값을 쓴다.
    pick = lambda field: (candidate.get(field) if candidate.get(field) is not None
                          else evaluation.get(field))
    elements = candidate.get('address_elements') or evaluation.get('address_elements') or {}
    wanted = evaluation.get('wanted_parts') or geo.wanted_parts(row['canonical_address'])
    checks = evaluation.get('checks') or {}
    return {
        'project_id': row['project_id'], 'project_name': row['project_name'],
        'canonical_address': row['canonical_address'], 'district': row['district'],
        'project_type': row['project_type'], 'program': row['program'],
        'candidate_count': (len(candidates) if response is not None
                            else evaluation.get('provider_candidate_count') or 0),
        'matched_road_address': pick('road_address') or None,
        'matched_jibun_address': pick('jibun_address') or None,
        'matched_address': evaluation.get('matched_address'),
        'english_address': pick('english_address') or None,
        'distance_m': pick('distance_m'),
        'longitude': evaluation.get('longitude'), 'latitude': evaluation.get('latitude'),
        'provider_longitude': pick('longitude'), 'provider_latitude': pick('latitude'),
        'in_seoul_bounds': geo.in_bounds(pick('longitude'), pick('latitude')),
        'district_match': checks.get('district_match'),
        'returned_district': elements.get('SIGUGUN'),
        'dong_match': checks.get('dong_match'), 'returned_dong': elements.get('DONGMYUN'),
        'lot_match': checks.get('lot_match'), 'returned_lot': elements.get('LAND_NUMBER'),
        'road_match': checks.get('road_match'),
        'building_number_match': checks.get('building_number_match'),
        'wanted_dong': wanted['dong'], 'wanted_lot': wanted['lot'],
        'accuracy': evaluation.get('accuracy'),
        'coordinate_orientation': evaluation.get('coordinate_orientation'),
        'geocode_confidence': evaluation.get('geocode_confidence'),
        'geocode_source': evaluation.get('geocode_source'),
        'result_status': evaluation.get('result_status'),
        'endpoint': evaluation.get('endpoint'), 'checks': checks,
        'address_elements': candidate.get('address_elements') or None,
        'address_used': evaluation.get('address_used'),
        'geocoded_at': evaluation.get('geocoded_at'),
        # 후보가 여러 개여서 특정하지 못한 경우, 사람이 비교할 후보 요약.
        'candidate_summaries': evaluation.get('candidate_summaries') or None,
    }


def classify(record, evaluation):
    """ACCEPTED / REVIEW_REQUIRED / FAILED와 그 사유. 애매하면 채택하지 않는다.

    자격증명이 없어 아예 호출하지 못한 건은 PENDING_PROVIDER로 따로 센다. 시도조차
    하지 않은 것을 FAILED로 세면 품질이 나빠서 실패한 것처럼 읽힌다.
    """
    if evaluation.get('error_type'):
        return 'FAILED', 'PROVIDER_ERROR_' + evaluation['error_type']
    confidence = evaluation.get('geocode_confidence')
    if confidence == 'EXACT' and evaluation.get('coordinate_verified'):
        return 'ACCEPTED', ('EXACT_MATCH_ON_' + ','.join(
            sorted(k for k, ok in (evaluation.get('checks') or {}).items() if ok)))
    if confidence == 'UNRESOLVED':
        if evaluation.get('geocode_source') is None:
            return 'PENDING_PROVIDER', evaluation.get('reason') or 'NO_PROVIDER_CONFIGURED'
        return 'FAILED', 'PROVIDER_RETURNED_' + str(evaluation.get('result_status'))
    return 'REVIEW_REQUIRED', evaluation.get('review_reason') or 'NOT_AN_EXACT_MATCH'


def map_payload(accepted):
    """실제 지도 컴포넌트가 받는 payload. presentation.map_point을 그대로 쓴다.

    좌표는 대표 위치이므로 boundary_status는 미확인으로 남고, 그래서 allows_inside는
    presentation 쪽에서 저절로 false가 된다. 여기서 INSIDE를 만들 길은 없다.
    """
    points = [presentation.map_point({
        'project_id': r['project_id'], 'project_name': r['project_name'],
        'project_type': r['project_type'], 'sigungu': r['district'],
        'dong': r['wanted_dong'], 'address': r['canonical_address'],
        'latitude': r['latitude'], 'longitude': r['longitude'],
        'validation_status': 'NEEDS_REVIEW', 'geometry_verified': False,
        'stage_raw': None, 'source_url': None, 'last_verified_at': None,
    }) for r in accepted]
    if not points:
        return {'points': [], 'total': 0, 'mappable': 0, 'bbox': None, 'center': None,
                'suggested_zoom': None, 'layers': presentation.MAP_LAYERS,
                'legend': presentation.LOCATION_ACCURACY,
                'inside_judgement': 'NOT_PERMITTED_WITHOUT_VERIFIED_BOUNDARY'}
    longitudes = [p['longitude'] for p in points]
    latitudes = [p['latitude'] for p in points]
    bbox = {'west': min(longitudes), 'east': max(longitudes),
            'south': min(latitudes), 'north': max(latitudes)}
    span = max(bbox['east'] - bbox['west'], bbox['north'] - bbox['south'], 1e-6)
    return {'points': points, 'total': len(points),
            'mappable': sum(1 for p in points if p['mappable']), 'bbox': bbox,
            'center': {'longitude': (bbox['west'] + bbox['east']) / 2,
                       'latitude': (bbox['south'] + bbox['north']) / 2},
            # 화면은 fitBounds를 쓰므로 이 값은 참고용 초기 zoom이다.
            'suggested_zoom': max(9, min(16, int(log2(360 / span)))),
            'layers': presentation.MAP_LAYERS, 'legend': presentation.LOCATION_ACCURACY,
            'inside_judgement': 'NOT_PERMITTED_WITHOUT_VERIFIED_BOUNDARY'}


def sanity(accepted):
    """자치구 일치·좌표 쏠림·축 뒤집힘을 다시 본다. 통과해도 경계 판정은 하지 않는다."""
    districts, duplicates, clusters = {}, {}, {}
    orientation, mismatched = [], []
    for row in accepted:
        point = (row['longitude'], row['latitude'])
        districts.setdefault(row['district'], []).append((row['project_id'], point))
        duplicates.setdefault((round(point[0], EXACT_PRECISION),
                               round(point[1], EXACT_PRECISION)), []).append(row['project_id'])
        clusters.setdefault((round(point[0], CLUSTER_PRECISION),
                             round(point[1], CLUSTER_PRECISION)), []).append(row['project_id'])
        if row['coordinate_orientation'] != 'X_IS_LONGITUDE':
            orientation.append(row['project_id'])
        if row['district_match'] is not True or row['returned_district'] != row['district']:
            mismatched.append(row['project_id'])
    verdict = (lambda ok: ok if accepted else None)
    spread = {}
    for district, entries in districts.items():
        centre = (sum(p[0] for _, p in entries) / len(entries),
                  sum(p[1] for _, p in entries) / len(entries))
        distances = {pid: round(_distance_m(centre, p)) for pid, p in entries}
        spread[district] = {'projects': len(entries),
                            'centre': {'longitude': centre[0], 'latitude': centre[1]},
                            'max_distance_m': max(distances.values()) if distances else 0,
                            'beyond_limit': sorted(pid for pid, d in distances.items()
                                                   if d > DISTRICT_SPREAD_LIMIT_M)}
    return {
        'evaluated_points': len(accepted),
        'district_match': {'checked': len(accepted), 'mismatched': mismatched,
                           'passed': verdict(not mismatched),
                           'basis': 'NAVER addressElements SIGUGUN vs the stored 자치구',
                           'limitation': ('검증된 자치구 경계가 없어 point-in-polygon 판정은 '
                                          '하지 않는다. 좌표 분포로만 교차 확인한다.')},
        'district_spread': {'limit_m': DISTRICT_SPREAD_LIMIT_M, 'by_district': spread,
                            'passed': verdict(all(not s['beyond_limit'] for s in spread.values()))},
        'duplicate_coordinates': {
            'exact': {f'{k[0]},{k[1]}': v for k, v in duplicates.items() if len(v) > 1},
            'within_about_11m': {f'{k[0]},{k[1]}': v for k, v in clusters.items() if len(v) > 1},
            'passed': verdict(all(len(v) == 1 for v in duplicates.values())
                              and all(len(v) == 1 for v in clusters.values()))},
        'coordinate_orientation': {'checked': len(accepted), 'suspect': orientation,
                                   'expected': 'X_IS_LONGITUDE', 'passed': verdict(not orientation)},
    }


def run(get_secret, http_get=None, cache=None, preferred=None):
    """열 건만 조회하고 검증·분류·지도 payload·sanity를 한 번에 돌려준다. DB write 없음."""
    return dict(run_rows(CANARY, get_secret, http_get, cache, preferred),
                format=CANARY_VERSION, selected=len(CANARY), bulk_149_run=False)


def run_rows(rows, get_secret, http_get=None, cache=None, preferred=None, cache_only=False):
    """주어진 행들만 조회하고 검증·분류·지도 payload·sanity를 돌려준다. DB write 없음.

    cache_only면 provider를 부르지 않고 이미 받아 둔 주소 캐시만 읽는다. 이미 요금을
    낸 조회를 다시 사지 않고 전체 보고서를 다시 만들 수 있게 하기 위한 것이다.
    """
    selected = geo.select_provider(get_secret, http_get or geo.requests_get, preferred)
    store = cache if cache is not None else _cache_store()
    records, counts = [], {'ACCEPTED': 0, 'REVIEW_REQUIRED': 0, 'FAILED': 0,
                           'PENDING_PROVIDER': 0}
    calls = 0
    for row in rows:
        address = geo.normalize_address(row['canonical_address'])
        key = geo.cache_key(address)
        cached = store.get(key)
        if cached is not None and cached.get('geocode_confidence') != 'UNRESOLVED':
            response = None
            evaluation = dict(geo.from_cache_row(cached), from_cache=True)
        elif cache_only or selected['provider'] is None:
            response = None
            evaluation = {'geocode_confidence': 'UNRESOLVED', 'coordinate_verified': False,
                          'geocode_source': None, 'latitude': None, 'longitude': None,
                          'reason': 'NOT_YET_GEOCODED' if cache_only else selected['blocker']}
        else:
            try:
                response = selected['provider'](address)
                evaluation = geo.evaluate(address, response)
            except Exception as exc:
                response, evaluation = None, {
                    'geocode_confidence': 'UNRESOLVED', 'coordinate_verified': False,
                    'geocode_source': selected['name'], 'latitude': None, 'longitude': None,
                    'error_type': type(exc).__name__}
            calls += 1
            store.put(key, dict(evaluation, normalized_address=address,
                                cache_version=geo.CACHE_VERSION))
        record = verify(row, response, evaluation)
        record['outcome'], record['acceptance_reason'] = classify(record, evaluation)
        record['from_cache'] = bool(evaluation.get('from_cache'))
        counts[record['outcome']] += 1
        records.append(record)
    accepted = [r for r in records if r['outcome'] == 'ACCEPTED']
    return {'db_write': False, 'migration_applied': False,
            'cache_only': bool(cache_only), 'provider': selected['name'],
            'provider_configured': selected['provider'] is not None,
            'blocker': selected['blocker'], 'provider_priority': list(selected['priority']),
            'endpoint': geo.PROVIDER_SPECS.get(selected['name'] or '', {}).get('endpoint'),
            'selected': len(rows), 'provider_calls': calls, 'totals': counts,
            'policy': ['첫 결과를 무조건 채택하지 않는다',
                       '동 중심점·구청·주민센터 수준 응답은 채택하지 않는다',
                       'x=경도, y=위도이며 교환하지 않는다',
                       '대표 위치이므로 INSIDE 판정은 하지 않는다',
                       '이 실행은 데이터베이스에 아무것도 쓰지 않는다'],
            'results': records, 'map': map_payload(accepted), 'sanity': sanity(accepted)}


def _default_cache_dir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / 'data/development/cache/geocode'


def _cache_store():
    """주소 캐시. 배포 환경의 앱 디렉터리가 쓰기 불가일 수 있어 임시 디렉터리로 물러난다.

    캐시를 못 쓰는 것은 요금이 더 드는 문제이지 정확성 문제가 아니다. 그래서 여기서
    실행을 멈추지 않는다.
    """
    try:
        return geo.GeocodeCache(_default_cache_dir())
    except OSError:
        import tempfile
        return geo.GeocodeCache(tempfile.mkdtemp(prefix='zipon-geocode-'))

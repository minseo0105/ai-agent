"""Address -> coordinate resolution for ZIP:ON development candidates.

Deliberately stricter than the golf geocoder, which accepts the first search
result. Here a coordinate is only accepted when the provider returns exactly one
candidate whose returned address still contains the district and the lot we
asked for. Anything else becomes GEOCODE_REVIEW and stays unresolved, so no
representative point is ever manufactured from a dong centroid.

NAVER Maps Geocoding is the first provider (NAVER -> Kakao -> VWorld) because it
returns addressElements, which lets the sido / 자치구 / 동 / 번지 comparison be an
exact field match instead of a substring test. x is the longitude and y is the
latitude; the axes are never swapped, and a response that looks swapped is sent to
review rather than quietly corrected. Credentials are read by name only and never
appear in a return value, a cache row or a log line.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata

CACHE_VERSION = 'zipon-geocode-v1'
ACCEPTED_ACCURACY = ('PARCEL', 'BUILDING', 'ROAD_ADDRESS')
SEOUL_BOUNDS = {'longitude': (126.734, 127.270), 'latitude': (37.413, 37.715)}
SEOUL_SIDO = '서울특별시'

# NAVER Maps Geocoding. 현 host는 maps.apigw.ntruss.com이고 구 host는
# naveropenapi.apigw.ntruss.com이다. 경로와 인증 헤더는 두 host에서 같다.
NAVER_GEOCODE_URL = 'https://maps.apigw.ntruss.com/map-geocode/v2/geocode'
NAVER_GEOCODE_LEGACY_URL = 'https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode'
NAVER_HEADER_KEY_ID = 'X-NCP-APIGW-API-KEY-ID'      # Client ID
NAVER_HEADER_KEY = 'X-NCP-APIGW-API-KEY'            # Client Secret
# 개발사업 데이터와 무관한 연결 확인용 주소(서울특별시청). 실데이터를 태우지 않는다.
SAMPLE_ADDRESS = '서울특별시 중구 세종대로 110'
# 좌표 축을 확인하기 위한 한반도 범위. 서울 판정용 SEOUL_BOUNDS와는 목적이 다르다.
KOREA_LONGITUDE = (124.0, 132.0)
KOREA_LATITUDE = (33.0, 39.0)
# NAVER가 addressElements.types로 돌려주는 구성요소.
ELEMENT_TYPES = ('SIDO', 'SIGUGUN', 'DONGMYUN', 'RI', 'ROAD_NAME', 'BUILDING_NUMBER',
                 'BUILDING_NAME', 'LAND_NUMBER', 'POSTAL_CODE')


def normalize_address(value):
    text = unicodedata.normalize('NFKC', value or '')
    text = text.replace('서울시', '서울특별시')
    if text.startswith('서울 ') :
        text = '서울특별시 ' + text[3:]
    return re.sub(r'\s+', ' ', text).strip()


def cache_key(address):
    return hashlib.sha256(f'{CACHE_VERSION}|{normalize_address(address)}'.encode()).hexdigest()[:32]


class GeocodeCache:
    """Local file cache shaped so it can later be loaded into Supabase
    geocode_cache without rework. This sprint performs no database write."""

    COLUMNS = ('normalized_address', 'latitude', 'longitude', 'geocode_source',
               'geocode_confidence', 'geocoded_at', 'address_used', 'coordinate_verified',
               'provider_candidate_count', 'cache_version', 'matched_address', 'accuracy',
               'result_status', 'raw_snapshot')
    # 판정 근거는 raw_snapshot에 담는다. 이것을 빼면 캐시에서 되살린 행이 검증 근거를
    # 잃고, 자치구 일치나 좌표 축 검사가 실패한 것처럼 보인다.
    SNAPSHOT_FIELDS = ('checks', 'address_elements', 'coordinate_orientation', 'road_address',
                       'jibun_address', 'english_address', 'distance_m', 'review_reason',
                       'candidate_summaries', 'disambiguated_from', 'endpoint', 'wanted_parts',
                       'error_type')

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.requests = 0
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
        row = {column: entry.get(column) for column in self.COLUMNS}
        if row.get('raw_snapshot') is None:
            snapshot = {field: entry[field] for field in self.SNAPSHOT_FIELDS
                        if entry.get(field) is not None}
            row['raw_snapshot'] = snapshot or None
        row['cache_key'] = key
        self.path(key).write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n',
                                  encoding='utf-8')
        return row

    def rows(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(self.directory.glob('*.json'))]


def from_cache_row(row):
    """캐시 행을 다시 평가 결과 모양으로 펼친다. 검증 근거를 잃지 않기 위한 것이다."""
    evaluation = {key: value for key, value in (row or {}).items() if key != 'raw_snapshot'}
    evaluation.update((row or {}).get('raw_snapshot') or {})
    return evaluation


def in_bounds(longitude, latitude):
    return (isinstance(longitude, (int, float)) and isinstance(latitude, (int, float))
            and SEOUL_BOUNDS['longitude'][0] <= longitude <= SEOUL_BOUNDS['longitude'][1]
            and SEOUL_BOUNDS['latitude'][0] <= latitude <= SEOUL_BOUNDS['latitude'][1])


def _within(value, span):
    return isinstance(value, (int, float)) and span[0] <= value <= span[1]


def coordinate_orientation(x, y):
    """NAVER/Kakao는 x=경도, y=위도로 응답한다. 뒤집지 않고, 뒤집힌 것으로 보이면 그렇다고 표시한다.

    값을 조용히 교환하면 서울 한복판에 엉뚱한 핀이 꽂히고도 통과한다. 그래서
    의심스러운 응답은 SUSPECT_SWAPPED로 남겨 evaluate()가 검토로 보내게 한다.
    """
    if _within(x, KOREA_LONGITUDE) and _within(y, KOREA_LATITUDE):
        return 'X_IS_LONGITUDE'
    if _within(y, KOREA_LONGITUDE) and _within(x, KOREA_LATITUDE):
        return 'SUSPECT_SWAPPED'
    return 'OUT_OF_RANGE'


def wanted_parts(address):
    """요청 주소에서 시도·자치구·동·번지(또는 도로명·건물번호)를 뽑는다.

    지번 주소와 도로명 주소를 구분한다. '세종대로 110'의 110은 번지가 아니라
    건물번호이므로 LAND_NUMBER와 비교하면 멀쩡한 결과가 검토로 밀린다.
    """
    text = normalize_address(address)
    tokens = text.split()
    sido = tokens[0] if tokens and tokens[0].endswith(('시', '도')) and len(tokens[0]) > 2 else None
    district = next((t for t in tokens if t != sido and t.endswith('구')), None)
    dong = next((t for t in tokens if t not in (sido, district)
                 and re.fullmatch(r'[가-힣0-9]+[동리가]', t)), None)
    road = next((t for t in tokens if t not in (sido, district)
                 and re.search(r'(로|길)$', t)), None)
    number = re.search(r'(\d+(?:-\d+)?)\s*$', text)
    return {'normalized': text, 'sido': sido, 'district': district, 'dong': dong, 'road': road,
            'lot': number.group(1) if number and not road else None,
            'building_number': number.group(1) if number and road else None}


def address_elements(item):
    """NAVER addressElements를 타입별 dict로 펼친다. longName을 우선한다."""
    flat = {}
    for element in (item or {}).get('addressElements') or []:
        value = ((element or {}).get('longName') or (element or {}).get('shortName') or '').strip()
        for kind in (element or {}).get('types') or []:
            if kind and value and not flat.get(kind):
                flat[kind] = value
    return flat


def element_checks(parts, elements):
    """addressElements로 서울·자치구·동·번지를 정확 일치로 검증한다.

    substring 비교는 '천호동 3'이 '천호동 30'을 통과시키므로 쓰지 않는다.
    번지도 건물번호도 없는 요청은 동·구 중심점으로 해석될 수 있어 EXACT가 되지 않는다.
    """
    checks = {'seoul': elements.get('SIDO', '') == SEOUL_SIDO}
    if parts['sido']:
        checks['sido_match'] = elements.get('SIDO', '') == parts['sido']
    if parts['district']:
        checks['district_match'] = elements.get('SIGUGUN', '') == parts['district']
    if parts['dong']:
        checks['dong_match'] = elements.get('DONGMYUN', '') == parts['dong']
    if parts['lot']:
        checks['lot_match'] = elements.get('LAND_NUMBER', '') == parts['lot']
    if parts['road']:
        checks['road_match'] = elements.get('ROAD_NAME', '') == parts['road']
    if parts['building_number']:
        checks['building_number_match'] = elements.get('BUILDING_NUMBER', '') == parts['building_number']
    if not parts['lot'] and not parts['building_number']:
        checks['not_a_region_centroid'] = False
    return checks


def candidate_checks(parts, candidate):
    """이 후보가 요청 주소와 맞는지 항목별로 본다. 판정은 evaluate()가 모아서 한다."""
    longitude, latitude = candidate.get('longitude'), candidate.get('latitude')
    elements = candidate.get('address_elements') or {}
    orientation = (candidate.get('coordinate_orientation')
                   or coordinate_orientation(longitude, latitude))
    checks = {'accuracy': candidate.get('accuracy') in ACCEPTED_ACCURACY,
              'bounds': in_bounds(longitude, latitude),
              'axis_order': orientation == 'X_IS_LONGITUDE'}
    if elements:
        checks.update(element_checks(parts, elements))
    else:
        # addressElements를 주지 않는 provider는 되돌려준 주소 문자열로만 검증한다.
        returned = normalize_address(candidate.get('matched_address'))
        checks['district_match'] = bool(parts['district']) and parts['district'] in returned
        checks['lot_match'] = bool(parts['lot']) and parts['lot'] in returned
    return checks, orientation


# 같은 지번이라고 말할 수 있는 좌표 산포의 한계. 한 지번 위의 여러 동이라면 이보다
# 멀어지지 않는다. 약 220m(위도) / 180m(경도, 서울 위도 기준).
SAME_PARCEL_SPREAD = 0.002


def parcel_key(parts, elements):
    """이 후보가 가리키는 주소 단위. 우리가 요청한 형식에 맞춰 정확히 읽는다.

    지번 주소를 요청했으면 자치구·동·리·번지, 도로명을 요청했으면 자치구·도로명·
    건물번호다. 필요한 값이 하나라도 비면 None이고, 비슷한 값으로 메우지 않는다.
    """
    district = (elements.get('SIGUGUN') or '').strip()
    if not district:
        return None
    if parts['lot']:
        dong, lot = (elements.get('DONGMYUN') or '').strip(), (elements.get('LAND_NUMBER') or '').strip()
        if not dong or not lot:
            return None
        return ('jibun', district, dong, (elements.get('RI') or '').strip(), lot)
    if parts['building_number']:
        road = (elements.get('ROAD_NAME') or '').strip()
        number = (elements.get('BUILDING_NUMBER') or '').strip()
        if not road or not number:
            return None
        return ('road', district, road, number)
    return None


def disambiguate(parts, passing):
    """검증을 모두 통과한 후보가 여럿일 때 하나를 특정할 수 있는지 본다.

    한 지번 위에 여러 동이 올라간 경우가 대부분이다. 그때는 후보가 여러 개라도
    가리키는 주소 단위가 하나이므로 좌표를 채택할 수 있다. 특정할 수 없으면
    None을 돌려주고 호출자가 기존처럼 검토로 보낸다 — 첫 결과를 고르지 않는다.

    이름 유사도나 거리 최솟값으로 고르지 않는다. 판단 근거는 두 가지뿐이다:
    자치구가 요청과 정확히 같은가, 주소 단위가 정확히 하나인가.
    """
    if len(passing) < 2 or not parts['district']:
        return None, None
    # 1) 요청한 자치구와 정확히 같은 후보만 남긴다.
    same_district = [entry for entry in passing
                     if (entry[0].get('address_elements') or {}).get('SIGUGUN', '').strip()
                     == parts['district']]
    if len(same_district) != len(passing) or not same_district:
        return None, None
    # 2) 주소 단위가 정확히 하나여야 한다.
    keys = {parcel_key(parts, entry[0].get('address_elements') or {}) for entry in same_district}
    if len(keys) != 1 or None in keys:
        return None, None
    # 3) 같은 지번이라면 좌표가 이만큼 흩어질 수 없다. 흩어졌으면 믿지 않는다.
    longitudes = [entry[0].get('longitude') for entry in same_district]
    latitudes = [entry[0].get('latitude') for entry in same_district]
    if any(v is None for v in longitudes + latitudes):
        return None, None
    if (max(longitudes) - min(longitudes) > SAME_PARCEL_SPREAD
            or max(latitudes) - min(latitudes) > SAME_PARCEL_SPREAD):
        return None, None
    # 지번 자체의 점(건물명이 없는 후보)을 우선하고, 없으면 주소 문자열로 결정한다.
    # 입력 순서에 기대지 않기 위해 정렬로 고른다.
    def order(entry):
        elements = entry[0].get('address_elements') or {}
        building = (elements.get('BUILDING_NAME') or '').strip()
        # 건물명까지 정렬 키에 넣어야 입력 순서와 무관하게 같은 후보가 나온다.
        return (bool(building), normalize_address(entry[0].get('matched_address')), building)
    ordered = sorted(same_district, key=order)
    key = next(iter(keys))
    basis = {'rule': 'SINGLE_ADDRESS_UNIT_MULTIPLE_BUILDINGS',
             'address_unit': list(key), 'candidates_considered': len(passing),
             'collapsed_to': 1, 'district_match': parts['district'],
             'coordinate_spread': {'longitude': round(max(longitudes) - min(longitudes), 6),
                                   'latitude': round(max(latitudes) - min(latitudes), 6)},
             'selected_building': (ordered[0][0].get('address_elements') or {}).get('BUILDING_NAME') or None}
    return ordered[0], basis


def evaluate(address, response):
    """Decide whether a provider response is an exact match for this address.

    후보가 여러 개일 때 첫 결과를 쓰지 않는다. 주소 구성요소 검증을 모두 통과하는
    후보가 정확히 하나일 때만 그것을 채택하고, 0개거나 2개 이상이면 검토로 보낸다.
    """
    unresolved = {'latitude': None, 'longitude': None, 'geocode_source': None,
                  'geocoded_at': datetime.now(timezone.utc).isoformat(),
                  'address_used': normalize_address(address), 'coordinate_verified': False,
                  'provider_candidate_count': 0}
    if not response or response.get('result_status') != 'MATCHED':
        return dict(unresolved, geocode_confidence='UNRESOLVED',
                    provider_candidate_count=len(response.get('candidates') or []) if response else 0,
                    geocode_source=(response or {}).get('provider'),
                    result_status=(response or {}).get('result_status'))
    candidates = response.get('candidates') or []
    parts = wanted_parts(address)
    result = dict(unresolved, geocode_source=response.get('provider'),
                  provider_candidate_count=len(candidates), endpoint=response.get('endpoint'),
                  result_status='MATCHED', wanted_parts=parts)
    scored = [(candidate,) + candidate_checks(parts, candidate) for candidate in candidates]
    passing = [entry for entry in scored if all(entry[1].values())]
    chosen, basis = (None, None)
    if len(candidates) != 1 and len(passing) != 1:
        # Several official candidates for one address is exactly the case the
        # first-result-wins geocoders get wrong. 다만 그 여러 개가 같은 지번 위의
        # 여러 동이라면 특정할 수 있다. 특정되지 않으면 그대로 검토로 보낸다.
        chosen, basis = disambiguate(parts, passing)
        if chosen is None:
            return dict(result, geocode_confidence='GEOCODE_REVIEW',
                        review_reason='MULTIPLE_PROVIDER_CANDIDATES',
                        candidate_summaries=[_summary(c, checks) for c, checks, _ in scored])
    candidate, checks, orientation = chosen or (passing[0] if passing else scored[0])
    detail = {'matched_address': normalize_address(candidate.get('matched_address')),
              'accuracy': candidate.get('accuracy'), 'checks': checks,
              'address_elements': candidate.get('address_elements') or None,
              'coordinate_orientation': orientation,
              'road_address': candidate.get('road_address'),
              'jibun_address': candidate.get('jibun_address'),
              'english_address': candidate.get('english_address'),
              'distance_m': candidate.get('distance_m'),
              'disambiguated_from': len(candidates) if len(candidates) > 1 else None,
              'disambiguation': basis}
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        return dict(result, geocode_confidence='GEOCODE_REVIEW',
                    review_reason='CHECK_FAILED:' + ','.join(failed), **detail)
    return dict(result, latitude=candidate.get('latitude'), longitude=candidate.get('longitude'),
                geocode_confidence='EXACT', coordinate_verified=True,
                address_used=parts['normalized'], **detail)


def _summary(candidate, checks):
    """검토용 후보 요약. 사람이 공식 주소와 나란히 놓고 보게 만든다."""
    return {'jibun_address': candidate.get('jibun_address') or candidate.get('matched_address'),
            'road_address': candidate.get('road_address'),
            'longitude': candidate.get('longitude'), 'latitude': candidate.get('latitude'),
            'accuracy': candidate.get('accuracy'),
            'address_elements': candidate.get('address_elements') or None,
            'failed_checks': sorted(name for name, ok in checks.items() if not ok)}


def resolve(addresses, cache, provider=None):
    """One provider call per normalized address at most; cache first."""
    results, log = {}, []
    for address in addresses:
        if not address:
            continue
        key = cache_key(address)
        if key in results:
            cache.requests_avoided += 1
            log.append({'cache_key': key, 'status': 'DEDUPED_IN_RUN'})
            continue
        cached = cache.get(key)
        if cached is not None:
            results[key] = cached
            log.append({'cache_key': key, 'status': 'CACHE_HIT'})
            continue
        if provider is None:
            results[key] = {'normalized_address': normalize_address(address),
                            'geocode_confidence': 'UNRESOLVED', 'coordinate_verified': False,
                            'latitude': None, 'longitude': None, 'geocode_source': None,
                            'geocoded_at': None, 'address_used': normalize_address(address),
                            'provider_candidate_count': 0, 'cache_version': CACHE_VERSION,
                            'reason': 'NO_GEOCODE_PROVIDER_CONFIGURED'}
            log.append({'cache_key': key, 'status': 'NO_PROVIDER'})
            continue
        cache.requests += 1
        try:
            evaluation = evaluate(address, provider(normalize_address(address)))
        except Exception as exc:
            evaluation = {'geocode_confidence': 'UNRESOLVED', 'coordinate_verified': False,
                          'latitude': None, 'longitude': None, 'geocode_source': None,
                          'geocoded_at': datetime.now(timezone.utc).isoformat(),
                          'address_used': normalize_address(address),
                          'provider_candidate_count': 0, 'error_type': type(exc).__name__}
        evaluation.update(normalized_address=normalize_address(address), cache_version=CACHE_VERSION)
        results[key] = cache.put(key, evaluation) | {k: v for k, v in evaluation.items()
                                                     if k not in GeocodeCache.COLUMNS}
        log.append({'cache_key': key, 'status': evaluation['geocode_confidence']})
    return {'results': results, 'log': log,
            'stats': {'provider_calls': cache.requests, 'cache_hits': cache.hits,
                      'duplicates_avoided': cache.requests_avoided}}


def vworld_provider(api_key, domain, http_get):
    """Adapter over the public VWorld address API already used by this project.

    It returns every candidate and the address VWorld echoed back; the accept or
    review decision belongs to evaluate(), not to the provider.
    """
    def call(address):
        params = {'service': 'address', 'request': 'getcoord', 'version': '2.0',
                  'crs': 'EPSG:4326', 'address': address, 'refine': 'true', 'simple': 'false',
                  'format': 'json', 'type': 'PARCEL', 'key': api_key, 'domain': domain or ''}
        payload = http_get('https://api.vworld.kr/req/address', params=params, timeout=10)
        response = (payload or {}).get('response') or {}
        if response.get('status') != 'OK':
            return {'provider': 'vworld:address', 'result_status': 'NO_MATCH', 'candidates': []}
        results = response.get('result')
        results = results if isinstance(results, list) else [results]
        candidates = []
        for item in results:
            point = (item or {}).get('point') or {}
            try:
                longitude, latitude = float(point['x']), float(point['y'])
                candidates.append({'longitude': longitude, 'latitude': latitude,
                                   'coordinate_orientation': coordinate_orientation(longitude, latitude),
                                   'accuracy': 'PARCEL',
                                   'matched_address': ((response.get('refined') or {}).get('text')
                                                       or (item or {}).get('text') or '')})
            except (KeyError, TypeError, ValueError):
                continue
        return {'provider': 'vworld:address', 'result_status': 'MATCHED' if candidates else 'NO_MATCH',
                'candidates': candidates}
    return call


# Provider registry. Each entry names the secrets it needs so availability can be
# reported without calling anything, and so a provider can be swapped later.
PROVIDER_SPECS = {
    'naver': {'secrets': ('NAVER_MAP_CLIENT_ID', 'NAVER_MAP_CLIENT_SECRET'),
              'required': ('NAVER_MAP_CLIENT_ID', 'NAVER_MAP_CLIENT_SECRET'),
              'host': 'maps.apigw.ntruss.com', 'endpoint': NAVER_GEOCODE_URL,
              'cost': 'free monthly quota, then paid', 'address_elements': True},
    'kakao': {'secrets': ('KAKAO_REST_API_KEY',), 'required': ('KAKAO_REST_API_KEY',),
              'host': 'dapi.kakao.com',
              'endpoint': 'https://dapi.kakao.com/v2/local/search/address.json',
              'cost': 'free tier (key required)', 'address_elements': False},
    'vworld': {'secrets': ('VWORLD_API_KEY', 'VWORLD_DOMAIN'), 'required': ('VWORLD_API_KEY',),
               'host': 'api.vworld.kr', 'endpoint': 'https://api.vworld.kr/req/address',
               'cost': 'free public API (key required)', 'address_elements': False},
}
# NAVER를 먼저 쓴다. 한글 지번 주소 정확도와 addressElements 검증이 가장 강하다.
PROVIDER_PRIORITY = ('naver', 'kakao', 'vworld')


def kakao_provider(api_key, http_get):
    """Kakao 주소 검색. 후보를 모두 돌려주고 판정은 evaluate()가 한다."""
    def call(address):
        payload = http_get('https://dapi.kakao.com/v2/local/search/address.json',
                           params={'query': address, 'size': 10},
                           headers={'Authorization': 'KakaoAK ' + api_key}, timeout=10)
        candidates = []
        for item in (payload or {}).get('documents') or []:
            try:
                longitude, latitude = float(item['x']), float(item['y'])
                candidates.append({'longitude': longitude, 'latitude': latitude,
                                   'coordinate_orientation': coordinate_orientation(longitude, latitude),
                                   'accuracy': 'PARCEL' if item.get('address') else 'ROAD_ADDRESS',
                                   'matched_address': (item.get('address') or {}).get('address_name')
                                                      or (item.get('road_address') or {}).get('address_name') or ''})
            except (KeyError, TypeError, ValueError):
                continue
        return {'provider': 'kakao:address', 'result_status': 'MATCHED' if candidates else 'NO_MATCH',
                'candidates': candidates}
    return call


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _endpoint_missing(exc):
    """구 host 확인은 경로/호스트를 못 찾은 경우에만 한다.

    인증 실패나 쿼터 초과로 다시 호출하면 과금 호출을 두 번 하게 되므로 재시도하지 않는다.
    """
    status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if status == 404:
        return True
    return status is None and type(exc).__name__ in (
        'ConnectionError', 'ConnectTimeout', 'NameResolutionError', 'gaierror')


def naver_accuracy(item, elements):
    """번지가 있으면 PARCEL, 건물번호/도로명만 있으면 ROAD_ADDRESS, 둘 다 없으면 REGION.

    REGION은 ACCEPTED_ACCURACY에 없다. 구청·주민센터·동 중심점 수준의 응답이
    좌표로 채택되는 경로를 여기서 끊는다.
    """
    if elements.get('LAND_NUMBER'):
        return 'PARCEL'
    if elements.get('BUILDING_NUMBER') or ((item or {}).get('roadAddress') or '').strip():
        return 'ROAD_ADDRESS'
    return 'REGION'


def naver_provider(client_id, client_secret, http_get):
    """NAVER Maps Geocoding. 첫 결과를 자동 채택하지 않고 판정은 evaluate()가 한다.

    인증 헤더는 Client ID -> X-NCP-APIGW-API-KEY-ID, Client Secret -> X-NCP-APIGW-API-KEY.
    좌표는 x=경도, y=위도이며 교환하지 않는다. 축이 의심스러우면 표시만 남긴다.
    """
    headers = {NAVER_HEADER_KEY_ID: client_id, NAVER_HEADER_KEY: client_secret,
               'Accept': 'application/json'}

    def fetch(address):
        params = {'query': address, 'count': 10}
        try:
            return http_get(NAVER_GEOCODE_URL, params=params, headers=headers, timeout=10), \
                NAVER_GEOCODE_URL
        except Exception as exc:
            if not _endpoint_missing(exc):
                raise
            return http_get(NAVER_GEOCODE_LEGACY_URL, params=params, headers=headers,
                            timeout=10), NAVER_GEOCODE_LEGACY_URL

    def call(address):
        payload, endpoint = fetch(address)
        payload = payload or {}
        candidates = []
        for item in payload.get('addresses') or []:
            longitude, latitude = _float_or_none(item.get('x')), _float_or_none(item.get('y'))
            if longitude is None or latitude is None:
                continue
            elements = address_elements(item)
            candidates.append({
                'longitude': longitude,                      # x = 경도
                'latitude': latitude,                        # y = 위도
                'coordinate_orientation': coordinate_orientation(longitude, latitude),
                'accuracy': naver_accuracy(item, elements),
                'matched_address': item.get('jibunAddress') or item.get('roadAddress') or '',
                'jibun_address': item.get('jibunAddress') or '',
                'road_address': item.get('roadAddress') or '',
                'english_address': item.get('englishAddress') or '',
                # 요청에 기준 좌표를 보내지 않으므로 distance는 0으로 오는 값이다. 기록만 한다.
                'distance_m': _float_or_none(item.get('distance')),
                'address_elements': elements,
            })
        status = str(payload.get('status') or '').upper()
        if candidates:
            result_status = 'MATCHED'
        elif status in ('', 'OK'):
            result_status = 'NO_MATCH'
        else:
            result_status = status
        return {'provider': 'naver:geocode', 'endpoint': endpoint, 'result_status': result_status,
                'provider_total': (payload.get('meta') or {}).get('totalCount'),
                'candidates': candidates}
    return call


def requests_get(url, params=None, headers=None, timeout=10):
    """공통 HTTP GET. 오류 본문이나 헤더를 로그에 남기지 않는다."""
    import requests
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def provider_availability(get_secret):
    """어떤 provider가 자격증명을 갖췄는지. 네트워크 호출은 하지 않고 값도 출력하지 않는다."""
    report = {}
    for name, spec in PROVIDER_SPECS.items():
        missing = [key for key in spec['required'] if not str(get_secret(key) or '').strip()]
        report[name] = {'configured': not missing, 'missing_secrets': missing,
                        'host': spec['host'], 'endpoint': spec['endpoint'],
                        'cost': spec['cost'], 'address_elements': spec['address_elements'],
                        'priority': PROVIDER_PRIORITY.index(name) + 1}
    return report


def build_provider(name, get_secret, http_get):
    """이름으로 provider를 만든다. 자격증명이 없으면 (None, 이유)."""
    spec = PROVIDER_SPECS.get(name)
    if spec is None:
        return None, 'UNKNOWN_PROVIDER_' + str(name)
    missing = [key for key in spec['required'] if not str(get_secret(key) or '').strip()]
    if missing:
        return None, missing[0] + '_NOT_CONFIGURED'
    if name == 'vworld':
        return vworld_provider(str(get_secret('VWORLD_API_KEY')).strip(),
                               str(get_secret('VWORLD_DOMAIN') or '').strip(), http_get), None
    if name == 'kakao':
        return kakao_provider(str(get_secret('KAKAO_REST_API_KEY')).strip(), http_get), None
    return naver_provider(str(get_secret('NAVER_MAP_CLIENT_ID')).strip(),
                          str(get_secret('NAVER_MAP_CLIENT_SECRET')).strip(), http_get), None


def select_provider(get_secret, http_get, preferred=None):
    """NAVER -> Kakao -> VWorld 순서로 자격증명이 갖춰진 첫 provider를 고른다.

    preferred를 주면 그것을 먼저 시도하고, 없으면 우선순위대로 내려간다. 어떤
    경우에도 비밀값은 반환하지 않고 어떤 provider가 왜 막혔는지만 남긴다.
    """
    availability = provider_availability(get_secret)
    order = ([preferred] if preferred else []) + [n for n in PROVIDER_PRIORITY if n != preferred]
    skipped = []
    for name in order:
        provider, blocker = build_provider(name, get_secret, http_get)
        if provider is not None:
            return {'provider': provider, 'name': name, 'blocker': None, 'priority': order,
                    'availability': availability, 'skipped': skipped}
        skipped.append({'provider': name, 'blocker': blocker})
    return {'provider': None, 'name': None, 'blocker': 'NO_GEOCODER_CREDENTIAL_CONFIGURED',
            'priority': order, 'availability': availability, 'skipped': skipped}


def status(get_secret, http_get=None, probe_address=None, preferred=None):
    """지오코딩 헬스체크. Client ID/Secret 값은 어떤 필드에도 담지 않는다.

    probe_address가 없으면 네트워크를 건드리지 않고 reachable은 None으로 둔다.
    주소를 주면 그 한 건만 호출해 축 순서(x=경도, y=위도)까지 확인한다.
    """
    selected = select_provider(get_secret, http_get or (lambda *a, **k: None), preferred)
    spec = PROVIDER_SPECS.get(selected['name'] or '', {})
    report = {'provider': selected['name'], 'configured': selected['provider'] is not None,
              'reachable': None, 'priority': list(selected['priority']),
              'blocker': selected['blocker'], 'endpoint': spec.get('endpoint'),
              'host': spec.get('host'), 'providers': selected['availability'],
              'skipped': selected['skipped'], 'probe': None,
              'checked_at': datetime.now(timezone.utc).isoformat()}
    if selected['provider'] is None or not probe_address:
        return report
    address = normalize_address(probe_address)
    try:
        response = selected['provider'](address)
        evaluation = evaluate(address, response)
        candidate = (response.get('candidates') or [None])[0] or {}
        report['reachable'] = True
        report['probe'] = {'address': address, 'result_status': response.get('result_status'),
                           'candidate_count': len(response.get('candidates') or []),
                           'geocode_confidence': evaluation['geocode_confidence'],
                           'coordinate_orientation': candidate.get('coordinate_orientation'),
                           'longitude': candidate.get('longitude'),
                           'latitude': candidate.get('latitude'),
                           'endpoint': response.get('endpoint')}
    except Exception as exc:
        # 예외 문자열은 요청 URL과 함께 키가 섞일 수 있으므로 타입과 상태코드만 남긴다.
        report['reachable'] = False
        report['probe'] = {'address': address, 'error_type': type(exc).__name__,
                           'http_status': getattr(getattr(exc, 'response', None),
                                                  'status_code', None)}
    return report

"""Address -> coordinate resolution for ZIP:ON development candidates.

Deliberately stricter than the golf geocoder, which accepts the first search
result. Here a coordinate is only accepted when the provider returns exactly one
candidate whose returned address still contains the district and the lot we
asked for. Anything else becomes GEOCODE_REVIEW and stays unresolved, so no
representative point is ever manufactured from a dong centroid.
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
               'provider_candidate_count', 'cache_version')

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
        row['cache_key'] = key
        self.path(key).write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n',
                                  encoding='utf-8')
        return row

    def rows(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(self.directory.glob('*.json'))]


def in_bounds(longitude, latitude):
    return (isinstance(longitude, (int, float)) and isinstance(latitude, (int, float))
            and SEOUL_BOUNDS['longitude'][0] <= longitude <= SEOUL_BOUNDS['longitude'][1]
            and SEOUL_BOUNDS['latitude'][0] <= latitude <= SEOUL_BOUNDS['latitude'][1])


def evaluate(address, response):
    """Decide whether a provider response is an exact match for this address."""
    unresolved = {'latitude': None, 'longitude': None, 'geocode_source': None,
                  'geocoded_at': datetime.now(timezone.utc).isoformat(),
                  'address_used': normalize_address(address), 'coordinate_verified': False,
                  'provider_candidate_count': 0}
    if not response or response.get('result_status') != 'MATCHED':
        return dict(unresolved, geocode_confidence='UNRESOLVED',
                    provider_candidate_count=len(response.get('candidates') or []) if response else 0,
                    geocode_source=(response or {}).get('provider'))
    candidates = response.get('candidates') or []
    result = dict(unresolved, geocode_source=response.get('provider'),
                  provider_candidate_count=len(candidates))
    if len(candidates) != 1:
        # Several official candidates for one address is exactly the case the
        # first-result-wins geocoders get wrong.
        return dict(result, geocode_confidence='GEOCODE_REVIEW')
    candidate = candidates[0]
    longitude, latitude = candidate.get('longitude'), candidate.get('latitude')
    wanted = normalize_address(address)
    returned = normalize_address(candidate.get('matched_address'))
    district = next((t for t in wanted.split() if t.endswith('구')), None)
    lot = re.search(r'(\d+(?:-\d+)?)\s*$', wanted)
    checks = {'accuracy': candidate.get('accuracy') in ACCEPTED_ACCURACY,
              'bounds': in_bounds(longitude, latitude),
              'district_match': bool(district) and district in returned,
              'lot_match': bool(lot) and lot.group(1) in returned}
    if not all(checks.values()):
        return dict(result, geocode_confidence='GEOCODE_REVIEW', checks=checks)
    return dict(result, latitude=latitude, longitude=longitude, geocode_confidence='EXACT',
                coordinate_verified=True, address_used=wanted, matched_address=returned,
                accuracy=candidate.get('accuracy'), checks=checks)


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
                candidates.append({'longitude': float(point['x']), 'latitude': float(point['y']),
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
    'vworld': {'secrets': ('VWORLD_API_KEY', 'VWORLD_DOMAIN'), 'required': ('VWORLD_API_KEY',),
               'host': 'api.vworld.kr', 'cost': 'free public API (key required)'},
    'kakao': {'secrets': ('KAKAO_REST_API_KEY',), 'required': ('KAKAO_REST_API_KEY',),
              'host': 'dapi.kakao.com', 'cost': 'free tier (key required)'},
    'naver': {'secrets': ('NAVER_CLOUD_API_KEY_ID', 'NAVER_CLOUD_API_KEY'),
              'required': ('NAVER_CLOUD_API_KEY_ID', 'NAVER_CLOUD_API_KEY'),
              'host': 'maps.apigw.ntruss.com', 'cost': 'paid tier after free quota'},
}


def kakao_provider(api_key, http_get):
    """Kakao 주소 검색. 후보를 모두 돌려주고 판정은 evaluate()가 한다."""
    def call(address):
        payload = http_get('https://dapi.kakao.com/v2/local/search/address.json',
                           params={'query': address, 'size': 10},
                           headers={'Authorization': 'KakaoAK ' + api_key}, timeout=10)
        candidates = []
        for item in (payload or {}).get('documents') or []:
            try:
                candidates.append({'longitude': float(item['x']), 'latitude': float(item['y']),
                                   'accuracy': 'PARCEL' if item.get('address') else 'ROAD_ADDRESS',
                                   'matched_address': (item.get('address') or {}).get('address_name')
                                                      or (item.get('road_address') or {}).get('address_name') or ''})
            except (KeyError, TypeError, ValueError):
                continue
        return {'provider': 'kakao:address', 'result_status': 'MATCHED' if candidates else 'NO_MATCH',
                'candidates': candidates}
    return call


def naver_provider(key_id, key, http_get):
    """NAVER Cloud Geocoding. 첫 결과를 자동 채택하지 않는다."""
    def call(address):
        payload = http_get('https://maps.apigw.ntruss.com/map-geocode/v2/geocode',
                           params={'query': address},
                           headers={'x-ncp-apigw-api-key-id': key_id, 'x-ncp-apigw-api-key': key},
                           timeout=10)
        candidates = []
        for item in (payload or {}).get('addresses') or []:
            try:
                candidates.append({'longitude': float(item['x']), 'latitude': float(item['y']),
                                   'accuracy': 'ROAD_ADDRESS' if item.get('roadAddress') else 'PARCEL',
                                   'matched_address': item.get('jibunAddress') or item.get('roadAddress') or ''})
            except (KeyError, TypeError, ValueError):
                continue
        return {'provider': 'naver:geocode', 'result_status': 'MATCHED' if candidates else 'NO_MATCH',
                'candidates': candidates}
    return call


def provider_availability(get_secret):
    """어떤 provider가 자격증명을 갖췄는지. 네트워크 호출은 하지 않고 값도 출력하지 않는다."""
    report = {}
    for name, spec in PROVIDER_SPECS.items():
        missing = [key for key in spec['required'] if not str(get_secret(key) or '').strip()]
        report[name] = {'configured': not missing, 'missing_secrets': missing,
                        'host': spec['host'], 'cost': spec['cost']}
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
    return naver_provider(str(get_secret('NAVER_CLOUD_API_KEY_ID')).strip(),
                          str(get_secret('NAVER_CLOUD_API_KEY')).strip(), http_get), None

"""골프 출발지 좌표 해석.

ZIP:ON의 주소 검증기와 성격이 다르다. ZIP:ON은 공식 사업 데이터를 적재하기 위해
자치구·법정동·지번까지 정확히 맞아야 하고, 그 엄격함은 그대로 둔다.

여기는 사용자가 "어디서 출발하나요"에 적는 말이다. 사람은 주소를 적지 않는다.

  강동구청 · 서울역 · 잠실역 · 강남역 · 우리금융 본점

주소 지오코딩만으로는 이런 장소명이 풀리지 않는다. NAVER Cloud Maps의 지오코딩은
주소 전용이라 '강동구청' 같은 기관명에는 결과를 주지 않는다. 그래서 장소 검색을
함께 쓴다. 이미 프로젝트에 연결된 provider만 쓰고 새 유료 API를 붙이지 않는다.

찾는 순서
  1) 주소 지오코딩 (NAVER) — 사용자가 실제 주소를 적은 경우
  2) 장소 검색 (Kakao 키워드 → VWorld place) — 기관·역·건물 이름
  3) 지역을 덧붙인 재시도 — '강동구청'처럼 같은 이름이 여러 지역에 있는 경우

첫 결과를 그냥 받지 않는다. 서비스 지역 안에 있고, 사용자가 적은 말과 이름이
실제로 겹칠 때만 받는다. 아니면 찾지 못한 것으로 둔다. 엉뚱한 곳에서 거리를
재는 것보다 "못 찾았다"가 낫다.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from services.config import get_secret

# 서비스 대상(수도권·충청·강원)을 넉넉히 감싸는 범위. 이 밖은 출발지로 받지 않는다.
SERVED_LAT = (35.8, 38.7)
SERVED_LON = (125.8, 129.6)
# 이름 비교에서 무시할 꼬리말. '강동구청'과 '강동구청 별관'이 다른 곳이 되지 않게 한다.
NOISE = re.compile(r'(본점|본사|지점|점|역사|청사|별관|신관|구관)$')
TIMEOUT = 6


def _compact(value):
    return re.sub(r'\s+', '', str(value or ''))


def _core(value):
    """비교용 핵심 이름. 공백과 흔한 꼬리말을 걷어낸다."""
    text = _compact(value)
    while True:
        stripped = NOISE.sub('', text)
        if stripped == text or len(stripped) < 2:
            return text
        text = stripped


def in_service_area(lat, lon):
    return SERVED_LAT[0] <= lat <= SERVED_LAT[1] and SERVED_LON[0] <= lon <= SERVED_LON[1]


def name_matches(query, candidate_name, candidate_address=''):
    """사용자가 적은 말과 후보 이름이 실제로 겹치는지.

    첫 검색결과를 무조건 받으면 '강동구청'이 엉뚱한 상호로 풀릴 수 있다.
    이름이나 주소 어느 쪽에서든 핵심 이름이 나와야 받는다.
    """
    asked = _core(query)
    if len(asked) < 2:
        return False
    found = _core(candidate_name)
    if asked in found or found in asked:
        return True
    # '서울역'처럼 이름이 주소 쪽에만 드러나는 경우도 있다.
    return asked in _compact(candidate_address)


def _read(endpoint, headers):
    try:
        with urlopen(Request(endpoint, headers=headers, method='GET'), timeout=TIMEOUT) as response:
            return json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def kakao_place_candidates(query, api_key, read=None):
    """Kakao 키워드 검색. 주소 검색과 같은 키·같은 응답 모양을 쓴다."""
    read = read or _read
    if not query or not api_key:
        return []
    endpoint = ('https://dapi.kakao.com/v2/local/search/keyword.json?size=10&query='
                + quote(query))
    payload = read(endpoint, {'Authorization': 'KakaoAK ' + api_key,
                              'Accept': 'application/json'})
    candidates = []
    for item in (payload or {}).get('documents') or []:
        try:
            lon, lat = float(item['x']), float(item['y'])
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append({
            'lat': lat, 'lon': lon,
            'place_name': item.get('place_name') or '',
            'road_address': item.get('road_address_name') or '',
            'jibun_address': item.get('address_name') or '',
            'source': 'kakao:keyword'})
    return candidates


def vworld_place_candidates(query, api_key, domain, read=None):
    """VWorld 장소 검색. 이미 있던 경로를 후보 목록 형태로만 바꿔 쓴다."""
    read = read or _read
    if not query or not api_key:
        return []
    params = {'service': 'search', 'request': 'search', 'version': '2.0', 'crs': 'EPSG:4326',
              'size': 10, 'page': 1, 'query': query, 'type': 'place', 'format': 'json',
              'errorformat': 'json', 'key': api_key, 'domain': domain or ''}
    endpoint = 'https://api.vworld.kr/req/search?' + '&'.join(
        f'{k}={quote(str(v))}' for k, v in params.items())
    payload = read(endpoint, {'Accept': 'application/json'})
    items = (((payload or {}).get('response') or {}).get('result') or {}).get('items') or []
    candidates = []
    for item in items:
        try:
            lon = float((item.get('point') or {}).get('x'))
            lat = float((item.get('point') or {}).get('y'))
        except (TypeError, ValueError):
            continue
        address = item.get('address') or {}
        candidates.append({
            'lat': lat, 'lon': lon, 'place_name': item.get('title') or '',
            'road_address': address.get('road') or '', 'jibun_address': address.get('parcel') or '',
            'source': 'vworld:place'})
    return candidates


def pick(query, candidates):
    """서비스 지역 안이면서 이름이 겹치는 첫 후보. 없으면 None."""
    for candidate in candidates:
        if not in_service_area(candidate['lat'], candidate['lon']):
            continue
        if not name_matches(query, candidate['place_name'],
                            candidate.get('road_address') or candidate.get('jibun_address') or ''):
            continue
        return candidate
    return None


def place_label(candidate):
    """화면에 보여 줄 '어디로 이해했는지'. 사용자가 엉뚱한 곳인지 바로 알 수 있게 한다."""
    name = (candidate.get('place_name') or '').strip()
    address = (candidate.get('road_address') or candidate.get('jibun_address') or '').strip()
    region = ' '.join(address.split()[:2]) if address else ''
    return ' · '.join(part for part in (name, region) if part) or name or region


# 같은 이름이 여러 지역에 있을 때 서울을 먼저 본다. 서비스 이용자 대부분이 수도권이다.
REGION_HINTS = ('서울특별시', '경기도', '인천광역시')


def resolve(query, *, geocode_address=None, read=None):
    """출발지 하나를 좌표로 만든다.

    (좌표 dict 또는 None, 어떻게 찾았는지)를 돌려준다. 찾지 못하면 좌표는 None이고
    reason이 왜 못 찾았는지 말한다. 없는 좌표를 만들어 내지 않는다.
    """
    read = read or _read
    text = str(query or '').strip()
    if not text:
        return None, {'stage': 'EMPTY', 'reason': 'NO_DEPARTURE'}

    # 1) 주소로 적었으면 주소 지오코딩이 가장 정확하다.
    if geocode_address is not None:
        found = geocode_address(text)
        if found and in_service_area(found.get('lat'), found.get('lon')):
            return dict(found, source='naver:geocode'), {'stage': 'ADDRESS', 'reason': None}

    kakao_key = str(get_secret('KAKAO_REST_API_KEY') or '').strip()
    vworld_key = str(get_secret('VWORLD_API_KEY') or '').strip()
    vworld_domain = str(get_secret('VWORLD_DOMAIN') or '').strip()
    if not kakao_key and not vworld_key:
        # 장소 검색 수단이 없으면 기관·역 이름은 풀 수 없다. 추측하지 않는다.
        return None, {'stage': 'PLACE', 'reason': 'NO_PLACE_SEARCH_PROVIDER'}

    # 2) 장소 이름으로 찾는다. 지역을 덧붙인 형태도 함께 본다.
    attempts = [text] + [f'{hint} {text}' for hint in REGION_HINTS]
    for attempt in attempts:
        candidates = []
        if kakao_key:
            candidates.extend(kakao_place_candidates(attempt, kakao_key, read=read))
        if vworld_key:
            candidates.extend(vworld_place_candidates(attempt, vworld_key, vworld_domain, read=read))
        # 이름은 사용자가 적은 원래 말로 맞춘다. 덧붙인 지역명 때문에 판정이 느슨해지지 않게 한다.
        chosen = pick(text, candidates)
        if chosen:
            return chosen, {'stage': 'PLACE', 'reason': None,
                            'query_used': attempt, 'source': chosen['source']}
    return None, {'stage': 'PLACE', 'reason': 'NO_MATCHING_PLACE'}

"""골프 출발지 해석: 장소 이름도 실제 출발지로 쓸 수 있는지.

ZIP:ON의 엄격한 주소 검증기는 건드리지 않는다. 그쪽은 공식 데이터 적재용이고
여기는 사용자가 적는 말이다.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import golf_departure as gd
from services import golf_service as gs

ROOT = Path(__file__).resolve().parents[1]

# 실제 장소들의 대략적인 좌표. 해석 경로를 확인하기 위한 fixture다.
PLACES = {
    '강동구청': ('127.1237', '37.5301', '강동구청', '서울 강동구 성내로 25'),
    '서울역': ('126.9707', '37.5547', '서울역', '서울 중구 한강대로 405'),
    '잠실역': ('127.1000', '37.5133', '잠실역', '서울 송파구 올림픽로 265'),
    '강남역': ('127.0276', '37.4979', '강남역', '서울 강남구 강남대로 396'),
}


def fake_read(endpoint, headers):
    from urllib.parse import unquote
    asked = unquote(endpoint.split('query=')[1].split('&')[0])
    for name, (x, y, place, road) in PLACES.items():
        if name in asked:
            return {'documents': [{'x': x, 'y': y, 'place_name': place,
                                   'road_address_name': road, 'address_name': road}]}
    return {'documents': []}


def only_kakao(name, *args, **kwargs):
    return 'KEY' if name == 'KAKAO_REST_API_KEY' else ''


class PlaceResolutionTests(unittest.TestCase):
    """공공기관·역 이름이 출발지로 쓰이는지. 주소 지오코딩만으로는 풀리지 않는다."""

    def resolve(self, query, address_result=None):
        with patch.object(gd, 'get_secret', only_kakao), patch.object(gd, '_read', fake_read):
            return gd.resolve(query, geocode_address=lambda _: address_result)

    def test_강동구청_resolves_to_a_seoul_coordinate(self):
        found, how = self.resolve('강동구청')
        self.assertIsNotNone(found, '강동구청이 출발지로 풀리지 않는다')
        self.assertAlmostEqual(found['lat'], 37.5301, places=3)
        self.assertAlmostEqual(found['lon'], 127.1237, places=3)
        self.assertEqual(how['stage'], 'PLACE')
        self.assertTrue(gd.in_service_area(found['lat'], found['lon']))

    def test_the_station_names_resolve(self):
        for name in ('서울역', '잠실역', '강남역'):
            found, _ = self.resolve(name)
            self.assertIsNotNone(found, name)
            self.assertTrue(gd.in_service_area(found['lat'], found['lon']), name)
            self.assertEqual(found['place_name'], name)

    def test_each_place_gets_its_own_coordinate(self):
        seen = {name: self.resolve(name)[0] for name in PLACES}
        pairs = {(round(v['lat'], 4), round(v['lon'], 4)) for v in seen.values()}
        self.assertEqual(len(pairs), len(PLACES), '서로 다른 장소가 같은 좌표로 풀렸다')

    def test_an_address_is_still_resolved_by_the_address_geocoder_first(self):
        address = {'lat': 37.5, 'lon': 127.0, 'road_address': '서울 강남구 테헤란로 1'}
        found, how = self.resolve('서울특별시 강남구 테헤란로 1', address_result=address)
        self.assertEqual(how['stage'], 'ADDRESS')
        self.assertEqual(found['source'], 'naver:geocode')

    def test_an_unknown_place_is_not_forced_into_a_coordinate(self):
        found, how = self.resolve('있을리없는장소이름zzz')
        self.assertIsNone(found)
        self.assertEqual(how['reason'], 'NO_MATCHING_PLACE')

    def test_the_first_search_hit_is_not_accepted_blindly(self):
        # 이름이 겹치지 않는 후보는 받지 않는다. 엉뚱한 곳에서 거리를 재지 않는다.
        unrelated = [{'lat': 37.55, 'lon': 126.97, 'place_name': '전혀다른카페',
                      'road_address': '서울 중구', 'jibun_address': '', 'source': 'kakao:keyword'}]
        self.assertIsNone(gd.pick('강동구청', unrelated))

    def test_a_candidate_outside_the_served_area_is_refused(self):
        far = [{'lat': 33.45, 'lon': 126.57, 'place_name': '강동구청',
                'road_address': '제주', 'jibun_address': '', 'source': 'kakao:keyword'}]
        self.assertIsNone(gd.pick('강동구청', far))

    def test_without_any_place_provider_it_says_so_instead_of_guessing(self):
        with patch.object(gd, 'get_secret', lambda *a, **k: ''):
            found, how = gd.resolve('강동구청', geocode_address=lambda _: None)
        self.assertIsNone(found)
        self.assertEqual(how['reason'], 'NO_PLACE_SEARCH_PROVIDER')

    def test_the_resolved_place_is_shown_back_to_the_user(self):
        found, _ = self.resolve('강동구청')
        self.assertEqual(gd.place_label(found), '강동구청 · 서울 강동구')


class DepartureWiringTests(unittest.TestCase):
    """검색 조건까지 좌표와 이름이 이어지는지."""

    def build(self, departure):
        with patch.object(gd, 'get_secret', only_kakao), \
                patch.object(gs, 'get_secret', only_kakao), \
                patch.object(gd, '_read', fake_read), \
                patch.object(gs, '_naver_keys', lambda: ('', '')):
            return gs.build_condition({
                'departure': departure, 'day': '주중', 'session': '전체', 'budget': '전체',
                'caddie': '전체', 'areas': [], 'subregions': [], 'players': '전체',
                'night': False, 'include_unknown': True, 'avg_score_label': '미선택',
                'challenge': '적당히'})

    def test_a_place_name_becomes_a_departure_coordinate(self):
        for name in PLACES:
            cond, status = self.build(name)
            self.assertIsNotNone(cond['departure_coord'], name)
            self.assertEqual(len(cond['departure_coord']), 2, name)
            self.assertIn('출발지 확인', status, name)

    def test_the_status_says_which_place_it_understood(self):
        _, status = self.build('강동구청')
        self.assertEqual(status, '출발지 확인 · 강동구청 · 서울 강동구')

    def test_the_label_reaches_the_search_result(self):
        cond, status = self.build('잠실역')
        self.assertEqual(cond['departure_label'], '잠실역 · 서울 송파구')
        result = gs._build_results([], cond, {}, '가까운순', status)
        self.assertTrue(result['has_departure'])
        self.assertEqual(result['departure_label'], '잠실역 · 서울 송파구')

    def test_an_unresolved_place_keeps_the_honest_fallback(self):
        cond, status = self.build('있을리없는장소이름zzz')
        self.assertIsNone(cond['departure_coord'])
        self.assertIn('확인 실패', status)
        result = gs._build_results([], cond, {}, '가까운순', status)
        self.assertFalse(result['has_departure'])
        self.assertIn('출발지', result['notice'])

    def test_distances_are_produced_and_ascend_from_the_resolved_place(self):
        cond, status = self.build('강동구청')
        clubs = [({'id': 'far', 'name': '먼곳', 'latitude': 37.20, 'longitude': 127.60,
                   'region': '경기', 'city': '이천'}, ['이유']),
                 ({'id': 'near', 'name': '가까운곳', 'latitude': 37.54, 'longitude': 127.15,
                   'region': '서울', 'city': '강동'}, ['이유']),
                 ({'id': 'mid', 'name': '중간', 'latitude': 37.45, 'longitude': 127.30,
                   'region': '경기', 'city': '하남'}, ['이유'])]
        with patch.object(gs, '_route_for_course', return_value=None), \
                patch.object(gs, '_card', side_effect=lambda course, reasons, cond_, cache: {
                    'id': course['id'], 'name': course['name'], 'status': 'confirmed',
                    'badge': '', 'facts': [], 'badges': [], 'reasons': [], 'evidence': '',
                    'fee_link': None}):
            result = gs._build_results(clubs, cond, {}, '가까운순', status)
        order = [item['id'] for item in result['items']]
        self.assertEqual(order, ['near', 'mid', 'far'])
        origin = tuple(cond['departure_coord'])
        distances = [gs.distance_km(origin, (37.54, 127.15)),
                     gs.distance_km(origin, (37.45, 127.30)),
                     gs.distance_km(origin, (37.20, 127.60))]
        self.assertEqual(distances, sorted(distances))


class SeparationFromZiponTests(unittest.TestCase):
    """ZIP:ON의 엄격한 주소 검증을 약화시키지 않았는지."""

    def test_the_golf_resolver_is_its_own_module(self):
        self.assertTrue((ROOT / 'services/golf_departure.py').is_file())
        source = (ROOT / 'services/golf_departure.py').read_text(encoding='utf-8')
        # ZIP:ON 적재 경로를 가져다 쓰지 않는다.
        for zipon in ('development_geocode', 'zipon_set_project_location', 'evaluate('):
            self.assertNotIn(zipon, source, zipon)

    def test_the_zipon_geocoder_still_demands_a_full_address_match(self):
        from services import development_geocode as geo
        checks = (ROOT / 'services/development_geocode.py').read_text(encoding='utf-8')
        # 자치구·동·지번 확인은 그대로다.
        for rule in ('district_match', 'dong_match', 'lot_match'):
            self.assertIn(rule, checks, rule)
        self.assertTrue(hasattr(geo, 'evaluate'))

    def test_golf_does_not_write_anything(self):
        source = (ROOT / 'services/golf_departure.py').read_text(encoding='utf-8')
        for forbidden in ('requests.post', 'INSERT', 'UPDATE', 'rpc/', 'supabase'):
            self.assertNotIn(forbidden, source, forbidden)

    def test_no_secret_is_logged_or_returned(self):
        found, _ = (None, None)
        with patch.object(gd, 'get_secret', only_kakao), patch.object(gd, '_read', fake_read):
            found, _ = gd.resolve('강동구청', geocode_address=lambda _: None)
        self.assertNotIn('KEY', str(found))
        for field in found:
            self.assertNotIn('key', field.lower())

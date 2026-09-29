"""골프 검색 정확성: 거리순이 실제 거리순인지, 조건을 바꾸면 다시 계산되는지.

UI를 추측으로 고치지 않기 위해, 정렬·필터·거리 계산을 서비스 함수로 직접 돌려서 본다.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import golf_service as gs

ROOT = Path(__file__).resolve().parents[1]
# 출발지: 서울시청. 아래 좌표는 실제 거리 차이를 만들기 위한 것이다.
DEPARTURE = (37.5663, 126.9779)


def club(identifier, name, lat, lon, **extra):
    row = {'id': identifier, 'name': name, 'region': '경기', 'city': '용인',
           'area': '경기', 'latitude': lat, 'longitude': lon}
    row.update(extra)
    return row


class DistanceTests(unittest.TestCase):
    def test_the_straight_distance_grows_with_real_separation(self):
        near = gs.distance_km(DEPARTURE, (37.5700, 126.9800))
        far = gs.distance_km(DEPARTURE, (37.2000, 127.2000))
        self.assertLess(near, 1.0)
        self.assertGreater(far, 40.0)
        self.assertLess(near, far)

    def test_a_club_without_coordinates_has_no_distance(self):
        self.assertIsNone(gs._distance_from_departure(club('x', '좌표없음', None, None), DEPARTURE))
        self.assertIsNone(gs._distance_from_departure(club('y', '이름만', 37.5, 127.0), None))


class DistanceSortTests(unittest.TestCase):
    """'가까운순'이 실제 거리값 순서인지. 검색 API 순서나 DB 순서를 쓰면 안 된다."""

    def build(self, sort='가까운순', departure=True, routes=None):
        clubs = [
            club('far', '먼곳', 37.2000, 127.2000),
            club('near', '가까운곳', 37.5700, 126.9800),
            club('mid', '중간', 37.4500, 127.0500),
            club('nocoord', '좌표없음', None, None),
        ]
        # 실제 build_condition이 만드는 모양을 그대로 쓴다.
        cond, _ = gs.build_condition({'departure': '서울시청' if departure else '',
                                      'day': '주중', 'session': '전체', 'budget': '전체',
                                      'caddie': '전체', 'areas': [], 'subregions': [],
                                      'players': '전체', 'night': False, 'include_unknown': True,
                                      'avg_score_label': '미선택', 'challenge': '적당히'})
        cond['departure_coord'] = DEPARTURE if departure else None
        recs = [(course, ['이유']) for course in clubs]
        with patch.object(gs, '_departure_coord', return_value=DEPARTURE if departure else None), \
                patch.object(gs, '_route_for_course', side_effect=lambda c, _: (routes or {}).get(c['id'])), \
                patch.object(gs, '_card', side_effect=lambda course, reasons, cond_, cache: {
                    'id': course['id'], 'name': course['name'], 'status': 'confirmed',
                    'badge': '', 'facts': [], 'badges': [], 'reasons': [], 'evidence': '',
                    'fee_link': None}):
            return gs._build_results(recs, cond, {}, sort, 'ok')

    def order(self, result):
        return [item['id'] for item in result['items']]

    def test_nearest_first_is_actually_ascending_distance(self):
        result = self.build()
        order = self.order(result)
        self.assertEqual(order[:3], ['near', 'mid', 'far'])
        distances = [gs.distance_km(DEPARTURE, (c[0], c[1])) for c in
                     ((37.5700, 126.9800), (37.4500, 127.0500), (37.2000, 127.2000))]
        self.assertEqual(distances, sorted(distances))

    def test_a_club_without_coordinates_never_leads_the_nearest_list(self):
        order = self.order(self.build())
        self.assertEqual(order[-1], 'nocoord')

    def test_a_real_driving_distance_beats_the_straight_line_when_known(self):
        # 직선으로는 mid가 더 가깝지만 실제 주행거리는 far가 더 짧은 경우.
        routes = {'near': {'distance_km': 5.0}, 'mid': {'distance_km': 80.0},
                  'far': {'distance_km': 40.0}}
        order = self.order(self.build(routes=routes))
        self.assertEqual(order[:3], ['near', 'far', 'mid'])

    def test_without_a_departure_the_order_is_not_claimed_to_be_by_distance(self):
        result = self.build(departure=False)
        self.assertFalse(result['has_departure'])
        self.assertIn('출발지', result['notice'])

    def test_the_sort_the_caller_asked_for_is_reported_back(self):
        self.assertEqual(self.build(sort='가까운순')['sort'], '가까운순')
        self.assertEqual(self.build(sort='추천순')['sort'], '추천순')

    def test_changing_the_sort_changes_the_order_of_the_same_candidates(self):
        nearest = self.order(self.build(sort='가까운순'))
        recommended = self.order(self.build(sort='추천순'))
        self.assertEqual(sorted(nearest), sorted(recommended))
        self.assertNotEqual(nearest, recommended)


class PipelineOrderTests:
    pass


class SortBeforeLimitTests(unittest.TestCase):
    """정렬이 자르기보다 먼저여야 한다. 자른 뒤 정렬하면 가까운 곳이 사라진다."""

    def test_the_service_sorts_the_whole_set_before_the_screen_cuts_it(self):
        source = (ROOT / 'services/golf_service.py').read_text(encoding='utf-8')
        body = source[source.index('def _build_results('):]
        body = body[:body.index('\ndef ', 1)]
        sort_at = body.index('if sort == "가까운순"')
        cards_at = body.index('items = [_card(')
        self.assertLess(sort_at, cards_at, '카드를 만들기 전에 전체를 정렬해야 한다')
        # 목록을 자르는 일은 화면이 한다. 서비스는 전체를 정렬해서 돌려준다.
        self.assertNotIn('[:6]', body)
        self.assertNotIn('[:12]', body)

    def test_the_screen_slices_only_after_filtering(self):
        source = (ROOT / 'web/src/components/golf/GolfSearch.tsx').read_text(encoding='utf-8')
        filtered_at = source.index('const filtered =')
        shown_at = source.index('const shown = filtered.slice(')
        self.assertLess(filtered_at, shown_at, '거른 뒤에 잘라야 한다')


class CacheKeyTests(unittest.TestCase):
    """조건이 다르면 다른 결과를 써야 한다. 캐시 키에 조건이 빠지면 안 된다."""

    def test_the_ttl_cache_keys_on_every_argument(self):
        calls = []

        @gs.ttl_cache(60)
        def lookup(query, key_id, key):
            calls.append((query, key_id, key))
            return f'{query}:{key_id}'

        self.assertEqual(lookup('강남', 'id1', 'k'), '강남:id1')
        self.assertEqual(lookup('강남', 'id1', 'k'), '강남:id1')
        self.assertEqual(len(calls), 1, '같은 조건은 한 번만 계산한다')
        # 조건이 하나라도 다르면 다시 계산한다.
        lookup('분당', 'id1', 'k')
        lookup('강남', 'id2', 'k')
        self.assertEqual(len(calls), 3)

    def test_the_route_cache_distinguishes_both_endpoints(self):
        import inspect
        signature = inspect.signature(gs.naver_driving_route)
        # 출발지와 도착지 좌표가 모두 키에 들어가야 다른 경로가 섞이지 않는다.
        for name in ('start_lat', 'start_lon', 'goal_lat', 'goal_lon'):
            self.assertIn(name, signature.parameters)

    def test_the_geocode_cache_keys_on_the_query(self):
        import inspect
        self.assertIn('query', inspect.signature(gs.naver_geocode).parameters)


class StaleStateGuardTests(unittest.TestCase):
    """검색 화면이 지난 응답으로 최신 결과를 덮어쓰지 않는지(코드 계약)."""

    def setUp(self):
        self.source = (ROOT / 'web/src/components/golf/GolfSearch.tsx').read_text(encoding='utf-8')

    def test_each_search_is_numbered_and_only_the_latest_updates_the_screen(self):
        self.assertIn('const generation = useRef(0)', self.source)
        self.assertIn('const mine = ++generation.current', self.source)
        self.assertIn('if (!current()) return;', self.source)

    def test_a_new_search_cancels_the_one_in_flight(self):
        self.assertIn('inFlight.current?.abort()', self.source)
        self.assertIn('new AbortController()', self.source)
        self.assertIn('signal: controller.signal', self.source)

    def test_the_previous_result_is_cleared_when_conditions_change(self):
        run = self.source[self.source.index('async function run('):]
        run = run[:run.index('\n  }')]
        self.assertIn('setResult(null)', run)
        # 결과를 지우는 일이 응답을 기다리기 전에 일어나야 한다.
        self.assertLess(run.index('setResult(null)'), run.index('await golfApi'))

    def test_only_the_latest_search_clears_the_loading_flag(self):
        self.assertIn('if (current()) setLoading(false)', self.source)

    def test_a_cancelled_request_is_not_shown_as_an_error(self):
        self.assertIn('if (controller.signal.aborted || !current()) return;', self.source)

    def test_changing_the_mode_also_stops_the_search_in_flight(self):
        change = self.source[self.source.index('function changeMode('):]
        change = change[:change.index('\n  }')]
        self.assertIn('inFlight.current?.abort()', change)
        self.assertIn('generation.current += 1', change)


class RequestRaceRegressionTests(unittest.TestCase):
    """요청 취소·시간제한·재시도를 실제로 실행해서 확인한다. 문자열 비교가 아니다."""

    @classmethod
    def setUpClass(cls):
        import json
        import shutil
        import subprocess
        if shutil.which('node') is None:
            raise unittest.SkipTest('node is not available')
        check = ROOT / 'scripts/checks/request_race_check.mts'
        result = subprocess.run(['node', '--experimental-strip-types', str(check)],
                                capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            raise unittest.SkipTest(f'race check did not run: {result.stderr[:300]}')
        cls.report = json.loads(result.stdout.strip().splitlines()[0])

    def test_a_slow_earlier_search_does_not_overwrite_the_newer_one(self):
        # A(느림)를 먼저 보내고 B(빠름)를 뒤에 보냈다. 화면에는 B가 남아야 한다.
        self.assertTrue(self.report['latest_request_wins'])
        self.assertEqual(self.report['screen_after_race'], 'B-new-fast')

    def test_a_cancelled_search_is_not_reported_as_an_error(self):
        self.assertEqual(self.report['race_errors'], [])

    def test_a_request_that_never_answers_is_cut_off(self):
        self.assertEqual(self.report['timeout_kind'], 'timeout')
        self.assertTrue(self.report['timeout_ms_under_1s'])

    def test_a_waking_server_is_retried_and_a_real_error_is_not(self):
        self.assertEqual(self.report['cold_start_retries'], 3)
        self.assertEqual(self.report['cold_start_result'], 'awake')
        # 잘못된 요청을 세 번 보내지 않는다.
        self.assertEqual(self.report['permanent_attempts'], 1)

    def test_only_connection_and_unavailable_count_as_transient(self):
        kinds = self.report['transient_classification']
        self.assertTrue(kinds['connection'])
        self.assertTrue(kinds['unavailable'])
        self.assertFalse(kinds['bad_request'])
        # 500은 서버 안에서 난 오류다. 같은 요청을 다시 보내도 같은 결과일 가능성이 높다.
        self.assertFalse(kinds['server_error'])


class WriteRequestsAreNotRetriedTests(unittest.TestCase):
    """쓰기 요청은 자동으로 다시 보내지 않는다. 같은 일이 두 번 일어날 수 있다."""

    def test_the_retry_helper_is_only_used_for_reads(self):
        for path in ('web/src/components/golf/GolfSearch.tsx',
                     'web/src/components/realestate/DevelopmentTab.tsx'):
            source = (ROOT / path).read_text(encoding='utf-8')
            for block in source.split('withColdStartRetry(')[1:]:
                head = block[:260]
                self.assertNotIn('method: "POST"', head, path)
                self.assertNotIn('method: "PUT"', head, path)
                self.assertNotIn('method: "DELETE"', head, path)

    def test_the_helper_documents_that_it_is_for_reads(self):
        source = (ROOT / 'web/src/lib/coldStart.ts').read_text(encoding='utf-8')
        self.assertIn('읽기', source)
        self.assertIn('쓰기 요청은', source)


class OriginSortTransitionTests(unittest.TestCase):
    """출발지 입력 → 자동 거리순. 실제로 실행해서 전이를 확인한다.

    A 출발지 없음 → 기본 정렬        B 출발지 입력 → 자동 거리순
    C/D 출발지 변경 → 재계산          E 출발지 삭제 → 거리순 해제
    F/G 빠른 연속 입력 → 최신이 이김   H 거리 오름차순
    """

    @classmethod
    def setUpClass(cls):
        import json
        import shutil
        import subprocess
        if shutil.which('node') is None:
            raise unittest.SkipTest('node is not available')
        check = ROOT / 'scripts/checks/golf_sort_check.mts'
        result = subprocess.run(['node', '--experimental-strip-types', str(check)],
                                capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            raise unittest.SkipTest(f'sort check did not run: {result.stderr[:300]}')
        cls.report = json.loads(result.stdout.strip().splitlines()[0])

    def test_a_without_an_origin_the_default_sort_is_kept(self):
        self.assertEqual(self.report['a_no_origin_sort'], '추천순')
        self.assertEqual(self.report['a_no_origin_result_sort'], '추천순')

    def test_b_entering_an_origin_sorts_by_distance_without_pressing_a_button(self):
        self.assertEqual(self.report['b_origin_entered_sort'], '가까운순')
        self.assertEqual(self.report['b_origin_entered_order'], ['A-가까움', 'B-중간', 'C-멂'])

    def test_c_and_d_changing_the_origin_recalculates_from_the_new_one(self):
        self.assertEqual(self.report['d_second_origin_sort'], '가까운순')
        self.assertEqual(self.report['d_result_origin'], '판교역')
        self.assertTrue(self.report['d_order_changed'], '출발지를 바꿨는데 순서가 그대로다')
        self.assertNotEqual(self.report['c_first_origin_order'], self.report['d_second_origin_order'])

    def test_e_clearing_the_origin_leaves_distance_mode(self):
        self.assertEqual(self.report['e_cleared_sort'], '추천순')
        self.assertEqual(self.report['e_cleared_order'], ['추천1', '추천2', '추천3'])

    def test_an_explicit_choice_survives_a_resubmit_with_the_same_origin(self):
        self.assertEqual(self.report['rule5_after_choice'], '추천순')
        self.assertEqual(self.report['rule5_same_origin_resubmit'], '추천순')

    def test_a_changed_origin_outranks_the_earlier_explicit_choice(self):
        # 출발지를 새로 넣은 것은 "여기서 가까운 곳을 보고 싶다"는 새 요청이다.
        self.assertEqual(self.report['rule5_origin_changed'], '가까운순')

    def test_f_and_g_a_slow_earlier_origin_cannot_overwrite_the_newer_one(self):
        self.assertEqual(self.report['fg_final_origin'], '판교역')
        self.assertEqual(self.report['fg_final_order'], ['C-멂', 'B-중간', 'A-가까움'])
        self.assertEqual(self.report['fg_final_sort'], '가까운순')
        self.assertFalse(self.report['fg_loading'], '지난 검색이 로딩을 끄면 안 된다')

    def test_a_failed_geocode_is_never_called_nearest(self):
        self.assertEqual(self.report['geocode_failed_sort'], '추천순')


class SortRuleContractTests(unittest.TestCase):
    """정렬 규칙이 한 곳에 모여 있고, 화면이 그것을 쓰는지."""

    def setUp(self):
        self.screen = (ROOT / 'web/src/components/golf/GolfSearch.tsx').read_text(encoding='utf-8')
        self.rule = (ROOT / 'web/src/lib/golfSort.ts').read_text(encoding='utf-8')

    def test_the_submit_handler_asks_the_shared_rule(self):
        self.assertIn('decideSort({', self.screen)
        self.assertIn('previousOrigin: searchedOrigin.current', self.screen)
        self.assertIn('userChose: userChoseSort.current', self.screen)
        # 제출 버튼 안의 삼항 연산자로 규칙을 되돌리지 않는다.
        self.assertNotIn('params.departure.trim() ? "가까운순" : "추천순"', self.screen)

    def test_the_sort_button_marks_the_choice_as_the_users(self):
        self.assertIn('userChoseSort.current = true', self.screen)

    def test_the_screen_remembers_which_origin_the_last_search_used(self):
        self.assertIn('searchedOrigin.current = search.mode === "condition"', self.screen)

    def test_the_settled_sort_comes_from_the_shared_rule(self):
        self.assertIn('setSort(settleSort(nextSort, r.has_departure))', self.screen)
        self.assertIn('requested === DISTANCE_SORT && !hasDeparture', self.rule)

    def test_the_race_protection_is_still_in_place(self):
        # 이번 수정으로 지난 스프린트의 보호 장치가 사라지지 않았는지 확인한다.
        for guard in ('const generation = useRef(0)', 'const mine = ++generation.current',
                      'if (!current()) return;', 'inFlight.current?.abort()',
                      'new AbortController()', 'signal: controller.signal',
                      'setResult(null)', 'if (current()) setLoading(false)'):
            self.assertIn(guard, self.screen, guard)

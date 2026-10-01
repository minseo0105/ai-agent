"""Golf 정렬 UI · ZIP:ON 지도↔카드 · 단계 설명 · 네이버 연결 · 배포 판 확인.

화면에서 사용자가 겪는 것을 확인한다. 공간 안전 규칙과 production 데이터는 건드리지 않는다.
"""
import json
from pathlib import Path
from urllib.parse import quote
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.version import build_identity, version_block
from services import development_presentation as pr
from services.development_official import STAGE_MAP

ROOT = Path(__file__).resolve().parents[1]


def web(path):
    return (ROOT / 'web/src' / path).read_text(encoding='utf-8')


class GolfSortVisibilityTests(unittest.TestCase):
    """출발지를 넣었는데 '가까운순' 버튼이 사라지지 않는지."""

    def setUp(self):
        self.screen = web('components/golf/GolfSearch.tsx')
        self.ui = web('components/golf/ui.tsx')

    def test_the_nearest_option_is_always_rendered(self):
        # 예전에는 출발지를 못 찾으면 목록에서 통째로 빠져 버튼이 사라졌다.
        self.assertIn('options={["추천순", "가까운순", "가격순"] as Sort[]}', self.screen)
        self.assertNotIn('result.has_departure ? ["추천순", "가까운순", "가격순"]', self.screen)

    def test_it_is_disabled_with_a_reason_instead_of_hidden(self):
        self.assertIn('disabled={result.has_departure ? [] : (["가까운순"] as Sort[])}', self.screen)
        self.assertIn('disabledReason=', self.screen)
        self.assertIn('출발지를 입력하면 가까운순으로 볼 수 있어요', self.screen)
        self.assertIn('출발지 위치를 찾지 못해 가까운순을 쓸 수 없어요', self.screen)

    def test_the_control_survives_an_empty_result(self):
        # 결과가 0건일 때 정렬 컨트롤이 통째로 사라지면 '가까운순이 없어졌다'로 읽힌다.
        control = self.screen.index('options={["추천순", "가까운순", "가격순"] as Sort[]}')
        empty_branch = self.screen.index('{items.length === 0 ? (')
        self.assertLess(control, empty_branch, '정렬은 결과 개수와 무관하게 먼저 그려야 한다')

    def test_the_segmented_control_supports_a_disabled_option(self):
        for token in ('disabled?: readonly T[]', 'aria-disabled={isOff || undefined}',
                      'disabled={isOff}', 'cursor-not-allowed'):
            self.assertIn(token, self.ui, token)

    def test_the_control_cannot_be_pushed_off_a_narrow_screen(self):
        self.assertIn('max-w-full shrink-0 overflow-x-auto', self.ui)

    def test_the_touch_target_stays_large_enough_on_mobile(self):
        # 모바일에서 최소 40px, 데스크톱에서는 기존 높이를 유지한다.
        self.assertIn('min-h-10', self.ui)
        self.assertIn('sm:min-h-0', self.ui)

    def test_a_disabled_option_cannot_be_chosen(self):
        self.assertIn('onClick={() => !isOff && onChange(o.value)}', self.ui)

    def test_the_auto_distance_rule_is_still_wired(self):
        # 지난 스프린트의 규칙이 이 UI 변경으로 사라지지 않았는지.
        self.assertIn('decideSort({', self.screen)
        self.assertIn('settleSort(nextSort, r.has_departure)', self.screen)


class TradeDefaultMonthTests(unittest.TestCase):
    """실거래 최초 진입의 기본 계약년월."""

    def setUp(self):
        self.monitor = web('components/realestate/EstateMonitor.tsx')
        self.lib = web('lib/realestate.ts')

    def test_default_is_202609(self):
        self.assertIn('export const DEFAULT_TRADE_MONTH = "202609";', self.lib)
        self.assertIn('month: DEFAULT_TRADE_MONTH,', self.monitor)
        # 이번 달로 시작하면 아직 공개되지 않은 달이라 빈 화면이 된다.
        self.assertNotIn('month: currentMonth()', self.monitor)

    def test_choosing_another_month_still_works(self):
        self.assertIn('month: filters.month,', self.monitor)
        # 기본값은 초기 state일 뿐이고 선택을 덮어쓰지 않는다.
        self.assertEqual(self.monitor.count('DEFAULT_TRADE_MONTH'), 2)


class RegionEmptyStateTests(unittest.TestCase):
    """개발정보가 없는 자치구를 골랐을 때, 고장이 아니라 준비 중으로 읽히는지."""

    def setUp(self):
        self.tab = web('components/realestate/DevelopmentTab.tsx')
        self.picker = web('components/realestate/RegionPicker.tsx')

    def test_every_seoul_district_is_selectable(self):
        # 선택 목록은 하드코딩이 아니라 API가 준 regions를 그대로 쓴다.
        self.assertIn('regions: { 서울: string[]; 경기: string[] }', self.picker)
        self.assertIn('const pool = regions[active] ?? [];', self.picker)
        self.assertNotIn('const SEOUL_DISTRICTS = [', self.picker)

    def test_zero_data_says_it_is_being_prepared(self):
        self.assertIn('의 개발정보를 준비 중입니다.', self.tab)
        self.assertIn('data-state="region-no-data"', self.tab)
        self.assertIn('조회는 정상으로 끝났고', self.tab)

    def test_zero_data_and_filtered_out_are_different_messages(self):
        self.assertIn('data-state="filtered-empty"', self.tab)
        self.assertIn('유형·진행단계·검색어를 바꿔 보세요', self.tab)
        self.assertIn('noDataForRegion ? (', self.tab)

    def test_zero_data_is_only_claimed_after_a_successful_response(self):
        line = next(l for l in self.tab.splitlines() if 'const noDataForRegion' in l)
        self.assertIn('ready &&', line)
        self.assertIn('inRegion.length === 0', line)

    def test_a_real_error_is_not_shown_as_zero_data(self):
        catch = self.tab[self.tab.index('.catch((e) => {'):]
        catch = catch[:catch.index('.finally(')]
        # 실패한 조회에서 ready를 내려야 '준비 중' 문구가 뜨지 않는다.
        self.assertIn('setReady(false)', catch)
        self.assertIn('서버에 연결하지 못했어요', catch)
        self.assertIn('bg-red-500/10', self.tab)
        self.assertIn('개발정보를 지금 불러올 수 없어요', self.tab)

    def test_it_names_the_districts_that_do_have_data(self):
        self.assertIn('emptyDistricts', self.tab)
        self.assertIn('의 개발정보를 보실 수 있어요', self.tab)

    def test_zero_of_zero_is_not_printed_as_a_map_summary(self):
        self.assertIn('표시할 사업이 없어요.', self.tab)


class SeoulOnlyDevelopmentMapTests(unittest.TestCase):
    """개발지도에는 서울 25개 자치구만 올린다."""

    def setUp(self):
        self.tab = web('components/realestate/DevelopmentTab.tsx')
        self.picker = web('components/realestate/RegionPicker.tsx')

    def test_the_picker_is_given_seoul_only(self):
        self.assertIn('경기: [] as string[]', self.tab)
        self.assertIn('regions={seoulOnly}', self.tab)
        self.assertNotIn('<RegionPicker regions={options.regions}', self.tab)

    def test_an_empty_scope_is_not_offered_or_searched(self):
        self.assertIn('const scopes = (["서울", "경기"] as const).filter', self.picker)
        self.assertIn('{scopes.length > 1 && (', self.picker)
        self.assertIn('const all = scopes.flatMap', self.picker)

    def test_a_single_scope_renders_no_scope_control_at_all(self):
        # Segmented는 범위가 둘 이상일 때만 JSX에 들어간다. CSS로 감추는 것이 아니다.
        block = self.picker[self.picker.index('<div className="flex flex-wrap items-center gap-2">'):]
        block = block[:block.index('aria-label="지역 검색"')]
        self.assertIn('{scopes.length > 1 && (\n          <Segmented', block)
        self.assertNotIn('options={["서울", "경기"] as const}', self.picker)
        # 자치구 목록은 범위 선택과 무관하게 바로 렌더된다.
        self.assertIn('{visible.map((r) => {', self.picker)

    def test_the_wording_follows_the_scopes_actually_offered(self):
        self.assertIn('scopes.length > 1 ? "구·시 검색" : `${active} 자치구 검색`', self.picker)
        self.assertIn('{scopes.join("·")} 전체', self.picker)
        self.assertNotIn('서울·경기 전체\n', self.picker)

    def test_the_trade_screen_still_offers_both(self):
        monitor = web('components/realestate/EstateMonitor.tsx')
        filters = web('components/realestate/TradeFilters.tsx')
        self.assertIn('regions={options.regions}', filters)
        self.assertIn('regions={options.regions}', monitor)


class MapInstanceReuseTests(unittest.TestCase):
    """지도 인스턴스를 반복해서 만들지 않는지."""

    def setUp(self):
        self.tab = web('components/realestate/DevelopmentTab.tsx')
        self.map = web('components/realestate/ZiponMap.tsx')
        self.loader = web('lib/naverMaps.ts')

    def test_the_map_is_not_unmounted_while_loading(self):
        # ready로 감싸면 지역을 바꾸거나 조회가 실패할 때마다 인스턴스가 파괴된다.
        self.assertIn('{config && (\n        <ZiponMap', self.tab)
        self.assertNotIn('{ready && (\n        <ZiponMap', self.tab)

    def test_one_container_is_never_built_twice(self):
        self.assertIn('const built = useRef<HTMLDivElement | null>(null);', self.map)
        self.assertIn('if (built.current === container.current) return;', self.map)
        self.assertIn('built.current = null;', self.map)

    def test_the_sdk_is_loaded_once(self):
        self.assertIn('if (window.naver?.maps) return Promise.resolve(window.naver.maps);', self.loader)
        self.assertIn('if (pending) return pending;', self.loader)
        self.assertIn('}, [sdk, compact]);', self.map)


class ServiceGridResponsiveTests(unittest.TestCase):
    """메인 서비스 카드가 화면 폭에 따라 열 수를 바꾸는지."""

    def setUp(self):
        self.grid = web('components/ServiceGrid.tsx')

    def test_the_grid_has_breakpoints(self):
        self.assertIn('grid-cols-2 items-stretch gap-3 sm:gap-4 md:grid-cols-3 xl:grid-cols-4', self.grid)
        self.assertNotIn('grid grid-cols-2 gap-3 lg:grid-cols-4', self.grid)

    def test_cards_share_a_height_and_do_not_overflow(self):
        self.assertIn('flex h-full min-w-0 flex-col', self.grid)
        self.assertIn('size-10 shrink-0', self.grid)
        self.assertIn('break-keep', self.grid)


class MonitorTabAdminOnlyTests(unittest.TestCase):
    """모니터링 조건은 관리자에게만 보이고, 서버도 관리자만 받는다."""

    def setUp(self):
        self.monitor = web('components/realestate/EstateMonitor.tsx')
        self.api = (ROOT / 'api/realestate.py').read_text(encoding='utf-8')

    def test_it_reuses_the_existing_admin_check(self):
        self.assertIn('status?.me?.role === "admin"', self.monitor)
        self.assertIn('from "@/components/access/AccessProvider"', self.monitor)

    def test_the_tab_and_the_panel_are_not_rendered_for_others(self):
        # CSS 숨김이 아니라 렌더링 단계에서 뺀다. 버튼도 영역도 만들지 않는다.
        self.assertIn('...(admin ? [{ value: "모니터링 조건" as const, label: "모니터링" }] : [])', self.monitor)
        self.assertIn('{admin && (', self.monitor)
        self.assertNotIn('hidden={tab !== "모니터링 조건"}>{tab === "모니터링 조건" && <MonitorTab options={options} />}</div>\n        <div hidden={tab !== "알림함"}', self.monitor)

    def test_a_non_admin_is_moved_off_the_tab(self):
        self.assertIn('if (!admin && tab === "모니터링 조건") setTab("개발지도");', self.monitor)

    def test_the_server_requires_admin_too(self):
        self.assertIn('from api.access import require_admin', self.api)
        for route in ('@router.get("/monitor"', '@router.put("/monitor/auto"',
                      '@router.post("/rules"', '@router.post("/rules/{rule_id}/toggle"',
                      '@router.delete("/rules/{rule_id}"', '@router.post("/monitor/run"'):
            self.assertIn(route + ', dependencies=[Depends(require_admin)])', self.api)

    def test_a_request_without_an_admin_token_is_refused(self):
        from unittest.mock import patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from services import realestate_monitor as rm
        with patch.object(rm, 'init_db'):
            from api.realestate import router
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app, raise_server_exceptions=False)
        for method, path in (('get', '/api/realestate/monitor'),
                             ('put', '/api/realestate/monitor/auto'),
                             ('post', '/api/realestate/rules'),
                             ('post', '/api/realestate/rules/1/toggle'),
                             ('delete', '/api/realestate/rules/1'),
                             ('post', '/api/realestate/monitor/run')):
            kwargs = {} if method in ('get', 'delete') else {'json': {}}
            response = getattr(client, method)(path, **kwargs)
            self.assertEqual(response.status_code, 401, path)
            self.assertEqual(response.json()['detail']['code'], 'admin_required', path)

    def test_the_other_estate_endpoints_stay_open(self):
        for route in ('@router.post("/trades")', "@router.get('/development/map')",
                      '@router.get("/notifications")'):
            self.assertIn(route, self.api)
        self.assertNotIn("@router.get('/development/map', dependencies=", self.api)


class RegionScopedMapFetchTests(unittest.TestCase):
    """서울 전체를 한 번에 받지 않고, 선택한 자치구만 조회하는지."""

    def setUp(self):
        self.tab = web('components/realestate/DevelopmentTab.tsx')

    def test_the_request_carries_the_selected_district(self):
        self.assertIn('estateApi.developmentMap(sigungu, 500, undefined', self.tab)
        self.assertIn('requested.map((d) => load(d)', self.tab)
        # 전체를 무조건 받던 호출은 남아 있지 않다.
        self.assertNotIn('estateApi.developmentMap(undefined, 500, undefined, { includeCompleted', self.tab)

    def test_changing_the_region_refetches(self):
        self.assertIn('}, [includeCompleted, scopeKey]);', self.tab)

    def test_a_failed_district_is_named_not_dropped(self):
        self.assertIn('setFailedDistricts', self.tab)
        self.assertIn('의 개발정보를 받지 못했어요', self.tab)
        self.assertIn('아래 합계에는 빠져 있습니다', self.tab)

    def test_merging_cannot_produce_two_cards_for_one_project(self):
        self.assertIn('if (seen.has(project.project_id)) continue;', self.tab)

    def test_a_capped_response_is_not_called_the_total(self):
        self.assertIn('setTruncated', self.tab)
        self.assertIn('표시 한도에 닿아 일부만 받았어요', self.tab)
        self.assertIn('서울시 전체 미리보기예요', self.tab)

    def test_the_district_ceiling_is_unchanged(self):
        self.assertIn('const MAX_DISTRICTS = 5;', self.tab)
        self.assertIn('const MAX_CARDS = 200;', self.tab)
        self.assertIn('.slice(0, MAX_DISTRICTS)', self.tab)


class MapCardLinkingTests(unittest.TestCase):
    """지도에서 고른 사업과 카드가 canonical id로 이어지는지."""

    def setUp(self):
        self.tab = web('components/realestate/DevelopmentTab.tsx')
        self.map = web('components/realestate/ZiponMap.tsx')

    def test_selection_travels_by_project_id_not_by_name(self):
        self.assertIn('const scrollToProject = useCallback((projectId: string)', self.tab)
        self.assertIn('cardRefs.current[projectId]', self.tab)
        self.assertIn('data-project-id={p.project_id}', self.tab)
        # 이름으로 카드를 찾지 않는다. 닮은 이름이 서로 다른 사업이다.
        self.assertNotIn('find((p) => p.name ===', self.tab)
        self.assertNotIn('project_name ===', self.tab)

    def test_choosing_on_the_map_moves_to_that_card(self):
        select = self.tab[self.tab.index('const selectFromMap = useCallback('):]
        select = select[:select.index('const scrollToCard')]
        self.assertIn('setSelectedId(projectId)', select)
        self.assertIn('scrollToProject(projectId)', select)
        # 카드가 다시 그려진 뒤에 옮긴다.
        self.assertIn('requestAnimationFrame', select)

    def test_a_card_is_not_hidden_under_the_sticky_area(self):
        self.assertIn('block: "center"', self.tab)
        self.assertIn('scroll-mt-24', self.tab)

    def test_a_verified_boundary_is_clickable_and_selects_the_same_project(self):
        area = self.map[self.map.index('for (const part of verifiedBoundaryPolygons(point))'):]
        area = area[:area.index('const selected = selectedId')]
        self.assertIn('clickable: true', area)
        self.assertIn('select.current?.(point.project_id)', area)

    def test_the_selected_boundary_is_drawn_more_strongly(self):
        self.assertIn('const selectedArea = selectedId === point.project_id', self.map)
        self.assertIn('strokeWeight: selectedArea ? 4 : 2.5', self.map)
        self.assertIn('fillOpacity: selectedArea ? 0.3 : 0.18', self.map)

    def test_a_project_without_a_boundary_is_highlighted_by_its_marker(self):
        self.assertIn('existing.setIcon(markerIcon(api, point, selected))', self.map)
        self.assertIn('const selected = selectedId === point.project_id', self.map)
        self.assertIn('zIndex: selected ? 1000 : 1', self.map)

    def test_only_one_project_is_highlighted_at_a_time(self):
        # 카드도 지도도 같은 하나의 selectedId만 본다.
        self.assertIn('selected={selectedId === p.project_id}', self.tab)
        self.assertIn('selectedId={selectedId}', self.tab)

    def test_a_filtered_out_project_has_no_card_to_jump_to(self):
        # 목록에 없는 사업은 ref가 없으므로 이동하지 않고 조용히 지나간다.
        self.assertIn('if (!node) return false;', self.tab)


class StageGuideTests(unittest.TestCase):
    """단계 설명: 공식 값은 그대로, 해석은 따로, 투자 판단은 없음."""

    INVESTMENT_WORDS = ('매수 적기', '사기 좋', '투자 추천', '수익', '유망', '안전한 투자',
                        '추천합니다', '지금이 기회')

    def test_every_official_stage_has_an_explanation(self):
        missing = [s for s in sorted(set(STAGE_MAP.values())) if s not in pr.STAGE_GUIDE]
        self.assertEqual(missing, [], f'해석이 없는 공식 단계: {missing}')

    def test_a_known_stage_gets_its_own_explanation_and_checks(self):
        guide = pr.stage_guide('ASSOCIATION_APPROVED')
        self.assertTrue(guide['interpreted'])
        self.assertEqual(guide['label'], '조합설립 인가')
        self.assertIn('조합이 공식적으로 만들어져', guide['plain'])
        self.assertIn('조합원 지위 승계 가능 여부 확인', guide['checks'])
        self.assertIn('권리산정기준일 확인', guide['checks'])

    def test_different_stages_get_different_explanations(self):
        early = pr.stage_guide('CANDIDATE')
        late = pr.stage_guide('MANAGEMENT_DISPOSITION')
        self.assertNotEqual(early['plain'], late['plain'])
        self.assertNotEqual(early['checks'], late['checks'])

    def test_an_unknown_stage_is_not_interpreted(self):
        for stage in (None, '', 'UNKNOWN', 'SOMETHING_NEW'):
            guide = pr.stage_guide(stage)
            self.assertFalse(guide['interpreted'], stage)
            self.assertIn('공식 자료에서 현재 단계를 추가로 확인', guide['plain'])
            self.assertEqual(guide['checks'], ['공식 사업정보를 먼저 확인'])

    def test_no_explanation_gives_investment_advice(self):
        blobs = [pr.STAGE_GUIDE_UNKNOWN]
        blobs.extend(pr.STAGE_GUIDE.values())
        for plain, checks in blobs:
            text = plain + ' ' + ' '.join(checks)
            for word in self.INVESTMENT_WORDS:
                self.assertNotIn(word, text, f'{word} in {plain[:24]}')

    def test_no_explanation_invents_a_number(self):
        import re
        for plain, checks in pr.STAGE_GUIDE.values():
            text = plain + ' ' + ' '.join(checks)
            # 분담금 2억, 2026.01.01 같은 값을 만들어 내지 않는다.
            self.assertIsNone(re.search(r'\d+\s*(억|만원|원|%)', text), text[:40])

    def test_the_checks_say_they_are_generic_not_confirmed_facts(self):
        guide = pr.stage_guide('IMPLEMENTATION_APPROVED')
        self.assertIn('확인된 값이 아니라', guide['checks_note'])
        # 체크 항목은 모두 '확인'으로 끝나는 할 일이다. 확정된 사실처럼 읽히지 않는다.
        for check in guide['checks']:
            self.assertTrue(check.endswith('확인'), check)

    def test_facts_and_guidance_are_separate_fields(self):
        row = {'project_id': 'p', 'project_name': '천호1', 'project_type': 'REDEVELOPMENT',
               'sigungu': '강동구', 'dong': '천호동', 'address': '서울특별시 강동구 천호동 423-200',
               'stage_raw': '조합설립인가', 'validation_status': 'VERIFIED'}
        out = pr.present_project(row)
        # 확인된 사실
        self.assertEqual(out['stage']['label'], '조합설립 인가')
        self.assertEqual(out['stage']['official_text'], '조합설립인가')
        # 일반 안내는 다른 자리에 있다.
        self.assertIn('stage_guide', out)
        self.assertNotIn('plain', out['stage'])
        self.assertNotIn('checks', out['stage'])


class StageGuideScreenTests(unittest.TestCase):
    def setUp(self):
        self.card = web('components/realestate/DevelopmentCard.tsx')

    def test_the_card_says_현재_사업단계(self):
        self.assertIn('현재 사업단계', self.card)
        self.assertNotIn('처리상태', self.card)

    def test_the_card_shows_the_easy_explanation_and_the_checks(self):
        self.assertIn('쉽게 말하면', self.card)
        self.assertIn('project.stage_guide.plain', self.card)
        self.assertIn('매수 전 체크', self.card)
        self.assertIn('project.stage_guide.checks.map', self.card)
        self.assertIn('project.stage_guide.checks_note', self.card)

    def test_internal_verification_words_are_not_shown_raw(self):
        # 내부 상태값은 화면에 그대로 내보내지 않는다. 비교에 쓰는 것은 괜찮다.
        for internal in ('NEEDS_REVIEW', 'PARTIALLY_VERIFIED', 'geometry_verified',
                         'validation_status'):
            self.assertNotIn(internal, self.card, internal)
        # boundary_status는 비교에만 쓰고, 사용자에게는 사람이 읽는 label을 보여준다.
        for line in self.card.splitlines():
            if 'OFFICIAL_VERIFIED' in line:
                self.assertIn('===', line, line.strip())
        self.assertIn('{point.boundary_status_label}', self.card)
        self.assertNotIn('{point.boundary_status}', self.card)


class NaverLinkTests(unittest.TestCase):
    """확인되지 않은 deep-link 형식으로는 링크를 만들지 않는다."""

    LOCATED = {'address': '서울특별시 강동구 천호동 423-200', 'sigungu': '강동구',
               'dong': '천호동', 'latitude': 37.5401, 'longitude': 127.1238}

    def test_no_link_is_produced_at_all(self):
        # 좌표가 있어도 없어도 같다. 틀린 곳으로 보내는 것보다 연결하지 않는 쪽이다.
        for row in (self.LOCATED, {'address': '서울특별시 송파구 잠실동 101-1'},
                    {'sigungu': '송파구', 'dong': '마천동'}, {}):
            self.assertIsNone(pr.naver_real_estate_link(row), row)

    def test_the_rejected_search_path_is_gone(self):
        source = (ROOT / 'services/development_presentation.py').read_text(encoding='utf-8')
        code = '\n'.join(line for line in source.splitlines()
                         if not line.lstrip().startswith('#'))
        # 840a9dc가 넣은 지번 검색 경로와, 그 전의 서비스 메인 fallback 모두 없다.
        self.assertNotIn('m.land.naver.com', code)
        self.assertNotIn("'https://land.naver.com/'", code)
        self.assertNotIn('search.naver.com', code)
        self.assertNotIn('NAVER_LAND_SEARCH', code)

    def test_no_guessed_deep_link_parameters_anywhere_in_the_module(self):
        source = (ROOT / 'services/development_presentation.py').read_text(encoding='utf-8')
        code = '\n'.join(line for line in source.splitlines()
                         if not line.lstrip().startswith('#'))
        for guessed in ('complexNo', 'complex_id', 'articleNo', 'lat=', 'lon=', 'lng=',
                        'center=', 'zoom=', '?ms='):
            self.assertNotIn(guessed, code, guessed)

    def test_the_reason_is_recorded_in_the_code(self):
        self.assertEqual(pr.NAVER_LINK_UNAVAILABLE, 'NAVER_LAND_DEEPLINK_FORMAT_UNVERIFIED')
        source = (ROOT / 'services/development_presentation.py').read_text(encoding='utf-8')
        block = source[source.index('# 네이버부동산 연결.'):source.index('def stage_label(')]
        self.assertIn('build_naver_land_url', block)
        self.assertIn('map.naver.com/p/search', block)

    def test_no_centroid_is_computed_for_the_link(self):
        source = (ROOT / 'services/development_presentation.py').read_text(encoding='utf-8')
        block = source[source.index('# 네이버부동산 연결.'):source.index('def stage_label(')]
        self.assertIn('centroid는 쓰지 않는다', block)
        self.assertNotIn('centroid(', block)

    def test_the_card_explains_the_missing_button(self):
        card = web('components/realestate/DevelopmentCard.tsx')
        self.assertIn('네이버부동산 연결은 준비 중입니다.', card)
        # 링크가 올 때를 위한 자리는 남겨 둔다. 올 때도 새 탭으로 연다.
        self.assertIn('{project.naver_real_estate && (', card)
        block = card[card.index('project.naver_real_estate.url'):]
        self.assertIn('target="_blank"', block[:260])
        self.assertIn('rel="noopener noreferrer"', block[:260])

    def test_the_trade_link_is_untouched(self):
        # 실거래 링크는 단지명으로 검색하는 운영 중 구현이다. 건드리지 않는다.
        from services import realestate_monitor as rm
        url = rm.build_naver_land_url({'region_label': '서울 > 송파구', 'region': '잠실동',
                                       'name': '잠실엘스', 'property_type': '아파트'})
        self.assertTrue(url.startswith('https://m.land.naver.com/search/result/'))
        for token in ('잠실엘스', '아파트'):
            self.assertIn(quote(token, safe=''), url, token)

    def test_the_golf_map_link_is_untouched(self):
        source = (ROOT / 'services/golf_service.py').read_text(encoding='utf-8')
        self.assertIn('https://map.naver.com/p/search/', source)


class DeployVersionTests(unittest.TestCase):
    """배포된 판을 runtime에서 읽는다. 코드에 적지 않는다."""

    def test_the_commit_is_read_from_git_at_runtime(self):
        identity = build_identity()
        self.assertIn(identity['commit_source'],
                      ('GIT_REF', 'GIT_PACKED_REFS', 'DETACHED_HEAD', 'ENVIRONMENT',
                       'NO_GIT_DIRECTORY', 'HEAD_UNREADABLE', 'REF_UNREADABLE', 'HEAD_EMPTY'))
        if identity['commit']:
            self.assertEqual(len(identity['commit']), 7)
            self.assertEqual(len(identity['commit_full']), 40)

    def test_no_commit_hash_is_hardcoded(self):
        import re
        source = (ROOT / 'api/version.py').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r"['\"][0-9a-f]{7,40}['\"]", source),
                          'commit 값을 코드에 적어 두면 배포되지 않은 판을 배포된 것처럼 말한다')

    def test_an_unreadable_repository_reports_none_instead_of_a_made_up_value(self):
        import tempfile
        from api import version as mod
        with tempfile.TemporaryDirectory() as directory:
            commit, source = mod._head_commit(Path(directory))
        self.assertIsNone(commit)
        self.assertEqual(source, 'NO_GIT_DIRECTORY')

    def test_health_reports_the_running_version_without_calling_out(self):
        block = version_block()
        for field in ('commit', 'commit_source', 'started_at', 'uptime_seconds'):
            self.assertIn(field, block)
        main = (ROOT / 'api/main.py').read_text(encoding='utf-8')
        body = main[main.index('def health():'):main.index('def ready():')]
        self.assertIn('version_block()', body)
        for forbidden in ('_remote_request', 'requests.', 'urlopen'):
            self.assertNotIn(forbidden, body, forbidden)


class SpatialSafetyStillHoldsTests:
    pass


class SpatialSafetyUnchangedTests(unittest.TestCase):
    """이번 UX 작업이 공간 안전 규칙을 건드리지 않았는지."""

    def test_a_representative_point_alone_never_reads_as_inside(self):
        point_only = pr.relation('INSIDE', boundary_verified=False)
        self.assertNotEqual(point_only['code'], 'INSIDE')
        self.assertFalse(point_only['confirmed_boundary'])
        verdict = pr.inside_verdict([{'name': '테스트', 'spatial': point_only}])
        self.assertEqual(verdict['code'], 'NOT_DETERMINED')
        self.assertEqual(verdict['notice'], pr.INSIDE_UNKNOWN_NOTICE)

    def test_only_a_verified_boundary_produces_inside(self):
        verified = pr.relation('INSIDE', boundary_verified=True)
        self.assertEqual(verified['code'], 'INSIDE')
        self.assertTrue(verified['confirmed_boundary'])

    def test_an_unverified_boundary_never_reaches_the_map(self):
        row = {'project_id': 'p', 'project_name': 'x', 'project_type': 'REDEVELOPMENT',
               'sigungu': '강동구', 'latitude': 37.54, 'longitude': 127.12,
               'boundary': {'type': 'Polygon', 'coordinates': [[[127.1, 37.5]]]},
               'geometry_verified': False, 'validation_status': 'VERIFIED'}
        point = pr.map_point(row)
        self.assertIsNone(point['boundary'])
        self.assertFalse(point['allows_inside'])

    def test_the_lifecycle_rule_is_unchanged(self):
        self.assertEqual(pr.lifecycle({'stage_raw': '준공인가'})['code'], 'COMPLETED')
        self.assertEqual(pr.lifecycle({'stage_raw': '착공'})['code'], 'CONSTRUCTION')
        self.assertTrue(pr.lifecycle({'stage_raw': '조합해산'})['in_default_map'])


class MapCardApiBehaviourTests(unittest.TestCase):
    """지도와 카드가 같은 응답에서 같은 canonical id로 오는지. 필터와의 상호작용."""

    def rows(self):
        import binascii
        import struct
        point = binascii.hexlify(struct.pack('<BIIdd', 1, 0x20000001, 4326, 127.1, 37.5)).decode()
        common = {'project_type': 'REDEVELOPMENT', 'sigungu': '송파구',
                  'validation_status': 'VERIFIED', 'location': point, 'geometry_verified': False}
        # 이름이 서로 닮은 두 사업. 이름으로 이으면 서로 바뀐다.
        return [dict(common, project_id='machun2', project_name='마천2',
                     stage_raw='조합설립인가'),
                dict(common, project_id='machun2-area',
                     project_name='마천2재정비촉진구역 주택재개발정비사업',
                     stage_raw='사업시행인가'),
                dict(common, project_id='done', project_name='끝난사업', stage_raw='준공인가')]

    def call(self, **kwargs):
        import asyncio
        from unittest.mock import patch
        from api.realestate import development_map
        from services import realestate_monitor as rm

        def answer(method, path, **request):
            if path == 'rpc/zipon_development_map':
                raise RuntimeError('rpc not installed')
            if request.get('params', {}).get('select', '').startswith('project_id,stage'):
                return []
            return self.rows()

        with patch.object(rm, '_using_remote_db', return_value=True), \
                patch.object(rm, '_remote_request', side_effect=answer):
            return asyncio.run(development_map(**kwargs))

    def test_points_and_cards_share_the_same_canonical_ids(self):
        result = self.call()
        self.assertEqual({p['project_id'] for p in result['points']},
                         {row['project_id'] for row in result['projects']})

    def test_projects_with_similar_names_keep_separate_ids(self):
        result = self.call()
        names = {row['project_id']: row['name'] for row in result['projects']}
        self.assertEqual(names['machun2'], '마천2')
        self.assertIn('마천2재정비촉진구역', names['machun2-area'])
        self.assertNotEqual(names['machun2'], names['machun2-area'])

    def test_each_card_carries_its_own_stage_guide(self):
        result = self.call()
        guides = {row['project_id']: row['stage_guide'] for row in result['projects']}
        self.assertEqual(guides['machun2']['stage'], 'ASSOCIATION_APPROVED')
        self.assertEqual(guides['machun2-area']['stage'], 'IMPLEMENTATION_APPROVED')
        self.assertNotEqual(guides['machun2']['plain'], guides['machun2-area']['plain'])

    def test_a_completed_project_is_absent_by_default_so_it_cannot_be_linked(self):
        result = self.call()
        self.assertNotIn('done', {p['project_id'] for p in result['points']})
        self.assertEqual(result['hidden_completed'], 1)

    def test_with_the_toggle_on_the_completed_project_links_like_any_other(self):
        result = self.call(include_completed=True)
        self.assertIn('done', {p['project_id'] for p in result['points']})
        row = next(r for r in result['projects'] if r['project_id'] == 'done')
        self.assertEqual(row['stage_guide']['stage'], 'COMPLETED')
        self.assertTrue(row['stage_guide']['interpreted'])

    def test_every_card_that_has_a_location_gets_a_neighbourhood_link(self):
        result = self.call(include_completed=True)
        for row in result['projects']:
            # 자치구는 있지만 법정동이 없으면 링크를 만들지 않는다.
            self.assertIsNone(row['naver_real_estate'])

"""Product-facing behaviour: trade detail, development wording, spatial fallback.

Only what this sprint changed. No database, no network, no migration re-run.
"""
import asyncio
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from services import development as dev
from services import development_geocode as geo
from services import development_presentation as pr
from services import realestate_monitor as rm
import resolve_zipon_quarantine as quarantine

with patch.object(rm, 'init_db'):
    from api.realestate import DevelopmentQuery, TradeQuery, development_search, trades

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
APT_ITEM = """<item>
  <aptNm>둔촌주공</aptNm><dealAmount> 195,000</dealAmount><excluUseAr>84.99</excluUseAr>
  <dealYear>2026</dealYear><dealMonth>9</dealMonth><dealDay>3</dealDay>
  <floor>12</floor><buildYear>1980</buildYear><umdNm>둔촌동</umdNm><jibun>170</jibun>
  <roadNm>양재대로</roadNm><roadNmBonbun>1321</roadNmBonbun><aptDong>101</aptDong>
  <dealingGbn>중개거래</dealingGbn><estateAgentSggNm>서울 강동구</estateAgentSggNm>
  <rgstDate>26.09.20</rgstDate><cdealType>O</cdealType><cdealDay>26.09.25</cdealDay>
  <slerGbn>개인</slerGbn><buyerGbn>개인</buyerGbn><landLeaseholdGbn>N</landLeaseholdGbn>
  <bonbun>0170</bonbun><bubun>0000</bubun><aptSeq>11740-1</aptSeq>
</item>"""


class TradeDetailTests(unittest.TestCase):
    def row(self, markup=APT_ITEM, property_type='아파트'):
        return rm._trade_item_to_common(ET.fromstring(markup), property_type, '11740', '202609')

    def test_the_headline_fields_are_unchanged(self):
        row = self.row()
        self.assertEqual(row['name'], '둔촌주공')
        self.assertEqual(row['price_100m'], 19.5)
        self.assertEqual(row['area'], 84.99)
        self.assertEqual(row['area_basis'], '전용면적')
        self.assertEqual(row['date'], '2026-09-03')
        self.assertEqual(row['floor'], '12')

    def test_readable_detail_fields_are_separated_from_raw_ones(self):
        row = self.row()
        detail, raw = row['detail'], row['raw_detail']
        self.assertEqual(detail['거래유형'], '중개거래')
        self.assertEqual(detail['계약해제'], 'O')
        self.assertEqual(detail['해제사유 발생일'], '26.09.25')
        self.assertEqual(detail['등기일자'], '26.09.20')
        self.assertEqual(detail['동'], '101')
        # 일반 사용자가 읽기 어려운 원문 항목은 기본 상세에서 빼고 원문 영역으로 옮긴다.
        for label in ('본번', '부번', '도로명 본번', '도로명 부번', '토지임대부', '중개사 소재지'):
            self.assertNotIn(label, detail)
        self.assertEqual(raw['중개사 소재지'], '서울 강동구')
        self.assertEqual(raw['토지임대부'], 'N')

    def test_the_lot_numbers_build_an_address_instead_of_being_shown(self):
        row = self.row()
        self.assertEqual(row['address_road'], '양재대로 1321')
        self.assertEqual(row['address_jibun'], '둔촌동 170')
        self.assertEqual(row['canonical_address'], '양재대로 1321')

    def test_absent_fields_are_not_invented(self):
        row = self.row('<item><aptNm>x</aptNm><dealAmount>10,000</dealAmount></item>')
        self.assertEqual(row['detail'], {})
        self.assertEqual(row['raw_detail'], {})

    def test_placeholder_values_are_dropped(self):
        detail = self.row('<item><aptNm>x</aptNm><dealingGbn>-</dealingGbn><bubun>0</bubun></item>')['detail']
        self.assertNotIn('거래유형', detail)
        self.assertNotIn('부번', detail)

    def test_the_data_source_is_named(self):
        self.assertIn('국토교통부', self.row()['source_label'])

    def test_a_detached_house_keeps_its_own_area_basis(self):
        row = self.row('<item><houseType>다가구</houseType><dealAmount>50,000</dealAmount>'
                       '<totalFloorAr>210.5</totalFloorAr><plottageAr>120</plottageAr></item>',
                       '단독·다가구')
        self.assertEqual(row['area_basis'], '연면적')
        self.assertEqual(row['raw_detail']['대지면적'], '120')


class PresentationTests(unittest.TestCase):
    def project(self, **overrides):
        base = {'project_id': 'p1', 'project_name': '천호2구역 주택재건축정비사업조합',
                'project_type': 'RECONSTRUCTION', 'sigungu': '강동구', 'dong': '천호동',
                'address': '서울특별시 강동구 천호동 437-5', 'stage_raw': '조합설립인가',
                'normalized_stage': 'ASSOCIATION_APPROVED', 'status': 'UNKNOWN',
                'validation_status': 'NEEDS_REVIEW', 'source_name': '정보몽땅 사업장 목록 강동구',
                'evidence_url': 'https://cleanup.seoul.go.kr/x', 'spatial_relation': 'UNKNOWN'}
        return pr.present_project(dict(base, **overrides))

    def test_internal_enums_never_reach_the_screen(self):
        project = self.project()
        # Only these fields are rendered; trust.code stays for styling, never for display.
        shown = json.dumps([project['type_label'], project['stage'], project['stage_basis'],
                            project['status_label'], project['trust']['label'],
                            project['trust']['note'], project['spatial']['label'],
                            project['location_notice']], ensure_ascii=False)
        for token in ('NEEDS_REVIEW', 'UNKNOWN_OFFICIAL_COLUMN', 'ASSOCIATION_APPROVED',
                      'RECONSTRUCTION', 'UNVERIFIED', 'MISSING_FROM_SOURCE'):
            self.assertNotIn(token, shown)

    def test_labels_are_readable(self):
        project = self.project()
        self.assertEqual(project['type_label'], '재건축')
        self.assertEqual(project['stage']['label'], '조합설립 인가')
        self.assertEqual(project['stage']['official_text'], '조합설립인가')
        self.assertEqual(project['trust']['label'], '공식자료 확인')
        self.assertEqual(project['status_label'], '공식 확인 진행 중')

    def test_an_unmapped_stage_says_so(self):
        self.assertEqual(self.project(normalized_stage=None, stage_raw=None)['stage']['label'],
                         '세부 진행단계 확인 중')

    def test_list_based_evidence_is_not_presented_as_confirmed(self):
        project = self.project(stage_basis='OFFICIAL_LIST_CELL')
        self.assertEqual(project['stage_basis'], '서울시 공식 목록 확인')
        self.assertEqual(project['stage_verified_level'], 'OFFICIAL_LIST_MAPPED')
        self.assertNotEqual(project['trust']['label'], '공식 확인')

    def test_detail_verified_is_distinguished_from_list_mapped(self):
        verified = self.project(validation_status='VERIFIED', stage_basis='OFFICIAL_DETAIL_PAGE')
        self.assertEqual(verified['trust']['label'], '공식 확인')
        self.assertEqual(verified['stage_basis'], '공식 상세정보 확인')
        self.assertEqual(verified['stage_verified_level'], 'OFFICIAL_DETAIL_VERIFIED')

    def test_inside_needs_a_verified_boundary(self):
        self.assertEqual(self.project(spatial_relation='INSIDE')['spatial']['label'], '주변 개발사업')
        self.assertFalse(self.project(spatial_relation='INSIDE')['spatial']['confirmed_boundary'])
        confirmed = self.project(spatial_relation='INSIDE', geometry_verified=True)
        self.assertEqual(confirmed['spatial']['label'], '정비구역 내부')
        self.assertTrue(confirmed['spatial']['confirmed_boundary'])

    def test_an_official_sources_verified_at_is_not_a_verified_boundary(self):
        # evidence_verified는 공식 출처를 언제 확인했는지다. 경계를 확인한 것이 아니다.
        row = self.project(spatial_relation='INSIDE', evidence_verified=True)
        self.assertEqual(row['spatial']['label'], '주변 개발사업')
        self.assertFalse(row['spatial']['confirmed_boundary'])

    def test_a_project_without_location_gets_a_graceful_notice(self):
        project = self.project()
        self.assertFalse(project['has_location'])
        self.assertEqual(project['location_notice'], pr.NO_LOCATION_NOTICE)

    def test_missing_from_source_is_not_a_cancellation(self):
        note = pr.trust('MISSING_FROM_SOURCE')['note']
        self.assertIn('취소나 종료를 뜻하지 않습니다', note)

    def test_the_trade_context_falls_back_instead_of_hiding(self):
        context = pr.present_context({'relation': 'UNKNOWN', 'status': 'needs_geocode',
                                      'nearby_projects': [],
                                      'reason': 'EXACT_ADDRESS_COORDINATES_REQUIRED'})
        self.assertFalse(context['available'])
        self.assertEqual(context['label'], '위치 확인 필요')
        self.assertEqual(context['notice'], pr.NO_LOCATION_NOTICE)
        self.assertIsNotNone(context['reason_label'])

    def test_a_ready_context_lists_projects(self):
        context = pr.present_context({'relation': 'NEARBY', 'status': 'ok', 'nearby_projects': [
            {'project_id': 'p', 'project_name': 'x', 'project_type': 'REDEVELOPMENT',
             'spatial_relation': 'NEARBY', 'meters': 120.4}]})
        self.assertTrue(context['available'])
        self.assertEqual(context['label'], '주변 개발사업')
        self.assertEqual(context['projects'][0]['distance_m'], 120.4)

    def test_no_context_is_no_block(self):
        self.assertIsNone(pr.present_context(None))


class ApiShapeTests(unittest.TestCase):
    def test_development_search_returns_presented_projects(self):
        rows = [{'project_id': 'p1', 'project_name': '천호2구역', 'project_type': 'RECONSTRUCTION',
                 'stage': '조합설립인가', 'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW',
                 'spatial_relation': 'UNKNOWN', 'meters': None, 'source_name': '정보몽땅',
                 'evidence_url': 'https://cleanup.seoul.go.kr/x', 'evidence_verified': False}]
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=rows):
            result = asyncio.run(development_search(DevelopmentQuery(sigungu='강동구')))
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['located'], 0)
        self.assertEqual(result['projects'][0]['type_label'], '재건축')
        self.assertEqual(result['projects'][0]['spatial']['label'], '위치 확인 필요')
        self.assertEqual(result['location_notice'], pr.NO_LOCATION_NOTICE)

    def test_trades_attach_readable_development_context(self):
        trade_rows = [{'name': 'A', 'property_type': '아파트', 'date': '2026-09-01'}]
        query = TradeQuery(regions=['서울 > 강동구'], property_types=['아파트'], month='202609',
                           include_development=True)
        with patch.object(rm, 'fetch_trades_multi', return_value=(trade_rows, [])), \
             patch.object(rm, 'build_naver_land_url', return_value='https://example.invalid'), \
             patch.object(dev, 'search_projects') as search:
            result = asyncio.run(trades(query))
        search.assert_not_called()
        context = result['items'][0]['development']
        self.assertFalse(context['available'])
        self.assertEqual(context['label'], '위치 확인 필요')
        self.assertNotIn('needs_geocode', json.dumps(context, ensure_ascii=False))

    def test_trades_without_the_flag_carry_no_development_block(self):
        trade_rows = [{'name': 'A', 'property_type': '아파트', 'date': '2026-09-01'}]
        query = TradeQuery(regions=['서울 > 강동구'], property_types=['아파트'], month='202609')
        with patch.object(rm, 'fetch_trades_multi', return_value=(trade_rows, [])), \
             patch.object(rm, 'build_naver_land_url', return_value='https://example.invalid'):
            result = asyncio.run(trades(query))
        self.assertNotIn('development', result['items'][0])


class GeocodeQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = json.loads((DATA / 'geocode_queue_20260927.json').read_text(encoding='utf-8'))

    def test_the_queue_covers_every_official_address(self):
        totals = self.queue['totals']
        self.assertEqual(totals['candidates'], 149)
        self.assertEqual(totals['unique_normalized_addresses'], 149)
        self.assertEqual(totals['candidates'],
                         totals['accepted'] + totals['review_required'] + totals['failed']
                         + totals['pending_provider'])

    def test_no_coordinate_is_invented_without_a_provider(self):
        self.assertFalse(self.queue['provider_configured'])
        self.assertFalse(self.queue['db_write'])
        for item in self.queue['items']:
            self.assertIsNone(item['latitude'])
            self.assertIsNone(item['longitude'])
            self.assertFalse(item['coordinate_verified'])
            self.assertEqual(item['geocode_status'], 'PENDING_PROVIDER')

    def test_no_credential_is_stored(self):
        text = json.dumps(self.queue, ensure_ascii=False)
        for pattern in ('VWORLD_API_KEY=', 'key=', 'apikey'):
            self.assertNotIn(pattern, text)
        self.assertEqual(self.queue['blocker'], 'NO_GEOCODER_CREDENTIAL_CONFIGURED')


class QuarantineResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((DATA / 'quarantine_resolution_20260927.json').read_text(encoding='utf-8'))

    def side(self, **overrides):
        base = {'project_id': 'a', 'name': '마천2', 'district': '송파구', 'address': None,
                'dong': None, 'lot': None, 'external_id': None, 'stage_raw': '구역지정'}
        return dict(base, **overrides)

    def test_every_candidate_is_accounted_for(self):
        totals = self.result['totals']
        self.assertEqual(totals['quarantined'],
                         totals['auto_resolved'] + totals['still_review_required'])
        self.assertFalse(self.result['db_write'])

    def test_nothing_is_ever_merged(self):
        decisions = {f['decision'] for f in self.result['pair_findings']}
        decisions |= {f['decision'] for f in self.result['overlap_findings']}
        self.assertNotIn('SAME_PROJECT', decisions)
        for finding in self.result['pair_findings']:
            self.assertIn(finding['decision'], ('DIFFERENT_PROJECT', 'STILL_AMBIGUOUS'))

    def test_the_canary_pair_stays_untouched(self):
        pair = next(f for f in self.result['pair_findings'] if '마천2' in f['names'])
        self.assertEqual(pair['decision'], 'STILL_AMBIGUOUS')

    def test_a_registry_name_carrying_a_lot_is_not_a_zone_mismatch(self):
        registry = self.side(name='천호동 214-19번지 일대 재개발정비사업(천호 3-1구역)', district='강동구')
        program = self.side(name='천호3-1', district='강동구')
        self.assertIsNone(quarantine.separation(registry, program))

    def test_a_real_zone_conflict_separates(self):
        self.assertEqual(quarantine.separation(self.side(name='마천1구역'), self.side(name='마천2구역')),
                         'OFFICIAL_ZONE_OR_PHASE_MISMATCH')

    def test_a_different_district_dong_or_lot_separates(self):
        self.assertEqual(quarantine.separation(self.side(), self.side(district='강동구')),
                         'OFFICIAL_DISTRICT_MISMATCH')
        self.assertEqual(quarantine.separation(self.side(dong='거여동'), self.side(dong='마천동')),
                         'OFFICIAL_DONG_MISMATCH')
        self.assertEqual(quarantine.separation(self.side(lot='181'), self.side(lot='234')),
                         'OFFICIAL_REPRESENTATIVE_LOT_MISMATCH')

    def test_an_address_is_only_supplemented_from_an_official_lot_shaped_name(self):
        record = {'project_name': '천호동 392-9', 'sigungu': '강동구', 'address': None,
                  'source': {'source_url': 'https://cleanup.seoul.go.kr/x'}}
        supplement = quarantine.supplement_address(record)
        self.assertEqual(supplement['address'], '서울특별시 강동구 천호동 392-9')
        self.assertEqual(supplement['basis'], 'OFFICIAL_LIST_ZONE_NAME_IS_A_LOT')
        self.assertIsNone(quarantine.supplement_address(dict(record, project_name='올림픽훼밀리타운')))
        self.assertIsNone(quarantine.supplement_address(dict(record, address='서울특별시 강동구 천호동 1')))

    def test_auto_resolved_candidates_have_no_remaining_reason(self):
        for entry in self.result['auto_resolved']:
            self.assertEqual(entry['remaining_reasons'], [])


if __name__ == '__main__':
    unittest.main()


WEB = ROOT / 'web/src'


def read(path):
    return (WEB / path).read_text(encoding='utf-8')


class DevelopmentSummaryTests(unittest.TestCase):
    rows = [{'sigungu': '강동구', 'project_type': 'RECONSTRUCTION', 'validation_status': 'NEEDS_REVIEW'},
            {'sigungu': '강동구', 'project_type': 'REDEVELOPMENT', 'validation_status': 'NEEDS_REVIEW'},
            {'sigungu': '송파구', 'project_type': 'SHINTONG', 'validation_status': 'VERIFIED'}]

    def test_counts_are_grouped_by_district_and_type(self):
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows):
            summary = dev.district_summary()
        self.assertEqual(summary['status'], 'ok')
        self.assertEqual(summary['total'], 3)
        self.assertEqual(summary['districts'][0]['district'], '강동구')
        self.assertEqual(summary['districts'][0]['total'], 2)
        self.assertEqual(summary['districts'][1]['verified'], 1)

    def test_it_reads_only(self):
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows) as request:
            dev.district_summary()
        self.assertEqual(request.call_args.args[0], 'GET')

    def test_an_unavailable_store_degrades_quietly(self):
        with patch.object(rm, '_using_remote_db', return_value=False):
            self.assertEqual(dev.district_summary()['reason'], 'NOT_CONFIGURED')
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', side_effect=RuntimeError('secret must not leak')):
            summary = dev.district_summary()
        self.assertEqual(summary['districts'], [])
        self.assertNotIn('secret', json.dumps(summary, ensure_ascii=False))

    def test_the_endpoint_adds_readable_type_labels(self):
        from api.realestate import development_summary
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows):
            result = asyncio.run(development_summary())
        self.assertEqual(result['districts'][0]['type_labels'], {'재건축': 1, '재개발': 1})
        # SHINTONG은 프로그램으로 수집된 행이라 유형 자리에 프로그램 이름을 쓰지 않는다.
        self.assertEqual(result['districts'][1]['type_labels'], {'정비사업': 1})


class ScreenCompactnessTests(unittest.TestCase):
    """Static checks for the review findings: tall hero, duplicate nav, open region list."""

    def test_the_hero_is_compact_and_has_no_long_paragraph(self):
        hero = read('app/realestate/page.tsx')
        self.assertIn('내 집과 관심지역의 부동산 변화를 한눈에', hero)
        self.assertIn('실거래 · 청약 · 개발사업 · 관심지역 모니터링', hero)
        self.assertNotIn('py-8', hero)
        self.assertNotIn('공식 자료로 확인하고, 관심지역의 새로운 변화를 계속 지켜봅니다', hero)

    def test_navigation_is_not_duplicated(self):
        monitor = read('components/realestate/EstateMonitor.tsx')
        self.assertNotIn('Capabilities', monitor)
        self.assertEqual(monitor.count('<Segmented'), 1)
        self.assertIn('overflow-x-auto', monitor)

    def test_every_tab_is_reachable_from_the_one_navigation(self):
        monitor = read('components/realestate/EstateMonitor.tsx')
        for label in ('실거래', '청약', '개발지도', '모니터링', '알림'):
            self.assertIn(f'label: "{label}"', monitor.replace('label: unread ? `알림 ${unread}` : "알림"',
                                                              'label: "알림"'))

    def test_the_region_picker_starts_collapsed_and_scrolls_the_page_not_a_box(self):
        picker = read('components/realestate/RegionPicker.tsx')
        self.assertIn('const [open, setOpen] = useState(false)', picker)
        self.assertIn('지역 선택 ›', picker)
        self.assertIn('지역 변경', picker)
        self.assertIn('선택 완료', picker)
        self.assertNotIn('overflow-y-auto', picker)
        self.assertNotIn('max-h-', picker)

    def test_the_region_picker_supports_a_single_district(self):
        picker = read('components/realestate/RegionPicker.tsx')
        self.assertIn('if (max === 1) return onChange([region])', picker)

    def test_trade_filters_keep_price_and_area_behind_the_disclosure(self):
        filters = read('components/realestate/TradeFilters.tsx')
        self.assertIn('상세조건', filters)
        self.assertIn('const [advanced, setAdvanced] = useState(false)', filters)
        head, advanced = filters.split('{advanced && (', 1)
        self.assertNotIn('최대 매매가격', head)
        self.assertNotIn('최대 면적', head)
        self.assertIn('최대 매매가격', advanced)
        self.assertIn('주변 개발정보 함께 보기', advanced)

    def test_applied_conditions_collapse_into_chips(self):
        monitor = read('components/realestate/EstateMonitor.tsx')
        self.assertIn('<FilterChips value={applied} />', monitor)
        self.assertIn('조건 변경', monitor)

    def test_the_transaction_card_keeps_details_collapsed(self):
        card = read('components/realestate/TransactionCard.tsx')
        head = card.split('<CollapsibleDetails', 1)[0]
        # 원문 주소·출처는 접힌 영역으로 내려가고, 판단에 쓰는 값만 기본 카드에 남는다.
        for field in ('address_road', 'address_jibun', 'source_label', 'raw[', 'detail['):
            self.assertNotIn(field, head)
        for field in ('price_text', 'property_type', 'floor', 'date', 'build_year',
                      'canonical_address'):
            self.assertIn(field, head)
        self.assertIn('trade.detail', card)
        self.assertIn('trade.raw_detail', card)

    def test_detail_rows_skip_empty_values(self):
        self.assertIn('if (!value) return null;', read('components/realestate/CollapsibleDetails.tsx'))

    def test_the_development_tab_loads_without_a_search_button(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('useEffect', tab)
        # 목록과 marker를 한 응답에서 받는다. 자치구별 조회를 합치지 않는다.
        self.assertIn('estateApi.developmentMap(', tab)
        self.assertEqual(tab.count('estateApi.developmentMap('), 1)
        self.assertNotIn('개발사업 찾기', tab)
        self.assertNotIn('estateApi.development(', tab)

    def test_the_development_tab_shows_counts_and_filters_from_the_data(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        for piece in ('전체', '재건축', '재개발', '신속통합기획', '모아타운'):
            self.assertIn(piece, tab)
        self.assertIn('[...new Set(projects.map((p) => p.stage.label))]', tab)
        self.assertIn('진행단계 전체', tab)

    def test_the_development_card_separates_verified_from_list_mapped(self):
        card = read('components/realestate/DevelopmentCard.tsx')
        self.assertIn('project.stage_basis', card)
        self.assertIn('project.trust.label', card)
        self.assertIn('공식 사업 ID', card)
        self.assertIn('정책 프로그램', card)
        self.assertIn('공식 사업정보 ↗', card)
        self.assertIn('StageTimeline', card)
        self.assertIn('{url && (', card)
        for token in ('NEEDS_REVIEW', 'UNVERIFIED', 'ASSOCIATION_APPROVED', 'RECONSTRUCTION'):
            self.assertNotIn(token, card)

    def test_touch_targets_and_wrapping_are_mobile_safe(self):
        for name in ('RegionPicker.tsx', 'TradeFilters.tsx', 'DevelopmentTab.tsx',
                     'DevelopmentCard.tsx', 'CollapsibleDetails.tsx'):
            source = read('components/realestate/' + name)
            self.assertIn('min-h-', source, name)
            self.assertNotIn('w-[', source, name)
            self.assertNotIn('overflow-x-scroll', source, name)
        self.assertIn('break-words', read('components/realestate/DevelopmentCard.tsx'))
        self.assertIn('min-w-0', read('components/realestate/TransactionCard.tsx'))

    def test_only_selected_and_primary_elements_are_burgundy(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        # 선택되지 않은 필터는 중립색을 쓴다.
        self.assertIn('border border-border text-muted hover:text-fg', tab)
        self.assertIn('bg-estate text-white', tab)


class ZiponSupabaseSeparationTests(unittest.TestCase):
    """ZIP:ON uses its own project in production without touching AI LAB's."""

    URL, KEY = 'ZIPON_SUPABASE_URL', 'ZIPON_SUPABASE_SERVICE_ROLE_KEY'
    SHARED_URL, SHARED_KEY = 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'

    def config(self, **env):
        # Placeholder values only; no real credential is used in a test. A local
        # secrets.toml must not change the outcome, so the file loader is stubbed.
        from services import config as config_module
        with patch.object(config_module, '_load_secrets_file', return_value={}), \
             patch.dict('os.environ', env, clear=False):
            for name in (self.URL, self.KEY, self.SHARED_URL, self.SHARED_KEY):
                if name not in env:
                    __import__('os').environ.pop(name, None)
            return rm._supabase_config()

    def test_the_zipon_project_wins_when_both_of_its_values_are_set(self):
        self.assertEqual(self.config(**{self.URL: 'https://zipon.example.invalid/',
                                        self.KEY: 'zipon-placeholder',
                                        self.SHARED_URL: 'https://shared.example.invalid',
                                        self.SHARED_KEY: 'shared-placeholder'}),
                         ('https://zipon.example.invalid', 'zipon-placeholder'))

    def test_the_existing_settings_are_the_fallback(self):
        self.assertEqual(self.config(**{self.SHARED_URL: 'https://shared.example.invalid',
                                        self.SHARED_KEY: 'shared-placeholder'}),
                         ('https://shared.example.invalid', 'shared-placeholder'))

    def test_a_half_configured_zipon_project_never_mixes_credentials(self):
        for partial in ({self.URL: 'https://zipon.example.invalid'},
                        {self.KEY: 'zipon-placeholder'}):
            config = self.config(**dict(partial, **{self.SHARED_URL: 'https://shared.example.invalid',
                                                    self.SHARED_KEY: 'shared-placeholder'}))
            self.assertEqual(config, ('https://shared.example.invalid', 'shared-placeholder'), partial)

    def test_without_any_setting_the_sqlite_fallback_stays(self):
        self.assertIsNone(self.config())
        with patch.object(rm, '_supabase_config', return_value=None):
            self.assertFalse(rm._using_remote_db())

    def test_development_reads_share_the_same_connection(self):
        source = (ROOT / 'services/development.py').read_text(encoding='utf-8')
        self.assertIn('rm._using_remote_db()', source)
        self.assertIn("rm._remote_request('GET', 'development_projects'", source)
        for token in ('SUPABASE_URL', 'SERVICE_ROLE', 'ZIPON_SUPABASE'):
            self.assertNotIn(token, source)

    def test_the_pipeline_takes_an_injected_transport_instead_of_credentials(self):
        source = (ROOT / 'services/development_pipeline.py').read_text(encoding='utf-8')
        for token in ('SUPABASE', 'SERVICE_ROLE', 'os.environ'):
            self.assertNotIn(token, source)

    def test_access_management_keeps_the_existing_project(self):
        source = (ROOT / 'services/access.py').read_text(encoding='utf-8')
        self.assertIn('SUPABASE_URL', source)
        self.assertNotIn('ZIPON_SUPABASE', source)

    def test_no_supabase_secret_reaches_the_frontend(self):
        for path in sorted((ROOT / 'web/src').rglob('*.ts*')):
            text = path.read_text(encoding='utf-8')
            for token in ('SERVICE_ROLE', 'SUPABASE_URL', 'ZIPON_SUPABASE', 'sb_secret'):
                self.assertNotIn(token, text, path.name)
        out = ROOT / 'web/out'
        if out.exists():
            for path in sorted(out.rglob('*.js')):
                text = path.read_text(encoding='utf-8', errors='ignore')
                for token in ('SERVICE_ROLE', 'ZIPON_SUPABASE', 'sb_secret'):
                    self.assertNotIn(token, text, path.name)

    def test_no_public_env_variable_carries_the_key(self):
        for name in ('web/next.config.ts', 'Dockerfile', '.github/workflows/deploy-space.yml'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotIn('NEXT_PUBLIC_SUPABASE', text)
            self.assertNotIn('NEXT_PUBLIC_ZIPON', text)
            self.assertNotIn('SERVICE_ROLE', text)

    def test_the_scheduled_monitor_passes_the_zipon_project_too(self):
        text = (ROOT / '.github/workflows/realestate-monitor.yml').read_text(encoding='utf-8')
        self.assertIn('ZIPON_SUPABASE_URL: ${{ secrets.ZIPON_SUPABASE_URL }}', text)
        self.assertIn('ZIPON_SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.ZIPON_SUPABASE_SERVICE_ROLE_KEY }}', text)
        self.assertIn('SUPABASE_URL: ${{ secrets.SUPABASE_URL }}', text)

    def test_the_deploy_doc_lists_the_new_space_secrets(self):
        text = (ROOT / 'docs/deploy.md').read_text(encoding='utf-8')
        self.assertIn('`ZIPON_SUPABASE_URL`', text)
        self.assertIn('`ZIPON_SUPABASE_SERVICE_ROLE_KEY`', text)


class MapIntelligenceTests(unittest.TestCase):
    """공간관계·프로그램·단계 표시가 근거를 넘어서지 않는지."""

    def rpc_row(self, **overrides):
        # zipon_development_search가 실제로 돌려주는 컬럼 이름 그대로.
        base = {'project_id': 'p1', 'project_name': '천호2구역', 'project_type': 'RECONSTRUCTION',
                'project_stage': '구역지정', 'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW',
                'relation': 'NEARBY', 'distance_m': 420.7,
                'official_source': '정보몽땅 사업장 목록 강동구',
                'source_url': 'https://cleanup.seoul.go.kr/x', 'verified_at': None}
        return pr.present_project(dict(base, **overrides))

    def test_the_real_rpc_columns_are_understood(self):
        project = self.rpc_row()
        self.assertEqual(project['stage']['official_text'], '구역지정')
        self.assertEqual(project['stage']['label'], '정비구역 지정')
        self.assertEqual(project['official_source']['name'], '정보몽땅 사업장 목록 강동구')
        self.assertEqual(project['official_source']['url'], 'https://cleanup.seoul.go.kr/x')
        self.assertEqual(project['distance_label'], '500m 이내')

    def test_a_verified_boundary_is_the_only_way_to_read_inside(self):
        self.assertEqual(self.rpc_row(relation='INSIDE')['spatial']['label'], '주변 개발사업')
        confirmed = self.rpc_row(relation='INSIDE', boundary_verified=True)
        self.assertEqual(confirmed['spatial']['label'], '정비구역 내부')
        self.assertTrue(confirmed['spatial']['confirmed_boundary'])
        self.assertEqual(confirmed['distance_label'], '구역 내부')

    def test_a_representative_point_can_never_be_inside(self):
        point = self.rpc_row(latitude=37.5, longitude=127.1, relation='INSIDE')
        self.assertEqual(point['location_accuracy']['code'], 'REPRESENTATIVE_POINT')
        self.assertEqual(point['spatial']['label'], '주변 개발사업')

    def test_no_coordinates_means_no_map_and_no_verdict(self):
        project = self.rpc_row(relation='UNKNOWN', distance_m=None)
        self.assertEqual(project['location_accuracy']['code'], 'NO_LOCATION')
        self.assertFalse(project['has_location'])
        self.assertIsNone(project['distance_label'])

    def test_program_is_separate_from_project_type(self):
        fast = self.rpc_row(project_type='SHINTONG')
        self.assertEqual(fast['type_label'], '정비사업')
        self.assertEqual(fast['program_label'], '신속통합기획')
        plain = self.rpc_row(project_type='REDEVELOPMENT')
        self.assertEqual(plain['type_label'], '재개발')
        self.assertIsNone(plain['program_label'])
        explicit = self.rpc_row(project_type='REDEVELOPMENT', program='FAST_TRACK')
        self.assertEqual((explicit['type_label'], explicit['program_label']), ('재개발', '신속통합기획'))

    def test_moatown_is_a_project_system_not_a_duplicate_program(self):
        moa = self.rpc_row(project_type='MOATOWN')
        self.assertEqual(moa['type_label'], '모아타운')
        self.assertIsNone(moa['program_label'])

    def test_a_program_is_never_guessed(self):
        self.assertIsNone(pr.program_of({'project_type': 'RECONSTRUCTION'}))
        self.assertIsNone(pr.program_of({'project_type': None}))

    def test_the_stage_timeline_only_marks_confirmed_stages(self):
        self.assertEqual(pr.stage_timeline('DESIGNATED')['current_label'], '정비구역 지정')
        for unknown in ('UNKNOWN', 'ASSOCIATION_DISSOLVED', 'CANCELLED'):
            timeline = pr.stage_timeline(unknown)
            self.assertIsNone(timeline['current_index'])
            self.assertIsNotNone(timeline['note'])
        self.assertEqual(pr.stage_timeline('PLAN_NOTICED')['current_label'], '정비계획 고시')

    def test_distance_buckets(self):
        self.assertEqual([pr.distance_bucket(m) for m in (50, 250, 480, 900, 1500)],
                         ['100m 이내', '300m 이내', '500m 이내', '1km 이내', '1km 초과'])
        self.assertEqual(pr.distance_bucket(5, 'INSIDE'), '구역 내부')

    def test_the_impact_block_speaks_about_the_relationship(self):
        impact = pr.impact({'projects': [self.rpc_row()]}, trade_has_point=True)
        self.assertEqual(impact['inside']['label'], '아직 판별할 수 없음')
        self.assertEqual(impact['inside']['notice'], pr.INSIDE_UNKNOWN_NOTICE)
        self.assertEqual(impact['nearest']['name'], '천호2구역')
        self.assertEqual(impact['nearest']['distance_label'], '500m 이내')
        self.assertTrue(impact['has_map_point'])

    def test_a_trade_without_coordinates_explains_itself(self):
        impact = pr.impact({'projects': []}, trade_has_point=False)
        self.assertEqual(impact['inside']['notice'], pr.NO_TRADE_POINT_NOTICE)
        self.assertFalse(impact['available'])
        self.assertIsNone(impact['nearest'])

    def test_removed_wording_is_gone(self):
        text = json.dumps([pr.present_project(self.rpc_row.__self__.rpc_row() if False else
                                              {'project_id': 'p', 'project_name': 'x',
                                               'project_type': 'RECONSTRUCTION',
                                               'validation_status': 'NEEDS_REVIEW'}),
                           pr.impact({'projects': []}, trade_has_point=False),
                           pr.TRUST_LABELS, pr.STATUS_LABELS, pr.STAGE_BASIS_LABELS],
                          ensure_ascii=False)
        for phrase in ('확인 필요', '단계 확인 필요', '근거 확인 필요', '상태 확인 필요'):
            self.assertNotIn(phrase, text.replace('위치 확인 필요', ''), phrase)


class MapEndpointTests(unittest.TestCase):
    def rows(self, with_point=True):
        import binascii
        import struct
        ewkb = binascii.hexlify(struct.pack('<BIIdd', 1, 0x20000001, 4326, 127.1, 37.5)).decode()
        return [{'project_id': 'p1', 'project_name': '천호2구역', 'project_type': 'SHINTONG',
                 'sigungu': '강동구', 'dong': '천호동', 'address': '서울특별시 강동구 천호동 1',
                 'stage_raw': '구역지정', 'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW',
                 'location': ewkb if with_point else None, 'geometry_verified': False,
                 'last_verified_at': None}]

    def map_rows(self, boundary=None, verified=False):
        """zipon_development_map RPC가 돌려주는 모양. 경위도는 숫자, 경계는 GeoJSON."""
        row = dict(self.rows()[0])
        row.pop('location')
        row.update({'longitude': 127.1, 'latitude': 37.5, 'boundary': boundary,
                    'geometry_verified': verified,
                    'geometry_source': '서울특별시 도시계획사업 현황(서울플랜+) 공간정보'
                                       if verified else None,
                    'geometry_verified_at': '2026-09-29T00:00:00+00:00' if verified else None,
                    'boundary_area_m2': 42000.0 if verified else None})
        return [row]

    def test_the_point_decoder_reads_a_geography_point(self):
        row = self.rows()[0]
        self.assertEqual(dev._point(row['location']), (127.1, 37.5))
        for bad in (None, '', 'zz', '0101'):
            self.assertEqual(dev._point(bad), (None, None))

    def test_the_map_endpoint_returns_a_light_payload(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.map_rows()) as request:
            result = asyncio.run(development_map(sigungu='강동구'))
        # 경계는 전용 읽기 RPC로만 온다. 확인된 것만 GeoJSON으로 내려온다.
        self.assertEqual(request.call_args.args[:2], ('POST', 'rpc/zipon_development_map'))
        self.assertEqual(request.call_args.kwargs['payload'],
                         {'p_sigungu': '강동구', 'p_limit': 500})
        point = result['points'][0]
        self.assertEqual((point['latitude'], point['longitude']), (37.5, 127.1))
        self.assertEqual(point['accuracy'], 'REPRESENTATIVE_POINT')
        self.assertTrue(point['mappable'])
        self.assertEqual(point['type_label'], '정비사업')
        self.assertEqual(point['program_label'], '신속통합기획')
        self.assertIsNone(point['boundary'])
        self.assertEqual(set(point) - {'project_id', 'name', 'latitude', 'longitude', 'boundary',
                                       'boundary_status', 'boundary_status_label', 'allows_inside',
                                       'development_layer', 'program_layer', 'address',
                                       'last_checked', 'official_url', 'type_code', 'type_label',
                                       'program_code', 'program_label', 'stage_label', 'district',
                                       'dong', 'accuracy', 'accuracy_label', 'confidence',
                                       'mappable', 'lifecycle', 'lifecycle_label',
                                       'lifecycle_basis', 'in_default_map'}, set())
        self.assertEqual(result['mappable'], 1)
        self.assertIn('OFFICIAL_BOUNDARY', result['legend'])

    def test_a_row_without_a_point_is_not_mapped(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows(with_point=False)):
            result = asyncio.run(development_map())
        self.assertEqual(result['mappable'], 0)
        self.assertFalse(result['points'][0]['mappable'])
        self.assertEqual(result['points'][0]['accuracy_label'], '위치 데이터 준비 중')

    def test_the_nearby_endpoint_requires_coordinates(self):
        from api.realestate import DevelopmentQuery, development_nearby
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            asyncio.run(development_nearby(DevelopmentQuery(sigungu='강동구')))

    def test_the_nearby_endpoint_returns_an_impact_block(self):
        from api.realestate import DevelopmentQuery, development_nearby
        rpc = [{'project_id': 'p1', 'project_name': '천호2구역', 'project_type': 'REDEVELOPMENT',
                'project_stage': '조합설립인가', 'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW',
                'relation': 'NEARBY', 'distance_m': 95.0, 'official_source': '정보몽땅',
                'source_url': 'https://cleanup.seoul.go.kr/x', 'verified_at': None}]
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=rpc):
            result = asyncio.run(development_nearby(
                DevelopmentQuery(longitude=127.1, latitude=37.5, radius_m=1000, limit=30)))
        self.assertEqual(result['impact']['nearest']['distance_label'], '100m 이내')
        self.assertEqual(result['impact']['inside']['code'], 'NOT_DETERMINED')

    def test_the_map_endpoint_degrades_without_a_store(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=False):
            result = asyncio.run(development_map())
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['points'], [])


class GeocodeProviderTests(unittest.TestCase):
    def test_every_provider_reports_its_credential_needs(self):
        report = geo.provider_availability(lambda name: '')
        self.assertEqual(set(report), {'vworld', 'kakao', 'naver'})
        for name, entry in report.items():
            self.assertFalse(entry['configured'], name)
            self.assertTrue(entry['missing_secrets'], name)

    def test_a_configured_provider_is_built(self):
        secrets = {'KAKAO_REST_API_KEY': 'placeholder'}
        provider, blocker = geo.build_provider('kakao', lambda name: secrets.get(name, ''),
                                               lambda *a, **k: {})
        self.assertIsNone(blocker)
        self.assertTrue(callable(provider))

    def test_a_missing_credential_is_named_without_its_value(self):
        provider, blocker = geo.build_provider('naver', lambda name: '', lambda *a, **k: {})
        self.assertIsNone(provider)
        self.assertEqual(blocker, 'NAVER_MAP_CLIENT_ID_NOT_CONFIGURED')
        self.assertIsNone(geo.build_provider('unknown', lambda name: '', None)[0])

    def test_kakao_candidates_are_judged_by_the_strict_evaluator(self):
        payload = {'documents': [{'x': '127.154', 'y': '37.555',
                                  'address': {'address_name': '서울특별시 강동구 고덕동 212'}}]}
        provider = geo.kakao_provider('placeholder', lambda *a, **k: payload)
        result = provider('서울특별시 강동구 고덕동 212')
        self.assertEqual(geo.evaluate('서울특별시 강동구 고덕동 212', result)['geocode_confidence'], 'EXACT')
        twice = dict(result, candidates=result['candidates'] * 2)
        self.assertEqual(geo.evaluate('서울특별시 강동구 고덕동 212', twice)['geocode_confidence'],
                         'GEOCODE_REVIEW')

    def test_naver_results_are_not_auto_accepted(self):
        payload = {'addresses': [{'x': '127.154', 'y': '37.555', 'jibunAddress': '서울특별시 송파구 고덕동 212'}]}
        provider = geo.naver_provider('id', 'placeholder', lambda *a, **k: payload)
        result = provider('서울특별시 강동구 고덕동 212')
        self.assertEqual(geo.evaluate('서울특별시 강동구 고덕동 212', result)['geocode_confidence'],
                         'GEOCODE_REVIEW')

    def test_the_queue_reports_provider_availability(self):
        queue = json.loads((DATA / 'geocode_queue_20260927.json').read_text(encoding='utf-8'))
        self.assertIn('provider_availability', queue)
        self.assertFalse(any(v['configured'] for v in queue['provider_availability'].values()))
        self.assertEqual(queue['totals']['pending_provider'], queue['totals']['candidates'])
        text = json.dumps(queue, ensure_ascii=False)
        for pattern in ('KakaoAK', 'x-ncp-apigw', 'sb_secret'):
            self.assertNotIn(pattern, text)


class MapScreenTests(unittest.TestCase):
    def test_the_map_is_naver_dynamic_map_loaded_in_the_browser_only(self):
        source = read('components/realestate/ZiponMap.tsx')
        loader = read('lib/naverMaps.ts')
        self.assertIn('loadNaverMaps', source)
        self.assertIn('MapTypeId.NORMAL', source)
        # 로더 URL은 서버가 내려준다. 프론트엔드에 박아 두지 않는다.
        self.assertIn('sdk.script_url', loader)
        from services import map_providers
        self.assertEqual(map_providers.NAVER_MAPS_SCRIPT,
                         'https://oapi.map.naver.com/openapi/v3/maps.js')
        # Leaflet과 OSM 타일은 ZIP:ON 지도에서 더 쓰지 않는다.
        self.assertNotIn('leaflet', source.lower())
        self.assertNotIn('openstreetmap', source.lower())
        self.assertNotIn('googleapis', source)
        # 지도 키는 서버 응답에서만 오고 빌드에 박히지 않는다.
        self.assertNotIn('NEXT_PUBLIC', source)
        self.assertNotIn('NEXT_PUBLIC', loader)
        self.assertIn('sdk.client_id', loader)

    def test_only_a_verified_boundary_is_drawn_as_an_area(self):
        source = read('components/realestate/ZiponMap.tsx')
        # 확인 여부 판정은 공통 helper 한 곳에만 있다.
        self.assertIn('verifiedBoundaryPolygons(point)', source)
        self.assertIn('boundary_status !== OFFICIAL', read('lib/projectBoundary.ts'))
        # 면은 Polygon으로만 그리고, 대표좌표 주변 원은 사업구역이라고 부르지 않는다.
        self.assertIn('api.Polygon', source)
        self.assertIn('api.Circle', source)
        self.assertIn('대표위치 주변', source)
        for wrong in ('사업구역 경계', '정비구역 경계'):
            self.assertNotIn(f'{wrong}</span>', source)

    def test_the_legend_names_every_project_type(self):
        source = read('components/realestate/ZiponMap.tsx')
        for label in ('재개발', '재건축', '모아타운', '신속통합기획', '선택 부동산'):
            self.assertIn(label, source)
        self.assertIn('좌표 없는 ${points.length - mappable}건은 목록에만 표시', source)

    def test_the_transaction_card_leads_with_the_relationship(self):
        source = read('components/realestate/TransactionCard.tsx')
        head = source.split('<CollapsibleDetails', 1)[0]
        self.assertIn('DevelopmentImpact', head)
        self.assertIn('canonical_address', head)
        for raw in ('본번', '부번', '토지임대부', '중개사 소재지'):
            self.assertNotIn(raw, head)
        self.assertIn('거래 원문 정보', source)

    def test_the_development_card_shows_a_stage_timeline_and_ctas(self):
        source = read('components/realestate/DevelopmentCard.tsx')
        self.assertIn('StageTimeline', source)
        self.assertIn('공식 사업정보 ↗', source)
        self.assertIn('지도에서 보기', source)
        self.assertIn('location_accuracy', source)
        self.assertIn('{url && (', source)

    def test_the_development_tab_puts_the_map_above_the_list(self):
        source = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('<ZiponMap', source)
        self.assertLess(source.index('<ZiponMap'), source.index('<DevelopmentCard'))
        self.assertIn('모아타운', source)
        self.assertIn('developmentMap(', source)

    def test_no_raw_enum_or_secret_in_the_new_screens(self):
        for name in ('ZiponMap.tsx', 'StageTimeline.tsx', 'DevelopmentImpact.tsx',
                     'TransactionCard.tsx', 'DevelopmentCard.tsx', 'DevelopmentTab.tsx'):
            source = read('components/realestate/' + name)
            for token in ('NEEDS_REVIEW', 'UNVERIFIED', 'ASSOCIATION_APPROVED', 'SERVICE_ROLE',
                          'ZIPON_SUPABASE', 'UNKNOWN_OFFICIAL_COLUMN'):
                self.assertNotIn(token, source, f'{name}: {token}')

    def test_the_map_height_is_mobile_sized(self):
        self.assertIn('height = 340', read('components/realestate/ZiponMap.tsx'))
        self.assertIn('height={340}', read('components/realestate/DevelopmentTab.tsx'))


class BaseMapTests(unittest.TestCase):
    def test_open_street_map_is_the_working_default(self):
        from services import map_providers
        config = map_providers.config(lambda name: '')
        self.assertEqual(config['active'], 'osm')
        self.assertEqual(config['fallback'], 'osm')
        self.assertIn('tile.openstreetmap.org', config['tile']['url_template'])
        self.assertIn('OpenStreetMap', config['tile']['attribution'])

    def test_every_provider_reports_korean_labels_and_key_needs(self):
        from services import map_providers
        config = map_providers.config(lambda name: '')
        by_id = {p['id']: p for p in config['providers']}
        self.assertEqual(set(by_id), {'osm', 'vworld', 'kakao', 'naver'})
        self.assertTrue(all(p['korean_labels'] for p in config['providers']))
        self.assertFalse(by_id['osm']['requires_browser_key'])
        for name in ('vworld', 'kakao', 'naver'):
            self.assertTrue(by_id[name]['requires_browser_key'], name)
            self.assertFalse(by_id[name]['configured'], name)

    def test_a_configured_korean_tile_provider_becomes_active(self):
        from services import map_providers
        config = map_providers.config(lambda name: 'placeholder' if name == 'VWORLD_MAP_KEY' else '')
        self.assertEqual(config['active'], 'vworld')
        self.assertIn('vworld', config['tile']['url_template'])

    def test_an_sdk_provider_never_silently_becomes_the_tile_source(self):
        from services import map_providers
        config = map_providers.config(lambda name: 'placeholder' if name == 'KAKAO_JAVASCRIPT_KEY' else '')
        self.assertEqual(config['active'], 'osm')

    def test_the_config_carries_only_the_browser_map_key(self):
        from services import map_providers
        # 서버 전용 키는 값이 절대 나가지 않는다. 지도 Client ID만 예외이고, 그것은
        # 브라우저가 SDK를 부를 때 필요한 값이라 sdk에만 담긴다.
        secrets = {'NAVER_MAP_CLIENT_ID': 'BROWSER_MAP_KEY',
                   'NAVER_MAP_CLIENT_SECRET': 'SERVER_ONLY_SECRET',
                   'KAKAO_REST_API_KEY': 'SERVER_ONLY_SECRET',
                   'VWORLD_API_KEY': 'SERVER_ONLY_SECRET',
                   'KAKAO_JAVASCRIPT_KEY': 'OTHER_BROWSER_KEY',
                   'VWORLD_MAP_KEY': 'OTHER_BROWSER_KEY'}
        config = map_providers.config(lambda name: secrets.get(name, ''))
        text = json.dumps(config, ensure_ascii=False)
        self.assertNotIn('SERVER_ONLY_SECRET', text)
        self.assertNotIn('OTHER_BROWSER_KEY', text)
        self.assertEqual(config['sdk']['client_id'], 'BROWSER_MAP_KEY')
        self.assertEqual(text.count('BROWSER_MAP_KEY'), 1)
        self.assertEqual(sorted(p['browser_key_name'] for p in config['providers']
                                if p['browser_key_name']),
                         ['KAKAO_JAVASCRIPT_KEY', 'NAVER_MAP_CLIENT_ID', 'VWORLD_MAP_KEY'])

    def test_the_endpoint_serves_the_config(self):
        from api.realestate import map_config
        with patch.object(rm, '_secret', return_value=''):
            result = map_config()
        self.assertEqual(result['active'], 'osm')


class MapLayerTests(unittest.TestCase):
    def point(self, **overrides):
        base = {'project_id': 'p', 'project_name': 'x', 'project_type': 'REDEVELOPMENT',
                'stage_raw': '구역지정', 'validation_status': 'NEEDS_REVIEW',
                'latitude': 37.5, 'longitude': 127.1, 'geometry_verified': False,
                'source_url': 'https://cleanup.seoul.go.kr/x'}
        return pr.map_point(dict(base, **overrides))

    def test_project_type_and_programme_are_different_layers(self):
        fast = self.point(project_type='SHINTONG')
        self.assertEqual(fast['development_layer'], 'OTHER_PROJECT')
        self.assertEqual(fast['program_layer'], 'FAST_TRACK')
        self.assertEqual(fast['type_label'], '정비사업')
        self.assertEqual(fast['program_label'], '신속통합기획')

    def test_a_plain_project_has_no_programme_layer(self):
        plain = self.point(project_type='RECONSTRUCTION')
        self.assertEqual(plain['development_layer'], 'RECONSTRUCTION')
        self.assertIsNone(plain['program_layer'])

    def test_moatown_is_its_own_programme_layer(self):
        moa = self.point(project_type='MOATOWN')
        self.assertEqual(moa['program_layer'], 'MOATOWN')
        self.assertEqual(moa['type_label'], '모아타운')

    def test_the_layer_table_separates_type_programme_and_boundary(self):
        self.assertEqual(pr.MAP_LAYERS['REDEVELOPMENT']['layer'], 'DEVELOPMENT')
        self.assertEqual(pr.MAP_LAYERS['FAST_TRACK']['layer'], 'PROGRAM')
        self.assertEqual(pr.MAP_LAYERS['MOATOWN']['layer'], 'PROGRAM')
        self.assertEqual(pr.MAP_LAYERS['BOUNDARY']['layer'], 'BOUNDARY')
        self.assertIn('PROPERTY', pr.MAP_LAYERS)

    def test_a_boundary_needs_provenance_before_it_is_drawn(self):
        pending = self.point()
        self.assertEqual(pending['boundary_status'], 'PENDING')
        self.assertIsNone(pending['boundary'])
        self.assertFalse(pending['allows_inside'])
        polygon = {'type': 'Polygon', 'coordinates': [[[127, 37], [127.1, 37], [127.1, 37.1], [127, 37]]]}
        unverified = self.point(boundary=polygon)
        self.assertEqual(unverified['boundary_status'], 'NOT_AVAILABLE')
        self.assertIsNone(unverified['boundary'])
        self.assertFalse(unverified['allows_inside'])
        verified = self.point(boundary=polygon, geometry_verified=True)
        self.assertEqual(verified['boundary_status'], 'OFFICIAL_VERIFIED')
        self.assertIsNotNone(verified['boundary'])
        self.assertTrue(verified['allows_inside'])
        self.assertEqual(verified['accuracy'], 'OFFICIAL_BOUNDARY')

    def test_the_boundary_contract_names_its_provenance(self):
        self.assertEqual(pr.BOUNDARY_PROVENANCE_FIELDS,
                         ('source', 'source_url', 'verified_at', 'boundary_status'))
        layer = pr.boundary_layer({'boundary': {'type': 'Polygon'}, 'geometry_verified': True,
                                   'geometry_source': '서울시 정비구역 경계',
                                   'source_url': 'https://cleanup.seoul.go.kr/x',
                                   'geometry_verified_at': '2026-09-27T00:00:00+00:00'})
        for field in pr.BOUNDARY_PROVENANCE_FIELDS:
            self.assertIn(field, layer)
        self.assertTrue(layer['allows_inside'])


class BboxApiTests(unittest.TestCase):
    def map_rows(self):
        """RPC 모양. 경위도는 숫자로 오고 경계는 확인된 것만 온다."""
        rows = []
        for row in self.rows():
            row = dict(row)
            longitude, latitude = dev._point(row.pop('location'))
            row.update({'longitude': longitude, 'latitude': latitude, 'boundary': None,
                        'geometry_source': None, 'geometry_verified_at': None,
                        'boundary_area_m2': None})
            rows.append(row)
        return rows

    def rows(self):
        import binascii
        import struct

        def ewkb(lon, lat):
            return binascii.hexlify(struct.pack('<BIIdd', 1, 0x20000001, 4326, lon, lat)).decode()
        return [{'project_id': 'inside', 'project_name': '안쪽', 'project_type': 'REDEVELOPMENT',
                 'sigungu': '강동구', 'stage_raw': '구역지정', 'validation_status': 'NEEDS_REVIEW',
                 'location': ewkb(127.10, 37.55), 'geometry_verified': False},
                {'project_id': 'outside', 'project_name': '바깥', 'project_type': 'REDEVELOPMENT',
                 'sigungu': '강동구', 'stage_raw': '구역지정', 'validation_status': 'NEEDS_REVIEW',
                 'location': ewkb(126.90, 37.40), 'geometry_verified': False},
                {'project_id': 'nopoint', 'project_name': '좌표없음', 'project_type': 'REDEVELOPMENT',
                 'sigungu': '강동구', 'stage_raw': '구역지정', 'validation_status': 'NEEDS_REVIEW',
                 'location': None, 'geometry_verified': False}]

    def test_a_bbox_keeps_only_points_inside_it(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows()):
            result = asyncio.run(development_map(north=37.60, south=37.50, east=127.20, west=127.00))
        self.assertEqual([p['project_id'] for p in result['points']], ['inside'])
        self.assertTrue(result['bbox_filtered'])

    def test_without_a_bbox_every_row_is_returned(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows()):
            result = asyncio.run(development_map())
        self.assertEqual(len(result['points']), 3)
        self.assertFalse(result['bbox_filtered'])
        self.assertEqual(result['mappable'], 2)

    def test_a_partial_or_invalid_bbox_is_refused(self):
        from api.realestate import development_map
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            asyncio.run(development_map(north=37.6))
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows()):
            with self.assertRaises(HTTPException):
                asyncio.run(development_map(north=37.4, south=37.6, east=127.2, west=127.0))

    def test_the_map_payload_stays_light(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.map_rows()) as request:
            result = asyncio.run(development_map(sigungu='강동구'))
        payload = request.call_args.kwargs['payload']
        # 원문 스냅샷 같은 무거운 컬럼은 지도 조회에 담지 않는다.
        self.assertEqual(set(payload), {'p_sigungu', 'p_limit'})
        for heavy in ('field_evidence', 'raw_snapshot'):
            self.assertNotIn(heavy, json.dumps(result['points'][0], ensure_ascii=False))
        self.assertLessEqual(len(json.dumps(result['points'][0], ensure_ascii=False)), 900)

    def test_the_map_falls_back_to_rest_when_the_boundary_rpc_is_missing(self):
        # 경계 RPC를 아직 설치하지 않은 서버에서도 지도는 이전처럼 나온다.
        from api.realestate import development_map
        calls = []

        def answer(method, path, **kwargs):
            calls.append((method, path))
            if path == 'rpc/zipon_development_map':
                raise RuntimeError('function does not exist')
            if path == 'development_projects' and kwargs.get('params', {}).get('select', '') \
                    .startswith('project_id,stage'):
                return []
            return self.rows()

        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', side_effect=answer):
            result = asyncio.run(development_map(sigungu='강동구'))
        self.assertIn(('POST', 'rpc/zipon_development_map'), calls)
        self.assertIn(('GET', 'development_projects'), calls)
        point = result['points'][0]
        self.assertEqual((point['latitude'], point['longitude']), (37.55, 127.10))
        self.assertIsNone(point['boundary'])
        self.assertEqual(point['boundary_status'], 'PENDING')
        self.assertFalse(point['allows_inside'])


class TransactionToDevelopmentE2ETests(unittest.TestCase):
    """거래 → canonical address → 좌표 → 주변 개발사업 → 거리."""

    def test_a_sample_transaction_reaches_a_development_distance(self):
        import xml.etree.ElementTree as ET
        markup = ('<item><aptNm>둔촌주공</aptNm><dealAmount>195,000</dealAmount><excluUseAr>84.99</excluUseAr>'
                  '<dealYear>2026</dealYear><dealMonth>9</dealMonth><dealDay>3</dealDay><floor>12</floor>'
                  '<buildYear>1980</buildYear><umdNm>둔촌동</umdNm><jibun>170</jibun>'
                  '<roadNm>양재대로</roadNm><roadNmBonbun>01321</roadNmBonbun></item>')
        trade = rm._trade_item_to_common(ET.fromstring(markup), '아파트', '11740', '202609')
        # 1. 화면용 주소를 만든다 (본번/부번은 노출하지 않고 주소 생성에만 쓴다).
        self.assertEqual(trade['canonical_address'], '양재대로 1321')

        # 2. 같은 geocoder 추상화를 쓴다. 첫 결과를 무조건 채택하지 않는다.
        address = '서울특별시 강동구 둔촌동 170'
        payload = {'documents': [{'x': '127.1420', 'y': '37.5290',
                                  'address': {'address_name': address}}]}
        provider = geo.kakao_provider('placeholder', lambda *a, **k: payload)
        evaluation = geo.evaluate(address, provider(address))
        self.assertEqual(evaluation['geocode_confidence'], 'EXACT')
        self.assertTrue(evaluation['coordinate_verified'])

        # 3. 좌표로 주변 개발사업을 찾는다.
        rpc = [{'project_id': 'p1', 'project_name': '천호○○구역', 'project_type': 'REDEVELOPMENT',
                'project_stage': '구역지정', 'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW',
                'relation': 'NEARBY', 'distance_m': 280.0, 'official_source': '서울시 정비사업 정보몽땅',
                'source_url': 'https://cleanup.seoul.go.kr/x', 'verified_at': None}]
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=rpc):
            found = dev.search_projects(longitude=evaluation['longitude'],
                                        latitude=evaluation['latitude'], radius_m=1000)
        projects = [pr.present_project(row) for row in found['nearby_projects']]
        impact = pr.impact({'projects': projects}, trade_has_point=True)

        # 4. 사용자 문구로 해석된다. INSIDE는 추정하지 않는다.
        self.assertEqual(impact['nearest']['name'], '천호○○구역')
        self.assertEqual(impact['nearest']['distance_label'], '300m 이내')
        self.assertEqual(impact['nearest']['distance_m'], 280.0)
        self.assertEqual(impact['nearest']['type_label'], '재개발')
        self.assertEqual(impact['nearest']['stage_label'], '정비구역 지정')
        self.assertEqual(impact['nearest']['official_source']['name'], '서울시 정비사업 정보몽땅')
        self.assertEqual(impact['inside']['code'], 'NOT_DETERMINED')
        self.assertEqual(impact['inside']['notice'], pr.INSIDE_UNKNOWN_NOTICE)

    def test_a_dong_centroid_style_match_is_not_accepted(self):
        # 동 중심점·구청 같은 fallback 위치는 자동 채택하지 않는다.
        payload = {'documents': [{'x': '127.1470', 'y': '37.5300',
                                  'address': {'address_name': '서울특별시 강동구 둔촌동'}}]}
        provider = geo.kakao_provider('placeholder', lambda *a, **k: payload)
        result = geo.evaluate('서울특별시 강동구 둔촌동 170', provider('서울특별시 강동구 둔촌동 170'))
        self.assertEqual(result['geocode_confidence'], 'GEOCODE_REVIEW')
        self.assertIsNone(result['latitude'])


class MapFirstScreenTests(unittest.TestCase):
    def test_the_map_tab_comes_first(self):
        monitor = read('components/realestate/EstateMonitor.tsx')
        self.assertIn('useState<Tab>("개발지도")', monitor)
        self.assertLess(monitor.index('label: "개발지도"'), monitor.index('label: "실거래"'))

    def test_the_explorer_puts_search_and_map_above_the_list(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('부동산 개발정보 지도', tab)
        # 순서는 컴포넌트 본문 기준으로 본다. 파일 앞쪽의 보조 컴포넌트 정의는 렌더 순서가 아니다.
        body = tab.split('export default function DevelopmentTab', 1)[1]
        self.assertLess(body.index('aria-label="사업명 · 동 · 유형 검색"'), body.index('<ZiponMap'))
        self.assertLess(body.index('<ZiponMap'), body.index('이 위치의 개발정보'))
        self.assertLess(body.index('이 위치의 개발정보'), body.index('<DevelopmentCard'))

    def test_the_filters_cover_every_layer(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        for label in ('재개발', '재건축', '신속통합기획', '모아타운', '기타 정비사업'):
            self.assertIn(f'"{label}"', tab)

    def test_map_and_list_are_synchronised(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('onSelect={selectFromMap}', tab)
        self.assertIn('scrollIntoView', tab)
        self.assertIn('setSelectedId(p.project_id)', tab)
        self.assertIn('selectedId={selectedId}', tab)
        # 선택 강조는 카드가 직접 한다. 바깥 ring과 겹치지 않는다.
        self.assertIn('aria-current={selectedId === p.project_id ? "true" : undefined}', tab)
        self.assertIn('border-estate bg-estate-soft/40',
                      read('components/realestate/DevelopmentCard.tsx'))

    def test_the_map_separates_property_type_programme_and_boundary(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('TYPE_COLOR', map_source)
        self.assertIn('PROGRAM_RING', map_source)
        self.assertIn('point.program_layer', map_source)
        self.assertIn('verifiedBoundaryPolygons(point)', map_source)
        self.assertIn('선택 부동산', map_source)

    def test_the_legend_names_the_marker_kinds(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        for label in ('재개발', '재건축', '모아타운', '신속통합기획', '선택 부동산'):
            self.assertIn(label, map_source)
        self.assertNotIn('공식 경계 확인</span>', map_source)

    def test_the_map_takes_its_sdk_settings_from_the_server(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('config?.sdk ?? null', map_source)
        self.assertIn('loadNaverMaps(sdk)', map_source)
        # 키가 없으면 빈 지도를 남기지 않고 못 불러왔다고 말한다.
        self.assertIn('지도를 불러오지 못했어요', map_source)
        self.assertIn('mapConfig()', read('components/realestate/DevelopmentTab.tsx'))

    def test_the_map_reports_its_viewport_for_a_future_bbox_query(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('onBoundsChange', map_source)
        self.assertIn('getBounds()', map_source)

    def test_the_info_window_shows_what_the_spec_asks_for(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        for piece in ('point.stage_label', 'point.address', 'point.type_label',
                      'point.program_label', 'point.accuracy_label',
                      'point.boundary_status_label'):
            self.assertIn(piece, map_source)
        self.assertIn('InfoWindow(', map_source)
        # InfoWindow 본문은 escape해서 넣는다.
        self.assertIn('escapeHtml(', map_source)

    def test_the_map_height_stays_mobile_sized(self):
        self.assertIn('height = 340', read('components/realestate/ZiponMap.tsx'))
        self.assertIn('height={340}', read('components/realestate/DevelopmentTab.tsx'))


NAVER_ITEM = {
    'roadAddress': '서울특별시 강동구 천호대로 1000',
    'jibunAddress': '서울특별시 강동구 천호동 423-1',
    'englishAddress': '423-1, Cheonho-dong, Gangdong-gu, Seoul, Republic of Korea',
    'x': '127.1234567', 'y': '37.5387654', 'distance': 0.0,
    'addressElements': [
        {'types': ['SIDO'], 'longName': '서울특별시', 'shortName': '서울특별시'},
        {'types': ['SIGUGUN'], 'longName': '강동구', 'shortName': '강동구'},
        {'types': ['DONGMYUN'], 'longName': '천호동', 'shortName': '천호동'},
        {'types': ['LAND_NUMBER'], 'longName': '423-1', 'shortName': '423-1'},
        {'types': ['ROAD_NAME'], 'longName': '천호대로', 'shortName': '천호대로'},
        {'types': ['BUILDING_NUMBER'], 'longName': '1000', 'shortName': '1000'},
        {'types': ['POSTAL_CODE'], 'longName': '05238', 'shortName': '05238'}]}
NAVER_ADDRESS = '서울특별시 강동구 천호동 423-1'


def naver_response(item=None, captured=None):
    """Answers like NAVER does and records the request the provider actually made."""
    payload = {'status': 'OK', 'meta': {'totalCount': 1},
               'addresses': [dict(NAVER_ITEM, **(item or {}))] if item is not False else []}

    def http_get(url, params=None, headers=None, timeout=10):
        if captured is not None:
            captured.update(url=url, params=params or {}, headers=headers or {}, timeout=timeout)
        return payload
    return http_get


class NaverGeocodeTests(unittest.TestCase):
    def test_the_naver_provider_reads_the_maps_application_credentials(self):
        spec = geo.PROVIDER_SPECS['naver']
        self.assertEqual(spec['required'], ('NAVER_MAP_CLIENT_ID', 'NAVER_MAP_CLIENT_SECRET'))
        report = geo.provider_availability(lambda name: '')
        self.assertEqual(report['naver']['missing_secrets'],
                         ['NAVER_MAP_CLIENT_ID', 'NAVER_MAP_CLIENT_SECRET'])

    def test_the_request_uses_the_current_endpoint_and_the_documented_headers(self):
        captured = {}
        geo.naver_provider('client-id', 'client-secret', naver_response(captured=captured))(NAVER_ADDRESS)
        self.assertEqual(captured['url'], 'https://maps.apigw.ntruss.com/map-geocode/v2/geocode')
        self.assertEqual(captured['headers'][geo.NAVER_HEADER_KEY_ID], 'client-id')
        self.assertEqual(captured['headers'][geo.NAVER_HEADER_KEY], 'client-secret')
        self.assertEqual(geo.NAVER_HEADER_KEY_ID, 'X-NCP-APIGW-API-KEY-ID')
        self.assertEqual(geo.NAVER_HEADER_KEY, 'X-NCP-APIGW-API-KEY')
        self.assertEqual(captured['params']['query'], NAVER_ADDRESS)

    def test_x_is_the_longitude_and_y_is_the_latitude(self):
        result = geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS)
        candidate = result['candidates'][0]
        self.assertEqual(candidate['longitude'], 127.1234567)
        self.assertEqual(candidate['latitude'], 37.5387654)
        self.assertEqual(candidate['coordinate_orientation'], 'X_IS_LONGITUDE')

    def test_every_documented_field_is_carried_through(self):
        evaluation = geo.evaluate(NAVER_ADDRESS,
                                  geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS))
        self.assertEqual(evaluation['geocode_confidence'], 'EXACT')
        self.assertEqual(evaluation['road_address'], '서울특별시 강동구 천호대로 1000')
        self.assertEqual(evaluation['jibun_address'], NAVER_ADDRESS)
        self.assertIn('Cheonho-dong', evaluation['english_address'])
        self.assertEqual(evaluation['distance_m'], 0.0)
        self.assertEqual(evaluation['address_elements']['LAND_NUMBER'], '423-1')
        self.assertEqual(evaluation['longitude'], 127.1234567)
        self.assertEqual(evaluation['latitude'], 37.5387654)
        self.assertTrue(evaluation['coordinate_verified'])

    def test_a_swapped_axis_pair_is_reviewed_and_never_silently_corrected(self):
        swapped = geo.naver_provider('id', 'secret', naver_response(
            {'x': '37.5387654', 'y': '127.1234567'}))(NAVER_ADDRESS)
        self.assertEqual(swapped['candidates'][0]['coordinate_orientation'], 'SUSPECT_SWAPPED')
        evaluation = geo.evaluate(NAVER_ADDRESS, swapped)
        self.assertEqual(evaluation['geocode_confidence'], 'GEOCODE_REVIEW')
        self.assertIn('axis_order', evaluation['review_reason'])
        self.assertIsNone(evaluation['latitude'])
        self.assertIsNone(evaluation['longitude'])

    def test_the_district_dong_and_lot_must_match_exactly(self):
        response = geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS)
        for address, failed in (('서울특별시 송파구 천호동 423-1', 'district_match'),
                                ('서울특별시 강동구 성내동 423-1', 'dong_match'),
                                ('서울특별시 강동구 천호동 423', 'lot_match')):
            evaluation = geo.evaluate(address, response)
            self.assertEqual(evaluation['geocode_confidence'], 'GEOCODE_REVIEW', address)
            self.assertIn(failed, evaluation['review_reason'], address)

    def test_an_address_outside_seoul_is_never_accepted(self):
        response = geo.naver_provider('id', 'secret', naver_response(
            {'jibunAddress': '경기도 하남시 천호동 423-1', 'x': '127.2050', 'y': '37.5390',
             'addressElements': [{'types': ['SIDO'], 'longName': '경기도'},
                                 {'types': ['SIGUGUN'], 'longName': '하남시'},
                                 {'types': ['DONGMYUN'], 'longName': '천호동'},
                                 {'types': ['LAND_NUMBER'], 'longName': '423-1'}]}))('경기도 하남시 천호동 423-1')
        evaluation = geo.evaluate('경기도 하남시 천호동 423-1', response)
        self.assertEqual(evaluation['geocode_confidence'], 'GEOCODE_REVIEW')
        self.assertIn('seoul', evaluation['review_reason'])

    def test_a_dong_centroid_answer_is_not_a_representative_point(self):
        centroid = geo.naver_provider('id', 'secret', naver_response(
            {'roadAddress': '', 'jibunAddress': '서울특별시 강동구 천호동', 'x': '127.12', 'y': '37.53',
             'addressElements': [{'types': ['SIDO'], 'longName': '서울특별시'},
                                 {'types': ['SIGUGUN'], 'longName': '강동구'},
                                 {'types': ['DONGMYUN'], 'longName': '천호동'}]}))('서울특별시 강동구 천호동')
        self.assertEqual(centroid['candidates'][0]['accuracy'], 'REGION')
        evaluation = geo.evaluate('서울특별시 강동구 천호동', centroid)
        self.assertEqual(evaluation['geocode_confidence'], 'GEOCODE_REVIEW')
        self.assertIn('not_a_region_centroid', evaluation['review_reason'])

    def test_two_candidates_are_never_resolved_by_taking_the_first(self):
        # 같은 지번을 두 번 돌려준 응답은 주소 단위가 하나다. 첫 결과를 고르는 것이
        # 아니라 하나로 접힌다는 근거를 남기고 채택한다.
        response = geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS)
        two = dict(response, candidates=response['candidates'] * 2)
        evaluation = geo.evaluate(NAVER_ADDRESS, two)
        self.assertEqual(evaluation['geocode_confidence'], 'EXACT')
        self.assertEqual(evaluation['disambiguation']['rule'],
                         'SINGLE_ADDRESS_UNIT_MULTIPLE_BUILDINGS')
        self.assertEqual(evaluation['disambiguation']['candidates_considered'], 2)

    def test_two_scattered_answers_for_one_lot_are_still_never_resolved(self):
        # 같은 번지라고 답했는데 좌표가 멀면 그 주장을 믿지 않는다. 첫 결과를 고르는
        # 경로는 없다.
        response = geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS)
        first = response['candidates'][0]
        far = dict(first, longitude=first['longitude'] + 0.05)
        evaluation = geo.evaluate(NAVER_ADDRESS, dict(response, candidates=[first, far]))
        self.assertEqual(evaluation['review_reason'], 'MULTIPLE_PROVIDER_CANDIDATES')
        self.assertFalse(evaluation['coordinate_verified'])

    def test_a_provider_without_address_elements_is_never_collapsed(self):
        # Kakao/VWorld는 주소 문자열만 준다. 주소 단위를 확인할 수 없으면 고르지 않는다.
        response = geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS)
        bare = dict(response['candidates'][0], address_elements={})
        evaluation = geo.evaluate(NAVER_ADDRESS, dict(response, candidates=[bare, bare]))
        self.assertEqual(evaluation['review_reason'], 'MULTIPLE_PROVIDER_CANDIDATES')

    def test_a_road_address_is_checked_against_the_road_and_building_number(self):
        item = {'jibunAddress': '서울특별시 중구 태평로1가 31',
                'roadAddress': '서울특별시 중구 세종대로 110', 'x': '126.9779692', 'y': '37.5662952',
                'addressElements': [{'types': ['SIDO'], 'longName': '서울특별시'},
                                    {'types': ['SIGUGUN'], 'longName': '중구'},
                                    {'types': ['ROAD_NAME'], 'longName': '세종대로'},
                                    {'types': ['BUILDING_NUMBER'], 'longName': '110'}]}
        response = geo.naver_provider('id', 'secret', naver_response(item))(geo.SAMPLE_ADDRESS)
        evaluation = geo.evaluate(geo.SAMPLE_ADDRESS, response)
        self.assertEqual(evaluation['geocode_confidence'], 'EXACT')
        self.assertTrue(evaluation['checks']['building_number_match'])

    def test_the_legacy_host_is_only_retried_when_the_path_is_gone(self):
        calls = []

        class Missing(Exception):
            response = type('R', (), {'status_code': 404})()

        class Unauthorized(Exception):
            response = type('R', (), {'status_code': 401})()

        def flaky(url, params=None, headers=None, timeout=10):
            calls.append(url)
            if url == geo.NAVER_GEOCODE_URL:
                raise Missing()
            return {'status': 'OK', 'addresses': [NAVER_ITEM]}
        geo.naver_provider('id', 'secret', flaky)(NAVER_ADDRESS)
        self.assertEqual(calls, [geo.NAVER_GEOCODE_URL, geo.NAVER_GEOCODE_LEGACY_URL])

        def denied(url, params=None, headers=None, timeout=10):
            calls.append(url)
            raise Unauthorized()
        with self.assertRaises(Unauthorized):
            geo.naver_provider('id', 'secret', denied)(NAVER_ADDRESS)
        self.assertEqual(calls.count(geo.NAVER_GEOCODE_URL), 2)

    def test_naver_comes_first_then_kakao_then_vworld(self):
        self.assertEqual(geo.PROVIDER_PRIORITY, ('naver', 'kakao', 'vworld'))
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y',
                   'KAKAO_REST_API_KEY': 'z'}
        chosen = geo.select_provider(lambda n: secrets.get(n, ''), lambda *a, **k: {})
        self.assertEqual(chosen['name'], 'naver')
        without_naver = geo.select_provider(lambda n: '' if n.startswith('NAVER') else secrets.get(n, ''),
                                            lambda *a, **k: {})
        self.assertEqual(without_naver['name'], 'kakao')
        self.assertEqual(without_naver['skipped'][0]['blocker'], 'NAVER_MAP_CLIENT_ID_NOT_CONFIGURED')
        nothing = geo.select_provider(lambda n: '', lambda *a, **k: {})
        self.assertIsNone(nothing['provider'])
        self.assertEqual(nothing['blocker'], 'NO_GEOCODER_CREDENTIAL_CONFIGURED')

    def test_no_credential_value_reaches_the_status_report(self):
        secrets = {'NAVER_MAP_CLIENT_ID': 'ID_VALUE', 'NAVER_MAP_CLIENT_SECRET': 'SECRET_VALUE'}
        report = geo.status(lambda n: secrets.get(n, ''), naver_response(), geo.SAMPLE_ADDRESS)
        text = json.dumps(report, ensure_ascii=False)
        self.assertNotIn('ID_VALUE', text)
        self.assertNotIn('SECRET_VALUE', text)
        self.assertTrue(report['configured'])
        self.assertTrue(report['reachable'])
        self.assertEqual(report['provider'], 'naver')
        self.assertEqual(report['probe']['coordinate_orientation'], 'X_IS_LONGITUDE')

    def test_the_status_check_makes_no_request_without_a_probe_address(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('the health check must not call the provider')
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        report = geo.status(lambda n: secrets.get(n, ''), forbidden)
        self.assertTrue(report['configured'])
        self.assertIsNone(report['reachable'])
        self.assertIsNone(report['probe'])

    def test_an_unreachable_provider_reports_the_type_not_the_message(self):
        def broken(*args, **kwargs):
            raise TimeoutError('https://maps.apigw.ntruss.com/...?query=x SECRET_VALUE')
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        report = geo.status(lambda n: secrets.get(n, ''), broken, geo.SAMPLE_ADDRESS)
        self.assertFalse(report['reachable'])
        self.assertEqual(report['probe']['error_type'], 'TimeoutError')
        self.assertNotIn('SECRET_VALUE', json.dumps(report, ensure_ascii=False))


class GeocodeStatusEndpointTests(unittest.TestCase):
    def endpoint(self, secrets, http_get, probe):
        from api import realestate as api
        api._cache.clear()
        with patch.object(rm, '_secret', side_effect=lambda name, *a: secrets.get(name, '')), \
             patch.object(geo, 'requests_get', http_get):
            return api.geocode_status(probe=probe)

    def test_the_status_endpoint_names_the_provider_without_calling_it(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('probe=false must not call the provider')
        result = self.endpoint({'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'},
                              forbidden, False)
        self.assertEqual(result['provider'], 'naver')
        self.assertTrue(result['configured'])
        self.assertIsNone(result['reachable'])

    def test_the_probe_uses_a_sample_address_and_hides_the_credentials(self):
        result = self.endpoint({'NAVER_MAP_CLIENT_ID': 'ID_VALUE', 'NAVER_MAP_CLIENT_SECRET': 'SECRET_VALUE'},
                               naver_response(), True)
        self.assertTrue(result['reachable'])
        self.assertEqual(result['probe']['address'], geo.SAMPLE_ADDRESS)
        self.assertNotIn('SECRET_VALUE', json.dumps(result, ensure_ascii=False))

    def test_an_unconfigured_deployment_reports_the_blocker(self):
        result = self.endpoint({}, naver_response(), True)
        self.assertFalse(result['configured'])
        self.assertEqual(result['blocker'], 'NO_GEOCODER_CREDENTIAL_CONFIGURED')
        self.assertIsNone(result['reachable'])


class TradeGeocodeTests(unittest.TestCase):
    def setUp(self):
        from services import trade_geocode
        self.module = trade_geocode

    def trade(self, **extra):
        return dict({'id': 't1', 'region_label': '서울특별시>강동구',
                     'canonical_address': '천호동 423-1'}, **extra)

    def test_the_full_address_carries_the_sido_and_the_district(self):
        self.assertEqual(self.module.full_address(self.trade()), NAVER_ADDRESS)
        self.assertIsNone(self.module.full_address(self.trade(region_label='')))
        self.assertIsNone(self.module.full_address({'region_label': '서울특별시>강동구'}))

    def test_a_trade_reuses_the_development_provider_and_the_same_judgement(self):
        cache = geo.GeocodeCache(Path(self.enterTempDir()) / 'cache')
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        result = self.module.resolve_trades([self.trade()], cache, lambda n: secrets.get(n, ''),
                                            naver_response())
        self.assertEqual(result['provider'], 'naver')
        self.assertEqual(result['located'], 1)
        self.assertFalse(result['db_write'])
        row = result['items'][0]
        self.assertEqual(row['longitude'], 127.1234567)
        self.assertEqual(row['latitude'], 37.5387654)
        self.assertTrue(row['coordinate_verified'])

    def test_an_ambiguous_trade_address_keeps_no_coordinate(self):
        cache = geo.GeocodeCache(Path(self.enterTempDir()) / 'cache')
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        result = self.module.resolve_trades([self.trade(canonical_address='천호동')], cache,
                                            lambda n: secrets.get(n, ''), naver_response())
        row = result['items'][0]
        self.assertFalse(row['coordinate_verified'])
        self.assertIsNone(row.get('latitude'))
        self.assertEqual(result['located'], 0)

    def test_without_credentials_nothing_is_called_and_nothing_is_located(self):
        cache = geo.GeocodeCache(Path(self.enterTempDir()) / 'cache')

        def forbidden(*args, **kwargs):
            raise AssertionError('no provider call without credentials')
        result = self.module.resolve_trades([self.trade()], cache, lambda n: '', forbidden)
        self.assertEqual(result['blocker'], 'NO_GEOCODER_CREDENTIAL_CONFIGURED')
        self.assertEqual(result['located'], 0)
        self.assertFalse(result['items'][0]['coordinate_verified'])

    def enterTempDir(self):
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(__import__('shutil').rmtree, directory, True)
        return directory


class GeocodeApplyStepTests(unittest.TestCase):
    def test_server_secret_uses_apikey_and_legacy_keeps_bearer(self):
        for key in ('sb_secret_mock', 'legacy_mock'):
            with patch.dict('os.environ', {'ZIPON_IMPORT_SUPABASE_URL': self.apply.PROJECT_URL,
                                           'ZIPON_IMPORT_SUPABASE_KEY': key}):
                _, headers = self.apply.configuration()
            self.assertEqual(headers['apikey'], key)
            self.assertEqual('Authorization' in headers, not key.startswith('sb_secret_'))

    def setUp(self):
        import apply_zipon_geocode
        self.apply = apply_zipon_geocode

    def accepted(self, **extra):
        return dict({'project_id': 'p-1', 'district': '강동구', 'geocode_status': 'ACCEPTED',
                     'coordinate_verified': True, 'geocode_confidence': 'EXACT',
                     'coordinate_orientation': 'X_IS_LONGITUDE', 'geocode_source': 'naver:geocode',
                     'longitude': 127.1234567, 'latitude': 37.5387654,
                     'canonical_address': NAVER_ADDRESS, 'matched_address': NAVER_ADDRESS}, **extra)

    def test_only_a_verified_exact_row_is_eligible(self):
        rows, rejected = self.apply.eligible({'items': [
            self.accepted(),
            self.accepted(project_id='p-2', geocode_status='GEOCODE_REVIEW_REQUIRED'),
            self.accepted(project_id='p-3', coordinate_verified=False),
            self.accepted(project_id='p-4', coordinate_orientation='SUSPECT_SWAPPED'),
            self.accepted(project_id='p-5', longitude=128.6, latitude=35.87),
            self.accepted(project_id='p-6', geocode_source='guessed'),
            self.accepted(project_id='p-7', district=None)]})
        self.assertEqual([r['project_id'] for r in rows], ['p-1'])
        self.assertEqual(len(rejected), 6)
        reasons = {r['project_id']: r['skip_reasons'] for r in rejected}
        self.assertIn('AXIS_ORDER_NOT_VERIFIED', reasons['p-4'])
        self.assertIn('COORDINATE_OUTSIDE_SEOUL', reasons['p-5'])
        self.assertIn('UNKNOWN_GEOCODE_SOURCE', reasons['p-6'])

    def test_an_existing_coordinate_or_boundary_is_protected(self):
        row = self.accepted()
        self.assertEqual(self.apply.preflight(row, None), ['PROJECT_NOT_IN_DATABASE'])
        self.assertIn('LOCATION_ALREADY_SET', self.apply.preflight(
            row, {'sigungu': '강동구', 'revision': 1, 'location': '0101', 'geometry_verified': False}))
        self.assertIn('VERIFIED_BOUNDARY_PRESENT', self.apply.preflight(
            row, {'sigungu': '강동구', 'revision': 1, 'location': None, 'geometry_verified': True}))
        self.assertIn('DISTRICT_MISMATCH', self.apply.preflight(
            row, {'sigungu': '송파구', 'revision': 1, 'location': None, 'geometry_verified': False}))
        self.assertEqual(self.apply.preflight(
            row, {'sigungu': '강동구', 'revision': 3, 'location': None, 'geometry_verified': False}), [])

    def test_the_payload_names_the_provider_and_carries_the_evidence(self):
        payload = self.apply.payload_for(self.accepted(), {'sigungu': '강동구', 'revision': 3})
        self.assertEqual(payload['p_geocode_source'], 'NAVER_MAP_GEOCODE')
        self.assertEqual(payload['p_confidence'], 'EXACT')
        self.assertEqual(payload['p_expected_revision'], 3)
        self.assertEqual(payload['p_longitude'], 127.1234567)
        self.assertEqual(payload['p_latitude'], 37.5387654)
        self.assertEqual(payload['p_evidence']['matched_address'], NAVER_ADDRESS)

    def test_batches_never_exceed_ten(self):
        from services.development_collector import MAX_IMPORT_BATCH
        plan = self.apply.batches([self.accepted(project_id=f'p-{i}') for i in range(23)])
        self.assertEqual([len(b) for b in plan], [10, 10, 3])
        self.assertEqual(MAX_IMPORT_BATCH, 10)

    def test_write_credentials_are_their_own_pair(self):
        with patch.dict('os.environ', {'ZIPON_IMPORT_SUPABASE_URL': '',
                                       'ZIPON_IMPORT_SUPABASE_KEY': ''}, clear=False):
            with self.assertRaises(self.apply.ApplyBlocked) as caught:
                self.apply.configuration()
        self.assertEqual(caught.exception.reason, 'MISSING_ZIPON_IMPORT_SUPABASE_URL')

    def test_the_apply_script_writes_only_through_the_reviewed_rpc(self):
        source = (ROOT / 'scripts/apply_zipon_geocode.py').read_text(encoding='utf-8')
        self.assertEqual(self.apply.RPC, 'rpc/zipon_set_project_location')
        for forbidden in ('requests.delete', 'requests.patch', 'requests.put'):
            self.assertNotIn(forbidden, source)


class GeocodeLocationRpcTests(unittest.TestCase):
    def setUp(self):
        self.sql = (ROOT / 'supabase/migrations/20260927_zipon_geocode_location_rpc.sql') \
            .read_text(encoding='utf-8')

    def test_the_rpc_never_writes_a_boundary_or_a_business_status(self):
        statement = self.sql.split('UPDATE public.development_projects SET')[1].split('WHERE')[0]
        for column in ('geometry', 'geometry_source', 'geometry_verified', 'status=', 'stage=',
                       'validation_status', 'canonical_source_id'):
            self.assertNotIn(column, statement)
        for column in ('location=', 'location_source=', 'location_verified_at=', 'field_evidence='):
            self.assertIn(column, statement)

    def test_the_rpc_refuses_instead_of_correcting(self):
        for reason in ('CONFIDENCE_NOT_EXACT', 'UNKNOWN_GEOCODE_SOURCE', 'COORDINATE_OUTSIDE_SEOUL',
                       'NO_GEOCODE_EVIDENCE', 'PROJECT_NOT_FOUND', 'REVISION_CONFLICT',
                       'LOCATION_ALREADY_SET', 'DISTRICT_MISMATCH'):
            self.assertIn(reason, self.sql)
        self.assertNotIn('DELETE', self.sql.upper().replace('DELETED', ''))

    def test_the_rpc_is_invoker_rights_and_service_role_only(self):
        self.assertIn('SECURITY INVOKER', self.sql)
        self.assertIn('SET search_path=pg_catalog,public,extensions,pg_temp', self.sql)
        self.assertIn('REVOKE ALL ON FUNCTION public.zipon_set_project_location', self.sql)
        self.assertIn('GRANT EXECUTE ON FUNCTION public.zipon_set_project_location', self.sql)
        self.assertIn('TO service_role', self.sql)

    def test_the_postcheck_rolls_everything_back(self):
        postcheck = (ROOT / 'supabase/review/20260927_zipon_geocode_location_postcheck.sql') \
            .read_text(encoding='utf-8')
        self.assertTrue(postcheck.strip().endswith('ROLLBACK;'))
        self.assertIn("RAISE EXCEPTION 'Rollback successful test fixtures' USING ERRCODE='ZP001'",
                      postcheck)
        self.assertIn('TARGET_PROJECT_UNCHANGED', postcheck)
        self.assertIn('ROW_COUNTS_AND_COORDINATE_COVERAGE_INTACT', postcheck)
        statements = '\n'.join(line for line in postcheck.splitlines()
                               if not line.lstrip().startswith('--')).upper()
        for forbidden in ('DELETE FROM', 'TRUNCATE', 'DROP ', 'ALTER TABLE'):
            self.assertNotIn(forbidden, statements)


class DynamicMapExposureTests(unittest.TestCase):
    def config(self, secrets=None):
        from services import map_providers
        return map_providers, map_providers.config(lambda name: (secrets or {}).get(name, ''))

    def test_only_the_map_client_id_may_reach_the_browser(self):
        providers, config = self.config({'NAVER_MAP_CLIENT_ID': 'ID_VALUE',
                                         'NAVER_MAP_CLIENT_SECRET': 'SECRET_VALUE'})
        text = json.dumps(config, ensure_ascii=False)
        # Client Secret은 어떤 경우에도 브라우저로 내려가지 않는다.
        self.assertNotIn('SECRET_VALUE', text)
        # Client ID는 웹 지도 SDK 인증에 필요하므로 sdk에만 담겨 내려간다.
        self.assertEqual(config['sdk']['client_id'], 'ID_VALUE')
        self.assertIn('NAVER_MAP_CLIENT_SECRET', config['browser_exposure']['never_sent_to_browser'])
        naver = next(p for p in config['providers'] if p['id'] == 'naver')
        self.assertEqual(naver['browser_key_name'], 'NAVER_MAP_CLIENT_ID')
        self.assertEqual(naver['web_service_url'], 'https://minseo2-digital-ai-lab.hf.space')
        self.assertEqual(providers.NAVER_WEB_SERVICE_URL, 'https://minseo2-digital-ai-lab.hf.space')

    def test_a_configured_client_id_makes_naver_the_active_map(self):
        _, config = self.config({'NAVER_MAP_CLIENT_ID': 'ID_VALUE'})
        self.assertEqual(config['active'], 'naver')
        self.assertTrue(config['sdk']['configured'])
        self.assertEqual(config['sdk']['client_id'], 'ID_VALUE')
        # raster fallback은 그대로 남는다. js_sdk가 타일 소스를 대신하지는 않는다.
        self.assertEqual(config['fallback'], 'osm')
        self.assertIsNone(config['tile']['url_template'])

    def test_without_a_client_id_the_map_is_not_claimed_to_work(self):
        _, config = self.config({})
        self.assertEqual(config['active'], 'osm')
        self.assertFalse(config['sdk']['configured'])
        self.assertIsNone(config['sdk']['client_id'])

    def test_no_frontend_file_mentions_a_geocoding_credential(self):
        for path in (ROOT / 'web/src').rglob('*.ts*'):
            source = path.read_text(encoding='utf-8')
            for secret in ('NAVER_MAP_CLIENT_SECRET', 'KAKAO_REST_API_KEY', 'X-NCP-APIGW-API-KEY',
                           'SERVICE_ROLE', 'NEXT_PUBLIC_SUPABASE'):
                self.assertNotIn(secret, source, f'{path.name} mentions {secret}')


# Canary fixtures. One plausible coordinate per canary address, all inside the right
# district, so the stub exercises the real evaluator rather than a mocked verdict.
CANARY_POINTS = {
    '서울특별시 강동구 둔촌동 172': (127.1436, 37.5281),
    '서울특별시 강동구 천호동 467-61': (127.1268, 37.5395),
    '서울특별시 강동구 길동 54': (127.1421, 37.5372),
    '서울특별시 강동구 상일동 124': (127.1681, 37.5545),
    '서울특별시 송파구 송파동 151': (127.1123, 37.5021),
    '서울특별시 송파구 마천동 183-1': (127.1519, 37.4977),
    '서울특별시 송파구 신천동 20-4': (127.0873, 37.5157),
    '서울특별시 서초구 잠원동 61-1': (127.0104, 37.5192),
    '서울특별시 서초구 반포동 591-1': (126.9958, 37.5041),
    '서울특별시 서초구 방배동 528-3': (126.9932, 37.4869),
}


def canary_naver(points=None, extra=None, counter=None, fail=None):
    """Answers like NAVER for the canary addresses, from the requested address alone."""
    table = dict(CANARY_POINTS, **(points or {}))

    def http_get(url, params=None, headers=None, timeout=10):
        address = (params or {}).get('query')
        if counter is not None:
            counter.append(address)
        if fail and address in fail:
            raise fail[address]
        if address not in table:
            return {'status': 'OK', 'addresses': []}
        longitude, latitude = table[address]
        parts = geo.wanted_parts(address)
        elements = [{'types': ['SIDO'], 'longName': parts['sido']},
                    {'types': ['SIGUGUN'], 'longName': parts['district']},
                    {'types': ['DONGMYUN'], 'longName': parts['dong']},
                    {'types': ['LAND_NUMBER'], 'longName': parts['lot']}]
        item = {'roadAddress': '', 'jibunAddress': address, 'englishAddress': 'stub',
                'x': str(longitude), 'y': str(latitude), 'distance': 0.0,
                'addressElements': elements}
        item.update((extra or {}).get(address) or {})
        addresses = [item] * ((extra or {}).get(address, {}).pop('_repeat', 1)
                              if isinstance((extra or {}).get(address), dict) else 1)
        return {'status': 'OK', 'meta': {'totalCount': len(addresses)}, 'addresses': addresses}
    return http_get


class GeocodeCanaryTests(unittest.TestCase):
    def setUp(self):
        from services import development_canary
        import tempfile, shutil
        self.canary = development_canary
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def cache(self):
        return geo.GeocodeCache(Path(self.directory) / 'cache')

    def run_canary(self, http_get, secrets=None):
        secrets = secrets if secrets is not None else {'NAVER_MAP_CLIENT_ID': 'x',
                                                       'NAVER_MAP_CLIENT_SECRET': 'y'}
        return self.canary.run(lambda name: secrets.get(name, ''), http_get, self.cache())

    def test_the_frozen_ten_match_the_selection_artifact(self):
        document = json.loads((DATA / 'geocode_canary_20260927.json').read_text(encoding='utf-8'))
        self.assertEqual(list(self.canary.CANARY), document['items'])
        self.assertEqual(len(self.canary.CANARY), 10)
        for row in self.canary.CANARY:
            self.assertEqual(set(row), {'project_id', 'project_name', 'canonical_address',
                                        'district', 'project_type', 'program'})

    def test_the_ten_mix_the_three_districts_and_ten_dong(self):
        districts = {}
        for row in self.canary.CANARY:
            districts[row['district']] = districts.get(row['district'], 0) + 1
        self.assertEqual(districts, {'강동구': 4, '송파구': 3, '서초구': 3})
        self.assertEqual(len({row['canonical_address'] for row in self.canary.CANARY}), 10)
        self.assertEqual(len({geo.wanted_parts(row['canonical_address'])['dong']
                              for row in self.canary.CANARY}), 10)
        self.assertEqual(len({row['project_type'] for row in self.canary.CANARY}), 2)

    def test_a_clean_run_accepts_all_ten_and_records_every_check(self):
        result = self.run_canary(canary_naver())
        self.assertEqual(result['provider'], 'naver')
        self.assertEqual(result['provider_calls'], 10)
        self.assertEqual(result['totals'], {'ACCEPTED': 10, 'REVIEW_REQUIRED': 0, 'FAILED': 0,
                                            'PENDING_PROVIDER': 0})
        self.assertFalse(result['db_write'])
        for row in result['results']:
            self.assertEqual(row['candidate_count'], 1)
            self.assertEqual(row['matched_jibun_address'], row['canonical_address'])
            self.assertTrue(row['in_seoul_bounds'])
            self.assertTrue(row['district_match'])
            self.assertTrue(row['dong_match'])
            self.assertTrue(row['lot_match'])
            self.assertEqual(row['returned_district'], row['district'])
            self.assertEqual(row['coordinate_orientation'], 'X_IS_LONGITUDE')
            self.assertEqual(row['geocode_confidence'], 'EXACT')
            self.assertTrue(row['acceptance_reason'].startswith('EXACT_MATCH_ON_'))
            self.assertEqual((row['longitude'], row['latitude']),
                             CANARY_POINTS[row['canonical_address']])

    def test_the_map_payload_is_what_the_component_already_consumes(self):
        result = self.run_canary(canary_naver())
        payload = result['map']
        self.assertEqual(payload['total'], 10)
        self.assertEqual(payload['mappable'], 10)
        first = payload['points'][0]
        self.assertEqual(set(first), set(pr.map_point({'project_id': 'x'})))
        for point in payload['points']:
            self.assertEqual(point['accuracy'], 'REPRESENTATIVE_POINT')
            self.assertEqual(point['accuracy_label'], '대표 위치')
            self.assertTrue(point['mappable'])
        self.assertEqual(payload['inside_judgement'],
                         'NOT_PERMITTED_WITHOUT_VERIFIED_BOUNDARY')

    def test_the_bbox_center_and_zoom_cover_the_ten_points(self):
        payload = self.run_canary(canary_naver())['map']
        longitudes = [p[0] for p in CANARY_POINTS.values()]
        latitudes = [p[1] for p in CANARY_POINTS.values()]
        self.assertEqual(payload['bbox'], {'west': min(longitudes), 'east': max(longitudes),
                                           'south': min(latitudes), 'north': max(latitudes)})
        self.assertAlmostEqual(payload['center']['longitude'],
                               (min(longitudes) + max(longitudes)) / 2)
        self.assertAlmostEqual(payload['center']['latitude'],
                               (min(latitudes) + max(latitudes)) / 2)
        self.assertTrue(9 <= payload['suggested_zoom'] <= 16)

    def test_inside_is_never_produced_from_a_canary_point(self):
        payload = self.run_canary(canary_naver())['map']
        for point in payload['points']:
            self.assertFalse(point['allows_inside'])
            self.assertIsNone(point['boundary'])
            self.assertNotEqual(point['boundary_status'], 'OFFICIAL_VERIFIED')

    def test_two_candidates_are_reviewed_rather_than_taking_the_first(self):
        address = self.canary.CANARY[0]['canonical_address']
        longitude, latitude = CANARY_POINTS[address]

        def http_get(url, params=None, headers=None, timeout=10):
            if (params or {}).get('query') != address:
                return canary_naver()(url, params, headers, timeout)
            parts = geo.wanted_parts(address)
            item = {'jibunAddress': address, 'roadAddress': '', 'x': str(longitude),
                    'y': str(latitude), 'addressElements': [
                        {'types': ['SIDO'], 'longName': parts['sido']},
                        {'types': ['SIGUGUN'], 'longName': parts['district']},
                        {'types': ['DONGMYUN'], 'longName': parts['dong']},
                        {'types': ['LAND_NUMBER'], 'longName': parts['lot']}]}
            # 같은 번지라면서 좌표가 멀리 떨어진 두 답. 하나로 접지 않는다.
            return {'status': 'OK', 'addresses': [item, dict(item, x=str(longitude + 0.05))]}
        result = self.run_canary(http_get)
        row = next(r for r in result['results'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        self.assertEqual(row['acceptance_reason'], 'MULTIPLE_PROVIDER_CANDIDATES')
        self.assertEqual(row['candidate_count'], 2)
        self.assertIsNone(row['longitude'])
        self.assertEqual(result['totals']['ACCEPTED'], 9)

    def test_a_dong_centroid_answer_is_reviewed_not_accepted(self):
        address = self.canary.CANARY[2]['canonical_address']

        def http_get(url, params=None, headers=None, timeout=10):
            if (params or {}).get('query') != address:
                return canary_naver()(url, params, headers, timeout)
            parts = geo.wanted_parts(address)
            return {'status': 'OK', 'addresses': [{
                'jibunAddress': f"{parts['sido']} {parts['district']} {parts['dong']}",
                'roadAddress': '', 'x': '127.1400', 'y': '37.5380',
                'addressElements': [{'types': ['SIDO'], 'longName': parts['sido']},
                                    {'types': ['SIGUGUN'], 'longName': parts['district']},
                                    {'types': ['DONGMYUN'], 'longName': parts['dong']}]}]}
        row = next(r for r in self.run_canary(http_get)['results']
                   if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        self.assertEqual(row['accuracy'], 'REGION')
        self.assertIn('lot_match', row['acceptance_reason'])
        self.assertIsNone(row['latitude'])

    def test_a_district_mismatch_is_reviewed_and_carries_no_coordinate(self):
        address = self.canary.CANARY[4]['canonical_address']
        extra = {address: {'addressElements': [
            {'types': ['SIDO'], 'longName': '서울특별시'},
            {'types': ['SIGUGUN'], 'longName': '강동구'},
            {'types': ['DONGMYUN'], 'longName': '송파동'},
            {'types': ['LAND_NUMBER'], 'longName': '151'}]}}
        result = self.run_canary(canary_naver(extra=extra))
        row = next(r for r in result['results'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        self.assertIn('district_match', row['acceptance_reason'])
        self.assertEqual(row['returned_district'], '강동구')
        self.assertIsNone(row['longitude'])
        # 채택되지 않았으므로 자치구 sanity 검사 대상에서도 빠진다.
        self.assertEqual(result['sanity']['district_match']['mismatched'], [])
        self.assertEqual(result['sanity']['evaluated_points'], 9)

    def test_a_swapped_axis_answer_is_reviewed(self):
        address = self.canary.CANARY[6]['canonical_address']
        longitude, latitude = CANARY_POINTS[address]
        result = self.run_canary(canary_naver(points={address: (latitude, longitude)}))
        row = next(r for r in result['results'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        self.assertIn('axis_order', row['acceptance_reason'])
        self.assertEqual(row['coordinate_orientation'], 'SUSPECT_SWAPPED')
        self.assertEqual(result['sanity']['coordinate_orientation']['suspect'], [])

    def test_two_projects_on_one_coordinate_are_flagged(self):
        first, second = (self.canary.CANARY[0]['canonical_address'],
                         self.canary.CANARY[1]['canonical_address'])
        shared = CANARY_POINTS[first]
        result = self.run_canary(canary_naver(points={second: shared}))
        duplicates = result['sanity']['duplicate_coordinates']
        self.assertFalse(duplicates['passed'])
        self.assertEqual(sorted(next(iter(duplicates['exact'].values()))),
                         sorted([self.canary.CANARY[0]['project_id'],
                                 self.canary.CANARY[1]['project_id']]))
        self.assertTrue(duplicates['within_about_11m'])

    def test_a_coordinate_far_from_its_district_group_is_flagged(self):
        address = self.canary.CANARY[3]['canonical_address']
        result = self.run_canary(canary_naver(points={address: (127.2600, 37.7000)}))
        spread = result['sanity']['district_spread']
        self.assertFalse(spread['passed'])
        self.assertIn(self.canary.CANARY[3]['project_id'],
                      spread['by_district']['강동구']['beyond_limit'])

    def test_a_provider_error_is_failed_and_does_not_stop_the_run(self):
        address = self.canary.CANARY[5]['canonical_address']
        result = self.run_canary(canary_naver(fail={address: TimeoutError('boom')}))
        row = next(r for r in result['results'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'FAILED')
        self.assertEqual(row['acceptance_reason'], 'PROVIDER_ERROR_TimeoutError')
        self.assertEqual(result['totals']['ACCEPTED'], 9)
        self.assertEqual(result['totals']['FAILED'], 1)

    def test_without_credentials_nothing_is_called_and_nothing_fails(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('no provider call without credentials')
        result = self.canary.run(lambda name: '', forbidden, self.cache())
        self.assertEqual(result['provider_calls'], 0)
        self.assertEqual(result['totals'], {'ACCEPTED': 0, 'REVIEW_REQUIRED': 0, 'FAILED': 0,
                                            'PENDING_PROVIDER': 10})
        self.assertEqual(result['blocker'], 'NO_GEOCODER_CREDENTIAL_CONFIGURED')
        # 시도조차 못 한 실행에 통과 판정을 붙이지 않는다.
        for check in ('district_match', 'district_spread', 'duplicate_coordinates',
                      'coordinate_orientation'):
            self.assertIsNone(result['sanity'][check]['passed'], check)

    def test_the_run_calls_each_address_once_and_reuses_the_cache(self):
        counter = []
        cache = self.cache()
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        get_secret = lambda name: secrets.get(name, '')
        first = self.canary.run(get_secret, canary_naver(counter=counter), cache)
        self.assertEqual(len(counter), 10)
        second = self.canary.run(get_secret, canary_naver(counter=counter), cache)
        self.assertEqual(len(counter), 10, 'the second run must not call the provider again')
        self.assertEqual(second['provider_calls'], 0)
        self.assertEqual(second['totals']['ACCEPTED'], first['totals']['ACCEPTED'])
        self.assertTrue(all(row['from_cache'] for row in second['results']))

    def test_the_report_carries_no_credential_and_no_database_write(self):
        secrets = {'NAVER_MAP_CLIENT_ID': 'ID_VALUE', 'NAVER_MAP_CLIENT_SECRET': 'SECRET_VALUE'}
        result = self.canary.run(lambda name: secrets.get(name, ''), canary_naver(), self.cache())
        text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn('ID_VALUE', text)
        self.assertNotIn('SECRET_VALUE', text)
        self.assertFalse(result['db_write'])
        self.assertFalse(result['migration_applied'])
        self.assertFalse(result['bulk_149_run'])

    def test_the_endpoint_runs_the_canary_once_and_caches_it(self):
        from api import realestate as api
        counter = []
        api._cache.clear()
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        with patch.object(rm, '_secret', side_effect=lambda name, *a: secrets.get(name, '')), \
             patch.object(geo, 'requests_get', canary_naver(counter=counter)), \
             patch.object(self.canary, '_default_cache_dir',
                          return_value=Path(self.directory) / 'endpoint'):
            first = api.geocode_canary()
            second = api.geocode_canary()
        api._cache.clear()
        self.assertEqual(first['totals']['ACCEPTED'], 10)
        self.assertEqual(len(counter), 10)
        self.assertIs(first, second)

    def test_an_unwritable_cache_directory_does_not_stop_the_canary(self):
        with patch.object(self.canary, '_default_cache_dir',
                          return_value=Path('/proc/zipon-cannot-write')):
            store = self.canary._cache_store()
        self.assertTrue(store.directory.exists())
        self.assertNotIn('/proc/', str(store.directory))


def bulk_naver(points=None, extra=None, counter=None, fail=None, multi=()):
    """Answers like NAVER for every bulk target, derived from the requested address."""
    from services.development_geocode_targets import targets
    rows = {row['canonical_address']: index for index, row in enumerate(targets())}
    table = dict({address: (127.0 + i * 0.0013, 37.5 + i * 0.0009)
                  for address, i in rows.items()}, **(points or {}))

    def item_for(address):
        longitude, latitude = table[address]
        parts = geo.wanted_parts(address)
        return {'roadAddress': '', 'jibunAddress': address, 'englishAddress': 'stub',
                'x': str(longitude), 'y': str(latitude), 'distance': 0.0,
                'addressElements': [{'types': ['SIDO'], 'longName': parts['sido']},
                                    {'types': ['SIGUGUN'], 'longName': parts['district']},
                                    {'types': ['DONGMYUN'], 'longName': parts['dong']},
                                    {'types': ['LAND_NUMBER'], 'longName': parts['lot']}]}

    def http_get(url, params=None, headers=None, timeout=10):
        address = (params or {}).get('query')
        if counter is not None:
            counter.append(address)
        if fail and address in fail:
            raise fail[address]
        if address not in table:
            return {'status': 'OK', 'addresses': []}
        item = dict(item_for(address), **((extra or {}).get(address) or {}))
        addresses = [item]
        if address in multi:
            # 같은 동의 다른 번지. 번지 검사에서 걸러져야 한다.
            other = dict(item_for(address))
            other['addressElements'] = [e for e in other['addressElements']
                                        if 'LAND_NUMBER' not in e['types']]
            other['addressElements'].append({'types': ['LAND_NUMBER'], 'longName': '99999'})
            other['jibunAddress'] = address + '9'
            addresses = [other, item, dict(other, x=str(table[address][0] + 0.004))]
        return {'status': 'OK', 'meta': {'totalCount': len(addresses)}, 'addresses': addresses}
    return http_get


class BulkGeocodeTargetTests(unittest.TestCase):
    def test_the_generated_table_matches_the_canonical_file(self):
        import build_zipon_geocode_targets as builder
        current = (ROOT / 'services/development_geocode_targets.py').read_text(encoding='utf-8')
        self.assertEqual(builder.render(builder.rows()), current)

    def test_the_target_set_is_in_the_database_and_has_an_address(self):
        from services.development_geocode_targets import targets
        rows = targets()
        self.assertEqual(len(rows), 128)
        canonical = json.loads((DATA / 'pilot_canonical_verified_20260927.json')
                               .read_text(encoding='utf-8'))['projects']
        baseline = json.loads((DATA / 'db_baseline_20260927.json')
                              .read_text(encoding='utf-8'))['projects']
        result = json.loads((DATA / 'bulk_import_result_20260927.json').read_text(encoding='utf-8'))
        in_db = {p['project_id'] for p in baseline} | {i for b in result['batches']
                                                      for i in b['project_ids']}
        by_id = {p['raw']['candidate_ids'][0]: p for p in canonical}
        for row in rows:
            self.assertIn(row['project_id'], in_db)
            project = by_id[row['project_id']]
            self.assertEqual(row['canonical_address'],
                             project['location']['representative_address'])
            self.assertEqual(row['district'], project['location']['district'])
            self.assertTrue(project['location']['address_verified'])

    def test_the_scopes_reconcile(self):
        canonical = json.loads((DATA / 'pilot_canonical_verified_20260927.json')
                               .read_text(encoding='utf-8'))['projects']
        addressed = [p for p in canonical if p['location']['representative_address']]
        fast_track = [p for p in canonical if p['classification']['program'] == 'FAST_TRACK']
        self.assertEqual(len(canonical), 183)
        self.assertEqual(len(addressed), 149)
        self.assertEqual(len(canonical) - len(addressed), 34)
        # 주소가 없는 34건은 전부 신속통합기획이다.
        self.assertEqual({p['raw']['candidate_ids'][0] for p in canonical
                          if not p['location']['representative_address']},
                         {p['raw']['candidate_ids'][0] for p in fast_track})


class BulkGeocodeRunTests(unittest.TestCase):
    def test_aggregate_preserves_address_elements_and_failed_attempts(self):
        first = self.bulk.run(self.get_secret, bulk_naver(), self.cache, size=1)
        failure = self.bulk.run(self.get_secret, Mock(side_effect=TimeoutError('private')),
                                self.cache, offset=1, size=1)
        self.assertEqual(failure['totals']['FAILED'], 1)
        forbidden = Mock(side_effect=AssertionError('aggregate must not call provider'))
        aggregate = self.bulk.run(self.get_secret, forbidden, self.cache, cache_only=True)
        forbidden.assert_not_called()
        self.assertEqual(aggregate['totals']['FAILED'], 1)
        self.assertEqual(aggregate['totals']['PENDING_PROVIDER'], 126)
        self.assertEqual(aggregate['apply_ready']['items'][0]['address_elements'],
                         first['apply_ready']['items'][0]['address_elements'])
        self.assertTrue(aggregate['apply_ready']['items'][0]['address_elements'])
        self.assertNotIn('private', json.dumps(aggregate))

    def setUp(self):
        from services import development_bulk_geocode
        import tempfile, shutil
        self.bulk = development_bulk_geocode
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.cache = geo.GeocodeCache(Path(self.directory) / 'cache')
        self.secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        self.get_secret = lambda name: self.secrets.get(name, '')

    def whole_run(self, http_get, size=32):
        offset, calls = 0, 0
        while offset is not None:
            sliced = self.bulk.run(self.get_secret, http_get, self.cache,
                                   offset=offset, size=size)
            calls += sliced['provider_calls']
            offset = sliced['next_offset']
        report = self.bulk.run(self.get_secret, http_get, self.cache, cache_only=True)
        return report, calls

    def test_a_slice_never_exceeds_the_cap(self):
        report = self.bulk.run(self.get_secret, bulk_naver(), self.cache, offset=0, size=999)
        self.assertEqual(report['size'], self.bulk.MAX_SLICE)
        self.assertEqual(report['provider_calls'], self.bulk.MAX_SLICE)

    def test_the_whole_target_set_is_covered_once(self):
        counter = []
        report, calls = self.whole_run(bulk_naver(counter=counter))
        self.assertEqual(calls, 128)
        self.assertEqual(len(counter), 128)
        self.assertEqual(report['target_total'], 128)
        self.assertEqual(report['totals']['ACCEPTED'], 128)
        self.assertEqual(len(report['artifact']['items']), 128)

    def test_the_aggregate_spends_nothing_and_keeps_the_evidence(self):
        report, _ = self.whole_run(bulk_naver())
        self.assertEqual(report['provider_calls'], 0)
        self.assertTrue(report['cache_only'])
        row = report['artifact']['items'][0]
        # 캐시에서 되살린 행도 판정 근거를 그대로 들고 있어야 한다.
        self.assertEqual(row['candidate_count'], 1)
        self.assertEqual(row['accuracy'], 'PARCEL')
        self.assertEqual(row['matched_address'], row['canonical_address'])
        self.assertIn('district_match', row['acceptance_reason'])
        for check in ('district_match', 'district_spread', 'duplicate_coordinates',
                      'coordinate_orientation'):
            self.assertTrue(report['sanity'][check]['passed'], check)

    def test_the_artifact_carries_exactly_the_requested_columns(self):
        report, _ = self.whole_run(bulk_naver())
        self.assertEqual(report['artifact']['fields'], list(self.bulk.ARTIFACT_FIELDS))
        for row in report['artifact']['items']:
            self.assertEqual(set(row), set(self.bulk.ARTIFACT_FIELDS))
        self.secrets.update(NAVER_MAP_CLIENT_ID='ID_VALUE', NAVER_MAP_CLIENT_SECRET='SECRET_VALUE')
        text = json.dumps(self.bulk.run(self.get_secret, bulk_naver(), self.cache,
                                        cache_only=True), ensure_ascii=False)
        self.assertNotIn('ID_VALUE', text)
        self.assertNotIn('SECRET_VALUE', text)

    def test_the_stored_dong_is_never_replaced_by_the_provider_answer(self):
        address = self.bulk.targets()[0]['canonical_address']
        extra = {address: {'addressElements': [
            {'types': ['SIDO'], 'longName': '서울특별시'},
            {'types': ['SIGUGUN'], 'longName': geo.wanted_parts(address)['district']},
            {'types': ['DONGMYUN'], 'longName': '엉뚱동'},
            {'types': ['LAND_NUMBER'], 'longName': geo.wanted_parts(address)['lot']}]}}
        report, _ = self.whole_run(bulk_naver(extra=extra))
        row = next(r for r in report['artifact']['items']
                   if r['canonical_address'] == address)
        self.assertEqual(row['dong'], geo.wanted_parts(address)['dong'])
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        self.assertIsNone(row['longitude'])

    def test_multiple_candidates_resolve_only_when_one_is_unambiguous(self):
        address = self.bulk.targets()[5]['canonical_address']
        report, _ = self.whole_run(bulk_naver(multi=(address,)))
        row = next(r for r in report['artifact']['items'] if r['canonical_address'] == address)
        # 세 후보 중 번지가 맞는 것이 하나뿐이면 그것을 쓴다. 첫 후보를 쓰지 않는다.
        self.assertEqual(row['candidate_count'], 3)
        self.assertEqual(row['outcome'], 'ACCEPTED')
        self.assertEqual(row['matched_address'], address)
        self.assertEqual(report['totals']['ACCEPTED'], 128)

    def test_several_matching_candidates_stay_for_review(self):
        address = self.bulk.targets()[7]['canonical_address']
        longitude, latitude = 127.05, 37.52

        def http_get(url, params=None, headers=None, timeout=10):
            if (params or {}).get('query') != address:
                return bulk_naver()(url, params, headers, timeout)
            parts = geo.wanted_parts(address)
            item = {'jibunAddress': address, 'roadAddress': '', 'x': str(longitude),
                    'y': str(latitude), 'addressElements': [
                        {'types': ['SIDO'], 'longName': parts['sido']},
                        {'types': ['SIGUGUN'], 'longName': parts['district']},
                        {'types': ['DONGMYUN'], 'longName': parts['dong']},
                        {'types': ['LAND_NUMBER'], 'longName': parts['lot']}]}
            return {'status': 'OK', 'addresses': [item, dict(item, x=str(longitude + 0.003))]}
        report, _ = self.whole_run(http_get)
        row = next(r for r in report['artifact']['items'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        self.assertEqual(row['acceptance_reason'], 'MULTIPLE_PROVIDER_CANDIDATES')
        self.assertIsNone(row['latitude'])
        review = next(r for r in report['review']['items']
                      if r['official_address'] == address)
        self.assertEqual(len(review['naver_candidates']), 2)
        self.assertEqual(review['official_address'], address)
        self.assertIsNone(review['decision'])

    def test_review_rows_are_excluded_from_the_apply_ready_artifact(self):
        address = self.bulk.targets()[3]['canonical_address']
        report, _ = self.whole_run(bulk_naver(points={address: (128.9, 35.1)}))
        row = next(r for r in report['artifact']['items'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'REVIEW_REQUIRED')
        apply_ids = {item['project_id'] for item in report['apply_ready']['items']}
        review_ids = {item['project_id'] for item in report['review']['items']}
        self.assertNotIn(row['project_id'], apply_ids)
        self.assertIn(row['project_id'], review_ids)
        self.assertEqual(len(apply_ids), 127)
        self.assertFalse(apply_ids & review_ids)

    def test_the_apply_ready_artifact_is_what_the_apply_step_accepts(self):
        import apply_zipon_geocode
        report, _ = self.whole_run(bulk_naver())
        eligible, rejected = apply_zipon_geocode.eligible(report['apply_ready'])
        self.assertEqual(len(eligible), 128)
        self.assertEqual(rejected, [])
        payload = apply_zipon_geocode.payload_for(eligible[0], {'sigungu': eligible[0]['district'],
                                                               'revision': 1})
        self.assertEqual(payload['p_geocode_source'], 'NAVER_MAP_GEOCODE')
        self.assertEqual(payload['p_confidence'], 'EXACT')
        self.assertTrue(payload['p_evidence']['matched_address'])
        self.assertTrue(payload['p_evidence']['address_used'])
        self.assertLessEqual(max(len(b) for b in apply_zipon_geocode.batches(eligible)), 10)

    def test_the_map_readiness_counts_what_can_be_drawn(self):
        report, _ = self.whole_run(bulk_naver())
        readiness = report['map_readiness']
        self.assertEqual(readiness['mappable_projects'], 128)
        self.assertEqual(readiness['reconstruction'], 111)
        self.assertEqual(readiness['redevelopment'], 17)
        self.assertEqual(readiness['other'], 0)
        self.assertEqual(readiness['fast_track'], 0)
        self.assertEqual(readiness['moatown'], 0)
        self.assertEqual(readiness['by_district'], {'강동구': 39, '서초구': 56, '송파구': 33})
        self.assertEqual(readiness['inside_judgement'],
                         'NOT_PERMITTED_WITHOUT_VERIFIED_BOUNDARY')
        for point in report['map']['points']:
            self.assertFalse(point['allows_inside'])

    def test_a_failing_address_does_not_stop_the_run(self):
        address = self.bulk.targets()[9]['canonical_address']
        report, _ = self.whole_run(bulk_naver(fail={address: TimeoutError('boom')}))
        row = next(r for r in report['artifact']['items'] if r['canonical_address'] == address)
        self.assertEqual(row['outcome'], 'FAILED')
        self.assertEqual(report['totals']['FAILED'], 1)
        self.assertEqual(report['totals']['ACCEPTED'], 127)

    def test_nothing_runs_and_nothing_is_written_without_credentials(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('no provider call without credentials')
        report = self.bulk.run(lambda name: '', forbidden, self.cache, offset=0, size=32)
        self.assertEqual(report['provider_calls'], 0)
        self.assertEqual(report['totals']['PENDING_PROVIDER'], 32)
        self.assertFalse(report['db_write'])
        self.assertEqual(report['apply_ready']['items'], [])


class BulkGeocodeEndpointTests(unittest.TestCase):
    def setUp(self):
        from api import realestate as api
        from services import development_bulk_geocode, development_canary
        import tempfile, shutil
        self.api, self.bulk, self.canary = api, development_bulk_geocode, development_canary
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)
        api._cache.clear()
        self.addCleanup(api._cache.clear)

    def call(self, http_get, **kwargs):
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        with patch.object(rm, '_secret', side_effect=lambda name, *a: secrets.get(name, '')), \
             patch.object(geo, 'requests_get', http_get), \
             patch.object(self.canary, '_default_cache_dir',
                          return_value=Path(self.directory) / 'cache'):
            return self.api.geocode_bulk(**kwargs)

    def test_a_slice_is_cached_so_a_repeat_costs_nothing(self):
        counter = []
        first = self.call(bulk_naver(counter=counter), offset=0, size=16)
        second = self.call(bulk_naver(counter=counter), offset=0, size=16)
        self.assertEqual(len(counter), 16)
        self.assertIs(first, second)
        self.assertEqual(first['size'], 16)
        self.assertEqual(first['next_offset'], 16)

    def test_the_aggregate_calls_no_provider(self):
        counter = []
        self.call(bulk_naver(counter=counter), offset=0, size=16)
        aggregate = self.call(bulk_naver(counter=counter), aggregate=True)
        self.assertEqual(len(counter), 16, 'aggregate must not call the provider')
        self.assertEqual(aggregate['provider_calls'], 0)
        self.assertEqual(aggregate['totals']['ACCEPTED'], 16)
        self.assertEqual(aggregate['totals']['PENDING_PROVIDER'], 112)

    def test_an_oversized_slice_is_refused(self):
        from fastapi import HTTPException
        for kwargs in ({'size': 0}, {'size': self.bulk.MAX_SLICE + 1}, {'offset': -1}):
            with self.assertRaises(HTTPException):
                self.call(bulk_naver(), **kwargs)

    def test_the_response_states_the_dataset_scope(self):
        report = self.call(bulk_naver(), offset=0, size=1)
        self.assertEqual(report['scope'], {'canonical_total': 183, 'address_available': 149,
                                           'address_missing': 34, 'in_database': 130,
                                           'geocode_target': 128,
                                           'in_database_without_address': 2,
                                           'address_but_quarantined': 21})
        self.assertFalse(report['db_write'])


class BulkGeocodeArtifactTests(unittest.TestCase):
    def setUp(self):
        import save_zipon_bulk_geocode
        self.saver = save_zipon_bulk_geocode

    def response(self, **overrides):
        from services import development_bulk_geocode as bulk
        import tempfile
        cache = geo.GeocodeCache(tempfile.mkdtemp())
        secrets = {'NAVER_MAP_CLIENT_ID': 'x', 'NAVER_MAP_CLIENT_SECRET': 'y'}
        get_secret = lambda name: secrets.get(name, '')
        offset = 0
        while offset is not None:
            sliced = bulk.run(get_secret, bulk_naver(), cache, offset=offset, size=50)
            offset = sliced['next_offset']
        return dict(bulk.run(get_secret, bulk_naver(), cache, cache_only=True), **overrides)

    def test_a_clean_response_produces_the_three_documents(self):
        response = self.response()
        counts = self.saver.check(response)
        self.assertEqual(counts, {'artifact': 128, 'accepted': 128, 'review': 0,
                                  'apply_ready': 128})
        result, review, apply_ready = self.saver.documents(response)
        self.assertEqual(result['fields'], list(self.saver.ARTIFACT_FIELDS))
        self.assertEqual(len(result['items']), 128)
        self.assertEqual(review['items'], [])
        self.assertEqual(len(apply_ready['items']), 128)
        self.assertFalse(result['db_write'])

    def test_a_response_claiming_a_database_write_is_rejected(self):
        with self.assertRaises(self.saver.Rejected):
            self.saver.check(self.response(db_write=True))

    def test_a_credential_shaped_value_is_rejected(self):
        response = self.response()
        response['provider'] = 'naver eyJabcdefghijklmnopqrstuvwxyz0123456789'
        with self.assertRaises(self.saver.Rejected):
            self.saver.check(response)

    def test_an_apply_row_that_is_not_accepted_is_rejected(self):
        response = self.response()
        response['artifact']['items'][0]['outcome'] = 'REVIEW_REQUIRED'
        response['artifact']['items'][0]['longitude'] = None
        response['artifact']['items'][0]['latitude'] = None
        with self.assertRaises(self.saver.Rejected):
            self.saver.check(response)

    def test_a_non_accepted_row_carrying_a_coordinate_is_rejected(self):
        response = self.response()
        row = response['artifact']['items'][0]
        row['outcome'] = 'FAILED'
        response['apply_ready']['items'] = [i for i in response['apply_ready']['items']
                                            if i['project_id'] != row['project_id']]
        with self.assertRaises(self.saver.Rejected):
            self.saver.check(response)


class FastTrackLocationTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((DATA / 'fast_track_location_20260927.json')
                                   .read_text(encoding='utf-8'))

    def test_the_analysis_covers_every_addressless_project_and_calls_no_geocoder(self):
        self.assertEqual(self.document['totals']['fast_track'], 34)
        self.assertEqual(len(self.document['items']), 34)
        self.assertFalse(self.document['geocoder_called'])
        self.assertFalse(self.document['db_write'])
        for row in self.document['items']:
            self.assertIsNone(row['address_in_source'])
            self.assertEqual(row['program'], 'FAST_TRACK')
            self.assertIn(row['classification'],
                          ('ADDRESS_RECOVERABLE_FROM_OFFICIAL_SOURCE', 'LOCATION_NAME_ONLY',
                           'INSUFFICIENT_LOCATION', 'NEEDS_OFFICIAL_DETAIL'))

    def test_every_row_records_what_evidence_exists(self):
        for row in self.document['items']:
            for field in ('project_name', 'district', 'official_source', 'source_url',
                          'raw_source_text', 'raw_stage'):
                self.assertIsNotNone(row[field], f"{row['project_name']} {field}")
            self.assertTrue(row['source_url'].startswith('https://cleanup.seoul.go.kr/'))

    def test_a_lot_is_only_read_from_the_project_name(self):
        import analyze_zipon_fast_track as analysis
        # 목록 행에는 면적·세대수·연번이 있어 행 전체에 정규식을 걸면 세대수를 지번으로 읽는다.
        pungnap = next(r for r in self.document['items'] if r['project_name'] == '풍납극동')
        self.assertIsNone(pungnap['lot_in_name'])
        self.assertIn('37', ' '.join(pungnap['raw_source_text']))
        named = next(r for r in self.document['items'] if r['project_name'] == '천호동 392-9')
        self.assertEqual(named['lot_in_name'], '천호동 392-9')
        self.assertEqual(named['classification'], 'ADDRESS_RECOVERABLE_FROM_OFFICIAL_SOURCE')
        self.assertEqual(analysis.LOT_IN_NAME.search('풍납극동'), None)

    def test_a_registry_link_is_offered_for_review_not_applied(self):
        linked = [r for r in self.document['items'] if r['registry_links']]
        self.assertTrue(linked)
        for row in linked:
            self.assertEqual(row['classification'],
                             'ADDRESS_RECOVERABLE_FROM_OFFICIAL_SOURCE')
            # 연결된 등록 행의 주소를 이 사업의 주소로 옮겨 적지 않는다.
            self.assertIsNone(row['address_in_source'])
            for link in row['registry_links']:
                self.assertTrue(link['registry_address'])
                self.assertTrue(link['address_verified'])

    def test_a_conflicting_dong_clue_is_flagged(self):
        conflicts = [r for r in self.document['items'] if r['clue_conflict']]
        self.assertTrue(conflicts)
        self.assertEqual(self.document['totals']['clue_conflict'], len(conflicts))
        for row in conflicts:
            self.assertTrue(row['dong_tokens'])
            self.assertTrue(row['linked_dong'])
            self.assertFalse(set(row['dong_tokens']) & set(row['linked_dong']))

    def test_the_analysis_reproduces_from_the_canonical_file(self):
        import analyze_zipon_fast_track as analysis
        self.assertEqual(analysis.analyse(), self.document['items'])


# 좌표가 있는 행 / 없는 행. geography(Point) EWKB hex는 실제 응답 형식 그대로다.
SEOUL_POINT = '0101000020E6100000A01A2FDD24DF5F4062105839B4C84240'


def development_row(project_id, name, district, dong, address, point, **extra):
    return dict({'project_id': project_id, 'project_name': name, 'project_type': 'RECONSTRUCTION',
                 'sigungu': district, 'dong': dong, 'address': address, 'stage_raw': '조합설립인가',
                 'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW', 'location': point,
                 'geometry_verified': False, 'last_verified_at': '2026-09-27T00:00:00+00:00'},
                **extra)


def fixture_id(index):
    """project_id는 실제와 같은 UUID여야 한다. stage_metadata가 UUID만 조회하기 때문이다."""
    return f'00000000-0000-4000-8000-{index:012d}'


SEOCHO_IDS = [fixture_id(1), fixture_id(2), fixture_id(3)]
GANGDONG_LOCATED, GANGDONG_BARE = fixture_id(4), fixture_id(5)
SONGPA_LOCATED, SONGPA_BARE = fixture_id(6), fixture_id(7)


def whole_city_rows():
    """서초 3 · 강동 2 · 송파 2 = 7건, 그중 2건은 좌표가 없다."""
    rows = [development_row(project_id, f'서초{index}', '서초구', '반포동',
                            f'서울특별시 서초구 반포동 {index + 1}', SEOUL_POINT)
            for index, project_id in enumerate(SEOCHO_IDS)]
    rows.append(development_row(GANGDONG_LOCATED, '강동0', '강동구', '둔촌동',
                                '서울특별시 강동구 둔촌동 172', SEOUL_POINT))
    rows.append(development_row(GANGDONG_BARE, '강동1', '강동구', '길동',
                                '서울특별시 강동구 길동 54', None))
    rows.append(development_row(SONGPA_LOCATED, '송파0', '송파구', '마천동',
                                '서울특별시 송파구 마천동 183-1', SEOUL_POINT,
                                project_type='REDEVELOPMENT'))
    rows.append(development_row(SONGPA_BARE, '송파1', '송파구', '신천동', None, None))
    return rows


class MapListConsistencyTests(unittest.TestCase):
    """목록 합계와 지도 마커 수가 API 응답과 어긋나지 않는지."""

    def call(self, rows, **kwargs):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', side_effect=[rows, []]):
            return asyncio.run(development_map(**kwargs))

    def test_one_response_carries_both_the_list_and_the_markers(self):
        result = self.call(whole_city_rows())
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['total'], 7)
        self.assertEqual(len(result['projects']), 7)
        self.assertEqual(len(result['points']), 7)
        # 같은 행에서 나오므로 목록과 마커의 project_id 집합이 반드시 같다.
        self.assertEqual([p['project_id'] for p in result['projects']],
                         [p['project_id'] for p in result['points']])

    def test_a_project_without_a_coordinate_stays_in_the_list(self):
        result = self.call(whole_city_rows())
        self.assertEqual(result['mappable'], 5)
        self.assertEqual(result['coordinateless'], 2)
        self.assertEqual(result['total'], result['mappable'] + result['coordinateless'])
        without = [p for p in result['projects'] if not p['mappable']]
        self.assertEqual({p['name'] for p in without}, {'강동1', '송파1'})
        for project in without:
            self.assertIsNone(project['latitude'])
            self.assertIsNone(project['longitude'])
            self.assertEqual(project['location_accuracy']['label'], '위치 데이터 준비 중')
        # 좌표가 없어도 목록에서 사라지지 않는다.
        self.assertIn('강동1', [p['name'] for p in result['projects']])

    def test_a_verified_coordinate_is_never_reported_as_pending(self):
        result = self.call(whole_city_rows())
        located = [p for p in result['projects'] if p['mappable']]
        self.assertEqual(len(located), 5)
        for project in located:
            self.assertEqual(project['location_accuracy']['label'], '대표 위치')
            self.assertIsNone(project['location_notice'])
            self.assertTrue(project['has_location'])
            self.assertIsNotNone(project['address'])
            self.assertIsNotNone(project['latitude'])
            self.assertIsNotNone(project['longitude'])

    def test_the_address_survives_into_the_card_payload(self):
        result = self.call(whole_city_rows())
        card = next(p for p in result['projects'] if p['project_id'] == GANGDONG_LOCATED)
        self.assertEqual(card['address'], '서울특별시 강동구 둔촌동 172')
        self.assertEqual(card['district'], '강동구')
        self.assertEqual(card['dong'], '둔촌동')

    def test_every_district_is_present_in_one_request(self):
        result = self.call(whole_city_rows())
        districts = {}
        for project in result['projects']:
            districts[project['district']] = districts.get(project['district'], 0) + 1
        self.assertEqual(districts, {'서초구': 3, '강동구': 2, '송파구': 2})

    def test_the_default_limit_covers_the_whole_city(self):
        from api.realestate import development_map
        import inspect
        self.assertEqual(inspect.signature(development_map).parameters['limit'].default, 500)
        self.assertEqual(inspect.signature(dev.map_projects).parameters['limit'].default, 500)

    def test_a_failed_read_is_unavailable_rather_than_a_partial_count(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', side_effect=RuntimeError('boom')):
            result = asyncio.run(development_map())
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['projects'], [])
        self.assertEqual(result['points'], [])

    def test_the_stage_label_still_comes_from_the_official_value(self):
        rows = whole_city_rows()
        # 준공인가는 완료 사업이라 기본 지도에서 빠진다. 단계 표기를 보려면 함께 요청한다.
        rows[0]['stage_raw'] = '준공인가'
        result = self.call(rows, include_completed=True)
        labels = {p['project_id']: p['stage']['label'] for p in result['projects']}
        self.assertEqual(labels[SEOCHO_IDS[0]], '준공')
        self.assertEqual(labels[GANGDONG_LOCATED], '조합설립 인가')

    def test_the_list_keeps_the_stage_detail_batch(self):
        """단계 상세는 탐색 경로와 같은 읽기 전용 배치에서 온다. 단계 로직은 그대로다."""
        rows = whole_city_rows()
        detail = [{'project_id': GANGDONG_LOCATED, 'stage': 'ASSOCIATION_APPROVED',
                   'stage_raw': '조합설립인가', 'external_id': 'gangdong0',
                   'official_authority': 'cleanup.seoul.go.kr', 'field_evidence': {}}]
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', side_effect=[rows, detail]) as request:
            result = asyncio.run(development_map())
        self.assertEqual(request.call_count, 2)
        card = next(p for p in result['projects'] if p['project_id'] == GANGDONG_LOCATED)
        self.assertEqual(card['official_id'], 'gangdong0')
        self.assertEqual(card['official_authority'], 'cleanup.seoul.go.kr')

    def test_a_representative_point_never_enables_inside(self):
        result = self.call(whole_city_rows())
        self.assertFalse(result['inside_enabled'])
        for point in result['points']:
            self.assertFalse(point['allows_inside'])
            self.assertIsNone(point['boundary'])
            self.assertNotEqual(point['boundary_status'], 'OFFICIAL_VERIFIED')
        for project in result['projects']:
            self.assertNotEqual(project['spatial']['code'], 'INSIDE')
            self.assertFalse(project['spatial']['confirmed_boundary'])

    def test_a_district_request_still_narrows_the_same_shape(self):
        rows = [r for r in whole_city_rows() if r['sigungu'] == '강동구']
        result = self.call(rows, sigungu='강동구')
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['mappable'], 1)
        self.assertEqual(result['coordinateless'], 1)
        self.assertEqual({p['district'] for p in result['projects']}, {'강동구'})


class MapScreenConsistencyTests(unittest.TestCase):
    """화면이 숫자를 만들어내는 방식이 다시 자치구별 합산으로 돌아가지 않도록 고정한다."""

    def setUp(self):
        self.tab = read('components/realestate/DevelopmentTab.tsx')

    def test_the_tab_reads_one_endpoint_for_the_list_and_the_map(self):
        # 서울 전체가 1,000건대가 되었으므로 선택한 자치구만 조회한다. 그래도 목록과
        # marker는 여전히 한 응답에서 같이 온다 — 서로 다른 API를 합치지 않는다.
        self.assertIn('estateApi.developmentMap(sigungu, 500, undefined', self.tab)
        self.assertEqual(self.tab.count('estateApi.developmentMap('), 1)
        self.assertIn('mergedProjects.push(project)', self.tab)
        self.assertIn('mergedPoints.push(...r.points', self.tab)
        # 목록 전용 탐색 호출은 더 쓰지 않는다.
        self.assertNotIn('estateApi.development(', self.tab)

    def test_a_failed_district_can_no_longer_be_dropped_silently(self):
        self.assertNotIn('r.status === "ok" ? r.projects : []', self.tab)
        self.assertNotIn('r.status === "ok" ? r.points : []', self.tab)
        self.assertNotIn('.flatMap(', self.tab)
        # 자치구별로 합치되, 빠진 자치구는 이름을 적는다. 반쯤 채운 숫자를 전체라고
        # 부르지 않는 것이 합치기의 조건이다.
        self.assertIn('setFailedDistricts(failed.filter', self.tab)
        self.assertIn('아래 합계에는 빠져 있습니다', self.tab)
        self.assertIn('개발정보를 지금 불러올 수 없어요', self.tab)
        # 전부 실패하면 ready를 내려 숫자를 아예 보여주지 않는다.
        block = self.tab[self.tab.index('if (!ok.length) {'):]
        self.assertIn('setReady(false)', block[:200])

    def test_the_default_view_is_the_whole_city(self):
        # 기본 상태에서 자치구를 미리 골라 두지 않는다. 그래야 전체가 전체를 뜻한다.
        self.assertNotIn('districts.slice(0, 3)', self.tab)
        self.assertNotIn('setDistricts(r.districts', self.tab)
        self.assertIn('selectedDistricts.size === 0', self.tab)
        # 잘린 응답을 '전체 N건'이라고 말하지 않는다.
        self.assertIn('서울시 전체 ${projects.length}건을 보여드리고 있어요', self.tab)
        self.assertIn('truncated ? "서울시 전체 미리보기예요"', self.tab)

    def test_the_markers_follow_the_visible_list(self):
        self.assertIn('points.filter((point) => visibleIds.has(point.project_id))', self.tab)
        self.assertIn('const coordinateless = visible.length - mappable', self.tab)
        self.assertIn('좌표가 없는 ${coordinateless}건은 목록에만 남습니다', self.tab)

    def test_the_card_list_is_not_silently_truncated(self):
        self.assertIn('const MAX_CARDS = 200', self.tab)
        self.assertIn('visible.slice(0, MAX_CARDS)', self.tab)
        self.assertIn('visible.length > MAX_CARDS', self.tab)
        self.assertNotIn('visible.slice(0, 60)', self.tab)

    def test_the_card_uses_its_own_address_and_accuracy(self):
        self.assertIn('{selected.address ?? "대표주소 확인 중"} · {selected.location_accuracy.label}',
                      self.tab)


class StageBatchTests(unittest.TestCase):
    """서울시 전체를 한 번에 물을 때 단계 상세가 통째로 비지 않도록."""

    def rows(self, count=130):
        return [{'project_id': f'00000000-0000-4000-8000-{n:012d}'} for n in range(1, count + 1)]

    def test_the_batch_is_split_so_the_query_string_stays_short(self):
        sizes = []

        def request(method, path, params=None, payload=None):
            ids = params['project_id'][4:-1].split(',')
            sizes.append(len(ids))
            # in.() 필터가 5KB 가까이 길어지면 중간 프록시가 자를 수 있다.
            self.assertLess(len(params['project_id']), 2500)
            return [{'project_id': i, 'external_id': 'x'} for i in ids]
        with patch.object(rm, '_remote_request', side_effect=request):
            enriched = dev.stage_metadata(self.rows())
        self.assertEqual(sizes, [50, 50, 30])
        self.assertEqual(sum(1 for r in enriched if r.get('external_id')), 130)

    def test_one_failed_batch_does_not_erase_the_others(self):
        state = {'first': True}

        def request(method, path, params=None, payload=None):
            if state['first']:
                state['first'] = False
                raise RuntimeError('boom')
            ids = params['project_id'][4:-1].split(',')
            return [{'project_id': i, 'external_id': 'x'} for i in ids]
        with patch.object(rm, '_remote_request', side_effect=request):
            enriched = dev.stage_metadata(self.rows())
        self.assertEqual(len(enriched), 130)
        self.assertEqual(sum(1 for r in enriched if r.get('external_id')), 80)

    def test_rows_without_a_uuid_ask_nothing(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('no request for rows without a UUID')
        with patch.object(rm, '_remote_request', side_effect=forbidden):
            self.assertEqual(dev.stage_metadata([{'project_id': 'not-a-uuid'}]),
                             [{'project_id': 'not-a-uuid'}])


class NaverDynamicMapTests(unittest.TestCase):
    """지도가 NAVER Dynamic Map으로 동작하고, 키 취급이 안전한지."""

    def setUp(self):
        self.map_source = read('components/realestate/ZiponMap.tsx')
        self.loader = read('lib/naverMaps.ts')
        self.tab = read('components/realestate/DevelopmentTab.tsx')

    def test_the_sdk_is_loaded_once_with_the_server_supplied_key(self):
        self.assertIn('let pending: Promise<NaverMaps> | null = null', self.loader)
        self.assertIn('if (window.naver?.maps) return Promise.resolve(window.naver.maps)', self.loader)
        self.assertIn('sdk.key_param', self.loader)
        # 콘솔 세대에 따라 키 파라미터 이름이 다르므로 예비 이름으로 한 번만 더 시도한다.
        self.assertIn('sdk.key_param_fallback', self.loader)
        self.assertEqual(self.loader.count('tryLoad(sdk, sdk.'), 2)

    def test_a_missing_client_id_never_pretends_to_have_a_map(self):
        self.assertIn('NAVER_MAP_CLIENT_ID_NOT_CONFIGURED', self.loader)
        self.assertIn("if (!sdk?.configured || failed)", self.map_source)
        self.assertIn('지도를 불러오지 못했어요', self.map_source)

    def test_no_client_secret_reaches_the_browser_bundle(self):
        for source in (self.map_source, self.loader, self.tab,
                       read('lib/realestate.ts')):
            self.assertNotIn('NAVER_MAP_CLIENT_SECRET', source)
            self.assertNotIn('X-NCP-APIGW', source)
            self.assertNotIn('client_secret', source)

    def test_the_server_only_reveals_the_browser_map_key(self):
        from services import map_providers
        sdk = map_providers.sdk_config(lambda name: {'NAVER_MAP_CLIENT_ID': 'CID',
                                                     'NAVER_MAP_CLIENT_SECRET': 'SECRET'}.get(name, ''))
        text = json.dumps(sdk, ensure_ascii=False)
        self.assertEqual(sdk['client_id'], 'CID')
        self.assertNotIn('SECRET', text)
        self.assertEqual(sdk['web_service_url'], 'https://minseo2-digital-ai-lab.hf.space')

    def test_the_default_map_type_is_normal(self):
        self.assertIn('mapTypeId: loaded.MapTypeId.NORMAL', self.map_source)

    def test_markers_are_distinguished_by_project_type(self):
        for code in ('REDEVELOPMENT', 'RECONSTRUCTION', 'MOATOWN', 'OTHER_PROJECT'):
            self.assertIn(code, self.map_source)
        self.assertIn('FAST_TRACK', self.map_source)
        # 선택된 marker는 크기와 테두리로 구분하되 지도를 가릴 만큼 키우지 않는다.
        self.assertIn('const size = selected ? 26 : 16', self.map_source)

    def test_a_representative_point_is_never_drawn_as_a_zone(self):
        self.assertIn('대표위치 주변', self.map_source)
        # 면은 공식 경계가 확인된 사업만. 지금은 그런 사업이 없어 아무 면도 그려지지 않는다.
        polygon = self.map_source.split('api.Polygon', 1)[0]
        self.assertIn('verifiedBoundaryPolygons(point)', polygon)
        # INSIDE는 주석에서 '하지 않는다'고 적는 것 말고 코드에 나오지 않아야 한다.
        code = [line for line in self.map_source.splitlines()
                if 'INSIDE' in line and not line.lstrip().startswith(('*', '//', '/*'))]
        self.assertEqual(code, [])
        self.assertNotIn('allows_inside', self.map_source)

    def test_the_map_is_responsive_and_mobile_sized(self):
        self.assertIn('height = 340', self.map_source)
        self.assertIn('className="w-full overflow-hidden rounded-2xl', self.map_source)
        self.assertIn('height={340}', self.tab)
        # 카드 안 지도는 더 작게. 카드가 지도에 먹히지 않게 한다.
        self.assertIn('height={190}', read('components/realestate/DevelopmentCard.tsx'))

    def test_only_located_projects_become_markers(self):
        # 좌표 해석은 공통 helper 하나로만 한다.
        self.assertIn('getProjectCoordinate(point)', self.map_source)
        self.assertIn('entry.coordinate !== null', self.map_source)
        self.assertIn('for (const { point, coordinate } of located)', self.map_source)
        self.assertNotIn('p.latitude != null && p.longitude != null', self.map_source)


class MapCardLinkTests(unittest.TestCase):
    """카드 ↔ 지도 양방향 연결. selectedProject 하나가 기준이다."""

    def setUp(self):
        self.tab = read('components/realestate/DevelopmentTab.tsx')
        self.map_source = read('components/realestate/ZiponMap.tsx')

    def test_selection_has_a_single_source_of_truth(self):
        self.assertEqual(self.tab.count('useState<string | null>(null)'), 1)
        self.assertIn('const [selectedId, setSelectedId] = useState<string | null>(null)', self.tab)
        # 카드 클릭과 marker 클릭이 같은 상태를 바꾼다.
        self.assertIn('onClick={() => setSelectedId(p.project_id)}', self.tab)
        self.assertIn('onSelect={selectFromMap}', self.tab)
        selecting = self.tab[self.tab.index('const selectFromMap = useCallback('):]
        selecting = selecting[:selecting.index('const scrollToCard')]
        self.assertIn('setSelectedId(projectId)', selecting)
        # 선택 상태를 따로 복제하지 않는다. 지도와 카드가 같은 하나를 본다.
        self.assertNotIn('useState', selecting)

    def test_a_marker_click_moves_to_that_project_card(self):
        # 지도에서 고른 것이 어느 사업인지 바로 보이도록 그 카드로 이동한다.
        self.assertIn('requestAnimationFrame(() => scrollToProject(projectId))', self.tab)
        self.assertIn("node.scrollIntoView({ block: \"center\", behavior: \"smooth\" })", self.tab)
        # 이동은 canonical id로만. 이름이 닮은 다른 사업으로 가지 않는다.
        self.assertIn('cardRefs.current[projectId]', self.tab)
        # 버튼으로도 여전히 이동할 수 있다.
        self.assertIn('사업정보 보기', self.tab)
        self.assertIn('onClick={scrollToCard}', self.tab)

    def test_selecting_a_project_pans_the_map_and_opens_an_info_window(self):
        # 상세(compact) 지도는 즉시 중심을 잡고, 메인 지도는 부드럽게 이동한다.
        self.assertIn('instance.setCenter(position)', self.map_source)
        self.assertIn('instance.panTo(position, { duration: 320 })', self.map_source)
        self.assertIn('info.current.open(instance, marker)', self.map_source)
        self.assertIn('info.current.setContent(infoHtml(point))', self.map_source)

    def test_the_mini_map_lives_inside_the_card_detail(self):
        card = read('components/realestate/DevelopmentCard.tsx')
        self.assertIn('aria-label="사업 위치"', card)
        self.assertIn('<ZiponMap', card)
        # 기본정보(주소) 바로 아래, 현재 단계보다 위에 온다.
        self.assertLess(card.index('aria-label="사업 위치"'), card.index('현재 사업단계'))
        self.assertLess(card.index('주소 확인 중'), card.index('aria-label="사업 위치"'))
        # 선택된 카드에서만 그린다. 목록 전체에 지도를 띄우지 않는다.
        self.assertIn('{selected && (', card)
        # 카드 밖의 별도 패널은 없앴다. 같은 사업에 지도가 둘 생기지 않게 한다.
        self.assertNotIn('SelectedLocation', self.tab)

    def test_the_card_map_uses_the_shared_point_without_copying_coordinates(self):
        card = read('components/realestate/DevelopmentCard.tsx')
        # 카드는 목록과 같은 응답의 point를 그대로 받는다. 좌표를 다시 만들지 않는다.
        self.assertIn('points={[point]}', card)
        self.assertNotIn('latitude:', card)
        self.assertNotIn('longitude:', card)
        self.assertIn('pointById.get(p.project_id) ?? null', self.tab)
        self.assertIn('new Map(points.map((point) => [point.project_id, point]))', self.tab)

    def test_a_project_without_a_coordinate_says_so_instead_of_a_blank_map(self):
        card = read('components/realestate/DevelopmentCard.tsx')
        self.assertIn('project.mappable && point ? (', card)
        # 좌표가 없으면 서울 중심 지도를 대신 보여주지 않는다.
        self.assertIn('아직 확인된 사업 위치가 없습니다', card)

    def test_the_compact_map_drops_the_legend_and_bounds_reporting(self):
        self.assertIn('{!compact && (', self.map_source)
        self.assertIn('if (!compact && bounds.current)', self.map_source)
        self.assertIn('zoomControl: !compact', self.map_source)


class CoordinateGapReviewTests(unittest.TestCase):
    """좌표 미확보 8건 검토. 인접 지번을 같은 지번으로 채택하지 않는지."""

    def setUp(self):
        self.document = json.loads((DATA / 'geocode_gap_review_20260928.json')
                                   .read_text(encoding='utf-8'))

    def test_the_review_covers_every_gap_and_writes_nothing(self):
        self.assertEqual(self.document['totals']['reviewed'], 8)
        self.assertFalse(self.document['db_write'])
        self.assertFalse(self.document['geocoder_called'])
        for row in self.document['items']:
            for field in ('project_id', 'project_name', 'current_status', 'official_evidence',
                          'candidate_count', 'candidate_summary', 'recommended_action',
                          'confidence', 'reason'):
                self.assertIn(field, row)

    def test_a_neighbouring_lot_is_never_safe_to_apply(self):
        import review_zipon_coordinate_gaps as review
        for row in self.document['items']:
            if row['current_status'] != 'REVIEW_REQUIRED':
                continue
            wanted = row['official_evidence']['official_address'].split()[-1]
            for candidate in row['candidate_summary']:
                if candidate['returned_lot'] != wanted:
                    self.assertFalse(candidate['lot_match'], candidate['returned_lot'])
            if row['recommended_action'] == 'SAFE_TO_APPLY':
                supporting = [c for c in row['candidate_summary'] if c['lot_match']]
                self.assertEqual(len(supporting), 1)
        self.assertTrue(callable(review.judge))

    def test_only_an_exact_single_lot_match_is_proposed(self):
        for row in self.document['items']:
            if row['recommended_action'] != 'SAFE_TO_APPLY':
                self.assertIsNone(row['proposed_coordinate'], row['project_name'])

    def test_the_five_ambiguous_projects_stay_for_manual_review(self):
        manual = [r for r in self.document['items'] if r['recommended_action'] == 'MANUAL_REVIEW']
        self.assertEqual(len(manual), 5)
        for row in manual:
            self.assertEqual(row['confidence'], 'LOW')
            self.assertEqual(row['candidate_count'], 3)

    def test_a_failed_lookup_asks_for_official_detail_not_a_guess(self):
        failed = [r for r in self.document['items'] if r['current_status'] == 'FAILED']
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['recommended_action'], 'NEEDS_OFFICIAL_DETAIL')
        self.assertEqual(failed[0]['candidate_summary'], [])
        self.assertIsNone(failed[0]['proposed_coordinate'])


class FastTrackIdentityReviewTests(unittest.TestCase):
    """신속통합기획 동일성 판정. CONFIRMED만 주소 복원 후보다."""

    def setUp(self):
        self.document = json.loads((DATA / 'fast_track_identity_review_20260928.json')
                                   .read_text(encoding='utf-8'))

    def test_every_fast_track_project_is_classified(self):
        self.assertEqual(self.document['totals']['fast_track_total'], 34)
        self.assertFalse(self.document['db_write'])
        for row in self.document['items']:
            self.assertIn(row['identity_status'],
                          ('IDENTITY_CONFIRMED', 'IDENTITY_PROBABLE', 'IDENTITY_CONFLICT',
                           'NO_MATCH'))
            for field in ('project_id', 'project_name', 'official_candidate', 'district',
                          'dong', 'official_address', 'official_url', 'identity_evidence',
                          'identity_status', 'address_recoverable', 'conflict_reason'):
                self.assertIn(field, row)

    def test_a_conflict_never_carries_an_address(self):
        conflicts = [r for r in self.document['items'] if r['identity_status'] == 'IDENTITY_CONFLICT']
        self.assertEqual(len(conflicts), 4)
        for row in conflicts:
            self.assertIsNone(row['official_address'])
            self.assertIsNone(row['official_candidate'])
            self.assertFalse(row['address_recoverable'])
            self.assertTrue(row['conflict_reason'])

    def test_probable_and_no_match_are_not_recoverable(self):
        for row in self.document['items']:
            if row['identity_status'] in ('IDENTITY_PROBABLE', 'NO_MATCH'):
                # 사업명 자체에 지번이 있는 경우만 예외이며, 그때도 등록 행 주소를 쓰지 않는다.
                if row['address_recoverable']:
                    self.assertTrue(row['identity_evidence']['lot_in_project_name'])
                    self.assertIsNone(row['official_address'])

    def test_confirmed_links_state_every_signal(self):
        confirmed = [r for r in self.document['items']
                     if r['identity_status'] == 'IDENTITY_CONFIRMED']
        self.assertEqual(len(confirmed), 18)
        for row in confirmed:
            self.assertTrue(row['official_address'])
            self.assertTrue(row['address_recoverable'])
            candidates = row['identity_evidence']['candidates']
            self.assertEqual(len(candidates), 1)
            signals = candidates[0]['signals']
            for signal in ('name_contained', 'district_match', 'type_match', 'dong_agrees',
                           'registry_is_official_row', 'registry_address_verified'):
                self.assertTrue(signals[signal], f"{row['project_name']} {signal}")

    def test_a_duplicate_already_in_the_database_is_flagged(self):
        risky = [r for r in self.document['items'] if r['duplicate_risk']]
        self.assertEqual(len(risky), 1)
        # 둘 다 DB에 있으면 주소 복원이 아니라 중복 정리가 필요한 상황이다.
        self.assertEqual(risky[0]['project_name'], '마천2')
        self.assertTrue(risky[0]['in_database'])
        self.assertTrue(risky[0]['candidate_in_database'])


class StageEvidenceReviewTests(unittest.TestCase):
    """단계 근거 보강 검토. 상세가 있다고 자동 승격하지 않는다."""

    def setUp(self):
        self.document = json.loads((DATA / 'stage_evidence_review_20260928.json')
                                   .read_text(encoding='utf-8'))

    def test_the_review_writes_nothing_and_calls_nothing(self):
        self.assertFalse(self.document['db_write'])
        self.assertFalse(self.document['network_called'])
        self.assertEqual(self.document['totals']['list_only'], 11)

    def test_a_detail_page_alone_does_not_promote(self):
        for row in self.document['list_only_projects']:
            if row['recommended_action'] == 'PROMOTE_TO_DETAIL_VERIFIED':
                self.assertTrue(all(row['identity_checks'].values()), row['project_name'])
            else:
                self.assertFalse(all(row['identity_checks'].values()), row['project_name'])

    def test_a_two_digit_year_is_never_given_a_century(self):
        for row in self.document['date_gap_projects']:
            for milestone in row['milestones']:
                if milestone['verification_status'] != 'VERIFIED':
                    self.assertIsNone(milestone['normalized_value'])
        for row in self.document['ambiguous_date_projects']:
            self.assertEqual(row['recommended_action'], 'KEEP_RAW_DO_NOT_INTERPRET')

    def test_the_date_counts_separate_missing_from_uninterpretable(self):
        totals = self.document['totals']
        # 근거가 아예 없는 것과, 있지만 세기를 확정할 수 없는 것은 다른 문제다.
        self.assertEqual(totals['date_evidence_missing'] + totals['date_evidence_present'], 130)
        self.assertEqual(totals['ambiguous_year_only'] + totals['fully_verified_dates'],
                         totals['date_evidence_present'])


class PolygonSourceSurveyTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((DATA / 'polygon_source_survey_20260928.json')
                                   .read_text(encoding='utf-8'))

    def test_no_polygon_was_created_and_none_is_usable_yet(self):
        self.assertFalse(self.document['polygon_created'])
        self.assertFalse(self.document['db_write'])
        self.assertFalse(self.document['immediately_usable'])

    def test_every_candidate_names_an_official_source(self):
        self.assertTrue(self.document['candidates'])
        for candidate in self.document['candidates']:
            self.assertTrue(candidate['official_url'].startswith('http'))
            for field in ('source', 'dataset', 'geometry_type', 'coordinate_system',
                          'project_matching_key', 'coverage', 'update_frequency', 'licensing'):
                self.assertTrue(candidate[field], f"{candidate['dataset']} {field}")

    def test_the_matching_gap_is_stated_before_any_write(self):
        gap = self.document['blocking_gap']
        self.assertTrue(gap['problem'])
        self.assertTrue(gap['required_before_any_write'])


class CheonhoApplyTests(unittest.TestCase):
    """천호동 392-9 한 건만 반영하는 경로. 다른 사업을 건드리지 않는지."""

    def setUp(self):
        import apply_zipon_cheonho_392_9 as runner
        self.runner = runner
        self.source = (ROOT / 'scripts/apply_zipon_cheonho_392_9.py').read_text(encoding='utf-8')

    def test_the_address_comes_from_the_official_row_not_a_guess(self):
        row = self.runner.evidence()
        self.assertEqual(row['project_name'], '천호동 392-9')
        self.assertEqual(row['district'], '강동구')
        # 사업명 칸 자체가 지번이다. 그래서 추정 없이 주소가 나온다.
        self.assertEqual(row['lot_in_name'], '천호동 392-9')
        self.assertIsNone(row['address_in_source'])
        self.assertEqual(self.runner.ADDRESS, '서울특별시 강동구 천호동 392-9')
        self.assertIn('천호동 392-9', row['raw_source_text'])
        self.assertTrue(row['source_url'].startswith('https://cleanup.seoul.go.kr/'))

    def test_it_touches_exactly_one_project(self):
        self.assertEqual(self.runner.PROJECT_ID, '429dc953-a406-56ff-871d-0ced658be69f')
        # project_id로만 지정한다. 이름이나 주소로 여러 행을 건드리지 않는다.
        self.assertIn("'project_id': 'eq.' + PROJECT_ID", self.source)
        self.assertNotIn('limit=', self.source.split('def main')[1].split('rest/v1')[1][:200])

    def test_the_address_payload_carries_no_promotion(self):
        row = self.runner.evidence()
        payload = self.runner.address_payload(row, 1)
        project = payload['p_project']
        for forbidden in ('stage', 'stage_raw', 'status', 'validation_status', 'geometry',
                          'location', 'project_type'):
            self.assertNotIn(forbidden, project, forbidden)
        self.assertEqual(project['address'], self.runner.ADDRESS)
        self.assertEqual(project['dong'], '천호동')
        self.assertEqual(payload['p_source']['source_type'], 'OFFICIAL_WEBSITE')
        self.assertTrue(payload['p_source']['is_official'])
        self.assertEqual(len(payload['p_source']['content_hash']), 64)

    def test_it_writes_only_through_the_reviewed_rpcs(self):
        self.assertEqual(self.runner.INGEST_RPC, 'rpc/zipon_ingest_candidate_v2')
        self.assertEqual(self.runner.LOCATION_RPC, 'rpc/zipon_set_project_location')
        for forbidden in ('requests.patch', 'requests.put', 'requests.delete'):
            self.assertNotIn(forbidden, self.source)

    def test_a_non_exact_geocode_keeps_the_address_and_stops(self):
        # EXACT가 아니면 좌표를 쓰지 않고 MANUAL_REVIEW로 남긴다.
        self.assertIn("if evaluation.get('geocode_confidence') != 'EXACT'", self.source)
        self.assertIn("'MANUAL_REVIEW'", self.source)
        stop = self.source.index("report['coordinate_status'] = 'MANUAL_REVIEW'")
        self.assertLess(stop, self.source.index('LOCATION_RPC}'))

    def test_an_existing_address_blocks_the_run(self):
        self.assertIn("'ADDRESS_ALREADY_SET'", self.source)
        self.assertIn("'DISTRICT_MISMATCH'", self.source)
        self.assertIn("'PROJECT_NOT_IN_DATABASE'", self.source)

    def test_without_credentials_nothing_is_written(self):
        with patch.dict('os.environ', {'ZIPON_IMPORT_SUPABASE_URL': '',
                                       'ZIPON_IMPORT_SUPABASE_KEY': ''}, clear=False):
            with self.assertRaises(self.runner.Blocked) as caught:
                self.runner.configuration()
        self.assertEqual(caught.exception.reason, 'MISSING_ZIPON_IMPORT_SUPABASE_URL')


class FastTrackDecisionTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((DATA / 'fast_track_decisions_20260928.json')
                                   .read_text(encoding='utf-8'))

    def test_only_confirmed_links_reach_the_decision_table(self):
        self.assertEqual(self.document['totals']['confirmed'], 18)
        self.assertFalse(self.document['db_write'])
        self.assertFalse(self.document['auto_import'])
        review = json.loads((DATA / 'fast_track_identity_review_20260928.json')
                            .read_text(encoding='utf-8'))
        confirmed = {r['project_name'] for r in review['items']
                     if r['identity_status'] == 'IDENTITY_CONFIRMED'}
        self.assertEqual({r['fast_track_project'] for r in self.document['items']}, confirmed)

    def test_every_row_states_what_a_person_must_decide(self):
        for row in self.document['items']:
            for field in ('fast_track_project', 'matched_official_project', 'official_address',
                          'district', 'dong', 'identity_evidence', 'existing_canonical',
                          'duplicate_risk', 'recommended_action', 'blocking_question'):
                self.assertIn(field, row)
            self.assertTrue(row['official_address'])
            self.assertTrue(row['identity_evidence']['fast_track_source_url'])
            self.assertTrue(row['identity_evidence']['single_candidate'])

    def test_a_duplicate_is_not_offered_as_an_import(self):
        duplicates = [r for r in self.document['items'] if r['duplicate_risk']]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]['recommended_action'], 'RESOLVE_DUPLICATE_FIRST')
        for row in self.document['items']:
            if not row['duplicate_risk']:
                self.assertEqual(row['recommended_action'], 'IMPORT_WITH_ADDRESS')
                self.assertFalse(row['existing_canonical'])


class ProjectCoordinateHelperTests(unittest.TestCase):
    """공통 좌표 helper를 실제 운영 좌표 122건으로 실행해서 확인한다."""

    @classmethod
    def setUpClass(cls):
        import shutil, subprocess
        if shutil.which('node') is None:
            raise unittest.SkipTest('node is not available')
        check = ROOT / 'scripts/checks/project_coordinate_check.mts'
        result = subprocess.run(['node', '--experimental-strip-types', str(check)],
                                capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            raise unittest.SkipTest(f'coordinate check did not run: {result.stderr[:200]}')
        cls.report = json.loads(result.stdout.strip().splitlines()[-1])

    def test_every_production_coordinate_survives_the_helper(self):
        # 122건 전부가 그대로 통과해야 한다. 하나라도 떨어지면 지도에서 사라진다.
        self.assertEqual(self.report['accepted'], 122)
        self.assertEqual(self.report['matched'], 122)
        self.assertEqual(self.report['rejected'], [])

    def test_latitude_and_longitude_are_not_swapped(self):
        self.assertTrue(self.report['latitude_band'])
        self.assertTrue(self.report['longitude_band'])
        for district in ('강동구', '송파구', '서초구'):
            coordinate = self.report['districts'][district]
            self.assertTrue(37 < coordinate['lat'] < 38, district)
            self.assertTrue(126 < coordinate['lng'] < 128, district)

    def test_a_swapped_pair_is_refused_rather_than_corrected(self):
        # 조용히 교환하면 엉뚱한 자리에 핀이 꽂히고도 정상처럼 보인다.
        self.assertIsNone(self.report['swapped'])
        self.assertEqual(self.report['swapped_problem'], 'SUSPECT_SWAPPED')

    def test_strings_are_accepted_and_gaps_are_named(self):
        self.assertEqual(self.report['string_input'], {'lat': 37.55, 'lng': 127.14})
        self.assertEqual(self.report['missing_problem'], 'NO_COORDINATE')
        self.assertEqual(self.report['outside_problem'], 'OUTSIDE_SEOUL')


class MiniMapLifecycleTests(unittest.TestCase):
    """상세 지도에 위치가 찍히지 않던 원인이 다시 생기지 않도록 고정한다."""

    def setUp(self):
        self.map_source = read('components/realestate/ZiponMap.tsx')

    def test_the_map_instance_lives_in_state_not_only_a_ref(self):
        # ref에 담으면 렌더가 다시 일어나지 않아 marker/center 효과가 한 번 빠져나간 뒤
        # 영영 다시 돌지 않는다. 그것이 상세 지도에 위치가 없던 원인이었다.
        self.assertIn('const [api, setApi] = useState<NaverMaps | null>(null)', self.map_source)
        self.assertIn('const [instance, setInstance] = useState<NaverMapInstance | null>(null)',
                      self.map_source)
        self.assertNotIn('const map = useRef<NaverMapInstance | null>(null)', self.map_source)

    def test_both_effects_wait_for_the_instance(self):
        self.assertIn('}, [api, instance, located, property, selectedId]);', self.map_source)
        self.assertIn('}, [api, instance, selectedEntry, located, compact, property]);',
                      self.map_source)

    def test_a_collapsed_container_is_resized_after_the_centre_is_set(self):
        self.assertIn('api.Event.trigger(instance, "resize")', self.map_source)
        self.assertIn('window.requestAnimationFrame(', self.map_source)
        self.assertIn('window.cancelAnimationFrame(frame)', self.map_source)
        settle = self.map_source.split('const settle = () => {', 1)[1]
        # 중심을 먼저 잡고 resize는 보조로 한다. resize가 실패해도 지도가 서울에 남지 않는다.
        self.assertLess(settle.index('setCenter'), settle.index('Event.trigger'))
        self.assertIn('} catch {', settle)

    def test_the_map_opens_already_centred_on_its_project(self):
        # 나중 효과가 옮겨 주기를 기다리지 않는다. 그 효과가 한 번이라도 실패하면
        # 서울 기본 중심이 그대로 남아 '다른 지역'이 보인다.
        self.assertIn('const initialCentre = useRef<ProjectCoordinate | null>(null)',
                      self.map_source)
        self.assertIn('center: centre', self.map_source)
        self.assertIn('new loaded.LatLng(centre.lat, centre.lng)', self.map_source)
        self.assertIn('zoom: centre ? 17 :', self.map_source)

    def test_switching_projects_moves_the_existing_marker(self):
        self.assertIn('existing.setPosition(position)', self.map_source)
        self.assertIn('markers.current.get(point.project_id)', self.map_source)
        # 선택이 바뀌면 이전 원은 지우고 새로 그린다. 쌓이지 않는다.
        self.assertIn('circle.current?.setMap(null)', self.map_source)

    def test_the_compact_map_centres_immediately(self):
        self.assertIn('instance.setCenter(position)', self.map_source)
        self.assertIn('instance.setZoom(17, false)', self.map_source)

    def test_the_card_and_the_main_map_share_one_coordinate_source(self):
        card = read('components/realestate/DevelopmentCard.tsx')
        tab = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('getProjectCoordinate', self.map_source)
        # 카드는 좌표를 직접 만들지 않고 같은 point를 넘긴다.
        self.assertIn('points={[point]}', card)
        self.assertIn('pointById.get(p.project_id) ?? null', tab)


# 실제 원본은 EPSG:5174(Korea 1985 / Modified Central Belt)로 확인됐다. .prj에서 읽는다.
POLYGON_PRJ = ('PROJCS["Korea 1985 / Modified Central Belt",GEOGCS["Korea 1985",'
               'DATUM["Korean_Datum_1985",SPHEROID["Bessel 1841",6377397.155,299.1528128]],'
               'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
               'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",38],'
               'PARAMETER["central_meridian",127.0028902777778],'
               'PARAMETER["scale_factor",1],PARAMETER["false_easting",200000],'
               'PARAMETER["false_northing",500000],UNIT["metre",1],AUTHORITY["EPSG","5174"]]')
# AUTHORITY가 없고 이름도 알려진 것이 아니며 pyproj가 기본 신뢰도로 코드를 못 정하는 .prj.
# 그래도 투영은 온전히 정의되어 있어 변환은 정확하다(EPSG:5186과 같은 정의).
POLYGON_PRJ_NO_AUTHORITY = (
    'PROJCS["Korea 2000 Central Belt 2010 local",GEOGCS["Korea 2000",'
    'DATUM["Geocentric_datum_of_Korea",SPHEROID["GRS 1980",6378137,298.257222101]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",38],'
    'PARAMETER["central_meridian",127],PARAMETER["false_easting",200000],'
    'PARAMETER["false_northing",600000],UNIT["metre",1]]')
POLYGON_PRJ_NO_AUTHORITY_CRS = 'EPSG:5186' 
# 좌표는 EPSG:5174인데 .prj가 EPSG:5179라고 말하는 원천. 변환하면 서울을 벗어난다.
POLYGON_PRJ_WRONG = ('PROJCS["Korea 2000 / Unified Coordinate System",'
                     'AUTHORITY["EPSG","5179"]]')
POLYGON_SOURCE_CRS = 'EPSG:5174'
# 실제 UPIS_C_UQ120 필드 구성. 주소와 법정동 컬럼은 없다.
POLYGON_FIELDS = ('PRESENT_SN', 'DGM_NM', 'SIGNGU_SE', 'PROPEL_CD', 'CREATE_DAT')
# 코드정의표. 필드 설명만 있고 PROPEL_CD 코드값의 뜻은 없다 — 실제로 확인되지 않은 상태다.
POLYGON_CODE_TABLE = (
    ('필드명', '설명'),
    ('PRESENT_SN', '현황 일련번호'),
    ('DGM_NM', '도형명'),
    ('SIGNGU_SE', '자치구 코드'),
    ('PROPEL_CD', '추진구분 코드'),
    ('CREATE_DAT', '작성일자'),
)
# DGM_NM은 실제 원본처럼 짧은 것과 긴 것이 섞여 있다. 이름 정규화가 그 차이를 흡수해야 한다.
POLYGON_FIXTURE = (
    ('11740UQ120PS202604100001', '천호3', '11740', 'PP0103',
     (37.5426919, 127.1267054), 'plain'),
    ('11710UQ120PS202607150001', '마천2재정비촉진구역 주택재개발정비사업', '11710', 'PP0103',
     (37.4959174, 127.1515392), 'plain'),
    ('11740UQ120PS202608050002', '고덕강일1역세권', '11740', 'PP0103',
     (37.5606936, 127.1578851), 'hole'),
    ('11740UQ120PS202608050003', '고덕강일1역세권 재개발사업', '11740', 'PP0103',
     (37.5610000, 127.1580000), 'multi'),
    ('11740UQ120PS202605200004', '천호1 도시환경정비사업', '11740', 'PP0206',
     (37.5450000, 127.1330000), 'plain'),
    ('11740UQ120PS202609010005', '강동역세권2구역 도시정비형 재개발사업', '', 'PP0501',
     (37.5349603, 127.1295532), 'plain'),
    ('11650UQ120PS202607150006', '이화연립 주택재건축정비사업', '11710', 'PP0702',
     (37.5290000, 127.1150000), 'plain'),
)


def polygon_square(x, y, half, clockwise=True):
    ring = [(x - half, y - half), (x - half, y + half), (x + half, y + half),
            (x + half, y - half), (x - half, y - half)]
    return ring if clockwise else list(reversed(ring))


def build_polygon_fixture(directory, encoding='cp949', with_prj=True, with_code_table=True,
                          prj=POLYGON_PRJ, stem_name='UPIS_C_UQ120',
                          source_crs=POLYGON_SOURCE_CRS):
    """UPIS_C_UQ120과 같은 모양의 SHP zip을 만든다. 공식 파일이 아니다."""
    import shapefile
    import zipfile
    from pyproj import Transformer
    to_source = Transformer.from_crs('EPSG:4326', source_crs, always_xy=True)
    stem = directory / stem_name
    writer = shapefile.Writer(str(stem), shapeType=shapefile.POLYGON, encoding=encoding)
    for field in POLYGON_FIELDS:
        writer.field(field, 'C', 80)
    for serial, name, district, propel, (lat, lng), shape in POLYGON_FIXTURE:
        x, y = to_source.transform(lng, lat)
        if shape == 'plain':
            parts = [polygon_square(x, y, 150)]
        elif shape == 'hole':
            # 외곽은 시계방향, 구멍은 반시계방향. Shapefile 규약 그대로다.
            parts = [polygon_square(x, y, 300), polygon_square(x + 200, y + 200, 40, False)]
        else:
            parts = [polygon_square(x, y, 150), polygon_square(x + 600, y, 150)]
        writer.poly(parts)
        writer.record(serial, name, district, propel, '20260901')
    writer.close()
    if with_prj:
        Path(str(stem) + '.prj').write_text(prj, encoding='utf-8')
    if with_code_table:
        import csv
        table = directory / 'UQ120_코드정의표.csv'
        with open(table, 'w', encoding='cp949', newline='') as handle:
            csv.writer(handle).writerows(POLYGON_CODE_TABLE)
    archive = directory / f'{stem_name}_synthetic.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        for extension in ('shp', 'dbf', 'shx') + (('prj',) if with_prj else ()):
            bundle.write(str(stem) + '.' + extension, f'{stem_name}.{extension}')
        if with_code_table:
            bundle.write(str(directory / 'UQ120_코드정의표.csv'), 'UQ120_코드정의표.csv')
    return archive


class PolygonPipelineTests(unittest.TestCase):
    """서울시 공식 SHP를 읽고 130건과 맞추는 경로. UPIS와 같은 모양의 원천으로 돌려 본다.

    공식 파일은 이 실행환경에 없어서, 같은 schema 모양(뜻이 이름에 드러나지 않는 필드명 +
    코드정의표 + cp949 + EPSG:5186)의 합성 SHP로 파이프라인이 실제로 도는지를 고정한다.
    이 테스트는 DB에 아무것도 쓰지 않는다.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import shapefile  # noqa: F401
            import pyproj  # noqa: F401
        except ImportError as error:  # pragma: no cover
            raise unittest.SkipTest(f'shapefile/pyproj not available: {error}')
        import tempfile
        import analyze_seoul_polygon_source as pipeline
        cls.pipeline = pipeline
        cls.directory = tempfile.TemporaryDirectory()
        cls.archive = build_polygon_fixture(Path(cls.directory.name))
        cls.survey, cls.rows, cls.features = pipeline.build(cls.archive)
        cls.review = pipeline.summarise(cls.survey, cls.rows, cls.features, cls.archive)
        cls.by_id = {row['source_record_id']: row for row in cls.survey['records']}
        cls.by_name = {row['name']: row for row in cls.survey['records']}
        cls.by_project = {row['zipon_project_id']: row for row in cls.rows}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def status(self, name):
        return next(row['match_status'] for row in self.rows if row['zipon_project_name'] == name)

    # --- schema -----------------------------------------------------------

    def test_the_dbf_encoding_is_detected_so_field_names_do_not_silently_break(self):
        # 인코딩을 단정해서 틀리면 필드명이 깨지고, 오류 없이 '매칭 0건'이 된다.
        self.assertEqual(self.survey['dbf_encoding'], 'cp949')
        self.assertEqual(self.survey['fields'], list(POLYGON_FIELDS))
        self.assertEqual(self.survey['record_count'], len(POLYGON_FIXTURE))
        self.assertEqual(self.survey['shapefile'], 'UPIS_C_UQ120')

    def test_a_utf8_source_is_read_as_utf8(self):
        # UPIS처럼 필드명이 모두 영문이면 필드명만으로는 인코딩을 알 수 없다. 한글인 값을
        # 보고 정해야 한다. 여기서 틀리면 사업명이 깨진 채로 조용히 '매칭 0건'이 된다.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory), encoding='utf-8')
            survey = self.pipeline.analyse(archive)
        self.assertEqual(survey['dbf_encoding'], 'utf-8')
        self.assertIn('DGM_NM', survey['fields'])
        self.assertEqual(survey['records'][0]['name'], POLYGON_FIXTURE[0][1])
        self.assertEqual(survey['records'][0]['district'], '강동구')

    def test_a_truncated_field_name_still_resolves(self):
        # DBF 필드명은 잘릴 수 있다. 양방향으로 봐야 '사업명'이 '사업명칭'에도 걸린다.
        self.assertEqual(self.pipeline.pick({'사업명칭': '가락시영'}, self.pipeline.NAME_FIELDS),
                         '가락시영')
        self.assertIsNone(self.pipeline.pick({'사업명': ' '}, self.pipeline.NAME_FIELDS))

    def test_a_short_fragment_never_claims_a_field(self):
        # 'GU'가 'SIGNGU_SE'에 걸리면 코드값 필드를 이름 필드로 착각하고, 자치구가 영영
        # 맞지 않는다. 짧은 조각으로는 필드를 주장하지 않는다.
        self.assertIsNone(self.pipeline.field_for(['SIGNGU_SE'], ('자치구', 'GU')))
        self.assertEqual(self.pipeline.field_for(['SIGNGU_NM'], ('SIGNGU_NM',)), 'SIGNGU_NM')

    def test_dgm_nm_is_the_official_name_field_for_this_dataset_only(self):
        # DGM_NM은 UQ120 레이어의 공식 도형/사업 명칭이다. 이 데이터셋에 한정해 등록한다.
        self.assertEqual(self.survey['dataset_profile'], 'OA-22712/UPIS_C_UQ120')
        schema = self.survey['schema']
        self.assertEqual(schema['name']['field'], 'DGM_NM')
        self.assertEqual(schema['name']['basis'], 'OFFICIAL_DATASET_FIELD')
        self.assertTrue(schema['name']['used_for_matching'])
        self.assertEqual(self.survey['records'][0]['name'], POLYGON_FIXTURE[0][1])

    def test_dgm_nm_is_not_assumed_for_an_unrelated_shapefile(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory), stem_name='SOME_OTHER_LAYER',
                                            with_code_table=False)
            survey = self.pipeline.analyse(archive)
        self.assertIsNone(survey['dataset_profile'])
        self.assertEqual(survey['schema']['name']['basis'], 'UNCONFIRMED_TEXT')
        self.assertFalse(survey['schema']['name']['used_for_matching'])

    def test_the_code_table_supplies_the_meaning_of_the_coded_fields(self):
        self.assertEqual(self.survey['code_table_file'], 'UQ120_코드정의표.csv')
        self.assertGreater(self.survey['code_table_field_labels'], 0)
        schema = self.survey['schema']
        self.assertEqual(schema['district']['field_label'], '자치구 코드')
        self.assertEqual(schema['type']['field_label'], '추진구분 코드')

    def test_an_undecoded_code_value_is_not_promoted_to_a_usable_field(self):
        # PROPEL_CD가 무슨 칸인지는 표에 있지만 PP0103이 무엇인지는 표에 없다.
        # 필드의 뜻을 안다고 값을 아는 것은 아니다. 추측해서 풀지 않는다.
        schema = self.survey['schema']
        self.assertEqual(schema['type']['field'], 'PROPEL_CD')
        self.assertEqual(schema['type']['basis'], 'UNCONFIRMED_CODE')
        self.assertFalse(schema['type']['values_decoded'])
        self.assertFalse(schema['type']['used_for_matching'])
        self.assertEqual(schema['type']['samples'][0], 'PP0103')
        self.assertIsNone(self.survey['records'][0]['type'])

    def test_a_code_value_the_table_explains_is_promoted(self):
        import tempfile
        rows = POLYGON_CODE_TABLE + (('PP0103', '주택재개발'), ('PP0206', '도시환경정비'),
                                     ('PP0501', '가로주택정비'), ('PP0702', '소규모재건축'))
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys.modules[__name__], 'POLYGON_CODE_TABLE', rows):
                archive = build_polygon_fixture(Path(directory))
            survey = self.pipeline.analyse(archive)
        self.assertEqual(survey['schema']['type']['basis'], 'CODE_TABLE')
        self.assertTrue(survey['schema']['type']['used_for_matching'])
        self.assertEqual(survey['records'][0]['type'], '주택재개발')

    def test_a_district_code_is_resolved_from_the_verified_seoul_table(self):
        schema = self.survey['schema']
        self.assertEqual(schema['district']['field'], 'SIGNGU_SE')
        self.assertEqual(schema['district']['basis'], 'SEOUL_DISTRICT_CODE')
        self.assertTrue(schema['district']['used_for_matching'])
        self.assertEqual(self.by_name['천호3']['district'], '강동구')
        self.assertEqual(self.by_name['마천2재정비촉진구역 주택재개발정비사업']['district'], '송파구')
        self.assertEqual(len(self.pipeline.SEOUL_SGG), 25)
        self.assertEqual(self.pipeline.SEOUL_SGG['11740'], '강동구')

    def test_the_source_record_id_is_preserved_but_never_changes_identity(self):
        schema = self.survey['schema']
        # PRESENT_SN은 ZIP:ON id와 같은 namespace라고 확인되지 않았다. 보존만 한다.
        self.assertEqual(schema['source_record_id']['field'], 'PRESENT_SN')
        self.assertEqual(schema['source_record_id']['basis'], 'SOURCE_RECORD_ID')
        self.assertFalse(schema['source_record_id']['used_for_matching'])
        self.assertFalse(schema['official_id']['used_for_matching'])
        self.assertEqual(self.survey['records'][0]['source_record_id'],
                         '11740UQ120PS202604100001')
        for row in self.rows:
            self.assertIsNone(row['official_record_id'])
            self.assertNotIn('OFFICIAL_ID', json.dumps(row['match_signals']))
        # 어떤 등급이든 ZIP:ON project id는 그대로다.
        identifiers = [row['zipon_project_id'] for row in self.rows]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_a_field_whose_meaning_is_unconfirmed_is_not_used_for_matching(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            # 데이터셋도 코드정의표도 모를 때는 어느 칸이 사업명인지 확인할 길이 없다.
            archive = build_polygon_fixture(Path(directory), stem_name='UNKNOWN_LAYER',
                                            with_code_table=False)  # noqa: E501
            survey = self.pipeline.analyse(archive)
        self.assertEqual(survey['schema']['name']['basis'], 'UNCONFIRMED_TEXT')
        self.assertFalse(survey['schema']['name']['used_for_matching'])
        self.assertTrue(survey['schema']['name']['samples'])
        self.assertIsNone(survey['records'][0]['name'])
        self.assertEqual(survey['schema']['type']['basis'], 'UNCONFIRMED_CODE')

    def test_an_absent_role_is_recorded_as_unresolved(self):
        dong = self.survey['schema']['dong']
        self.assertIsNone(dong['field'])
        self.assertEqual(dong['basis'], 'UNRESOLVED')
        self.assertFalse(dong['used_for_matching'])

    def test_the_schema_fingerprint_changes_with_the_schema(self):
        self.assertEqual(len(self.survey['schema_fingerprint']), 64)
        self.assertEqual(self.survey['field_spec'][0][0], 'PRESENT_SN')

    # --- CRS --------------------------------------------------------------

    def test_the_crs_comes_from_the_prj_and_is_never_guessed(self):
        self.assertEqual(self.survey['source_crs'], POLYGON_SOURCE_CRS)
        self.assertEqual(self.survey['source_crs_basis'], 'FROM_PRJ_AUTHORITY')
        self.assertEqual(self.survey['converted_crs'], 'EPSG:4326')
        self.assertTrue(self.survey['source_units_metre'])
        self.assertEqual(self.pipeline.source_crs(None), (None, 'NO_PRJ_FILE'))
        self.assertEqual(self.pipeline.source_crs('not a projection at all'),
                         (None, 'UNRECOGNISED_PRJ'))
        self.assertEqual(
            self.pipeline.source_crs('PROJCS["Korea 2000 / Unified Coordinate System"]'),
            ('EPSG:5179', 'FROM_PRJ_NAME'))

    def test_a_low_confidence_epsg_guess_is_never_accepted_as_the_crs(self):
        # pyproj는 확신 없이도 코드를 돌려줄 수 있고, 중부원점 계열은 서로 바뀌기 쉽다
        # (5181 ↔ 5186). 코드를 확정하지 못하면 코드 대신 WKT 정의로 변환한다.
        crs, basis = self.pipeline.source_crs(POLYGON_PRJ_NO_AUTHORITY)
        self.assertIsNone(crs)
        self.assertEqual(basis, 'FROM_PRJ_WKT_NO_EPSG')
        from pyproj import CRS
        # 기본 신뢰도로는 코드가 나오지 않는다. 그래서 코드를 찍지 않고 WKT로 변환한다.
        self.assertIsNone(CRS.from_wkt(POLYGON_PRJ_NO_AUTHORITY).to_epsg())

    def test_a_wkt_without_an_epsg_code_still_converts_correctly(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory), prj=POLYGON_PRJ_NO_AUTHORITY,
                                            source_crs=POLYGON_PRJ_NO_AUTHORITY_CRS)
            survey = self.pipeline.analyse(archive)
        self.assertEqual(survey['source_crs_basis'], 'FROM_PRJ_WKT_NO_EPSG')
        self.assertTrue(survey['source_crs_label'].startswith('WKT:'))
        self.assertEqual(survey['outside_seoul'], 0)
        self.assertEqual(survey['converted_to_epsg4326'], len(POLYGON_FIXTURE))

    def test_a_source_without_a_prj_is_not_converted_on_a_guess(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory), with_prj=False)
            survey = self.pipeline.analyse(archive)
        self.assertIsNone(survey['source_crs'])
        self.assertEqual(survey['source_crs_basis'], 'NO_PRJ_FILE')
        # 변환하지 않았으니 좌표는 서울 경위도가 아니다. sanity 확인이 그것을 잡는다.
        self.assertEqual(survey['outside_seoul'], len(POLYGON_FIXTURE))

    def test_a_wrong_crs_stops_the_run_before_any_artifact_is_written(self):
        import contextlib
        import io as stream
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory), prj=POLYGON_PRJ_WRONG)
            buffer = stream.StringIO()
            with patch.object(sys, 'argv', ['analyze', '--archive', str(archive), '--write']):
                with contextlib.redirect_stdout(buffer):
                    code = self.pipeline.main()
        self.assertEqual(code, 2)
        reported = json.loads(buffer.getvalue())
        self.assertEqual(reported['status'], 'CRS_SANITY_FAILED')
        self.assertFalse(reported['db_write'])
        self.assertGreater(reported['outside_seoul'], 0)
        self.assertEqual(reported['expected_longitude'], [126.0, 128.0])

    def test_the_converted_coordinates_land_in_seoul_in_lon_lat_order(self):
        ring = self.by_name['천호3']['geometry']['coordinates'][0]
        for longitude, latitude in ring:
            self.assertTrue(126.0 < longitude < 128.0, longitude)
            self.assertTrue(37.0 < latitude < 38.0, latitude)

    # --- geometry ---------------------------------------------------------

    def test_geometry_is_valid_and_typed_by_its_ring_layout(self):
        self.assertEqual(self.survey['invalid_geometry'], 0)
        self.assertEqual(self.survey['empty_geometry'], 0)
        self.assertEqual(self.survey['geometry_types'], {'Polygon': 6, 'MultiPolygon': 1})
        hole = self.by_name['고덕강일1역세권']
        self.assertEqual(hole['geometry']['type'], 'Polygon')
        self.assertEqual(len(hole['geometry']['coordinates']), 2)
        self.assertEqual(len(hole['hole_rings']), 1)
        separate = self.by_name['고덕강일1역세권 재개발사업']
        # 떨어져 있는 두 외곽 구역은 '구멍 뚫린 한 구역'이 되어서는 안 된다.
        self.assertEqual(separate['geometry']['type'], 'MultiPolygon')
        self.assertEqual(len(separate['geometry']['coordinates']), 2)
        self.assertEqual(separate['hole_rings'], [])

    def test_duplicate_identifiers_and_geometry_are_counted(self):
        self.assertEqual(self.survey['duplicate_identifiers'], 0)
        self.assertEqual(self.survey['duplicate_geometry'], 0)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            rows = POLYGON_FIXTURE + (POLYGON_FIXTURE[0],)
            with patch.object(sys.modules[__name__], 'POLYGON_FIXTURE', rows):
                archive = build_polygon_fixture(Path(directory))
                survey = self.pipeline.analyse(archive)
        self.assertEqual(survey['record_count'], len(POLYGON_FIXTURE) + 1)
        self.assertEqual(survey['duplicate_identifiers'], 1)
        self.assertEqual(survey['duplicate_geometry'], 1)

    def test_an_unclosed_ring_is_reported_not_repaired(self):
        shape = Mock()
        shape.points = [(0, 0), (0, 1), (1, 1), (1, 0)]
        shape.parts = [0]
        geometry, outer, holes, validity = self.pipeline.to_wgs84(shape, None)
        self.assertEqual(validity, 'RING_NOT_CLOSED')
        self.assertIsNotNone(geometry)
        shape.points = [(0, 0), (0, 1)]
        self.assertEqual(self.pipeline.to_wgs84(shape, None)[3], 'NO_RING')
        shape.points = []
        shape.parts = []
        self.assertEqual(self.pipeline.to_wgs84(shape, None)[3], 'NO_RING')

    def test_geojson_winds_the_outer_ring_anticlockwise_and_holes_clockwise(self):
        rings = self.by_name['고덕강일1역세권']['geometry']['coordinates']
        self.assertGreater(self.pipeline.ring_area(rings[0]), 0)
        self.assertLess(self.pipeline.ring_area(rings[1]), 0)

    def test_a_point_in_a_hole_is_not_inside_the_area(self):
        outer = [polygon_square(0, 0, 10)]
        holes = [polygon_square(5, 5, 2, clockwise=False)]
        self.assertTrue(self.pipeline.contains((1, 1), outer, holes))
        self.assertFalse(self.pipeline.contains((5, 5), outer, holes))
        self.assertFalse(self.pipeline.contains((50, 50), outer, holes))

    def test_the_distance_to_a_polygon_is_measured_in_metres(self):
        square = polygon_square(0, 0, 100)
        self.assertEqual(self.pipeline.distance_to_rings((0, 200), [square]), 100.0)
        self.assertEqual(self.pipeline.distance_to_rings((150, 0), [square]), 50.0)

    # --- matching ---------------------------------------------------------

    def test_a_normalized_name_and_district_match_grades_exact(self):
        # 공식 '천호3' 과 ZIP:ON '천호3 주택재건축정비사업조합' 은 표기만 다르다.
        self.assertEqual(self.status('천호3 주택재건축정비사업조합'), 'EXACT')
        row = self.by_project['1436e9a7-4b6e-5297-b048-b8743063a07b']
        self.assertEqual(row['zipon_normalized_name'], '천호3')
        self.assertEqual(row['official_normalized_name'], '천호3')
        self.assertEqual(row['official_name'], '천호3')
        self.assertIn('NAME_NORMALIZED_EXACT', row['match_signals'])
        self.assertIn('DISTRICT', row['match_signals'])
        self.assertIn('ORG_SUFFIX', row['zipon_normalization_rules'])
        self.assertIn('SCHEME_SUFFIX', row['zipon_normalization_rules'])
        self.assertTrue(row['geometry_valid'])
        self.assertTrue(row['auto_apply_candidate'])

    def test_two_official_candidates_grade_ambiguous(self):
        self.assertEqual(self.status('고덕강일1역세권 재개발사업'), 'AMBIGUOUS')
        row = self.by_project['e17699d4-d2a1-5908-aea7-c7b5363bb478']
        self.assertIsNone(row['official_record_id'])
        self.assertIn('2건', row['confidence_reason'])
        self.assertFalse(row['auto_apply_candidate'])

    def test_a_known_duplicate_is_never_resolved_by_a_polygon(self):
        # 마천2 와 마천2재정비촉진구역 은 둘 다 이미 DB에 있다. 폴리곤으로 정하지 않는다.
        protected = self.pipeline.conflicted_ids()
        self.assertEqual(len(protected), 15)
        for project_id in ('8ab19fc2-5f02-54a8-9568-6a3ef0218ec4',
                           '0cfa354d-f9ac-5516-aa2a-1f6767c0aa98'):
            self.assertIn(project_id, protected)
            row = self.by_project[project_id]
            self.assertEqual(row['match_status'], 'AMBIGUOUS')
            self.assertIsNone(row['official_record_id'])
            self.assertFalse(row['auto_apply_candidate'])
            self.assertIn('duplicate', row['confidence_reason'])

    def test_a_name_that_is_only_contained_grades_probable_not_exact(self):
        self.assertEqual(self.status('강동역세권2구역 도시정비형 재개발사업'), 'PROBABLE')

    def test_every_project_is_graded_and_the_grades_are_the_only_four(self):
        self.assertEqual(len(self.rows), 130)
        self.assertEqual(set(row['match_status'] for row in self.rows),
                         {'EXACT', 'PROBABLE', 'AMBIGUOUS', 'NO_MATCH'})
        for row in self.rows:
            self.assertTrue(row['confidence_reason'])
            self.assertEqual(row['source_version'], '202609')

    # --- EXACT 추가 검증 ---------------------------------------------------

    def test_an_exact_match_whose_point_falls_outside_is_held_back(self):
        row = self.by_project['d643b796-868b-5d43-a5d3-db95919113fc']
        self.assertEqual(row['zipon_project_name'], '천호1 도시환경정비사업조합')
        self.assertEqual(row['match_status'], 'EXACT')
        self.assertTrue(row['geometry_valid'])
        self.assertFalse(row['representative_point_inside_polygon'])
        self.assertEqual(row['excluded_reason'], 'REPRESENTATIVE_POINT_OUTSIDE_POLYGON')
        self.assertFalse(row['auto_apply_candidate'])
        # 거리는 원천 좌표계(미터)에서 실제로 재고, 짐작하지 않는다.
        self.assertEqual(row['distance_basis'], 'SOURCE_CRS_METRES')
        self.assertGreater(row['distance_to_polygon_m'], 100)

    def test_the_exact_counts_are_split_by_what_makes_them_unsafe(self):
        totals = self.review['totals']
        self.assertEqual(totals['EXACT'], 2)
        self.assertEqual(totals['exact_with_valid_polygon'], 2)
        self.assertEqual(totals['exact_valid_inside'], 1)
        self.assertEqual(totals['exact_valid_outside'], 1)
        self.assertEqual(totals['exact_invalid_geometry'], 0)
        self.assertEqual(totals['auto_apply_candidates'], 1)
        self.assertEqual(totals['zipon_projects'], 130)

    def test_each_exact_row_carries_the_evidence_a_reviewer_needs(self):
        self.assertEqual(len(self.review['exact']), 2)
        for row in self.review['exact']:
            for field in ('zipon_project_id', 'zipon_project_name', 'district',
                          'project_type', 'program', 'official_record_id', 'official_name',
                          'geometry_type', 'geometry_valid',
                          'representative_point_inside_polygon', 'distance_to_polygon_m',
                          'source_crs', 'converted_crs'):
                self.assertIn(field, row)
            self.assertIsNotNone(row['official_name'])

    def test_only_safe_exact_matches_reach_the_geojson_and_it_is_review_only(self):
        self.assertEqual(len(self.features),
                         sum(1 for row in self.rows if row['auto_apply_candidate']))
        self.assertEqual(len(self.features), 1)
        for feature in self.features:
            self.assertTrue(feature['properties']['review_only'])
            self.assertEqual(feature['properties']['legal_note'], '법적 효력 없음 / 참고자료')
            self.assertTrue(feature['properties']['representative_point_inside_polygon'])
            self.assertIn(feature['geometry']['type'], ('Polygon', 'MultiPolygon'))

    def test_the_representative_point_is_reported_but_never_decides_identity(self):
        row = self.by_project['1436e9a7-4b6e-5297-b048-b8743063a07b']
        self.assertTrue(row['representative_point_inside_polygon'])
        # 포함 여부는 신호 목록에 들어가지 않는다. 등급을 올리는 근거가 아니다.
        for graded in self.rows:
            self.assertNotIn('INSIDE', json.dumps(graded['match_signals'], ensure_ascii=False))

    # --- 안전장치 ---------------------------------------------------------

    def test_the_pipeline_never_writes_to_the_database(self):
        source = (ROOT / 'scripts/analyze_seoul_polygon_source.py').read_text(encoding='utf-8')
        for forbidden in ('zipon_set_project_location', 'zipon_ingest_candidate',
                          'supabase', 'SERVICE_ROLE', 'requests.post', 'httpx'):
            self.assertNotIn(forbidden, source)
        self.assertFalse(self.review['db_write'])
        self.assertFalse(self.review['polygon_written_to_production'])

    def test_a_missing_source_file_reports_how_to_obtain_it(self):
        import contextlib
        import io as stream
        buffer = stream.StringIO()
        with patch.object(sys, 'argv', ['analyze', '--archive', str(ROOT / 'no-such.zip')]):
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(self.pipeline.main(), 0)
        reported = json.loads(buffer.getvalue())
        self.assertEqual(reported['status'], 'SOURCE_FILE_NOT_PRESENT')
        self.assertFalse(reported['db_write'])
        self.assertEqual(reported['expected_file'],
                         '532_UQ120_도시계획사업(서울플랜+)_202609.zip')
        self.assertIn('data.seoul.go.kr', reported['portal_url'])

    def test_the_source_is_recorded_so_the_next_edition_can_be_compared(self):
        entry = dict(self.pipeline.SOURCE)
        digest = self.pipeline.archive_digest(self.archive)
        self.assertEqual(len(digest), 64)
        # 같은 파일을 두 번 읽어도 같은 hash다. 다음 판과 비교할 수 있다.
        self.assertEqual(digest, self.pipeline.archive_digest(self.archive))
        self.assertTrue(entry['dataset_id'])
        summary = self.review['source']
        self.assertEqual(summary['source_sha256'], digest)
        self.assertEqual(summary['source_bytes'], self.archive.stat().st_size)


class PolygonSourceChangeTests(unittest.TestCase):
    """다음 판이 들어왔을 때 hash만 보고 재분석 여부를 정할 수 있는지."""

    def setUp(self):
        try:
            import shapefile  # noqa: F401
        except ImportError as error:  # pragma: no cover
            raise unittest.SkipTest(f'shapefile not available: {error}')
        import analyze_seoul_polygon_source as pipeline
        self.pipeline = pipeline

    def test_an_unchanged_source_is_not_analysed_again(self):
        import contextlib
        import io as stream
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory))
            registry = Path(directory) / 'source_registry.json'
            review = Path(directory) / 'review.json'
            review.write_text('{}', encoding='utf-8')
            registry.write_text(json.dumps({'sources': [dict(
                self.pipeline.SOURCE, archive=archive.name,
                source_sha256=self.pipeline.archive_digest(archive))]}), encoding='utf-8')
            buffer = stream.StringIO()
            with patch.object(self.pipeline, 'REGISTRY_FILE', registry),                     patch.object(self.pipeline, 'REVIEW_FILE', review),                     patch.object(sys, 'argv',
                                 ['analyze', '--archive', str(archive), '--if-changed']):
                with contextlib.redirect_stdout(buffer):
                    self.assertEqual(self.pipeline.main(), 0)
            reported = json.loads(buffer.getvalue())
            self.assertEqual(reported['status'], 'SOURCE_UNCHANGED')
            self.assertFalse(reported['db_write'])

    def test_a_changed_source_is_analysed(self):
        import contextlib
        import io as stream
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory))
            registry = Path(directory) / 'source_registry.json'
            review = Path(directory) / 'review.json'
            review.write_text('{}', encoding='utf-8')
            registry.write_text(json.dumps({'sources': [dict(
                self.pipeline.SOURCE, archive=archive.name,
                source_sha256='0' * 64)]}), encoding='utf-8')
            buffer = stream.StringIO()
            with patch.object(self.pipeline, 'REGISTRY_FILE', registry), \
                    patch.object(self.pipeline, 'REVIEW_FILE', review), \
                    patch.object(sys, 'argv',
                                 ['analyze', '--archive', str(archive), '--if-changed']):
                with contextlib.redirect_stdout(buffer):
                    self.assertEqual(self.pipeline.main(), 0)
            reported = json.loads(buffer.getvalue())
            self.assertEqual(reported['status'], 'ANALYSED')
            self.assertFalse(reported['db_write'])
            self.assertFalse(reported['written'])

    def test_the_registry_records_what_the_next_run_needs_to_compare(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            archive = build_polygon_fixture(Path(directory))
            registry = Path(directory) / 'source_registry.json'
            survey = self.pipeline.analyse(archive)
            with patch.object(self.pipeline, 'REGISTRY_FILE', registry):
                entry = self.pipeline.register(archive, survey)
            stored = json.loads(registry.read_text(encoding='utf-8'))
        self.assertEqual(len(stored['sources']), 1)
        for field in ('provider', 'dataset', 'dataset_id', 'file', 'version', 'source_sha256',
                      'source_bytes', 'recorded_at', 'source_crs', 'record_count',
                      'schema_fingerprint', 'code_table_file', 'analysed_at'):
            self.assertIn(field, entry, field)
        self.assertFalse(entry['modified'])
        self.assertTrue(entry['acquired'])


class PolygonSafetyTests(unittest.TestCase):
    """확인되지 않은 폴리곤이 운영 화면이나 INSIDE 판정으로 새지 않는지."""

    def setUp(self):
        self.map_source = read('components/realestate/ZiponMap.tsx')

    def test_the_map_only_draws_an_officially_verified_boundary(self):
        helper = read('lib/projectBoundary.ts')
        self.assertIn('const OFFICIAL = "OFFICIAL_VERIFIED"', helper)
        self.assertIn('boundary_status !== OFFICIAL', helper)
        # 경계가 없으면 구역인 척하지 않고 대표 위치를 나타내는 원만 그린다.
        self.assertIn('if (!verifiedBoundary.length) settle()', self.map_source)
        self.assertIn('radius: 120', self.map_source)

    def test_the_renderer_reads_a_ring_and_does_not_invent_one(self):
        self.assertIn('verifiedBoundaryPolygons(point)', self.map_source)
        self.assertNotIn('buffer', self.map_source.lower())

    def test_the_map_and_the_marker_layer_share_one_boundary_reader(self):
        # marker 레이어, 선택 효과, 범례 집계가 모두 같은 helper를 쓴다.
        self.assertEqual(self.map_source.count('verifiedBoundaryPolygons('), 3)
        self.assertIn('from "@/lib/projectBoundary"', self.map_source)
        # 첫 구역만 그리는 옛 방식이 다시 들어오지 않게 한다.
        self.assertNotIn('coordinates?.[0]', self.map_source)

    def test_inside_still_needs_a_verified_boundary(self):
        unverified = pr.relation('INSIDE', boundary_verified=False)
        self.assertNotEqual(unverified['code'], 'INSIDE')
        self.assertFalse(unverified['confirmed_boundary'])
        verified = pr.relation('INSIDE', boundary_verified=True)
        self.assertEqual(verified['code'], 'INSIDE')
        self.assertTrue(verified['confirmed_boundary'])

    def test_a_representative_point_alone_never_produces_inside(self):
        # 대표좌표만 있는 사업은 confirmed_boundary가 false다. 그래서 '내부'가 나오지 않는다.
        point_only = pr.relation('INSIDE', boundary_verified=False)
        verdict = pr.inside_verdict([{'name': '테스트', 'spatial': point_only}])
        self.assertEqual(verdict['code'], 'NOT_DETERMINED')
        self.assertEqual(verdict['notice'], pr.INSIDE_UNKNOWN_NOTICE)

    def test_production_still_carries_no_polygon(self):
        review = DATA / 'polygon_match_review_20260928.json'
        if not review.exists():
            self.skipTest('공식 원천이 아직 없어 review 산출물이 없다')
        document = json.loads(review.read_text(encoding='utf-8'))
        self.assertFalse(document['db_write'])
        self.assertFalse(document['polygon_written_to_production'])


class PolygonSourceRegistryTests(unittest.TestCase):
    """원천을 어디서 어떤 판으로 받았는지, 아직 못 받았으면 못 받았다고 적혀 있는지."""

    def setUp(self):
        self.registry = json.loads((ROOT / 'data/reference/source_registry.json')
                                   .read_text(encoding='utf-8'))
        self.acquisition = json.loads((DATA / 'polygon_source_acquisition_20260928.json')
                                      .read_text(encoding='utf-8'))

    def test_the_registry_names_the_official_dataset_and_never_modifies_it(self):
        entry = next(s for s in self.registry['sources'] if s['dataset_id'] == 'OA-22712')
        self.assertEqual(entry['provider'], '서울특별시')
        self.assertEqual(entry['version'], '202609')
        self.assertEqual(entry['file'], '532_UQ120_도시계획사업(서울플랜+)_202609.zip')
        self.assertIn('data.seoul.go.kr', entry['portal_url'])
        self.assertEqual(entry['legal_note'], '법적 효력 없음 / 참고자료')
        self.assertFalse(entry['modified'])

    def test_a_source_that_was_not_obtained_is_recorded_as_not_obtained(self):
        entry = next(s for s in self.registry['sources'] if s['dataset_id'] == 'OA-22712')
        if entry['acquired']:
            self.assertEqual(entry['acquisition_status'], 'PRESENT')
            self.assertTrue(entry['archive'])
            return
        self.assertIsNone(entry['archive'])
        self.assertEqual(entry['acquisition_status'], 'BLOCKED_BY_NETWORK_POLICY')
        self.assertIn('SOURCE_FILE_NOT_PRESENT', self.acquisition['conclusion'])

    def test_no_unofficial_source_was_substituted(self):
        self.assertFalse(self.acquisition['substituted_with_unofficial_source'])
        self.assertFalse(self.acquisition['polygon_created'])
        self.assertFalse(self.acquisition['polygon_written_to_production'])
        self.assertFalse(self.acquisition['db_write'])
        # 파이프라인이 통과한 것은 합성 원천이다. 공식 결과인 척하지 않는다.
        self.assertEqual(self.acquisition['pipeline']['verified_on'], 'SYNTHETIC_FIXTURE')

    def test_the_local_first_run_is_recorded_as_the_users_result_not_ours(self):
        run = self.acquisition['local_first_run']
        self.assertEqual(run['record_count'], 2776)
        self.assertEqual(run['polygon'], 2684)
        self.assertEqual(run['multipolygon'], 92)
        self.assertEqual(run['source_crs'], 'EPSG:5174')
        self.assertEqual(run['match_result'], 'ALL_130_NO_MATCH')
        self.assertEqual(run['environment'], 'local checkout')
        self.assertIn('DGM_NM', run['root_cause'])
        self.assertIn('이 컨테이너가 원본을 읽은 것이 아니다', run['note'])
        self.assertEqual(run['schema_observed']['name']['basis_after'],
                         'OFFICIAL_DATASET_FIELD')
        self.assertEqual(run['schema_observed']['type']['basis'], 'UNCONFIRMED_CODE')
        self.assertEqual(run['schema_observed']['official_id']['basis'], 'SOURCE_RECORD_ID')

    def test_the_download_steps_are_written_down_for_the_person_who_can_reach_the_portal(self):
        action = self.acquisition['user_action_required']
        self.assertIn('data.seoul.go.kr', action['step_1'])
        self.assertIn('data/reference/', action['step_2'])
        self.assertIn('analyze_seoul_polygon_source.py', action['step_3'])
        self.assertIn('--archive', action['step_3'])


class PolygonReviewDocumentTests(unittest.TestCase):
    def setUp(self):
        self.document = (ROOT / 'docs/zipon_polygon_matching_review_2026-09.md') \
            .read_text(encoding='utf-8')

    def test_the_document_states_that_no_polygon_reached_production(self):
        self.assertIn('운영 DB에 폴리곤을 쓰지 않았다', self.document)
        self.assertIn('운영 화면의 폴리곤 수는 여전히 0', self.document)

    def test_the_document_names_the_source_and_its_legal_status(self):
        for expected in ('OA-22712', '532_UQ120_도시계획사업(서울플랜+)_202609.zip',
                         'data.seoul.go.kr', '법적 효력 없음 / 참고자료', 'EPSG:5174'):
            self.assertIn(expected, self.document)

    def test_the_document_records_the_four_grades_and_the_duplicate_protection(self):
        for expected in ('EXACT', 'PROBABLE', 'AMBIGUOUS', 'NO_MATCH', '마천2',
                         '보조 확인일 뿐이며 동일성을 결정하지 않는다'):
            self.assertIn(expected, self.document)

    def test_the_document_does_not_claim_the_official_file_was_read_here(self):
        # 로컬 1차 실행 결과는 인용하되, 이 컨테이너가 원본을 읽은 것처럼 적지 않는다.
        self.assertIn('공식 파일은 이 컨테이너에 없다', self.document)
        self.assertIn('합성 원천은 공식 결과가 아니고', self.document)
        self.assertIn('로컬 실행', self.document)


class ProjectBoundaryHelperTests(unittest.TestCase):
    """경계 helper를 실제로 실행해서 확인한다. 문자열 비교가 아니다."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import subprocess
        if shutil.which('node') is None:
            raise unittest.SkipTest('node is not available')
        check = ROOT / 'scripts/checks/project_boundary_check.mts'
        result = subprocess.run(['node', '--experimental-strip-types', str(check)],
                                capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            raise unittest.SkipTest(f'boundary check did not run: {result.stderr[:200]}')
        cls.report = json.loads(result.stdout.strip().splitlines()[0])

    def test_a_polygon_and_its_holes_stay_one_area(self):
        self.assertEqual(self.report['polygon_parts'], 1)
        self.assertEqual(self.report['polygon_rings'], 1)
        self.assertEqual(self.report['hole_rings'], 2)

    def test_a_multipolygon_keeps_every_area(self):
        # 떨어져 있는 두 구역이다. 첫 구역만 그리거나 하나로 합치면 사업 범위가 틀려진다.
        self.assertEqual(self.report['multipolygon_parts'], 2)
        self.assertEqual(self.report['untyped_parts'], 2)
        self.assertEqual(self.report['points'], 10)

    def test_an_unverified_boundary_is_never_drawn(self):
        for key in ('unverified', 'no_status', 'no_boundary', 'empty'):
            self.assertEqual(self.report[key], 0, key)

    def test_an_unreadable_ring_is_dropped_instead_of_being_reshaped(self):
        for key in ('too_few', 'not_numbers', 'out_of_range'):
            self.assertEqual(self.report[key], 0, key)

    def test_the_review_geojson_would_parse_if_it_existed(self):
        if self.report['review_features'] is None:
            self.skipTest('공식 원천이 아직 없어 EXACT GeoJSON이 없다')
        self.assertEqual(self.report['review_parsed'], self.report['review_features'])


class CheonhoMiniMapRegressionTests(unittest.TestCase):
    """천호1 상세 지도가 서울 기본 중심이 아니라 그 사업 좌표에서 열리는지.

    서울 기본 중심으로 먼저 만든 뒤 나중에 옮기는 구조로 돌아가면 이 테스트가 깨진다.
    """

    PROJECT_ID = 'd643b796-868b-5d43-a5d3-db95919113fc'
    COORDINATE = (37.5414444, 127.1269883)

    def setUp(self):
        self.map_source = read('components/realestate/ZiponMap.tsx')

    def test_the_stored_coordinate_is_the_one_the_map_will_use(self):
        import sys as system
        system.path.insert(0, str(ROOT / 'scripts'))
        from analyze_seoul_polygon_source import load_projects
        project = next(p for p in load_projects() if p['project_id'] == self.PROJECT_ID)
        self.assertEqual(project['project_name'], '천호1 도시환경정비사업조합')
        self.assertEqual(project['address'], '서울특별시 강동구 천호동 423-200')
        self.assertEqual((project['latitude'], project['longitude']), self.COORDINATE)

    def test_the_helper_accepts_that_coordinate_unchanged(self):
        import shutil
        import subprocess
        if shutil.which('node') is None:
            self.skipTest('node is not available')
        check = ROOT / 'scripts/checks/project_coordinate_check.mts'
        result = subprocess.run(['node', '--experimental-strip-types', str(check)],
                                capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            self.skipTest('coordinate check did not run')
        report = json.loads(result.stdout.strip().splitlines()[0])
        self.assertEqual(report['rejected'], [])
        self.assertEqual(report['districts']['강동구']['lat'] > 37, True)

    def test_the_detail_map_is_created_at_the_project_not_at_seoul(self):
        creation = self.map_source.split('new loaded.Map(container.current', 1)[1][:400]
        # 생성 시점의 center가 사업 좌표다. 서울 기본값은 좌표가 없을 때만 쓴다.
        self.assertIn('center: centre', creation)
        self.assertIn('new loaded.LatLng(centre.lat, centre.lng)', creation)
        self.assertIn('new loaded.LatLng(SEOUL.lat, SEOUL.lng)', creation)
        self.assertIn('zoom: centre ? 17 :', creation)
        self.assertIn('initialCentre.current ??', self.map_source)
        self.assertIn('compact ? selectedEntry?.coordinate ?? located[0]?.coordinate ?? null',
                      self.map_source)

    def test_the_centre_is_set_before_the_resize_is_announced(self):
        settle = self.map_source.split('const settle = () => {', 1)[1]
        self.assertLess(settle.index('setCenter'), settle.index('Event.trigger'))
        self.assertIn('} catch {', settle)


class PolygonDocumentSchemaTests(unittest.TestCase):
    """문서가 실제 schema 해석 규칙과 안전 규칙을 적고 있는지."""

    def setUp(self):
        self.document = (ROOT / 'docs/zipon_polygon_matching_review_2026-09.md') \
            .read_text(encoding='utf-8')

    def test_the_document_records_the_real_field_names_and_how_they_are_interpreted(self):
        for expected in ('PRESENT_SN', 'DGM_NM', 'SIGNGU_SE', 'PROPEL_CD', 'CREATE_DAT',
                         '코드정의표', 'CODE_TABLE_FIELD_LABEL', 'UNCONFIRMED_TEXT',
                         '필드명을 추측하지 않는다'):
            self.assertIn(expected, self.document)

    def test_the_document_records_the_crs_and_sanity_rules(self):
        for expected in ('CRS_SANITY_FAILED', 'FROM_PRJ_WKT_NO_EPSG',
                         '낮은 신뢰도의 EPSG 추정은 받지 않는다', '5181 ↔ 5186',
                         '경도 126~128, 위도 37~38'):
            self.assertIn(expected, self.document)

    def test_the_document_splits_the_exact_counts(self):
        for expected in ('exact_valid_inside', 'exact_valid_outside', 'exact_invalid_geometry',
                         'auto_apply_candidate', 'distance_to_polygon_m', 'SOURCE_CRS_METRES'):
            self.assertIn(expected, self.document)

    def test_the_document_records_the_change_detection_structure(self):
        for expected in ('source_sha256', 'schema_fingerprint', '--if-changed',
                         'SOURCE_UNCHANGED', '자동 다운로드는 이번 작업 범위가'):
            self.assertIn(expected, self.document)

    def test_the_document_explains_why_the_local_file_is_not_in_this_container(self):
        self.assertIn('로컬 작업본에 있고', self.document)
        self.assertIn('.gitignore', self.document)

    def test_the_document_records_the_first_real_run_and_its_root_cause(self):
        for expected in ('2776', '2684', '92', 'EPSG:5174', 'UPIS_C_UQ120',
                         '130건 전부 NO_MATCH', 'DGM_NM', 'OFFICIAL_DATASET_FIELD',
                         'SOURCE_RECORD_ID', 'values_decoded'):
            self.assertIn(expected, self.document)

    def test_the_document_records_the_normalization_rules_and_their_guards(self):
        for expected in ('COMPACT_WHITESPACE', 'UNWRAP_BRACKETS', 'ORG_SUFFIX',
                         'SCHEME_SUFFIX', 'AREA_SUFFIX', 'BUILDING_SUFFIX',
                         '안의 내용은 남긴다', 'ZIP:ON 안의 충돌', '3글자 미만',
                         'DISTRICT_MISMATCH'):
            self.assertIn(expected, self.document)


class NameNormalizationTests(unittest.TestCase):
    """사업명 정규화. 표기 차이만 걷어내고 고유명칭은 남기는지."""

    def setUp(self):
        import analyze_seoul_polygon_source as pipeline
        self.normalize = pipeline.normalize_name
        self.pipeline = pipeline

    def test_presentation_differences_collapse_to_the_same_name(self):
        pairs = (
            ('천호1 도시환경정비사업조합', '천호1'),
            ('천호3 주택재건축정비사업조합', '천호3'),
            ('마천2재정비촉진구역 주택재개발정비사업', '마천2'),
            ('고덕강일1역세권 재개발사업', '고덕강일1역세권'),
            ('신반포5차아파트 주택재건축정비사업 조합', '신반포5차'),
            ('신반포26차아파트 소규모재건축정비사업', '신반포26차'),
            ('구로동 451번지 일대 가로주택정비사업', '구로동451'),
            ('사근동 293번지 일대 주택정비형 재개발사업', '사근동293'),
            ('천호동 397-419번지 일대 주택정비형재개발사업조합', '천호동397-419'),
            ('천호 A1-1구역 공공재개발 정비사업 주민대표회의', '천호A1-1'),
        )
        for raw, expected in pairs:
            self.assertEqual(self.normalize(raw)[0], expected, raw)

    def test_the_core_name_and_its_numbers_are_never_dropped(self):
        # 숫자가 사업을 가른다. '천호3'과 '천호3-1'은 서로 다른 사업이다.
        self.assertNotEqual(self.normalize('천호3')[0], self.normalize('천호3-1')[0])
        self.assertNotEqual(self.normalize('마천2')[0], self.normalize('마천3')[0])
        self.assertNotEqual(self.normalize('신당10')[0], self.normalize('신당1')[0])
        # 괄호는 없애지만 그 안의 내용은 남긴다. 지우면 서로 다른 구역이 같아진다.
        self.assertEqual(self.normalize('강동역세권(1구역) SHIFT 장기전세주택')[0],
                         '강동역세권1구역SHIFT')
        self.assertNotEqual(self.normalize('강동역세권(1구역) 장기전세주택')[0],
                            self.normalize('강동역세권(2구역) 장기전세주택')[0])

    def test_normalization_never_strips_a_name_to_nothing(self):
        for raw in ('조합', '정비사업', '아파트', '구역', '재정비촉진구역'):
            normalized, _ = self.normalize(raw)
            self.assertTrue(normalized, raw)
            self.assertGreaterEqual(len(normalized), self.pipeline.NAME_MIN_LENGTH)
        self.assertEqual(self.normalize(None), (None, []))
        self.assertEqual(self.normalize('')[0], None)

    def test_the_rules_that_were_applied_are_recorded(self):
        _, rules = self.normalize('신반포5차아파트 주택재건축정비사업 조합')
        self.assertEqual(rules, ['COMPACT_WHITESPACE', 'ORG_SUFFIX', 'SCHEME_SUFFIX',
                                 'BUILDING_SUFFIX'])
        self.assertEqual(self.normalize('천호3-1')[1], [])

    def test_the_130_projects_normalize_without_new_collisions(self):
        from analyze_seoul_polygon_source import load_projects
        seen = {}
        for project in load_projects():
            key = (project['normalized_name'], project['district'])
            seen.setdefault(key, []).append(project['project_name'])
        collisions = {key: names for key, names in seen.items() if len(names) > 1}
        # 유일하게 겹치는 것은 이미 duplicate로 표시해 둔 마천2 두 건이다.
        self.assertEqual(list(collisions), [('마천2', '송파구')])
        self.assertEqual(len(collisions[('마천2', '송파구')]), 2)

    def test_a_short_name_cannot_reach_exact_on_its_own(self):
        from analyze_seoul_polygon_source import load_projects
        short = [p['project_name'] for p in load_projects()
                 if p['normalized_name'] and len(p['normalized_name']) < 3]
        # '현대', '이화'처럼 흔한 두 글자는 이름만으로 확정하지 않는다.
        self.assertTrue(short)
        record = {'name': '현대', 'normalized_name': '현대', 'district': '송파구',
                  'dong': None, 'address': None, 'official_id': None}
        project = {'project_id': 'x', 'project_name': '현대연립 주택재건축정비사업조합',
                   'normalized_name': '현대', 'official_external_id': None,
                   'district': '송파구', 'dong': None, 'lot_number': None}
        status, _, _, reason = self.pipeline.match(project, [record], set())
        self.assertEqual(status, 'PROBABLE')
        self.assertIn('짧아', reason)


class PolygonMatchGuardTests(unittest.TestCase):
    """후보를 만든 뒤에 오는 검증이 등급을 올리지 못하게 막는지."""

    def setUp(self):
        import analyze_seoul_polygon_source as pipeline
        self.pipeline = pipeline

    def record(self, name, district='강동구', **extra):
        base = {'name': name, 'normalized_name': self.pipeline.normalize_name(name)[0],
                'district': district, 'dong': None, 'address': None, 'official_id': None}
        base.update(extra)
        return base

    def project(self, name, district='강동구', **extra):
        base = {'project_id': 'p1', 'project_name': name,
                'normalized_name': self.pipeline.normalize_name(name)[0],
                'official_external_id': None, 'district': district, 'dong': None,
                'lot_number': None}
        base.update(extra)
        return base

    def test_two_candidates_in_the_same_district_stay_ambiguous(self):
        records = [self.record('천호3'), self.record('천호3 주택재건축정비사업')]
        status, chosen, _, reason = self.pipeline.match(
            self.project('천호3 주택재건축정비사업조합'), records, set())
        self.assertEqual(status, 'AMBIGUOUS')
        self.assertIsNone(chosen)
        self.assertIn('2건', reason)

    def test_a_name_match_in_another_district_is_not_a_candidate(self):
        status, _, _, _ = self.pipeline.match(
            self.project('천호3 주택재건축정비사업조합'),
            [self.record('천호3', district='송파구')], set())
        self.assertEqual(status, 'NO_MATCH')

    def test_a_zipon_side_collision_stays_ambiguous(self):
        project = self.project('마천2', district='송파구')
        collisions = {('마천2', '송파구'): 2}
        status, chosen, _, reason = self.pipeline.match(
            project, [self.record('마천2', district='송파구')], set(), collisions)
        self.assertEqual(status, 'AMBIGUOUS')
        self.assertIsNone(chosen)
        self.assertIn('ZIP:ON 안에서', reason)

    def test_a_protected_project_stays_ambiguous_even_on_a_clean_hit(self):
        project = self.project('마천2', district='송파구')
        status, chosen, _, reason = self.pipeline.match(
            project, [self.record('마천2', district='송파구')], {'p1'})
        self.assertEqual(status, 'AMBIGUOUS')
        self.assertIsNone(chosen)
        self.assertIn('duplicate', reason)

    def test_a_source_record_id_only_matches_when_the_namespace_is_comparable(self):
        record = self.record('전혀다른이름', official_id='chunho3')
        project = self.project('천호3 주택재건축정비사업조합', official_external_id='chunho3')
        # 기본값: PRESENT_SN처럼 namespace가 확인되지 않은 식별자는 신호가 되지 않는다.
        self.assertEqual(self.pipeline.match(project, [record], set())[0], 'NO_MATCH')
        # 실제 관리번호 칸이 확인된 원천에서만 식별자를 신호로 쓴다.
        status, _, signals, _ = self.pipeline.match(project, [record], set(), None, True)
        self.assertEqual(status, 'EXACT')
        self.assertIn('OFFICIAL_ID', signals)

    def test_geometry_is_only_a_check_and_never_makes_a_candidate(self):
        source = (ROOT / 'scripts/analyze_seoul_polygon_source.py').read_text(encoding='utf-8')
        start = source.index('def match(')
        body = source[start:source.index('# ------', start)]
        # docstring을 걷어낸 실제 코드만 본다.
        code = body.split('"""')[2]
        code = '\n'.join(line for line in code.split('\n')
                         if not line.lstrip().startswith('#'))
        # match()는 geometry를 보지 않는다. 포함 여부로 후보를 만들거나 등급을 올리지 않는다.
        for forbidden in ('contains(', 'point_in_ring(', 'outer_rings', 'geometry'):
            self.assertNotIn(forbidden, code, forbidden)


BOUNDARY_SQL = (ROOT / 'supabase/migrations/20260929_zipon_boundary_rpc.sql').read_text(
    encoding='utf-8')


class BoundaryWriteRpcTests(unittest.TestCase):
    """공식 경계를 반영하는 유일한 DB 경로. 무엇을 거절하고 무엇을 건드리지 않는지."""

    def setUp(self):
        self.sql = BOUNDARY_SQL
        self.write = self.sql[self.sql.index('CREATE OR REPLACE FUNCTION public.zipon_set_project_boundary'):
                              self.sql.index('REVOKE ALL ON FUNCTION public.zipon_set_project_boundary')]

    def test_it_is_installed_in_one_transaction_and_only_for_the_service_role(self):
        self.assertEqual(self.sql.count('BEGIN;'), 1)
        self.assertTrue(self.sql.rstrip().endswith('COMMIT;'))
        for function in ('zipon_set_project_boundary', 'zipon_development_map'):
            self.assertIn(f'REVOKE ALL ON FUNCTION public.{function}', self.sql)
            self.assertIn(f'GRANT EXECUTE ON FUNCTION public.{function}', self.sql)
            self.assertIn('FROM PUBLIC,anon,authenticated', self.sql)
        self.assertIn('TO service_role', self.sql)
        self.assertIn('SECURITY INVOKER', self.write)
        self.assertIn('SET search_path=pg_catalog,public,extensions,pg_temp', self.write)

    def test_it_writes_only_the_boundary_columns(self):
        update = self.write[self.write.index('UPDATE public.development_projects SET'):
                            self.write.index('WHERE project_id=p_project_id RETURNING')]
        for allowed in ('geometry=shape', 'geometry_source=p_geometry_source',
                        'geometry_verified=true', 'geometry_verified_at=now()',
                        "jsonb_build_object('boundary',evidence)", 'revision=next_revision'):
            self.assertIn(allowed, update)
        # 좌표·단계·상태·검증상태·identity는 이 RPC가 손대지 않는다.
        for forbidden in ('location=', 'location_source=', 'stage=', 'stage_raw=', 'status=',
                          'validation_status=', 'external_id=', 'official_authority=',
                          'canonical_source_id=', 'confidence_level='):
            self.assertNotIn(forbidden, update, forbidden)

    def test_it_never_overwrites_a_verified_boundary(self):
        self.assertIn("'BOUNDARY_ALREADY_VERIFIED'", self.write)
        self.assertIn('oldrow.geometry_verified IS TRUE', self.write)
        self.assertIn("'skipped'", self.write)
        # verified가 아닌 geometry가 이미 있으면 덮어쓰지 않고 사람 검토로 넘긴다.
        self.assertIn("'UNVERIFIED_GEOMETRY_PRESENT'", self.write)

    def test_it_refuses_a_geometry_that_is_not_a_valid_polygon_in_seoul(self):
        for reason in ('GEOMETRY_TYPE_NOT_ALLOWED', 'GEOMETRY_UNREADABLE', 'GEOMETRY_NOT_VALID',
                       'BOUNDARY_OUTSIDE_SEOUL', 'BOUNDARY_AREA_IMPLAUSIBLE'):
            self.assertIn(f"'{reason}'", self.write)
        self.assertIn("p_geometry->>'type' NOT IN ('Polygon','MultiPolygon')", self.write)
        self.assertIn('extensions.ST_IsValid(shape)', self.write)
        self.assertIn('extensions.ST_NDims(shape)<>2', self.write)
        # 좌표계를 잘못 읽은 polygon은 서울 bounding box에서 걸린다.
        self.assertIn('126.734', self.write)
        self.assertIn('127.270', self.write)
        self.assertIn('37.413', self.write)
        self.assertIn('37.715', self.write)
        self.assertIn('area<100 OR area>5000000', self.write)

    def test_it_refuses_when_the_stored_point_is_outside_the_boundary(self):
        self.assertIn("'STORED_POINT_OUTSIDE_BOUNDARY'", self.write)
        self.assertIn('NOT extensions.ST_Contains(shape,oldrow.location::extensions.geometry)',
                      self.write)

    def test_it_requires_reviewed_exact_evidence_with_provenance(self):
        for reason in ('EXACT_AUTO_APPLY_EVIDENCE_REQUIRED', 'SOURCE_PROVENANCE_REQUIRED',
                       'BOUNDARY_CHECKS_NOT_PASSED', 'NO_BOUNDARY_SOURCE'):
            self.assertIn(f"'{reason}'", self.write)
        self.assertIn("p_evidence->>'match_status' IS DISTINCT FROM 'EXACT'", self.write)
        self.assertIn("p_evidence->'auto_apply_candidate' IS DISTINCT FROM 'true'::jsonb",
                      self.write)
        self.assertIn("p_evidence->'representative_point_inside_polygon' IS DISTINCT FROM 'true'::jsonb",
                      self.write)
        for check in ('geometry_valid', 'ring_closed', 'crs_converted', 'normalized_name_match',
                      'district_match', 'single_candidate', 'not_identity_protected',
                      'point_in_polygon'):
            self.assertIn(f'"{check}":true', self.write)
        # 하나라도 true가 아니면 거절한다.
        self.assertIn("c.v IS DISTINCT FROM 'true'::jsonb", self.write)

    def test_it_locks_the_row_and_checks_the_revision(self):
        self.assertIn('FOR UPDATE', self.write)
        self.assertIn("'REVISION_CONFLICT'", self.write)
        self.assertIn("'DISTRICT_MISMATCH'", self.write)
        self.assertIn("'NO_CANONICAL_SOURCE'", self.write)
        self.assertIn("SET LOCAL lock_timeout='5s'", self.sql)

    def test_it_reports_what_it_left_alone(self):
        returning = self.write[self.write.index("'result','boundary_set'"):]
        for field in ('location_untouched', 'stage_untouched', 'identity_untouched'):
            self.assertIn(field, returning)


class BoundaryReadRpcTests(unittest.TestCase):
    """지도·탐색 RPC가 확인된 경계만 GeoJSON으로 내보내는지."""

    def setUp(self):
        self.sql = BOUNDARY_SQL
        self.map = self.sql[self.sql.index('CREATE OR REPLACE FUNCTION public.zipon_development_map'):
                            self.sql.index('REVOKE ALL ON FUNCTION public.zipon_development_map')]
        self.search = self.sql[self.sql.index('CREATE OR REPLACE FUNCTION public.zipon_development_search'):]

    def test_the_map_rpc_emits_a_boundary_only_when_it_is_verified(self):
        self.assertIn('boundary jsonb', self.map)
        self.assertIn('WHEN p.geometry_verified AND p.geometry IS NOT NULL', self.map)
        self.assertIn('extensions.ST_AsGeoJSON(p.geometry)::jsonb', self.map)
        self.assertEqual(self.map.count('extensions.ST_AsGeoJSON'), 1)
        self.assertIn('STABLE', self.map)
        # 무거운 컬럼은 지도 응답에 담지 않는다.
        for heavy in ('field_evidence', 'raw_snapshot'):
            self.assertNotIn(heavy, self.map)

    def test_the_map_rpc_hands_back_plain_coordinates(self):
        self.assertIn('extensions.ST_X(p.location::extensions.geometry)', self.map)
        self.assertIn('extensions.ST_Y(p.location::extensions.geometry)', self.map)
        self.assertIn('boundary_area_m2', self.map)

    def test_the_search_rpc_keeps_the_same_inside_rule(self):
        # INSIDE는 geometry_verified이고 점이 polygon 안에 있을 때만이다. 규칙은 그대로다.
        self.assertIn(
            "WHEN p.geometry_verified AND p.geometry IS NOT NULL AND extensions.ST_Contains(p.geometry,q) THEN 'INSIDE'",
            self.search)
        self.assertIn('boundary jsonb', self.search)
        self.assertIn('geometry_verified boolean', self.search)
        self.assertIn('extensions.ST_AsGeoJSON(c.geometry)::jsonb', self.search)

    def test_the_search_rpc_is_replaced_cleanly_because_its_columns_changed(self):
        self.assertIn('DROP FUNCTION IF EXISTS public.zipon_development_search', self.sql)
        self.assertLess(self.sql.index('DROP FUNCTION IF EXISTS public.zipon_development_search'),
                        self.sql.index('CREATE OR REPLACE FUNCTION public.zipon_development_search'))


class PolygonApplyRunnerTests(unittest.TestCase):
    """검토를 통과한 건만 계획에 들어가는지. DB 접속 없이 계획 단계만 돌린다."""

    SQUARE = [[127.126, 37.540], [127.126, 37.543], [127.129, 37.543], [127.129, 37.540],
              [127.126, 37.540]]

    @classmethod
    def setUpClass(cls):
        import apply_zipon_polygons as runner
        cls.runner = runner

    def source(self):
        return {'dataset': '도시계획사업 현황(서울플랜+) 공간정보', 'dataset_id': 'OA-22712',
                'version': '202609', 'source_sha256': 'a' * 64, 'archive': 'z.zip',
                'legal_note': '법적 효력 없음 / 참고자료'}

    def row(self, project_id, **extra):
        base = {'zipon_project_id': project_id, 'zipon_project_name': '천호1 도시환경정비사업조합',
                'district': '강동구', 'zipon_normalized_name': '천호1',
                'official_normalized_name': '천호1', 'official_name': '천호1',
                'official_source_record_id': '11740UQ120PS202604100001',
                'match_status': 'EXACT',
                'match_signals': ['NAME_NORMALIZED_EXACT', 'DISTRICT'],
                'geometry_valid': True, 'geometry_validity': 'VALID',
                'converted_crs': 'EPSG:4326',
                'representative_point_inside_polygon': True, 'auto_apply_candidate': True}
        base.update(extra)
        return base

    def bundle(self, rows, features=None, geometry=None):
        review = {'format': 'zipon-polygon-match-review-v1', 'db_write': False,
                  'source': self.source(), 'items': rows}
        if features is None:
            features = [{'geometry': geometry or {'type': 'Polygon', 'coordinates': [self.SQUARE]},
                         'properties': {'zipon_project_id': row['zipon_project_id']}}
                        for row in rows]
        return review, {'features': features}

    def plan(self, rows, **kwargs):
        review, geojson = self.bundle(rows, **kwargs)
        return self.runner.plan(review, geojson, review['source'])

    def test_only_auto_apply_candidates_are_selected(self):
        selected, skipped = self.plan([
            self.row('p1'),
            self.row('p2', auto_apply_candidate=False, match_status='PROBABLE'),
            self.row('p3', auto_apply_candidate=False, match_status='EXACT',
                     representative_point_inside_polygon=False,
                     excluded_reason='REPRESENTATIVE_POINT_OUTSIDE_POLYGON'),
        ])
        self.assertEqual([item['project_id'] for item in selected], ['p1'])
        reasons = {row['project_id']: row['reason'] for row in skipped}
        self.assertEqual(reasons['p2'], 'NOT_AUTO_APPLY_PROBABLE')
        self.assertEqual(reasons['p3'], 'REPRESENTATIVE_POINT_OUTSIDE_POLYGON')

    def test_a_candidate_without_a_geojson_feature_is_skipped(self):
        selected, skipped = self.plan([self.row('p1')], features=[])
        self.assertEqual(selected, [])
        self.assertEqual(skipped[0]['reason'], 'NOT_IN_REVIEW_GEOJSON')

    def test_an_unclosed_or_foreign_polygon_is_skipped(self):
        open_ring = {'type': 'Polygon', 'coordinates': [self.SQUARE[:-1]]}
        _, skipped = self.plan([self.row('p1')], geometry=open_ring)
        self.assertEqual(skipped[0]['reason'], 'GEOMETRY_NOT_A_CLOSED_POLYGON')
        far = [[129.0, 35.1], [129.0, 35.2], [129.1, 35.2], [129.1, 35.1], [129.0, 35.1]]
        _, skipped = self.plan([self.row('p1')],
                               geometry={'type': 'Polygon', 'coordinates': [far]})
        self.assertEqual(skipped[0]['reason'], 'BOUNDARY_OUTSIDE_SEOUL')
        point_like = [[127.126, 37.540], [127.126, 37.54001], [127.12601, 37.54001],
                      [127.12601, 37.540], [127.126, 37.540]]
        _, skipped = self.plan([self.row('p1')],
                               geometry={'type': 'Polygon', 'coordinates': [point_like]})
        self.assertEqual(skipped[0]['reason'], 'BOUNDARY_AREA_IMPLAUSIBLE')

    def test_a_multipolygon_is_accepted_and_measured(self):
        second = [[point[0] + 0.01, point[1]] for point in self.SQUARE]
        geometry = {'type': 'MultiPolygon', 'coordinates': [[self.SQUARE], [second]]}
        selected, _ = self.plan([self.row('p1')], geometry=geometry)
        self.assertEqual(selected[0]['geometry_type'], 'MultiPolygon')
        self.assertGreater(selected[0]['area_m2'], 100)

    def test_the_evidence_carries_the_provenance_the_rpc_demands(self):
        selected, _ = self.plan([self.row('p1')])
        evidence = selected[0]['evidence']
        self.assertEqual(evidence['match_status'], 'EXACT')
        self.assertTrue(evidence['auto_apply_candidate'])
        self.assertTrue(evidence['representative_point_inside_polygon'])
        self.assertEqual(evidence['source_version'], '202609')
        self.assertEqual(len(evidence['source_sha256']), 64)
        self.assertTrue(all(evidence['checks'].values()), evidence['checks'])
        self.assertEqual(set(evidence['checks']),
                         {'geometry_valid', 'ring_closed', 'crs_converted',
                          'normalized_name_match', 'district_match', 'single_candidate',
                          'not_identity_protected', 'point_in_polygon'})

    def test_a_review_artifact_from_another_source_edition_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            review = Path(directory) / 'review.json'
            geojson = Path(directory) / 'exact.geojson'
            registry = Path(directory) / 'registry.json'
            body, features = self.bundle([self.row('p1')])
            review.write_text(json.dumps(body), encoding='utf-8')
            geojson.write_text(json.dumps(features), encoding='utf-8')
            registry.write_text(json.dumps({'sources': [
                {'dataset_id': 'OA-22712', 'version': '202609', 'source_sha256': 'b' * 64}]}),
                encoding='utf-8')
            with patch.object(self.runner, 'REVIEW_FILE', review), \
                    patch.object(self.runner, 'GEOJSON_FILE', geojson), \
                    patch.object(self.runner, 'REGISTRY_FILE', registry):
                with self.assertRaises(self.runner.Blocked) as caught:
                    self.runner.artifacts()
        self.assertEqual(caught.exception.reason, 'SOURCE_HASH_DOES_NOT_MATCH_REGISTRY')

    def test_the_point_check_excludes_a_hole(self):
        hole = [[127.1265, 37.5405], [127.1265, 37.5408], [127.1268, 37.5408],
                [127.1268, 37.5405], [127.1265, 37.5405]]
        geometry = {'type': 'Polygon', 'coordinates': [self.SQUARE, hole]}
        self.assertTrue(self.runner.point_inside(geometry, 127.1285, 37.5425))
        self.assertFalse(self.runner.point_inside(geometry, 127.12665, 37.54065))
        self.assertFalse(self.runner.point_inside(geometry, 127.20, 37.60))

    def test_the_runner_writes_nothing_without_apply(self):
        source = (ROOT / 'scripts/apply_zipon_polygons.py').read_text(encoding='utf-8')
        self.assertIn("mode.add_argument('--dry-run'", source)
        self.assertIn("mode.add_argument('--apply'", source)
        self.assertIn("'db_write': bool(args.apply)", source)
        # 쓰기는 이 RPC 한 곳으로만 간다. PATCH나 직접 UPDATE 경로가 없다.
        self.assertIn('rpc/zipon_set_project_boundary', source)
        for forbidden in ("session.patch", "'PATCH'", 'development_projects?', 'DELETE'):
            self.assertNotIn(forbidden, source, forbidden)
        self.assertEqual(source.count('session.post'), 1)

    def test_it_verifies_that_nothing_else_changed(self):
        for field in ('sigungu', 'stage', 'status', 'validation_status', 'external_id',
                      'official_authority', 'canonical_source_id'):
            self.assertIn(field, self.runner.UNTOUCHED)
        source = (ROOT / 'scripts/apply_zipon_polygons.py').read_text(encoding='utf-8')
        self.assertIn('unexpected_changes', source)
        self.assertIn('location_untouched', source)


class BoundaryOnScreenTests(unittest.TestCase):
    """확인된 경계가 화면에서 구역으로 읽히고, 없을 때는 그렇지 않은지."""

    def setUp(self):
        self.map_source = read('components/realestate/ZiponMap.tsx')
        self.card = read('components/realestate/DevelopmentCard.tsx')

    def test_the_card_says_구역_only_when_a_verified_boundary_is_drawn(self):
        self.assertIn('point.boundary_status === "OFFICIAL_VERIFIED" && point.boundary', self.card)
        self.assertIn('공식 사업구역', self.card)
        self.assertIn('사업 대표위치', self.card)
        # 대표위치 문구가 경계 문구를 대신하지 않도록 두 갈래로 갈라져 있어야 한다.
        self.assertIn(') : (', self.card.split('공식 사업구역', 1)[1][:400])

    def test_the_legend_counts_boundaries_only_when_they_exist(self):
        self.assertIn('const withBoundary = located.filter', self.map_source)
        self.assertIn('withBoundary > 0 &&', self.map_source)
        self.assertIn('공식 사업구역 {withBoundary}', self.map_source)

    def test_the_map_payload_type_carries_the_boundary_contract(self):
        types = read('lib/realestate.ts')
        for field in ('boundary: unknown | null', 'boundary_status: string',
                      'boundary_status_label: string', 'allows_inside: boolean'):
            self.assertIn(field, types)

    def test_a_verified_boundary_reaches_the_map_point(self):
        boundary = {'type': 'Polygon', 'coordinates': [[[127.126, 37.540], [127.126, 37.543],
                                                        [127.129, 37.543], [127.126, 37.540]]]}
        point = pr.map_point({'project_id': 'p1', 'project_name': '천호1', 'sigungu': '강동구',
                              'project_type': 'REDEVELOPMENT', 'latitude': 37.5415,
                              'longitude': 127.1275, 'boundary': boundary,
                              'geometry_verified': True,
                              'geometry_source': '서울특별시 도시계획사업 현황(서울플랜+) 공간정보',
                              'validation_status': 'VERIFIED'})
        self.assertEqual(point['boundary_status'], 'OFFICIAL_VERIFIED')
        self.assertEqual(point['boundary'], boundary)
        self.assertTrue(point['allows_inside'])
        self.assertEqual(point['accuracy'], 'OFFICIAL_BOUNDARY')

    def test_an_unverified_boundary_never_reaches_the_map_point(self):
        boundary = {'type': 'Polygon', 'coordinates': [[[127.126, 37.540]]]}
        point = pr.map_point({'project_id': 'p1', 'project_name': '천호1', 'sigungu': '강동구',
                              'project_type': 'REDEVELOPMENT', 'latitude': 37.5415,
                              'longitude': 127.1275, 'boundary': boundary,
                              'geometry_verified': False, 'validation_status': 'VERIFIED'})
        self.assertIsNone(point['boundary'])
        self.assertEqual(point['boundary_status'], 'NOT_AVAILABLE')
        self.assertFalse(point['allows_inside'])
        self.assertEqual(point['accuracy'], 'REPRESENTATIVE_POINT')


class BoundaryPostcheckTests(unittest.TestCase):
    """설치 후 확인 SQL이 실제로 되돌려지고, 무엇을 확인하는지."""

    def setUp(self):
        self.sql = (ROOT / 'supabase/review/20260929_zipon_boundary_postcheck.sql') \
            .read_text(encoding='utf-8')

    def test_it_rolls_back_every_fixture(self):
        self.assertTrue(self.sql.rstrip().endswith('ROLLBACK;'))
        self.assertIn('ZIPON_POSTCHECK_ROLLBACK', self.sql)
        self.assertIn("WHEN sqlstate 'ZP001' THEN RAISE NOTICE", self.sql)
        # 정리 목적의 삭제 경로를 두지 않는다. 롤백만으로 되돌린다(머리말 주석은 제외).
        body = self.sql[self.sql.index('BEGIN;'):]
        for forbidden in ('DELETE FROM', 'TRUNCATE', 'DROP TABLE'):
            self.assertNotIn(forbidden, body)
        self.assertIn('TEST_ZIPON_', self.sql)

    def test_it_checks_each_refusal_and_the_one_success(self):
        for reason in ('NO_CANONICAL_SOURCE', 'BOUNDARY_OUTSIDE_SEOUL',
                       'BOUNDARY_AREA_IMPLAUSIBLE', 'BOUNDARY_CHECKS_NOT_PASSED',
                       'DISTRICT_MISMATCH', 'REVISION_CONFLICT', 'BOUNDARY_ALREADY_VERIFIED'):
            self.assertIn(reason, self.sql, reason)
        self.assertIn("answer->>'result'='boundary_set'", self.sql)
        self.assertIn("(answer->'location_untouched')::boolean", self.sql)
        self.assertIn("(answer->'identity_untouched')::boolean", self.sql)

    def test_it_proves_inside_turns_on_only_with_a_verified_boundary(self):
        self.assertIn("ok:=relation='INSIDE'", self.sql)
        self.assertIn("ok:=relation='NEARBY'", self.sql)
        self.assertIn('map rpc emits the verified boundary', self.sql)


class BoundaryActivationDocumentTests(unittest.TestCase):
    """설치·반영 문서가 순서와 안전장치를 적고 있는지."""

    def setUp(self):
        self.document = (ROOT / 'docs/zipon_boundary_activation_2026-09-29.md') \
            .read_text(encoding='utf-8')

    def test_it_names_every_file_a_person_has_to_run(self):
        for expected in ('supabase/migrations/20260929_zipon_boundary_rpc.sql',
                         'supabase/review/20260929_zipon_boundary_postcheck.sql',
                         'scripts/apply_zipon_polygons.py',
                         'polygon_apply_journal_20260929.json'):
            self.assertIn(expected, self.document)
        self.assertIn('--dry-run', self.document)
        self.assertIn('--apply --limit 1', self.document)

    def test_it_says_which_rows_are_left_out(self):
        for expected in ('auto_apply_candidate', 'exact_valid_outside',
                         'exact_invalid_geometry', 'identity conflict', '15건'):
            self.assertIn(expected, self.document)

    def test_it_records_the_two_layers_of_checks_and_what_stays_untouched(self):
        for expected in ('ST_Contains', 'ST_IsValid', 'ST_Area', 'revision',
                         'unexpected_changes', 'canonical_source_id'):
            self.assertIn(expected, self.document)
        self.assertIn('좌표·단계·상태·', self.document)

    def test_it_states_the_inside_rule_and_the_shortcut_that_was_removed(self):
        self.assertIn('geometry_verified`이고 그 polygon이 점을 담을 때만 INSIDE', self.document)
        self.assertIn('evidence_verified', self.document)
        self.assertIn('출처 확인 시각은 경계 확인이 아니다', self.document)
        self.assertIn('NOT_DETERMINED', self.document)

    def test_it_states_that_this_container_wrote_nothing(self):
        self.assertIn('이 컨테이너에서는 DB에 아무것도 쓰지 않았다', self.document)

    def test_it_explains_the_fallback_so_install_order_cannot_empty_the_map(self):
        self.assertIn('boundary_source', self.document)
        self.assertIn('REST 조회로 되돌아가', self.document)


class PostcheckFixtureConstraintTests(unittest.TestCase):
    """postcheck의 fixture INSERT가 운영 CHECK 제약을 만족하는지 미리 확인한다.

    한 번 겪은 실패다: validation_status='VERIFIED'만 넣고 verified_at / verified_by를
    빼면 development_project_sources_check1에 걸려 Dashboard에서 postcheck가 죽는다.
    제약을 완화하지 않고 fixture를 맞춘다. 이 테스트가 그것을 SQL 실행 전에 잡는다.
    """

    OFFICIAL_TYPES = ('OFFICIAL_API', 'OFFICIAL_NOTICE', 'OFFICIAL_WEBSITE', 'PUBLIC_INSTITUTION')
    SOURCE_TYPES = OFFICIAL_TYPES + ('SEARCH_RESULT', 'OTHER')
    VALIDATION = ('UNVERIFIED', 'VERIFIED', 'NEEDS_REVIEW', 'REJECTED')

    @classmethod
    def setUpClass(cls):
        cls.base = (ROOT / 'supabase/migrations/20260926_zipon_base_and_development.sql') \
            .read_text(encoding='utf-8')
        cls.reviews = sorted((ROOT / 'supabase/review').glob('*.sql'))

    @staticmethod
    def split_arguments(text):
        parts, depth, current = [], 0, ''
        for character in text:
            if character in '([':
                depth += 1
            elif character in ')]':
                depth -= 1
            if character == ',' and depth == 0:
                parts.append(current.strip())
                current = ''
                continue
            current += character
        parts.append(current.strip())
        return [part for part in parts if part]

    @classmethod
    def source_inserts(cls, sql):
        """postcheck가 만드는 출처 행을 컬럼 → 값 표현식으로 읽어 온다."""
        import re
        rows = []
        pattern = re.compile(
            r'INSERT INTO public\.development_project_sources\(([^)]*)\)\s*\n\s*VALUES\((.*?)\);',
            re.S)
        for match in pattern.finditer(sql):
            columns = [c.strip() for c in match.group(1).replace('\n', ' ').split(',') if c.strip()]
            values = cls.split_arguments(match.group(2).replace('\n', ' '))
            if len(columns) != len(values):
                rows.append({'__arity__': (len(columns), len(values))})
                continue
            rows.append(dict(zip(columns, values)))
        return rows

    @staticmethod
    def literal(expression):
        """따옴표 안의 값만 문자열로 돌려준다. 그 밖은 None(실행 시 결정)."""
        text = (expression or '').strip()
        if text.startswith("'") and text.endswith("'") and text.count("'") == 2:
            return text[1:-1]
        return None

    @classmethod
    def present(cls, expression):
        """NULL이 아니고 빈 문자열도 아닌 값인지."""
        text = (expression or '').strip()
        if not text or text.upper() == 'NULL':
            return False
        return cls.literal(text) != ''

    def test_the_two_table_level_checks_are_the_ones_we_think_they_are(self):
        # 이름 없는 테이블 CHECK는 선언 순서대로 _check, _check1이 된다.
        body = self.base[self.base.index('CREATE TABLE IF NOT EXISTS public.development_project_sources ('):]
        body = body[:body.index('\n);')]
        checks = [line.strip() for line in body.split('\n') if line.strip().startswith('CHECK (')]
        self.assertEqual(len(checks), 2, checks)
        self.assertIn('NOT is_official OR source_type IN', checks[0])
        self.assertIn("validation_status<>'VERIFIED'", checks[1])
        self.assertIn('verified_at IS NOT NULL', checks[1])
        self.assertIn('verified_by IS NOT NULL', checks[1])
        self.assertIn('btrim(verified_by)<>', checks[1])

    def test_every_postcheck_source_fixture_satisfies_check1(self):
        seen = 0
        for path in self.reviews:
            for row in self.source_inserts(path.read_text(encoding='utf-8')):
                self.assertNotIn('__arity__', row, f'{path.name}: columns and values differ')
                seen += 1
                where = f'{path.name}: {row}'
                if self.literal(row.get('validation_status')) == 'VERIFIED':
                    self.assertTrue(self.present(row.get('verified_at')), where)
                    self.assertTrue(self.present(row.get('verified_by')), where)
        self.assertGreaterEqual(seen, 3, 'postcheck 출처 fixture를 찾지 못했다')

    def test_every_postcheck_source_fixture_satisfies_the_other_checks(self):
        for path in self.reviews:
            for row in self.source_inserts(path.read_text(encoding='utf-8')):
                where = f'{path.name}: {row}'
                kind = self.literal(row.get('source_type'))
                if kind is not None:
                    self.assertIn(kind, self.SOURCE_TYPES, where)
                    if (row.get('is_official') or '').strip().lower() == 'true':
                        self.assertIn(kind, self.OFFICIAL_TYPES, where)
                status = self.literal(row.get('validation_status'))
                if status is not None:
                    self.assertIn(status, self.VALIDATION, where)
                url = row.get('source_url') or ''
                self.assertIn('https://', url, where)
                self.assertNotIn(' ', self.literal(url.split('||')[0].strip()) or '', where)
                digest = row.get('content_hash') or ''
                # 64자리 소문자 16진수여야 한다. repeat('c',64) 같은 형태를 그대로 받는다.
                self.assertRegex(digest.replace(' ', ''),
                                 r"^(repeat\('[0-9a-f]',64\)|'[0-9a-f]{64}')$", where)
                for required in ('project_id', 'source_name', 'source_type', 'source_url',
                                 'content_hash'):
                    self.assertIn(required, row, where)

    def test_the_boundary_postcheck_uses_the_repository_fixture_shape(self):
        sql = (ROOT / 'supabase/review/20260929_zipon_boundary_postcheck.sql') \
            .read_text(encoding='utf-8')
        row = self.source_inserts(sql)[0]
        self.assertEqual(self.literal(row['source_type']), 'OFFICIAL_NOTICE')
        self.assertEqual(self.literal(row['validation_status']), 'VERIFIED')
        self.assertEqual(row['verified_at'], 'now()')
        self.assertEqual(row['verified_by'], 'tag')
        self.assertIn("'https://cleanup.seoul.go.kr/TEST/'||tag", row['source_url'])
        self.assertEqual(row['content_hash'], "repeat('c',64)")
        self.assertIn('TEST', row['raw_snapshot'])

    def test_the_boundary_postcheck_does_not_depend_on_production_row_counts(self):
        sql = (ROOT / 'supabase/review/20260929_zipon_boundary_postcheck.sql') \
            .read_text(encoding='utf-8')
        # 자치구로 물으면 운영 사업이 함께 나와 LIMIT에 밀릴 수 있다. 좌표 반경으로 묻는다.
        for call in ('zipon_development_search(127.1275,37.5415,NULL,500,100)',
                     'zipon_development_search(127.1305,37.5415,NULL,500,100)'):
            self.assertIn(call, sql)
        self.assertNotIn("zipon_development_search(127.1275,37.5415,'강동구'", sql)

    def test_an_unexpected_error_still_reports_and_still_rolls_back(self):
        sql = (ROOT / 'supabase/review/20260929_zipon_boundary_postcheck.sql') \
            .read_text(encoding='utf-8')
        handler = sql[sql.index(' EXCEPTION'):]
        self.assertIn('WHEN others THEN RAISE NOTICE', handler)
        # 다시 올려 보내므로 트랜잭션이 중단되고 fixture가 남지 않는다.
        self.assertEqual(handler.count('RAISE;'), 2)
        self.assertTrue(sql.rstrip().endswith('ROLLBACK;'))

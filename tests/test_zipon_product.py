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

    def test_official_detail_fields_are_exposed_for_the_collapsed_section(self):
        detail = self.row()['detail']
        self.assertEqual(detail['거래유형'], '중개거래')
        self.assertEqual(detail['중개사 소재지'], '서울 강동구')
        self.assertEqual(detail['계약해제'], 'O')
        self.assertEqual(detail['해제사유 발생일'], '26.09.25')
        self.assertEqual(detail['등기일자'], '26.09.20')
        self.assertEqual(detail['동'], '101')
        self.assertEqual(detail['토지임대부'], 'N')

    def test_absent_fields_are_not_invented(self):
        detail = self.row('<item><aptNm>x</aptNm><dealAmount>10,000</dealAmount></item>')['detail']
        self.assertEqual(detail, {})

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
        self.assertEqual(row['detail']['대지면적'], '120')


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
        self.assertEqual(project['trust']['label'], '확인 필요')
        self.assertEqual(project['status_label'], '상태 확인 필요')

    def test_an_unmapped_stage_says_so(self):
        self.assertEqual(self.project(normalized_stage=None, stage_raw=None)['stage']['label'],
                         '단계 확인 필요')

    def test_list_based_evidence_is_not_presented_as_confirmed(self):
        project = self.project(stage_basis='OFFICIAL_LIST_CELL')
        self.assertEqual(project['stage_basis'], '공식 목록 기준')
        self.assertNotEqual(project['trust']['label'], '공식 확인')

    def test_detail_verified_is_distinguished_from_list_mapped(self):
        verified = self.project(validation_status='VERIFIED', stage_basis='OFFICIAL_DETAIL_PAGE')
        self.assertEqual(verified['trust']['label'], '공식 확인')
        self.assertEqual(verified['stage_basis'], '공식 상세정보 기준')

    def test_inside_needs_a_verified_boundary(self):
        self.assertEqual(self.project(spatial_relation='INSIDE')['spatial']['label'], '주변 개발사업')
        self.assertFalse(self.project(spatial_relation='INSIDE')['spatial']['confirmed_boundary'])
        confirmed = self.project(spatial_relation='INSIDE', evidence_verified=True)
        self.assertEqual(confirmed['spatial']['label'], '정비구역 내')
        self.assertTrue(confirmed['spatial']['confirmed_boundary'])

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
        self.assertEqual(self.queue['blocker'], 'VWORLD_API_KEY_NOT_CONFIGURED')


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
        self.assertEqual(result['districts'][1]['type_labels'], {'신속통합기획': 1})


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
        for label in ('실거래', '청약', '개발사업', '모니터링', '알림'):
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
        for field in ('build_year', 'road_name', 'jibun', 'source_label'):
            self.assertNotIn(field, head)
        for field in ('price_text', 'property_type', 'floor', 'date'):
            self.assertIn(field, head)
        self.assertIn('trade.detail', card)

    def test_detail_rows_skip_empty_values(self):
        self.assertIn('if (!value) return null;', read('components/realestate/CollapsibleDetails.tsx'))

    def test_the_development_tab_loads_without_a_search_button(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('useEffect', tab)
        self.assertIn('developmentSummary()', tab)
        self.assertNotIn('개발사업 찾기', tab)
        self.assertIn('if (summary) load(districts)', tab)

    def test_the_development_tab_shows_counts_and_filters_from_the_data(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        for piece in ('전체', '재건축', '재개발', '신속통합기획'):
            self.assertIn(piece, tab)
        self.assertIn('const stages = [...new Set(projects.map((p) => p.stage.label))]', tab)
        self.assertIn('진행단계 전체', tab)

    def test_the_development_card_separates_verified_from_list_mapped(self):
        card = read('components/realestate/DevelopmentCard.tsx')
        self.assertIn('project.stage_basis', card)
        self.assertIn('project.trust.label', card)
        self.assertIn('공식 ID', card)
        self.assertIn('추진 프로그램', card)
        self.assertIn('공식자료 ↗', card)
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

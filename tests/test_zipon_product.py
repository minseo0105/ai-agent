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
                         '공식 단계 확인 중')

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
        confirmed = self.project(spatial_relation='INSIDE', evidence_verified=True)
        self.assertEqual(confirmed['spatial']['label'], '정비구역 내부')
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
        self.assertIn('developmentSummary()', tab)
        self.assertNotIn('개발사업 찾기', tab)
        self.assertIn('if (summary) load(districts)', tab)

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
        self.assertIn('서울시 공식자료 ↗', card)
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

    def test_the_point_decoder_reads_a_geography_point(self):
        row = self.rows()[0]
        self.assertEqual(dev._point(row['location']), (127.1, 37.5))
        for bad in (None, '', 'zz', '0101'):
            self.assertEqual(dev._point(bad), (None, None))

    def test_the_map_endpoint_returns_a_light_payload(self):
        from api.realestate import development_map
        with patch.object(rm, '_using_remote_db', return_value=True), \
             patch.object(rm, '_remote_request', return_value=self.rows()) as request:
            result = asyncio.run(development_map(sigungu='강동구'))
        self.assertEqual(request.call_args.args[0], 'GET')
        self.assertNotIn('field_evidence', request.call_args.kwargs['params']['select'])
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
                                       'mappable'}, set())
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
    def test_the_map_is_client_only_and_uses_open_tiles(self):
        source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('await import("leaflet")', source)
        self.assertIn('tile.openstreetmap.org', source)
        self.assertIn('OpenStreetMap contributors', source)
        self.assertNotIn('googleapis', source)
        self.assertNotIn('NEXT_PUBLIC', source)

    def test_only_a_verified_boundary_is_drawn_as_an_area(self):
        source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('point.boundary_status === "OFFICIAL_VERIFIED" && point.boundary', source)
        self.assertIn('circleMarker', source)

    def test_the_legend_explains_the_three_marks(self):
        source = read('components/realestate/ZiponMap.tsx')
        for label in ('선택 부동산', '공식 사업구역', '사업 대표위치', '위치 데이터 준비 중'):
            self.assertIn(label, source)

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
        self.assertIn('서울시 공식자료 ↗', source)
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

    def test_the_config_never_carries_a_key(self):
        from services import map_providers
        config = map_providers.config(lambda name: 'super-secret-value')
        text = json.dumps(config, ensure_ascii=False)
        # 키 이름은 어떤 키를 등록해야 하는지 알리기 위해 담고, 값은 절대 담지 않는다.
        self.assertNotIn('super-secret-value', text)
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
             patch.object(rm, '_remote_request', return_value=self.rows()) as request:
            result = asyncio.run(development_map(sigungu='강동구'))
        columns = request.call_args.kwargs['params']['select'].split(',')
        # 폴리곤·원문 스냅샷 같은 무거운 컬럼은 지도 조회에 담지 않는다.
        for heavy in ('field_evidence', 'raw_snapshot', 'geometry'):
            self.assertNotIn(heavy, columns)
        self.assertIn('geometry_verified', columns)
        self.assertLessEqual(len(json.dumps(result['points'][0], ensure_ascii=False)), 900)


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
        self.assertLess(tab.index('aria-label="사업명 · 동 · 유형 검색"'), tab.index('<ZiponMap'))
        self.assertLess(tab.index('<ZiponMap'), tab.index('이 위치의 개발정보'))
        self.assertLess(tab.index('이 위치의 개발정보'), tab.index('<DevelopmentCard'))

    def test_the_filters_cover_every_layer(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        for label in ('재개발', '재건축', '신속통합기획', '모아타운', '기타 정비사업'):
            self.assertIn(f'"{label}"', tab)

    def test_map_and_list_are_synchronised(self):
        tab = read('components/realestate/DevelopmentTab.tsx')
        self.assertIn('onSelect={selectFromMap}', tab)
        self.assertIn('scrollIntoView', tab)
        self.assertIn('setSelectedId(p.project_id)', tab)
        self.assertIn('ring-2 ring-estate', tab)
        self.assertIn('selectedId={selectedId}', tab)

    def test_the_map_separates_property_type_programme_and_boundary(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('DEVELOPMENT_COLOR', map_source)
        self.assertIn('PROGRAM_COLOR', map_source)
        self.assertIn('point.program_layer', map_source)
        self.assertIn('point.boundary_status === "OFFICIAL_VERIFIED" && point.boundary', map_source)
        self.assertIn('선택 부동산', map_source)

    def test_the_legend_names_the_three_marks(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        for label in ('선택 부동산', '공식 사업구역', '사업 대표위치'):
            self.assertIn(label, map_source)
        self.assertNotIn('공식 경계 확인</span>', map_source)

    def test_the_map_takes_its_basemap_from_the_server_with_an_osm_fallback(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('config?.tile ?? OSM', map_source)
        self.assertIn('tile.openstreetmap.org', map_source)
        self.assertIn('mapConfig()', read('components/realestate/DevelopmentTab.tsx'))

    def test_the_map_reports_its_viewport_for_a_future_bbox_query(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        self.assertIn('onBoundsChange', map_source)
        self.assertIn('getBounds()', map_source)

    def test_the_popup_shows_what_the_spec_asks_for(self):
        map_source = read('components/realestate/ZiponMap.tsx')
        for piece in ('point.stage_label', 'point.address', 'point.last_checked',
                      'point.official_url', 'point.accuracy_label', 'point.boundary_status_label'):
            self.assertIn(piece, map_source)

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
        response = geo.naver_provider('id', 'secret', naver_response())(NAVER_ADDRESS)
        two = dict(response, candidates=response['candidates'] * 2)
        evaluation = geo.evaluate(NAVER_ADDRESS, two)
        self.assertEqual(evaluation['review_reason'], 'MULTIPLE_PROVIDER_CANDIDATES')
        self.assertFalse(evaluation['coordinate_verified'])

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
        self.assertNotIn('ID_VALUE', text)
        self.assertNotIn('SECRET_VALUE', text)
        self.assertIn('NAVER_MAP_CLIENT_SECRET', config['browser_exposure']['never_sent_to_browser'])
        naver = next(p for p in config['providers'] if p['id'] == 'naver')
        self.assertEqual(naver['browser_key_name'], 'NAVER_MAP_CLIENT_ID')
        self.assertEqual(naver['web_service_url'], 'https://minseo2-digital-ai-lab.hf.space')
        self.assertEqual(providers.NAVER_WEB_SERVICE_URL, 'https://minseo2-digital-ai-lab.hf.space')

    def test_a_configured_naver_client_id_does_not_change_the_tile_source(self):
        _, config = self.config({'NAVER_MAP_CLIENT_ID': 'ID_VALUE'})
        self.assertEqual(config['active'], 'osm')
        self.assertIn('tile.openstreetmap.org', config['tile']['url_template'])

    def test_no_frontend_file_mentions_a_geocoding_credential(self):
        for path in (ROOT / 'web/src').rglob('*.ts*'):
            source = path.read_text(encoding='utf-8')
            for secret in ('NAVER_MAP_CLIENT_SECRET', 'KAKAO_REST_API_KEY', 'X-NCP-APIGW-API-KEY',
                           'SERVICE_ROLE', 'NEXT_PUBLIC_SUPABASE'):
                self.assertNotIn(secret, source, f'{path.name} mentions {secret}')

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
        for piece in ('전체', '재건축', '재개발', '신속통합기획'):
            self.assertIn(piece, tab)
        self.assertIn('const stages = [...new Set(projects.map((p) => p.stage.label))]', tab)
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
                                       'type_code', 'type_label', 'program_code', 'program_label',
                                       'stage_label', 'district', 'dong', 'accuracy',
                                       'accuracy_label', 'confidence', 'mappable'}, set())
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
        self.assertEqual(blocker, 'NAVER_CLOUD_API_KEY_ID_NOT_CONFIGURED')
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
        self.assertIn('point.accuracy === "OFFICIAL_BOUNDARY" && point.boundary', source)
        self.assertIn('circleMarker', source)

    def test_the_legend_explains_the_three_accuracy_levels(self):
        source = read('components/realestate/ZiponMap.tsx')
        for label in ('대표 위치', '공식 경계 확인', '위치 데이터 준비 중'):
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
        self.assertIn('height={320}', read('components/realestate/DevelopmentTab.tsx'))

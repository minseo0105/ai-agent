"""ZIP:ON 데이터 신선도 표시와 단계별 투자 접근 가이드.

DB·네트워크 없이 표현 계층만 검증한다. 운영 데이터와 안전장치는 건드리지 않는다.
"""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_investor as inv
from services import development_presentation as pr

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


class FreshnessTests(unittest.TestCase):
    def test_recent_check_is_fresh(self):
        result = inv.freshness(['2026-11-01T03:00:00+00:00'], now=NOW)
        self.assertEqual(result['state'], 'fresh')
        self.assertEqual(result['age_days'], 5)
        self.assertEqual(result['latest'], '2026-11-01')
        self.assertFalse(result['stale'])

    def test_old_check_is_stale_with_explicit_notice(self):
        result = inv.freshness(['2026-10-01', '2026-10-05T00:00:00Z'], now=NOW)
        self.assertEqual(result['state'], 'stale')
        self.assertTrue(result['stale'])
        self.assertEqual(result['latest'], '2026-10-05')
        self.assertEqual(result['age_days'], 32)
        self.assertIn('32', result['label'])
        self.assertEqual(result['threshold_days'], 14)

    def test_exactly_at_threshold_is_still_fresh(self):
        self.assertEqual(inv.freshness(['2026-10-23'], now=NOW)['state'], 'fresh')
        self.assertEqual(inv.freshness(['2026-10-22'], now=NOW)['state'], 'stale')

    def test_no_usable_date_is_unknown_not_fresh(self):
        for values in ([], [None], ['', 'not-a-date']):
            result = inv.freshness(values, now=NOW)
            self.assertEqual(result['state'], 'unknown')
            self.assertIsNone(result['age_days'])
            self.assertIsNone(result['stale'])

    def test_future_date_is_not_reported_as_negative_age(self):
        result = inv.freshness(['2026-12-01'], now=NOW)
        self.assertEqual(result['age_days'], 0)

    def test_garbage_among_valid_dates_is_ignored(self):
        result = inv.freshness(['??', '2026-11-05'], now=NOW)
        self.assertEqual(result['latest'], '2026-11-05')


class InvestorGuideTests(unittest.TestCase):
    def test_every_known_stage_has_a_guide(self):
        for stage in pr.STAGE_LABELS:
            if stage == 'UNKNOWN':
                continue
            guide = inv.investor_guide(stage)
            self.assertTrue(guide['interpreted'], stage)
            self.assertTrue(guide['risk_note'], stage)
            self.assertTrue(guide['watch_next'], stage)
            self.assertTrue(guide['pitfalls'], stage)
            self.assertIn(guide['phase'], inv.PHASES, stage)
            self.assertIn(guide['risk_level'], inv.RISK_LEVELS, stage)

    def test_unknown_stage_is_not_interpreted(self):
        for stage in ('UNKNOWN', None, 'NOT_A_STAGE'):
            guide = inv.investor_guide(stage)
            self.assertFalse(guide['interpreted'])
            self.assertEqual(guide['risk_level'], 'UNKNOWN')
            self.assertEqual(guide['pitfalls'], [])

    def test_guide_is_general_information_never_advice(self):
        guide = inv.investor_guide('ASSOCIATION_APPROVED')
        self.assertIn('투자 권유', guide['disclaimer'])
        self.assertIn('확인', guide['disclaimer'])
        banned = ('매수하세요', '추천', '사세요', '팔세요', '수익 보장', '확정 수익', '오른다')
        for stage in pr.STAGE_LABELS:
            text = ' '.join(str(v) for v in inv.investor_guide(stage).values())
            for word in banned:
                self.assertNotIn(word, text, f'{stage}: {word}')

    def test_no_stage_uses_the_screen_wording_the_product_forbids(self):
        # test_zipon_product가 화면 문구에서 금지하는 표현과 같은 규칙을 모든 단계에 적용한다.
        for stage in list(pr.STAGE_LABELS) + [None]:
            text = ' '.join(str(v) for v in inv.investor_guide(stage).values())
            for phrase in ('확인 필요', '단계 확인 필요', '근거 확인 필요', '상태 확인 필요'):
                self.assertNotIn(phrase, text, f'{stage}: {phrase}')

    def test_risk_does_not_fall_as_stage_stays_unverified(self):
        # 초기 단계는 후기 단계보다 위험이 낮게 표시되면 안 된다.
        order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        self.assertGreaterEqual(order[inv.investor_guide('CANDIDATE')['risk_level']],
                                order[inv.investor_guide('MANAGEMENT_DISPOSITION')['risk_level']])
        self.assertGreaterEqual(order[inv.investor_guide('MANAGEMENT_DISPOSITION')['risk_level']],
                                order[inv.investor_guide('COMPLETED')['risk_level']])

    def test_guide_returns_independent_copies(self):
        first = inv.investor_guide('PLANNING')
        first['pitfalls'].append('x')
        self.assertNotIn('x', inv.investor_guide('PLANNING')['pitfalls'])

    def test_regulation_is_flagged_as_needing_verification(self):
        guide = inv.investor_guide('ASSOCIATION_APPROVED')
        self.assertIn('규제', guide['disclaimer'])


class PresentProjectIntegrationTests(unittest.TestCase):
    ROW = {'project_id': 'p1', 'project_name': '테스트1구역', 'sigungu': '강동구',
           'normalized_stage': 'ASSOCIATION_APPROVED', 'project_type': 'REDEVELOPMENT',
           'last_verified_at': '2026-10-01T00:00:00+00:00'}

    def test_present_project_carries_investor_guide_and_freshness(self):
        project = pr.present_project(dict(self.ROW))
        self.assertIn('investor_guide', project)
        self.assertEqual(project['investor_guide']['stage'], 'ASSOCIATION_APPROVED')
        self.assertIn('freshness', project)
        self.assertIn(project['freshness']['state'], ('fresh', 'stale', 'unknown'))

    def test_existing_stage_guide_is_unchanged(self):
        project = pr.present_project(dict(self.ROW))
        self.assertEqual(project['stage_guide'], pr.stage_guide('ASSOCIATION_APPROVED'))


if __name__ == '__main__':
    unittest.main()

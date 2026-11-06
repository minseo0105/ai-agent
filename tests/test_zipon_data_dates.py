"""화면 날짜 구분: 단계 정보 수집일(카탈로그)과 DB 반영일. 어느 것도 '공식 확인일'로 표시하지 않는다."""
import unittest
from pathlib import Path

from services import development_investor as inv
from services import development_presentation as pr

ROOT = Path(__file__).resolve().parent.parent


class DataDatesTests(unittest.TestCase):
    def test_freshness_label_no_longer_claims_official_confirmation(self):
        for value in (['2026-09-27'], ['2026-11-06'], []):
            self.assertNotIn('공식 확인', inv.freshness(value)['label'])
        self.assertIn('단계 정보 수집일', inv.freshness(['2026-09-27'])['label'])

    def test_db_reflected_is_none_when_not_written_and_never_filled_from_catalog(self):
        p = pr.present_project({'project_id': 'x', 'project_name': '천호1', 'project_type': 'REDEVELOPMENT',
                                'sigungu': '강동구', 'stage_raw': '조합설립인가'})
        self.assertIsNone(p['data_dates']['db_reflected'])

    def test_db_reflected_comes_only_from_last_verified_at(self):
        p = pr.present_project({'project_id': 'x', 'project_name': '천호1', 'project_type': 'REDEVELOPMENT',
                                'sigungu': '강동구', 'stage_raw': '조합설립인가',
                                'last_verified_at': '2026-11-06T11:51:15+00:00'})
        self.assertEqual(p['data_dates']['db_reflected'], '2026-11-06')

    def test_screens_label_dates_separately_and_show_unrecorded(self):
        info = (ROOT / 'web/src/components/realestate/zip/tabs/ProjectInfoTab.tsx').read_text(encoding='utf-8')
        notice = (ROOT / 'web/src/components/realestate/zip/DashboardNotices.tsx').read_text(encoding='utf-8')
        self.assertIn('단계 정보 수집일', info)
        self.assertIn('DB 반영일', info)
        self.assertIn('"미기록"', info)
        self.assertNotIn('dbReflected', notice)  # 전체 DB 반영일 단일 값은 쓰지 않는다(건수로 표시)
        for src in (info, notice):
            self.assertNotIn('공식 확인일', src)


if __name__ == '__main__':
    unittest.main()

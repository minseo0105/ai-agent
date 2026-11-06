"""모바일 시트·줌 컨트롤과 지도 전체 신선도(중앙값·DB 반영 건수)."""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services import development_investor as inv

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)


def proj(stage=None, db=None):
    return {'data_dates': {'stage_collected': stage, 'db_reflected': db}}


class MapFreshnessTests(unittest.TestCase):
    def test_one_recent_project_does_not_make_the_whole_map_fresh(self):
        projects = [proj('2026-09-27') for _ in range(1188)] + [proj('2026-11-06', '2026-11-06'), proj('2026-10-01')]
        f = inv.map_freshness(projects, now=NOW)
        self.assertEqual((f['state'], f['median'], f['latest']), ('stale', '2026-09-27', '2026-11-06'))
        self.assertIn('DB 반영은 전체 1,190건 중 1건', f['label'])
        self.assertNotIn('공식 확인', f['label'])

    def test_fresh_when_most_projects_are_recent(self):
        f = inv.map_freshness([proj('2026-11-05') for _ in range(5)] + [proj('2026-09-01')], now=NOW)
        self.assertEqual(f['state'], 'fresh')
        self.assertIn('DB 반영 기록은 아직 없어요', f['label'])

    def test_unknown_without_any_stage_date(self):
        f = inv.map_freshness([proj(None, '2026-11-06')], now=NOW)
        self.assertEqual((f['state'], f['db_reflected']), ('unknown', 1))

    def test_map_endpoint_uses_map_freshness(self):
        src = (ROOT / 'api/realestate.py').read_text(encoding='utf-8')
        self.assertIn("'freshness': presentation.map_freshness(all_projects)", src)


class UndatedProjectsTests(unittest.TestCase):
    def test_undated_projects_count_as_oldest_and_prevent_overestimation(self):
        projects = [proj('2026-11-05') for _ in range(130)] + [proj(None) for _ in range(1060)]
        f = inv.map_freshness(projects, now=NOW)
        self.assertEqual((f['state'], f['undated'], f['stage_dated'], f['total']), ('stale', 1060, 130, 1190))
        self.assertIn('1,060건은 단계 정보 수집일 기록이 없어', f['label'])

    def test_minority_undated_still_shifts_the_median_older(self):
        projects = [proj('2026-11-05')] * 3 + [proj('2026-09-01')] * 2 + [proj(None)] * 2
        f = inv.map_freshness(projects, now=NOW)   # 7건, 중앙값 위치 3 → 날짜순 [미기록2, 9/1 2, 11/5 3]의 4번째 = 9/1
        self.assertEqual((f['median'], f['state']), ('2026-09-01', 'stale'))
        self.assertIn('기록이 없는 사업이 2건', f['label'])


class MobileSheetSourceTests(unittest.TestCase):
    def setUp(self):
        self.sheet = (ROOT / 'web/src/components/realestate/zip/MobileSheet.tsx').read_text(encoding='utf-8')

    def test_expanded_height_is_85_to_90_percent_with_vh_fallback(self):
        self.assertIn('h-[88vh] supports-[height:100svh]:h-[88svh]', self.sheet)
        self.assertIn('h-[42vh] supports-[height:100svh]:h-[42svh]', self.sheet)

    def test_drag_area_is_a_44px_target_and_body_scrolls(self):
        self.assertIn('data-sheet-handle', self.sheet)
        self.assertIn('min-h-11', self.sheet)
        self.assertIn('data-sheet-body className="flex min-h-0 flex-1 flex-col overflow-hidden"', self.sheet)
        panel = (ROOT / 'web/src/components/realestate/zip/ZoneDetailPanel.tsx').read_text(encoding='utf-8')
        self.assertIn('min-h-0 flex-1 overflow-y-auto', panel)


class ZoomControlSourceTests(unittest.TestCase):
    def test_narrow_screens_get_small_top_right_or_hidden_zoom(self):
        src = (ROOT / 'web/src/components/realestate/ZiponMap.tsx').read_text(encoding='utf-8')
        self.assertIn('...zoomControlOptions(loaded, compact)', src)
        self.assertIn('ZoomControlStyle?.SMALL', src)
        self.assertIn('{ zoomControl: false }', src)


if __name__ == '__main__':
    unittest.main()

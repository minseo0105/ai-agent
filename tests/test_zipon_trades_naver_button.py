"""실거래 탭의 네이버부동산 버튼: 항상 상단 1개, 기존 URL 재사용, 새 탭·보안 속성, 좌표 없으면 비활성."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / 'web/src/components/realestate/zip/tabs/TradesTab.tsx').read_text(encoding='utf-8')


class NaverButtonTests(unittest.TestCase):
    def test_rendered_once_at_the_top_of_the_tab_regardless_of_status(self):
        self.assertEqual(SRC.count('<NaverListingButton'), 1)
        default = SRC[SRC.index('export default function TradesTab'):]
        self.assertLess(default.index('<NaverListingButton'), default.index('<TradesBody'))
        self.assertNotIn('NaverFallback', SRC)

    def test_reuses_existing_url_and_opens_safely(self):
        self.assertIn('project?.naver_real_estate', SRC)
        self.assertIn('href={naver.url}', SRC)
        self.assertRegex(SRC, r'target="_blank" rel="noopener noreferrer"')
        self.assertNotRegex(SRC, r'fin\.land\.naver\.com|new\.land\.naver\.com')  # URL을 직접 만들지 않는다

    def test_disabled_without_coordinates(self):
        self.assertIn('disabled', SRC)
        self.assertIn('위치정보가 없어 연결할 수 없습니다.', SRC)

    def test_listing_prices_are_not_confused_with_molit_trades(self):
        self.assertIn('네이버부동산에서 매물·시세 확인', SRC)
        self.assertIn('국토교통부 실거래가(신고된 계약 금액)와 다릅니다', SRC)


if __name__ == '__main__':
    unittest.main()

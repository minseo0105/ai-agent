"""실거래·거래가이드 탭은 연동 전이므로 가상 거래 데이터를 만들거나 보여 주지 않는다(소스 점검)."""
import re
import unittest
from pathlib import Path

TABS = Path(__file__).resolve().parent.parent / "web/src/components/realestate/zip/tabs"


class UnconnectedTabsTests(unittest.TestCase):
    def setUp(self):
        self.trades = (TABS / "TradesTab.tsx").read_text(encoding="utf-8")
        self.guide = (TABS / "TradeGuideTab.tsx").read_text(encoding="utf-8")

    def test_badges_say_not_connected(self):
        self.assertIn("미연동", self.trades)
        self.assertIn("미연동", self.guide)

    def test_state_comes_from_server_connections_only(self):
        self.assertIn("connections.trades", self.trades)
        self.assertIn("connections.rights_engine", self.guide)

    def test_no_sample_or_random_trade_values(self):
        for name, text in (("trades", self.trades), ("guide", self.guide)):
            self.assertNotRegex(text, r"Math\.random|faker|dummy|sample|mock", name)
            # 억·만원 금액이나 ㎡ 면적 같은 숫자 리터럴이 화면 문구에 박혀 있지 않다.
            self.assertNotRegex(text, r"\d+억|\d[\d,]*만원|\d+\s*㎡|\d+층", name)

    def test_guide_never_declares_tradable(self):
        for phrase in ("거래 가능합니다", "안전한 매물입니다", "취득 가능합니다"):
            self.assertNotIn(phrase, self.guide)
        self.assertIn("판정하지 않아요", self.guide)


if __name__ == "__main__":
    unittest.main()

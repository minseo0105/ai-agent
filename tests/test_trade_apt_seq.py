"""실거래 행의 국토부 단지 일련번호(apt_seq) 노출. 재건축 단지 매칭의 근거로 쓴다."""
import unittest
import xml.etree.ElementTree as ET

from services import realestate_monitor as rm


def item(**fields):
    base = {"aptNm": "상아2차아파트", "umdNm": "오금동", "jibun": "165", "excluUseAr": "84.9", "dealAmount": "150,000",
            "dealYear": "2026", "dealMonth": "10", "dealDay": "1", "floor": "5", "buildYear": "1988", "bonbun": "0165"}
    base.update(fields)
    return ET.fromstring("<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in base.items() if v is not None) + "</item>")


class AptSeqTests(unittest.TestCase):
    def test_apartment_row_exposes_apt_seq(self):
        row = rm._trade_item_to_common(item(aptSeq="11710-124"), "아파트", "11710", "202610")
        self.assertEqual(row["apt_seq"], "11710-124")
        self.assertIn(":11710-124:", row["id"])  # 기존 id 형식은 그대로

    def test_missing_or_non_apartment_sequence_is_none(self):
        self.assertIsNone(rm._trade_item_to_common(item(), "아파트", "11710", "202610")["apt_seq"])
        row = rm._trade_item_to_common(item(aptNm=None, sggCd="11710", houseType="단독", totalFloorAr="86.4"), "단독·다가구", "11710", "202610")
        self.assertIsNone(row["apt_seq"])


if __name__ == "__main__":
    unittest.main()

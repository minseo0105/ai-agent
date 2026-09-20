"""Synthetic freshness fixtures; no NAVER responses are saved."""
import unittest
from datetime import date
from unittest.mock import patch
from services.golf_expressions import analyze_records, freshness_dates, get_expression_session, new_expression_session


def row(author, postdate, text="그린이 빠르다. 코스 관리가 좋다. 시설이 좋다. 페어웨이가 넓다. 코스가 어렵다"):
    return dict(title="레이크사이드CC 남코스 라운딩 후기", description=text,
                url=f"https://blog.naver.com/{author}/12345", published_at=postdate, query="synthetic")


class FreshnessTests(unittest.TestCase):
    def test_volatile_old_excluded_structural_preserved(self):
        records = [row("a", "20220803"), row("b", "20260617")]
        before = analyze_records(records, as_of=date(2026, 9, 20), apply_freshness=False)
        after = analyze_records(records, as_of=date(2026, 9, 20))
        for dimension in ("green", "maintenance", "facilities"):
            self.assertEqual(before["dimensions"][dimension]["independent_valid_count"], 2)
            m = after["dimensions"][dimension]
            self.assertEqual(m["independent_valid_count"], 1)
            self.assertEqual(m["label"], "정보 부족")
            self.assertIn("현재 판단하기에는 근거가 부족", m["insufficiency_reason"])
            self.assertEqual(m["recent_valid_evidence_count"], 1)
            self.assertEqual(m["latest_evidence_date"], "2026-06-17")
        for dimension in ("fairway", "difficulty"):
            self.assertEqual(after["dimensions"][dimension]["independent_valid_count"], 2)
        self.assertEqual(after["stats"]["over_24_months_count"], 1)
        self.assertEqual(after["courses"]["남코스"]["dimensions"]["green"]["independent_valid_count"], 1)

    def test_old_only_never_current_dominance(self):
        result = analyze_records([row(str(i), "20220803") for i in range(8)], as_of=date(2026, 9, 20))
        m = result["dimensions"]["green"]
        self.assertEqual(m["counts"]["fast"], 0)
        self.assertEqual(m["historical_counts"]["fast"], 8)
        self.assertEqual(m["label"], "정보 부족")
        self.assertIsNone(m["latest_evidence_date"])

    def test_cutoff_inclusive_leap_and_bad_dates(self):
        self.assertEqual(freshness_dates(date(2024, 2, 29))[1], date(2022, 2, 28))
        records = [row("a", "20240920"), row("b", "20240919"), row("c", ""),
                   row("d", "20260230"), row("e", "20260921")]
        result = analyze_records(records, as_of=date(2026, 9, 20))
        self.assertEqual(result["dimensions"]["green"]["counts"]["fast"], 1)
        self.assertEqual(result["stats"]["unknown_date_count"], 3)
        self.assertEqual(result["stats"]["over_24_months_count"], 1)

    def test_same_author_and_duplicates_still_conservative(self):
        records = [row("a", "20260801"), row("a", "20260801"), row("a", "20260801") | {"url":"https://blog.naver.com/a/54321"}]
        m = analyze_records(records, as_of=date(2026, 9, 20))["dimensions"]["green"]
        self.assertEqual(m["recent_valid_evidence_count"], 2)
        self.assertEqual(m["recent_independent_count"], 1)
        self.assertEqual(m["label"], "정보 부족")

    def test_migrate_session_with_no_requests_or_writes(self):
        state = new_expression_session()
        state["records"] = [row("a", "20220803")]
        state["result"] = analyze_records(state["records"], apply_freshness=False)
        state["result"]["rule_version"] = "expressions-5b-v1"
        session = {"golf_expression_session": state}
        with patch("requests.sessions.Session.request", side_effect=AssertionError("No request")), patch("builtins.open", side_effect=AssertionError("No write")):
            migrated = get_expression_session(session)
        self.assertEqual(migrated["naver_calls"], 0)
        self.assertEqual(migrated["result"]["dimensions"]["green"]["counts"]["fast"], 0)


if __name__ == "__main__":
    unittest.main()

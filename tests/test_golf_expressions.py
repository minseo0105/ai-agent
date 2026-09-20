"""Synthetic fixtures only: no live results or credentials are persisted."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.golf_api import AUTH_HEADERS, GolfAPIError
from services.golf_expressions import (
    analyze_records, detect_expressions, get_expression_session,
    new_expression_session, run_expression_pilot,
)

KEYS = {key: "synthetic" for key in AUTH_HEADERS}
CLUB = {"id": "lakeside", "name": "레이크사이드CC"}


def row(description, author="a", post="100", title="레이크사이드CC 라운딩 후기"):
    return {"title": title, "description": description,
            "url": f"https://blog.naver.com/{author}/{post}",
            "published_at": "20260101", "query": "synthetic"}


def collection(records):
    return {"records": records, "raw_result_count": len(records),
            "queries": [{"provider_total": 200, "http_status": 200}]}


class ExpressionTests(unittest.TestCase):
    def directions(self, text, dimension):
        return {o["classification"] for o in detect_expressions("레이크사이드CC", text)
                if o["dimension"] == dimension} - {"uncertain"}

    def test_html_and_original_link(self):
        r = row("<b>페어웨이</b>가 넓다 &amp; 좋다")
        ev = analyze_records([r])["evidence"][0]
        self.assertNotIn("<b>", ev["description"])
        self.assertIn("&", ev["description"])
        self.assertEqual(ev["link"], r["url"])

    def test_url_dedup_and_author_independence(self):
        r = row("페어웨이가 넓다")
        mobile = dict(r, url="https://m.blog.naver.com/a/100")
        view = dict(r, url="https://blog.naver.com/PostView.naver?blogId=a&logNo=100")
        result = analyze_records([r, r, mobile, view, row("페어웨이가 넓다", post="101")])
        self.assertEqual(result["stats"]["duplicate_count"], 3)
        metric = result["dimensions"]["fairway"]
        self.assertEqual(metric["counts"]["wide"], 2)
        self.assertEqual(metric["independent_valid_count"], 1)
        self.assertEqual(metric["label"], "정보 부족")

    def test_irrelevant_promo_and_ambiguous(self):
        rows = [row("레이크사이드와 달리 페어웨이가 넓다", title="남서울CC 라운딩 후기"),
                row("페어웨이가 넓다", "b", title="레이크사이드CC 근처 맛집"),
                row("회원권 매매 상담. 코스가 쉽다", "c"),
                row("이벤트 소개. 코스가 쉽다", "d")]
        result = analyze_records(rows)
        self.assertEqual(result["stats"]["irrelevant_count"], 2)
        self.assertEqual(result["stats"]["promotional_count"], 1)
        self.assertEqual(result["stats"]["uncertain_document_count"], 1)
        self.assertEqual(result["dimensions"]["difficulty"]["counts"]["easy"], 0)

    def test_place_before_target_is_not_another_club(self):
        for title in ("용인 레이크사이드CC 라운딩 후기", "가을골프의 정수 레이크사이드cc", "용인 레이크 사이드 CC 남코스 라운딩 후기"):
            self.assertEqual(analyze_records([row("페어웨이가 넓다", title=title)])["evidence"][0]["classification"], "relevant")

    def test_foreign_names_equipment_and_hashtags(self):
        self.assertEqual(analyze_records([row("관리가 잘 되었다", title="태국 로얄 레이크사이드CC 라운딩 후기")])["evidence"][0]["classification"], "irrelevant")
        self.assertEqual(analyze_records([row("코스가 어렵다", title="레이크사이드CC 웨지 사용 후기")])["evidence"][0]["classification"], "uncertain")
        self.assertFalse(self.directions("#관리가잘된", "maintenance"))
        self.assertFalse(self.directions("그린이 빠른가요?", "green"))
        self.assertFalse(self.directions("관리가 잘 안되어 있다", "maintenance"))

    def test_non_golf_context(self):
        for text in ("예약이 어렵다", "예약하기 어렵다", "찾기 어렵다"):
            self.assertFalse(self.directions(text, "difficulty"))
        for text in ("주차장이 넓다", "클럽하우스가 넓다"):
            self.assertFalse(self.directions(text, "fairway"))
        for text in ("경기 진행이 빠르다", "진행 속도가 빠르다", "진행이 빨라서 좋았다"):
            self.assertFalse(self.directions(text, "green"))

    def test_subject_and_contrast(self):
        self.assertEqual(self.directions("그린이 빠르다", "green"), {"fast"})
        self.assertEqual(self.directions("그린은 빨랐지만 경기 진행은 느렸다", "green"), {"fast"})
        self.assertEqual(self.directions("페어웨이가 넓어서 티샷 부담이 적었다", "fairway"), {"wide"})
        self.assertEqual(self.directions("예약하기 어려웠지만 코스 자체는 무난했다", "difficulty"), {"easy"})
        self.assertEqual(self.directions("그린 관리가 좋다", "maintenance"), {"positive"})
        self.assertFalse(self.directions("그린 관리가 좋다", "green"))
        self.assertEqual(self.directions("클럽하우스가 깔끔하다", "facilities"), {"positive"})

    def test_negation_uncertain(self):
        for text, dimension in (("페어웨이가 넓지 않았다", "fairway"),
                                ("그린이 빠르지 않다", "green"),
                                ("시설이 좋지 않다", "facilities"),
                                ("코스가 어렵지 않다", "difficulty")):
            self.assertFalse(self.directions(text, dimension))

    def test_threshold_conflict_and_repetition(self):
        result = analyze_records([row("페어웨이가 넓다. 페어웨이가 넓다")])
        self.assertEqual(result["dimensions"]["fairway"]["label"], "정보 부족")
        self.assertEqual(result["dimensions"]["fairway"]["counts"]["wide"], 1)
        rows = [row("페어웨이가 넓다", str(i)) for i in range(2)]
        self.assertIn("표본 적음", analyze_records(rows)["dimensions"]["fairway"]["label"])
        rows += [row("페어웨이가 좁다", str(i)) for i in range(2, 4)]
        self.assertEqual(analyze_records(rows)["dimensions"]["fairway"]["label"], "평가가 엇갈림")
        rows += [row("페어웨이가 넓다", str(i)) for i in range(4, 10)]
        self.assertIn("많이 확인됨", analyze_records(rows)["dimensions"]["fairway"]["label"])

    def test_courses(self):
        rows = [row("동코스는 페어웨이가 넓다", str(i)) for i in range(2)]
        rows += [row("남코스는 페어웨이가 좁다", "c"),
                 row("동코스 남코스 페어웨이가 넓다", "d")]
        result = analyze_records(rows)
        self.assertEqual(result["courses"]["동코스"]["dimensions"]["fairway"]["independent_valid_count"], 2)
        self.assertEqual(result["courses"]["남코스"]["label"], "코스별 정보 부족")

    def test_session_only_no_llm_and_budget(self):
        a, b = {}, {}
        state = get_expression_session(a)
        collector = Mock(return_value=collection([]))
        with patch("builtins.open", side_effect=AssertionError("No persistence")), \
             patch("requests.sessions.Session.request", side_effect=AssertionError("No LLM/network")):
            run_expression_pilot(CLUB, KEYS, state, collector=collector)
        self.assertEqual(collector.call_count, 6)
        self.assertEqual(state["naver_calls"], 6)
        self.assertEqual(state["result"]["external_llm_calls"], 0)
        self.assertIsNone(get_expression_session(b)["result"])
        self.assertTrue(all(c.kwargs["display"] == 100 for c in collector.call_args_list))
        with self.assertRaises(GolfAPIError):
            run_expression_pilot(CLUB, KEYS, state, collector=collector)
        self.assertEqual(collector.call_count, 6)

    def test_sufficient_dimensions_not_searched(self):
        collector = Mock(return_value=collection([row("페어웨이가 넓다", str(i)) for i in range(2)]))
        state = new_expression_session()
        run_expression_pilot(CLUB, KEYS, state, collector=collector)
        self.assertEqual(collector.call_count, 5)
        self.assertFalse(any(a["dimension"] == "fairway" for a in state["attempts"]))

    def test_failures_consume_budget_no_hidden_retry(self):
        collector = Mock(side_effect=GolfAPIError("HTTP 401"))
        state = new_expression_session()
        for _ in range(7):
            with self.assertRaises(GolfAPIError):
                run_expression_pilot(CLUB, KEYS, state, collector=collector)
        self.assertEqual(collector.call_count, 6)
        self.assertFalse(state["busy"])

    def test_page_results_and_rerun_without_requests(self):
        from streamlit.testing.v1 import AppTest
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(str(root / "pages/6_골프장_추천.py"), default_timeout=20)
        app.session_state["authenticated"] = True
        for key, value in KEYS.items():
            app.secrets[key] = value
        sample = [row("코스는 어렵다. 페어웨이가 넓다. 그린이 빠르다. 관리가 좋다. 시설이 좋다", str(i)) for i in range(2)]
        collector = Mock(return_value=collection(sample))

        def pilot(club, secrets, state, **kwargs):
            self.assertNotIn("OPENAI_API_KEY", secrets)
            return run_expression_pilot(club, secrets, state, collector=collector, **kwargs)

        with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")), \
             patch("services.golf_expressions.run_expression_pilot", pilot):
            app.run()
            self.assertEqual(collector.call_count, 0)
            app.button(key="golf_search_reviews").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(collector.call_count, 1)
            self.assertEqual(sum(e.label == "근거 후기 보기" for e in app.expander), 5)
            self.assertEqual(app.button(key="golf_search_reviews").label, "최신 후기 다시 분석")
            app.run()
            self.assertEqual(collector.call_count, 1)
            app.button(key="golf_search_reviews").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(collector.call_count, 2)
            self.assertEqual(app.session_state["golf_expression_session"]["total_naver_calls"], 2)


if __name__ == "__main__":
    unittest.main()

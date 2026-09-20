"""Synthetic-only tests; no real keys, requests, snippets or analysis saved to disk."""
import unittest
from unittest.mock import Mock, patch
import requests
from services.golf_api import AUTH_HEADERS, GolfAPIError, collect_reviews, hub_headers, secret_status
from services.golf_analysis import ASPECTS, analyze_pilot, build_analysis, next_query, prepare_candidates, search_pilot
from services.golf_cache import clear_experiment, get_experiment, new_experiment
from services.golf_catalog import ROOT, load_catalog

CLUB = {"id": "lakeside", "name": "레이크사이드CC", "aliases": ["레이크사이드"]}
KEYS = {"NAVER_API_KEY_ID": "synthetic-id", "NAVER_API_KEY": "synthetic-secret", "OPENAI_API_KEY": "synthetic-ai"}


def row(author="a", number="123", description=None):
    titles = {"a": "레이크사이드CC에서 직접 다녀온 동코스 기록", "b": "용인 레이크사이드CC 주말 가족 라운딩", "c": "레이크사이드CC 필드에서 보낸 여름 하루"}
    return {"url": f"https://blog.naver.com/{author}/{number}", "title": titles.get(author, f"레이크사이드CC 기록 {author}"),
            "description": description or "레이크사이드CC에서 라운딩을 했습니다. 동코스 페어웨이가 넓어서 편했습니다.",
            "published_at": "20260901", "query": "레이크사이드CC 라운딩 후기", "kind": "blog", "provider": "naver_api_hub"}


def collection(rows):
    return {"records": rows, "raw_result_count": len(rows), "queries": [], "collected_at": "2026-09-19T00:00:00+00:00"}


def extraction(records):
    return {"documents": [{"id": r["id"], "eligible": True, "experience_quote": r["description"].split(". ")[0],
            "reason": "", "observations": [{"aspect": "fairway", "value": "narrow" if "좁아서" in r["description"] else "wide",
            "quote": r["description"].split(". ")[-1], "course": "동코스"}]} for r in records]}


def make_result(rows=None, change=None):
    rows = rows or [row(), row("b", description="레이크사이드CC에 다녀왔습니다. 동코스 페어웨이가 넓어서 공략하기 좋았습니다.")]
    candidates, excluded, unique = prepare_candidates(CLUB, rows)
    output = extraction(candidates)
    if change:
        change(output["documents"])
    return build_analysis(CLUB, collection(rows), candidates, excluded, unique, output, "synthetic")


class GolfTests(unittest.TestCase):
    def test_public_catalog_unchanged(self):
        self.assertEqual(len(load_catalog()), 10)
        self.assertEqual(load_catalog()[0]["holes"], 54)

    def test_exact_header_alias_pair(self):
        secrets = {AUTH_HEADERS[0]: "id", AUTH_HEADERS[1]: "secret"}
        self.assertEqual(hub_headers(secrets), secrets)
        self.assertTrue(secret_status(secrets)["NAVER_API_KEY_ID"])

    def test_single_key_never_guesses_id(self):
        with self.assertRaises(GolfAPIError):
            hub_headers({"NAVER_API_KEY": "one-string"})

    def test_no_legacy_fallback(self):
        with self.assertRaises(GolfAPIError):
            hub_headers({"NAVER_CLIENT_ID": "old", "NAVER_CLIENT_SECRET": "old"})

    def test_one_request_100_results_schema_and_auth(self):
        client = Mock()
        client.get.return_value.status_code = 200
        client.get.return_value.json.return_value = {"total": 9999, "items": [{"title": "<b>후기</b>", "link": "https://example.com", "description": "요약", "bloggername": "A", "bloggerlink": "https://example.com/a", "postdate": "20260919"}]}
        result = collect_reviews(CLUB, KEYS, session=client)
        self.assertEqual(client.get.call_count, 1)
        args, kw = client.get.call_args
        self.assertEqual(args[0], "https://naverapihub.apigw.ntruss.com/search/v1/blog")
        self.assertEqual(kw["params"]["display"], 100)
        self.assertEqual(kw["params"]["query"], "레이크사이드CC 라운딩 후기")
        self.assertEqual(set(kw["headers"]), set(AUTH_HEADERS))
        self.assertFalse(kw["allow_redirects"])
        self.assertEqual(result["raw_result_count"], 1)
        self.assertEqual(result["queries"][0]["provider_total"], 9999)

    def test_all_http_failures_and_timeout_are_sanitized(self):
        for code in (400, 401, 403, 429, 500):
            with self.subTest(code=code):
                client = Mock()
                client.get.return_value.status_code = code
                client.get.return_value.text = "credential-leak"
                with self.assertRaises(GolfAPIError) as error:
                    collect_reviews(CLUB, KEYS, session=client)
                self.assertNotIn("credential-leak", str(error.exception))
                self.assertIn(str(code), str(error.exception))
                self.assertEqual(client.get.call_count, 1)
        client.get.side_effect = requests.Timeout("credential-leak")
        with self.assertRaises(GolfAPIError) as error:
            collect_reviews(CLUB, KEYS, session=client)
        self.assertNotIn("credential-leak", str(error.exception))

    def test_missing_keys_make_zero_requests(self):
        client = Mock()
        with self.assertRaises(GolfAPIError):
            collect_reviews(CLUB, {}, session=client)
        client.get.assert_not_called()

    def test_empty_results_are_valid(self):
        client = Mock()
        client.get.return_value.status_code = 200
        client.get.return_value.json.return_value = {"total": 0, "items": []}
        self.assertEqual(collect_reviews(CLUB, KEYS, session=client)["records"], [])

    def test_url_and_title_dedup(self):
        second = row()
        second["url"] = "https://m.blog.naver.com/PostView.naver?blogId=a&logNo=123"
        third = row("b", description="레이크사이드CC에 다녀왔습니다. 좋은 시설이 눈에 들어왔습니다.")
        third["title"] = row()["title"]
        candidates, excluded, _ = prepare_candidates(CLUB, [row(), second, third])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["id"], "E001")
        self.assertEqual(sum(e["category"] == "duplicate" for e in excluded), 2)

    def test_ad_in_other_snippet_excludes_entire_document(self):
        candidates, excluded, _ = prepare_candidates(CLUB, [row(), row(description="레이크사이드CC 라운딩 예약문의 #광고 특가 예약 상담")])
        self.assertEqual(candidates, [])
        self.assertTrue(any(e["category"] == "advertising" for e in excluded))

    def test_irrelevant_excluded(self):
        data = row()
        data.update(title="다른 골프장 라운딩", description="전혀 다른 골프장에 다녀왔습니다. 페어웨이가 넓습니다.")
        candidates, excluded, _ = prepare_candidates(CLUB, [data])
        self.assertFalse(candidates)
        self.assertEqual(excluded[0]["category"], "irrelevant")

    def test_independent_evidence_minimum(self):
        result = make_result()
        self.assertEqual(result["metrics"]["fairway"]["label"], "넓은 편")
        self.assertEqual(result["metrics"]["fairway"]["evidence_count"], 2)
        self.assertTrue(result["experimental"])
        self.assertEqual(set(result["metrics"]), set(ASPECTS))
        self.assertEqual(make_result([row()])["metrics"]["fairway"]["label"], "정보 부족")

    def test_same_author_not_independent(self):
        second = row("a", "456", "레이크사이드CC에 다녀왔습니다. 동코스 페어웨이가 넓어서 공략하기 좋았습니다.")
        second["title"] = "레이크사이드CC 새벽 티샷과 워터해저드 공략"
        self.assertEqual(make_result([row(), second])["metrics"]["fairway"]["evidence_count"], 1)

    def test_conflict(self):
        result = make_result([row(), row("b", description="레이크사이드CC에 다녀왔습니다. 동코스 페어웨이는 좁아서 티샷이 불편했습니다.")])
        self.assertEqual(result["metrics"]["fairway"]["label"], "평가가 엇갈림")

    def test_fabrication_and_course_mismatch_rejected(self):
        for change in ({"quote": "없는 페어웨이 인용문"}, {"course": "남코스"}):
            result = make_result(change=lambda docs: [d["observations"][0].update(change) for d in docs])
            self.assertEqual(result["review_count"], 0)
        with self.assertRaises(GolfAPIError):
            make_result(change=lambda docs: docs[0].update(id="invented"))

    def test_six_call_budget_and_no_automatic_ai(self):
        state = new_experiment()
        collector = Mock(return_value=collection([]))
        extractor = Mock(side_effect=AssertionError("empty data must not call AI"))
        for _ in range(6):
            search_pilot(CLUB, KEYS, state, collector=collector)
            analyze_pilot(CLUB, KEYS, state, extractor=extractor)
        self.assertIsNone(next_query(state))
        self.assertEqual(collector.call_count, 6)
        self.assertEqual(state["openai_calls"], 0)
        with self.assertRaises(GolfAPIError):
            search_pilot(CLUB, KEYS, state, collector=collector)
        clear_experiment(state)
        self.assertEqual(state["naver_calls"], 6)
        self.assertIsNone(next_query(state))

    def test_sufficient_dimension_not_searched(self):
        state = new_experiment()
        state.update(collection=collection([]), analysis=make_result(), analysis_current=True)
        queries = []
        while next_query(state):
            query = next_query(state)
            queries.append(query)
            state["attempts"].append({"query": query})
            state["naver_calls"] += 1
        self.assertTrue(queries)
        self.assertFalse(any("페어웨이" in q for q in queries))

    def test_failed_attempts_consume_budget_and_keep_search(self):
        state = new_experiment()
        fail = Mock(side_effect=GolfAPIError("timeout"))
        for _ in range(6):
            with self.assertRaises(GolfAPIError):
                search_pilot(CLUB, KEYS, state, collector=fail)
        self.assertEqual(fail.call_count, 6)
        self.assertFalse(state["busy"])
        state = new_experiment()
        search_pilot(CLUB, KEYS, state, collector=Mock(return_value=collection([row()])))
        with self.assertRaises(GolfAPIError):
            analyze_pilot(CLUB, KEYS, state, extractor=fail)
        self.assertTrue(state["collection"]["records"])
        self.assertIsNone(state["analysis"])

    def test_session_isolation_no_file_writes(self):
        a, b = {}, {}
        state = get_experiment(a)
        with patch("builtins.open", side_effect=AssertionError("No files")):
            search_pilot(CLUB, KEYS, state, collector=Mock(return_value=collection([row()])))
            analyze_pilot(CLUB, KEYS, state, extractor=lambda c, r, s, j: (extraction(r), "synthetic"))
        self.assertIsNone(get_experiment(b)["collection"])
        self.assertIsNotNone(state["analysis"])
        count = state["openai_calls"]
        analyze_pilot(CLUB, KEYS, state)
        self.assertEqual(state["openai_calls"], count)

    def test_page_missing_keys_offline_and_search_without_ai(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / "pages/6_골프장_추천.py"), default_timeout=15)
        app.session_state["authenticated"] = True
        for key in (*KEYS, *AUTH_HEADERS):
            app.secrets[key] = ""
        with patch("requests.sessions.Session.request", side_effect=AssertionError("unexpected network")):
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key="golf_search_reviews").disabled)
            app.text_input(key="golf_query_input").set_value("남서울")
            next(b for b in app.button if b.label == "골프장 찾기").click().run()
            self.assertFalse(app.exception)
        for key, value in KEYS.items():
            app.secrets[key] = value if key != "OPENAI_API_KEY" else ""
        app.session_state["golf_query"] = ""
        app.session_state["golf_selected_id"] = "lakeside"
        app.run()
        self.assertFalse(app.button(key="golf_search_reviews").disabled)
        self.assertFalse(any(b.key == "golf_analyze" for b in app.button))


if __name__ == "__main__":
    unittest.main()

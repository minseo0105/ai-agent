"""생활 속 종목 찾기 오프라인 테스트. 외부 API·AI를 부르지 않는다(가짜 응답 사용).

실행: python -B -m unittest tests.test_stockon_lifemap -v
"""

import json
import time
import unittest
from datetime import datetime
from unittest import mock

from services.stockon import ai, lifemap, news, store
from services.stockon.public_data import KST
from tests.test_stockon import TempStore

STOCKS = {
    "004370": {"name": "농심", "market": "KOSPI", "close": 400000, "change": 4000, "rate": 1.01, "cap": 2e12, "value": 1e10},
    "007310": {"name": "오뚜기", "market": "KOSPI", "close": 380000, "change": -3800, "rate": -0.99, "cap": 1.4e12, "value": 5e9},
    "003230": {"name": "삼양식품", "market": "KOSPI", "close": 700000, "change": 0, "rate": 0.0, "cap": 5e12, "value": 3e10},
    "097950": {"name": "CJ제일제당", "market": "KOSPI", "close": 250000, "change": 1000, "rate": 0.4, "cap": 4e12, "value": 2e10},
    "000120": {"name": "CJ대한통운", "market": "KOSPI", "close": 90000, "change": -900, "rate": -1.0, "cap": 2e12, "value": 1e10},
    "139480": {"name": "이마트", "market": "KOSPI", "close": 70000, "change": 700, "rate": 1.0, "cap": 2e12, "value": 1e10},
    "282330": {"name": "BGF리테일", "market": "KOSPI", "close": 110000, "change": -1100, "rate": -1.0, "cap": 2e12, "value": 1e10},
}

CHAIN = {"stages": [
    {"key": "retail", "detail": "편의점·마트", "companies": [
        {"name": "BGF리테일", "relevance": "중", "reason": "편의점 CU에서 라면을 판다"},
        {"name": "이마트", "relevance": "약", "reason": "대형마트에서 라면을 판다"}]},
    {"key": "making", "detail": "봉지·컵라면", "companies": [
        {"name": "농심", "relevance": "강", "reason": "신라면을 만든다"},
        {"name": "없는식품", "relevance": "강", "reason": "라면을 만든다"},
        {"name": "오뚜기", "relevance": "강", "reason": "진라면을 만든다"},
        {"name": "삼양식품", "relevance": "강", "reason": "불닭볶음면을 만든다"}]},
    {"key": "material", "detail": "밀가루", "companies": [
        {"name": "CJ 제일제당", "relevance": "중", "reason": "밀가루를 만든다"},
        {"name": "농심", "relevance": "강", "reason": "중복 회사"}]},
    {"key": "logistics", "detail": "택배", "companies": [
        {"name": "CJ대한통운", "relevance": "약", "reason": "라면 수혜가 기대된다"}]},
    {"key": "unknown", "detail": "", "companies": [{"name": "농심", "relevance": "강", "reason": "x"}]},
]}

HEADLINES = [{"title": f"기사 {i}", "url": f"https://news.example/{i}", "press": "news.example",
              "pub": datetime.now(KST).isoformat(), "snippet": "요약"} for i in range(1, 9)]


class FakePool:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))

    def run_all(self):
        calls, self.calls = self.calls, []
        for fn, args in calls:
            fn(*args)


class LifemapBase(TempStore):
    def setUp(self):
        super().setUp()
        store.write("stocks", {"as_of": "20261027", "stocks": STOCKS})
        lifemap._dir_cache.update(mtime=None)
        lifemap._jobs.clear()
        lifemap._sessions.clear()
        lifemap._live_count.clear()
        lifemap._examples_cache["value"] = {
            "topics": [{"name": "예시토픽", "summary": "예시", "articles": [], "map": {"word": "예시토픽", "stages": [
                {"key": "making", "label": "제조", "detail": "", "companies": [
                    {"code": "004370", "name": "농심", "relevance": "강", "reason": "라면을 만든다"}]}], "ai": True}}],
            "words": {"라면": {"word": "라면", "stages": [{"key": "making", "label": "제조", "detail": "", "companies": [
                {"code": "007310", "name": "오뚜기", "relevance": "강", "reason": "라면을 만든다"}]}], "ai": True}},
        }
        self.pool = FakePool()
        for p in (mock.patch.object(lifemap, "_pool", self.pool), mock.patch.object(ai, "available", return_value=True)):
            p.start()
            self.patches.append(p)

    def tearDown(self):
        lifemap._examples_cache["value"] = None
        super().tearDown()


class ValidateTest(LifemapBase):
    def test_removes_unlisted_companies_and_keeps_order(self):
        stocks, index, _ = lifemap.directory()
        stages, removed = lifemap.validate_chain(CHAIN, index, stocks)
        self.assertEqual([s["key"] for s in stages], ["material", "making", "retail"])  # 정해진 순서, 물류는 금지 표현으로 비어서 빠짐
        self.assertEqual(removed, ["없는식품"])
        making = stages[1]["companies"]
        self.assertEqual([c["name"] for c in making], ["농심", "오뚜기"])  # 단계당 2곳, 없는 회사 제거
        self.assertEqual(making[0]["code"], "004370")  # 코드는 목록에서 붙인다
        self.assertEqual(stages[0]["companies"][0]["name"], "CJ제일제당")  # 띄어쓰기 달라도 목록 이름으로
        self.assertEqual(len(stages[0]["companies"]), 1)  # 다른 단계에 이미 나온 농심은 빠짐
        codes = [c["code"] for s in stages for c in s["companies"]]
        self.assertEqual(len(codes), len(set(codes)))

    def test_retries_once_when_companies_were_removed(self):
        bad = {"stages": [{"key": "making", "detail": "", "companies": [{"name": "가짜", "relevance": "강", "reason": "라면"}]}]}
        with mock.patch.object(lifemap, "_ask", side_effect=[bad, CHAIN]) as ask:
            m = lifemap.build_chain("라면")
        self.assertEqual(ask.call_count, 2)
        self.assertIn("가짜", ask.call_args_list[1].args[2])  # 다시 부를 때 지운 이름을 알려 준다
        self.assertEqual(m["model"], "claude-sonnet-5-5")
        self.assertGreaterEqual(sum(len(s["companies"]) for s in m["stages"]), 3)

    def test_banned_words(self):
        for text in ("라면 수혜주", "매수 추천", "주가 상승이 기대된다", "유망한 회사"):
            self.assertTrue(lifemap._unsafe(text), text)
        self.assertFalse(lifemap._unsafe("신라면을 만든다"))
        self.assertTrue(lifemap.check_word("급등주"))
        self.assertTrue(lifemap.check_word("a" * 13))
        self.assertTrue(lifemap.check_word("<script>"))
        self.assertEqual(lifemap.check_word("붕어빵"), "")


class TopicsTest(LifemapBase):
    def test_pick_topics_validates_article_numbers(self):
        raw = {"topics": [
            {"name": "독감", "summary": "독감 환자가 늘었다", "articles": [1, 2]},
            {"name": "김장", "summary": "배추값이 올랐다", "articles": [3, 99]},  # 없는 번호 → 근거 1개라 제외
            {"name": "독감", "summary": "중복", "articles": [4, 5]},
            {"name": "커피", "summary": "커피 수혜 기대", "articles": [6, 7]},  # 금지 표현
            {"name": "버스", "summary": "버스 요금이 바뀐다", "articles": [8, 8, 7]},
            {"name": "달걀", "summary": "달걀값이 올랐다", "articles": [1, 6]},  # 독감과 근거 기사(1)가 겹침 → 같은 뉴스라 제외
        ]}
        with mock.patch.object(lifemap, "_ask", return_value=raw) as ask:
            topics = lifemap.pick_topics(HEADLINES)
        self.assertEqual(ask.call_args.args[0], "claude-haiku-5-5")
        self.assertEqual([t["name"] for t in topics], ["독감", "버스"])
        self.assertEqual([a["url"] for a in topics[1]["articles"]], ["https://news.example/8", "https://news.example/7"])

    def test_daily_falls_back_to_examples_when_ai_fails(self):
        with mock.patch.object(lifemap, "collect_headlines", return_value=HEADLINES), \
                mock.patch.object(lifemap, "_ask", side_effect=RuntimeError("down")):
            data = lifemap.run_daily()
        self.assertEqual(data["fresh"], 0)
        self.assertEqual([t["name"] for t in data["topics"]], ["예시토픽"])
        self.assertTrue(data["topics"][0]["carried"])
        view = lifemap.overview()
        self.assertEqual(len(view["topics"]), 1)
        self.assertIn("라면", view["chip_maps"])  # 칩도 예시로 채워진다(빈 화면 없음)

    def test_daily_generates_topics_and_maps(self):
        topic_raw = {"topics": [{"name": n, "summary": f"{n} 소식", "articles": [i, i + 1]}
                                for i, n in ((1, "라면"), (3, "독감"), (5, "김장"))]}

        def fake_ask(model, *args, **kw):
            return topic_raw if model == lifemap.TOPIC_MODEL else CHAIN

        with mock.patch.object(lifemap, "collect_headlines", return_value=HEADLINES), \
                mock.patch.object(lifemap, "_ask", side_effect=fake_ask):
            data = lifemap.run_daily()
        self.assertEqual(data["fresh"], 3)
        self.assertEqual(len(data["topics"][0]["articles"]), 2)
        st = store.read("lifemap_status")
        self.assertTrue(st["ok"])

    def test_daily_due_once_per_day(self):
        morning = datetime(2026, 11, 17, 7, 5, tzinfo=KST)
        self.assertFalse(lifemap.daily_due(morning.replace(hour=6)))
        self.assertTrue(lifemap.daily_due(morning))
        store.write("lifemap", {"day": "2026-11-17", "fresh": 3})
        self.assertFalse(lifemap.daily_due(morning))

    def test_collector_starts_daily_in_background(self):
        with mock.patch.object(news, "configured", return_value=True), \
                mock.patch.object(lifemap, "daily_due", return_value=True), \
                mock.patch.object(lifemap.threading, "Thread") as thread:
            self.assertTrue(lifemap.maybe_run_daily(datetime(2026, 11, 17, 7, 5, tzinfo=KST)))
            self.assertFalse(lifemap.maybe_run_daily(datetime(2026, 11, 17, 7, 6, tzinfo=KST)))  # 돌고 있으면 또 시작하지 않음
        thread.return_value.start.assert_called_once()
        lifemap._daily_lock.release()
        self.assertEqual(store.read("lifemap_status")["tries"], 1)


class ReadTest(LifemapBase):
    def test_prices_attached_at_read_time(self):
        store.write("lifemap_chips", {"라면": {"word": "라면", "stages": [{"key": "making", "label": "제조", "detail": "", "companies": [
            {"code": "004370", "name": "농심", "relevance": "강", "reason": "만든다"},
            {"code": "000000", "name": "상폐", "relevance": "강", "reason": "만든다"}]}], "ai": True, "removed": ["x"]}})
        view = lifemap.overview()
        c = view["chip_maps"]["라면"]["stages"][0]["companies"]
        self.assertEqual([x["name"] for x in c], ["농심"])  # 목록에서 빠진 회사는 숨김
        self.assertEqual(c[0]["rate"], 1.01)
        self.assertNotIn("removed", view["chip_maps"]["라면"])
        self.assertEqual(view["chip_maps"]["라면"]["price_as_of"], "20261027")

    def test_overview_never_calls_ai(self):
        with mock.patch.object(lifemap, "_ask", side_effect=AssertionError("AI 호출")), \
                mock.patch.object(news, "search", side_effect=AssertionError("뉴스 호출")):
            lifemap.overview()
            lifemap.word_status("라면")


class LiveQueueTest(LifemapBase):
    def test_cached_word_returns_immediately(self):
        store.write("lifemap_words", {"붕어빵": {"word": "붕어빵", "stages": [], "ai": True}})
        r = lifemap.request_word(" 붕어빵 ", "s1")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(self.pool.calls, [])

    def test_queue_dedup_and_result(self):
        r1 = lifemap.request_word("붕어빵", "s1")
        r2 = lifemap.request_word("붕어빵", "s2")  # 다른 사람이 같은 단어 → 같은 작업에 묶임
        self.assertEqual((r1["status"], r2["status"]), ("queued", "queued"))
        self.assertEqual(len(self.pool.calls), 1)
        self.assertEqual(lifemap.word_status("붕어빵")["status"], "queued")
        with mock.patch.object(lifemap, "_ask", return_value=CHAIN):
            self.pool.run_all()
        done = lifemap.word_status("붕어빵")
        self.assertEqual(done["status"], "ready")
        self.assertEqual(done["map"]["stages"][1]["companies"][0]["rate"], 1.01)
        self.assertEqual(store.read("lifemap_usage_live"), None)  # _ask를 가짜로 바꿔서 기록 없음(실제 호출만 기록)

    def test_positions(self):
        for w in ("가", "나", "다"):
            lifemap.request_word(w, w)
        self.assertEqual(lifemap.word_status("다")["position"], 2)
        lifemap._jobs["가"]["state"] = "running"
        self.assertEqual(lifemap.word_status("다")["position"], 1)

    def test_failure_shows_example(self):
        lifemap.request_word("붕어빵", "s1")
        with mock.patch.object(lifemap, "_ask", side_effect=RuntimeError("timeout")):
            self.pool.run_all()
        r = lifemap.word_status("붕어빵")
        self.assertEqual(r["status"], "failed")
        self.assertTrue(r["map"]["example"])
        self.assertTrue(r["map"]["stages"])

    def test_limits(self):
        for i in range(lifemap.LIVE_PER_SESSION):
            self.assertEqual(lifemap.request_word(f"단어{i}", "same")["status"], "queued")
        self.assertEqual(lifemap.request_word("단어x", "same")["status"], "limited")
        for i in range(lifemap.LIVE_QUEUE_MAX - lifemap.LIVE_PER_SESSION):
            lifemap.request_word(f"다른{i}", f"s{i}")
        busy = lifemap.request_word("넘침", "new")
        self.assertEqual(busy["status"], "busy")
        self.assertTrue(busy["map"]["stages"])  # 넘쳐도 예시로 화면을 채운다
        self.assertEqual(lifemap.request_word("<b>", "new")["status"], "invalid")

    def test_daily_cap(self):
        store.write("lifemap_live_count", {"day": datetime.now(KST).strftime("%Y-%m-%d"), "n": lifemap.LIVE_DAILY_MAX})
        r = lifemap.request_word("붕어빵", "s1")
        self.assertEqual(r["status"], "daily_limit")
        self.assertEqual(self.pool.calls, [])

    def test_ai_unavailable(self):
        with mock.patch.object(ai, "available", return_value=False):
            r = lifemap.request_word("붕어빵", "s1")
        self.assertEqual(r["status"], "unavailable")
        self.assertTrue(r["map"]["example"])


class ThirtyPeopleTest(LifemapBase):
    """시연 기준: 30명이 동시에 서로 다른 새 단어를 누르고, 동시에 화면을 읽는다."""

    def test_concurrency_cap_queue_and_fast_reads(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor

        real_pool = ThreadPoolExecutor(max_workers=lifemap.LIVE_CONCURRENCY)
        lock, state = threading.Lock(), {"now": 0, "max": 0}

        def slow_ask(*args, **kw):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            time.sleep(0.15)
            with lock:
                state["now"] -= 1
            return CHAIN

        with mock.patch.object(lifemap, "_pool", real_pool), mock.patch.object(lifemap, "_ask", side_effect=slow_ask):
            with ThreadPoolExecutor(max_workers=30) as people:
                results = list(people.map(lambda i: lifemap.request_word(f"단어{i:02d}", f"person{i}"), range(30)))
                t0 = time.time()
                list(people.map(lambda i: lifemap.overview(), range(30)))
                read_sec = time.time() - t0
            real_pool.shutdown(wait=True)
        statuses = [r["status"] for r in results]
        self.assertEqual(statuses.count("queued"), lifemap.LIVE_QUEUE_MAX)
        self.assertEqual(statuses.count("busy"), 30 - lifemap.LIVE_QUEUE_MAX)
        self.assertTrue(all(r["map"]["stages"] for r in results if r["status"] == "busy"))  # 넘친 사람도 예시를 본다
        self.assertLessEqual(state["max"], lifemap.LIVE_CONCURRENCY)
        self.assertLess(read_sec, 2.0)
        done = [lifemap.word_status(r["word"])["status"] for r in results if r["status"] == "queued"]
        self.assertEqual(done, ["ready"] * lifemap.LIVE_QUEUE_MAX)


class ApiTest(LifemapBase):
    def _client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        from services import access as ac

        env = mock.patch.dict("os.environ", {"STOCKON_ENABLED": "1", "ADMIN_PASSWORD": "pw-test", "ACCESS_SECRET": "test-secret"})
        site = mock.patch.object(ac, "_read_raw", lambda fresh=False: {"site_mode": "public"})
        for p in (env, site):
            p.start()
            self.patches.append(p)
        return TestClient(app)

    def test_visitor_reads_without_ai_and_word_queues(self):
        client = self._client()
        blocked = AssertionError("outbound call during visitor read")
        with mock.patch.object(lifemap, "_ask", side_effect=blocked), mock.patch("requests.get", side_effect=blocked):
            r = client.get("/api/stock/lifemap")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["chips"], lifemap.CHIPS)
            self.assertTrue(body["topics"])  # 저장된 것이 없어도 예시로 채움
            self.assertEqual(client.get("/api/stock/lifemap/word", params={"w": "라면"}).json()["status"], "ready")
        sid = {"X-Stockon-Session": "abcdef12-3456"}
        r = client.post("/api/stock/lifemap/word", json={"word": "붕어빵"}, headers=sid)
        self.assertEqual(r.json()["status"], "queued")
        self.assertIn("s:abcdef12-3456", lifemap._sessions)
        self.assertEqual(client.get("/api/stock/lifemap/word", params={"w": "붕어빵"}).json()["status"], "queued")
        self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "x" * 21}).status_code, 422)
        self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "<b>"}).json()["status"], "invalid")

    def test_disabled_server(self):
        client = self._client()
        with mock.patch.dict("os.environ", {"STOCKON_ENABLED": ""}):
            self.assertEqual(client.get("/api/stock/lifemap").status_code, 404)
            self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "라면"}).status_code, 404)


class ScreenWordsTest(unittest.TestCase):
    """화면에 보이는 문구(따옴표 안 한글)에 '추천·수혜' 표현이 없어야 한다. 주석은 제외."""

    def test_no_recommendation_words_on_screen(self):
        import re
        from pathlib import Path

        root = Path(lifemap.__file__).resolve().parents[2]
        files = [root / "services/stockon/lifemap.py", *(root / "web/src/components/stock").glob("Life*.tsx"),
                 root / "web/src/components/stock/MindMap.tsx", root / "web/src/components/stock/StockTabs.tsx"]
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                code = re.sub(r"(^\s*(#|//|\*|/\*).*$)|(\{/\*.*?\*/\})", "", line)
                for text in re.findall(r"[\"'`>]([^\"'`<>]*[가-힣][^\"'`<>]*)[\"'`<]", code):
                    if "쓰지 않는다" in line or "금지" in line or "re.compile" in line:
                        continue  # 금지 규칙을 설명하는 문장(AI 지시·문서)
                    self.assertNotRegex(text, r"추천|수혜", f"{f.name}: {text}")


class ExamplesFileTest(unittest.TestCase):
    def test_repo_examples_are_complete_and_safe(self):
        data = json.loads(lifemap.EXAMPLES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data["words"]), sorted(lifemap.CHIPS))
        self.assertEqual(len(data["topics"]), 3)
        maps = list(data["words"].values()) + [t["map"] for t in data["topics"]]
        for m in maps:
            self.assertTrue(m["stages"])
            self.assertLessEqual(len(m["stages"]), 4)
            for st in m["stages"]:
                self.assertIn(st["key"], lifemap.STAGES)
                self.assertLessEqual(len(st["companies"]), 2)
                for c in st["companies"]:
                    self.assertRegex(c["code"], r"^[0-9A-Z]{6}$")
                    self.assertFalse(lifemap._unsafe(c["reason"]), c["reason"])
        for t in data["topics"]:
            self.assertEqual(len(t["articles"]), 2)


if __name__ == "__main__":
    unittest.main()

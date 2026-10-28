"""생활 속 종목 찾기(증시를 움직인 뉴스) 오프라인 테스트. 외부 API·AI를 부르지 않는다(가짜 응답 사용).

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
    "042510": {"name": "라온시큐어", "market": "KOSDAQ", "close": 3000, "change": 460, "rate": 18.1, "cap": 1e11, "value": 9e10},
    "053800": {"name": "안랩", "market": "KOSDAQ", "close": 70000, "change": 6000, "rate": 9.4, "cap": 7e11, "value": 5e10},
    "012450": {"name": "한화에어로스페이스", "market": "KOSPI", "close": 900000, "change": -50000, "rate": -5.3, "cap": 4e13, "value": 8e11},
}


def _mover(code):
    return {"code": code, **STOCKS[code]}


MARKET = {
    "as_of": "20261027",
    "indices": [{"name": "코스피", "series": [{"d": "20261024", "c": 1}, {"d": "20261027", "c": 1}]}],
    "movers": {"up": [_mover("042510"), _mover("053800"), _mover("004370")],
               "down": [_mover("012450"), _mover("007310")],
               "value": [_mover("012450"), _mover("042510")]},
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

SECURITY_CHAIN = {"stages": [
    {"key": "making", "detail": "보안 솔루션", "companies": [
        {"name": "라온시큐어", "relevance": "강", "reason": "모바일 인증 보안 솔루션을 만든다"},
        {"name": "안랩", "relevance": "강", "reason": "백신·보안 솔루션을 만든다"}]},
    {"key": "retail", "detail": "판매", "companies": [{"name": "이마트", "relevance": "약", "reason": "보안 제품을 판다"}]},
]}

ARTICLES = [{"title": f"기사 {i}", "url": f"https://news.example/{i}", "press": "news.example",
             "pub": "2026-10-27T10:00:00+09:00", "snippet": "요약"} for i in range(1, 11)]

EXAMPLE_MAP = {"word": "보안", "stages": [{"key": "making", "label": "제조", "detail": "", "companies": [
    {"code": "053800", "name": "안랩", "relevance": "강", "reason": "보안 솔루션을 만든다", "rate": 9.4, "moved": True}]}],
    "ai": True, "basis_label": "10/24 장 기준"}


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
        store.write("market", MARKET)
        lifemap._dir_cache.update(mtime=None)
        lifemap._jobs.clear()
        lifemap._sessions.clear()
        lifemap._live_count.clear()
        lifemap._examples_cache["value"] = {
            "basis": {"key": "public:20261024", "source": "public", "as_of": "20261024", "label": "10/24 장 기준"},
            "topics": [{"name": "예시토픽", "title": "예시 제목", "impact": "예시 영향", "sector": "예시", "stocks": [],
                        "articles": [], "map": {**EXAMPLE_MAP, "word": "예시토픽"}}],
            "sectors": {"보안": EXAMPLE_MAP},
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

    def test_retries_once_when_companies_were_removed(self):
        bad = {"stages": [{"key": "making", "detail": "", "companies": [{"name": "가짜", "relevance": "강", "reason": "라면"}]}]}
        with mock.patch.object(lifemap, "_ask", side_effect=[bad, CHAIN]) as ask:
            m = lifemap.build_chain("라면", must=["농심(+1.0%)"])
        self.assertEqual(ask.call_count, 2)
        self.assertIn("가짜", ask.call_args_list[1].args[2])  # 다시 부를 때 지운 이름을 알려 준다
        self.assertEqual(ask.call_args_list[0].args[3]["실제로 움직인 종목"], ["농심(+1.0%)"])
        self.assertEqual(m["model"], "claude-sonnet-5-5")

    def test_single_stage_retries_once_for_more_stages(self):
        one = {"stages": [SECURITY_CHAIN["stages"][0]]}
        with mock.patch.object(lifemap, "_ask", side_effect=[one, SECURITY_CHAIN]) as ask:
            m = lifemap.build_chain("보안")
        self.assertEqual(ask.call_count, 2)
        self.assertIn("한 단계뿐", ask.call_args_list[1].args[2])
        self.assertEqual([s["key"] for s in m["stages"]], ["making", "retail"])
        with mock.patch.object(lifemap, "_ask", side_effect=[SECURITY_CHAIN, one]) as ask:
            self.assertEqual(len(lifemap.build_chain("보안")["stages"]), 2)
        self.assertEqual(ask.call_count, 1)  # 한 번에 두 단계·3곳이면 다시 부르지 않음
        with mock.patch.object(lifemap, "_ask", side_effect=[one, {"stages": []}]):
            self.assertEqual(len(lifemap.build_chain("보안")["stages"]), 1)  # 다시 그린 것이 더 적으면 처음 것

    def test_banned_words(self):
        for text in ("라면 수혜주", "매수 추천", "주가 상승이 기대된다", "유망한 회사", "보안 테마주", "앞으로 급등할 것"):
            self.assertTrue(lifemap._unsafe(text), text)
        for text in ("보안 사고 터지자 보안주 급등", "방산주가 급락했다", "신라면을 만든다"):
            self.assertFalse(lifemap._unsafe(text), text)  # 이미 일어난 움직임은 쓸 수 있다
        self.assertTrue(lifemap.check_word("급등주"))
        self.assertTrue(lifemap.check_word("a" * 13))
        self.assertEqual(lifemap.check_word("붕어빵"), "")


class BasisTest(LifemapBase):
    def test_public_basis_uses_market_date_and_its_news_window(self):
        b = lifemap.topic_basis(datetime(2026, 10, 28, 14, 0, tzinfo=KST))
        self.assertEqual((b["key"], b["label"]), ("public:20261027", "10/27 장 기준"))
        self.assertEqual(b["window"][0].isoformat(), "2026-10-24T15:30:00+09:00")  # 직전 거래일 마감 뒤부터
        self.assertEqual(b["window"][1].isoformat(), "2026-10-28T08:00:00+09:00")  # 기준일 다음 날 아침까지
        self.assertEqual(b["rates"]["042510"], 18.1)
        self.assertEqual(b["rates"]["003230"], 0.0)  # 종목 목록이 같은 기준일이면 모든 종목 등락률
        self.assertEqual([m["code"] for m in b["movers"]], ["042510", "053800", "004370", "012450", "007310"])

    def test_kiwoom_basis_only_when_today_and_fresh(self):
        now = datetime(2026, 11, 17, 11, 20, tzinfo=KST)
        kw = {"as_of": "20261117", "session": "open", "fetched_ts": now.timestamp(),
              "movers": {"up": [{"code": "042510", "name": "라온시큐어", "rate": 22.0, "value": 1}], "down": [], "value": []},
              "heatmap": {"KOSPI": [{"code": "004370", "rate": 2.0}]}}
        store.write("market_kiwoom", kw)
        store.write("kiwoom_status", {"price_source": "public"})
        with mock.patch.object(lifemap.time, "time", return_value=now.timestamp()):
            self.assertEqual(lifemap.topic_basis(now)["source"], "public")  # 키움 모드가 아니면 공공데이터
            store.write("kiwoom_status", {"price_source": "kiwoom"})
            self.assertEqual(lifemap.topic_basis(now.replace(hour=9, minute=30))["source"], "public")  # 10시 전
            b = lifemap.topic_basis(now)
            self.assertEqual((b["key"], b["label"]), ("kiwoom:20261117:open", "11/17 장중 11:20 기준"))
            self.assertEqual(b["rates"], {"004370": 2.0, "042510": 22.0})
        with mock.patch.object(lifemap.time, "time", return_value=now.timestamp() + 3600):
            self.assertEqual(lifemap.topic_basis(now)["source"], "public")  # 1시간 갱신 안 됨 → 공공데이터
        store.write("market_kiwoom", {**kw, "session": "closed"})
        self.assertEqual(lifemap.topic_basis(now.replace(hour=15, minute=40))["label"], "11/17 장 마감 기준")

    def test_topics_due_once_per_basis(self):
        b = lifemap.topic_basis()
        self.assertTrue(lifemap.topics_due(b))
        store.write("lifemap", {"basis": {"key": b["key"]}, "fresh": 3})
        self.assertFalse(lifemap.topics_due(b))
        store.write("market", {**MARKET, "as_of": "20261028"})
        self.assertTrue(lifemap.topics_due(lifemap.topic_basis()))  # 새 기준일 시세가 들어오면 다시
        self.assertFalse(lifemap.topics_due(None))


class TopicsTest(LifemapBase):
    def _basis(self):
        return lifemap.topic_basis(datetime(2026, 10, 28, 14, 0, tzinfo=KST))

    def test_pick_topics_requires_moved_stock_distinct_sector_and_articles(self):
        raw = {"topics": [
            {"title": "보안 사고 터지자 보안주 급등", "impact": "라온시큐어 등 보안 종목이 크게 올랐다", "keyword": "보안", "sector": "보안",
             "stocks": ["안랩", "라온시큐어", "없는회사"], "articles": [1, 2]},
            {"title": "방산 수주 소식", "impact": "방산주가 내렸다", "keyword": "방산", "sector": "방산",
             "stocks": ["한화에어로스페이스"], "articles": [2, 3]},  # 근거 기사 2가 겹침 → 제외
            {"title": "보안 인증 확대", "impact": "인증 관련주 상승", "keyword": "인증", "sector": "보안 ",
             "stocks": ["라온시큐어"], "articles": [4, 5]},  # 같은 섹터 → 제외
            {"title": "라면 수출 증가", "impact": "식품주 수혜 기대", "keyword": "라면", "sector": "식품",
             "stocks": ["농심"], "articles": [6, 7]},  # 금지 표현
            {"title": "금리 인하 기대감", "impact": "증시 반등", "keyword": "금리", "sector": "금융",
             "stocks": ["모르는회사"], "articles": [8, 9]},  # 실제로 움직인 종목이 목록에 없음 → 제외
            {"title": "방산 수출 계약", "impact": "한화에어로스페이스가 5% 내렸다", "keyword": "방산", "sector": "방산",
             "stocks": ["한화에어로스페이스"], "articles": [3, 10]},
            {"title": "보안 솔루션 수주", "impact": "안랩이 올랐다", "keyword": "보안솔루션", "sector": "보안솔루션",
             "stocks": ["안랩"], "articles": [6, 8]},  # '보안'을 포함한 섹터 → 같은 섹터로 제외
        ]}
        with mock.patch.object(lifemap, "_ask", return_value=raw) as ask:
            topics = lifemap.pick_topics(self._basis(), ARTICLES)
        self.assertEqual(ask.call_args.args[0], "claude-haiku-5-5")
        payload = ask.call_args.args[3]
        self.assertEqual(payload["많이 움직인 종목"][0], {"이름": "라온시큐어", "등락률": 18.1, "거래대금_억": 900})
        self.assertEqual([t["name"] for t in topics], ["보안", "방산"])
        self.assertEqual([s["name"] for s in topics[0]["stocks"]], ["라온시큐어", "안랩"])  # 등락률 큰 순, 없는 회사 제외
        self.assertEqual(topics[0]["stocks"][0]["rate"], 18.1)
        self.assertEqual([a["url"] for a in topics[1]["articles"]], ["https://news.example/3", "https://news.example/10"])
        self.assertEqual(lifemap._last_rejects, {"articles": 1, "sector": 2, "text": 2})  # "기대감"은 금지 표현이 먼저 걸림

    def test_run_topics_marks_moved_and_fills_to_three(self):
        topic_raw = {"topics": [{"title": "보안 사고 터지자 보안주 급등", "impact": "보안 종목이 크게 올랐다", "keyword": "보안",
                                 "sector": "보안", "stocks": ["라온시큐어"], "articles": [1, 2]}]}

        def fake_ask(model, *args, **kw):
            return topic_raw if model == lifemap.TOPIC_MODEL else SECURITY_CHAIN

        b = self._basis()
        with mock.patch.object(lifemap, "collect_market_news", return_value=ARTICLES), \
                mock.patch.object(lifemap, "_ask", side_effect=fake_ask) as ask:
            data = lifemap.run_topics(b)
        chain_payload = [c.args[3] for c in ask.call_args_list if c.args[0] == lifemap.CHAIN_MODEL][0]
        self.assertEqual(chain_payload["실제로 움직인 종목"], ["라온시큐어(+18.1%)"])
        self.assertEqual(data["fresh"], 1)
        self.assertEqual(data["basis"]["label"], "10/27 장 기준")
        self.assertEqual(store.read("lifemap_status")["rejects"], {})
        self.assertEqual([t["name"] for t in data["topics"]], ["보안"])  # 하나라도 만들었으면 다른 날 예시를 섞지 않는다
        companies = {c["name"]: c for s in data["topics"][0]["map"]["stages"] for c in s["companies"]}
        self.assertTrue(companies["라온시큐어"]["moved"])     # 토픽 종목
        self.assertTrue(companies["안랩"]["moved"])            # +9.4% ≥ 5%
        self.assertFalse(companies["이마트"]["moved"])
        self.assertEqual(companies["안랩"]["rate"], 9.4)
        self.assertEqual(data["topics"][0]["map"]["basis_label"], "10/27 장 기준")

    def test_run_topics_falls_back_to_examples_when_ai_fails(self):
        with mock.patch.object(lifemap, "collect_market_news", return_value=ARTICLES), \
                mock.patch.object(lifemap, "_ask", side_effect=RuntimeError("down")):
            data = lifemap.run_topics(self._basis())
        self.assertEqual(data["fresh"], 0)
        self.assertTrue(data["topics"][0]["carried"])
        view = lifemap.overview()
        self.assertEqual(view["hot"], ["예시토픽"])
        self.assertIn("보안", view["sector_maps"])  # 섹터도 예시로 채워진다(빈 화면 없음)
        self.assertTrue(view["sector_maps"]["보안"]["example"])

    def test_sectors_use_sector_news_and_keep_old_on_failure(self):
        found = ARTICLES[:2]
        store.write("lifemap_sectors", {"maps": {"조선": {**EXAMPLE_MAP, "word": "조선"}}})

        def chain(model, system, task, payload, *a, **kw):
            if payload["단어"] == "조선":
                raise RuntimeError("down")
            return SECURITY_CHAIN

        with mock.patch.object(news, "configured", return_value=True), \
                mock.patch.object(news, "search_window", return_value=found) as search, \
                mock.patch.object(lifemap, "_ask", side_effect=chain):
            made = lifemap.run_sectors(self._basis())
        self.assertEqual(made, len(lifemap.SECTORS) - 1)
        self.assertEqual(search.call_args_list[0].args[0], "금융 관련주")
        maps = store.read("lifemap_sectors")["maps"]
        self.assertEqual(maps["조선"]["word"], "조선")  # 실패한 섹터는 이전 것 유지
        self.assertEqual([a["url"] for a in maps["보안"]["articles"]], ["https://news.example/1", "https://news.example/2"])
        self.assertEqual(store.read("lifemap_sectors")["basis"]["label"], "10/27 장 기준")

    def test_collector_starts_in_background_once(self):
        with mock.patch.object(news, "configured", return_value=True), \
                mock.patch.object(lifemap.threading, "Thread") as thread:
            self.assertTrue(lifemap.maybe_run_daily(datetime(2026, 10, 28, 14, 0, tzinfo=KST)))
            self.assertFalse(lifemap.maybe_run_daily(datetime(2026, 10, 28, 14, 1, tzinfo=KST)))  # 돌고 있으면 또 시작하지 않음
        thread.return_value.start.assert_called_once()
        lifemap._daily_lock.release()
        st = store.read("lifemap_status")
        self.assertEqual((st["try_key"], st["tries"]), ("public:20261027", 1))

    def test_collect_market_news_uses_window_and_mover_names(self):
        b = self._basis()
        with mock.patch.object(news, "search_window", return_value=[]) as sw:
            lifemap.collect_market_news(b)
        queries = [c.args[0] for c in sw.call_args_list]
        self.assertIn("특징주", queries)
        self.assertIn("뉴욕증시", queries)
        self.assertIn('"라온시큐어"', queries)
        first = sw.call_args_list[0]
        self.assertEqual(first.args[1:3], b["window"])
        self.assertEqual(first.kwargs["extra_queries"], ["특징주 10월 27일"])


class ReadTest(LifemapBase):
    def test_stored_rate_kept_and_new_words_use_directory(self):
        store.write("lifemap_sectors", {"maps": {"보안": {"word": "보안", "stages": [{"key": "making", "label": "제조", "detail": "", "companies": [
            {"code": "053800", "name": "안랩", "relevance": "강", "reason": "만든다", "rate": 3.0, "moved": False},
            {"code": "000000", "name": "상폐", "relevance": "강", "reason": "만든다"}]}], "ai": True, "removed": ["x"],
            "basis_label": "10/24 장 기준"}}})
        view = lifemap.overview()
        c = view["sector_maps"]["보안"]["stages"][0]["companies"]
        self.assertEqual([x["name"] for x in c], ["안랩"])  # 목록에서 빠진 회사는 숨김
        self.assertEqual((c[0]["rate"], c[0]["moved"]), (3.0, False))  # 기준 시점 값 유지
        self.assertEqual(view["sector_maps"]["보안"]["basis_label"], "10/24 장 기준")
        self.assertNotIn("removed", view["sector_maps"]["보안"])
        fresh = lifemap.with_prices({"word": "x", "stages": [{"key": "making", "companies": [{"code": "042510", "name": "라온시큐어"}]}]})
        self.assertEqual((fresh["stages"][0]["companies"][0]["rate"], fresh["stages"][0]["companies"][0]["moved"]), (18.1, True))
        self.assertEqual(fresh["basis_label"], "10/27 장 기준")

    def test_overview_never_calls_ai_or_news(self):
        with mock.patch.object(lifemap, "_ask", side_effect=AssertionError("AI 호출")), \
                mock.patch.object(news, "search", side_effect=AssertionError("뉴스 호출")), \
                mock.patch.object(news, "search_window", side_effect=AssertionError("뉴스 호출")):
            view = lifemap.overview()
            self.assertEqual(view["sectors"], lifemap.SECTORS)
            self.assertEqual(lifemap.word_status("보안")["status"], "ready")


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
            self.assertEqual(body["sectors"], lifemap.SECTORS)
            self.assertTrue(body["topics"])  # 저장된 것이 없어도 예시로 채움
            self.assertEqual(body["basis"]["label"], "10/24 장 기준")
            self.assertEqual(client.get("/api/stock/lifemap/word", params={"w": "보안"}).json()["status"], "ready")
        sid = {"X-Stockon-Session": "abcdef12-3456"}
        r = client.post("/api/stock/lifemap/word", json={"word": "붕어빵"}, headers=sid)
        self.assertEqual(r.json()["status"], "queued")
        self.assertIn("s:abcdef12-3456", lifemap._sessions)
        self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "x" * 21}).status_code, 422)
        self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "<b>"}).json()["status"], "invalid")

    def test_disabled_server(self):
        client = self._client()
        with mock.patch.dict("os.environ", {"STOCKON_ENABLED": ""}):
            self.assertEqual(client.get("/api/stock/lifemap").status_code, 404)
            self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "보안"}).status_code, 404)


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
        self.assertEqual(sorted(data["sectors"]), sorted(lifemap.SECTORS))
        self.assertGreaterEqual(len(data["topics"]), lifemap.TOPICS_MIN)
        self.assertTrue(data["basis"]["label"].endswith("기준"))
        maps = list(data["sectors"].values()) + [t["map"] for t in data["topics"]]
        for m in maps:
            self.assertTrue(m["stages"])
            self.assertLessEqual(len(m["stages"]), 4)
            for st in m["stages"]:
                self.assertIn(st["key"], lifemap.STAGES)
                self.assertLessEqual(len(st["companies"]), 2)
                for c in st["companies"]:
                    self.assertRegex(c["code"], r"^[0-9A-Z]{6}$")
                    self.assertFalse(lifemap._unsafe(c["reason"]), c["reason"])
        sectors = set()
        for t in data["topics"]:
            self.assertEqual(len(t["articles"]), 2)
            self.assertTrue(t["stocks"])
            self.assertNotIn(t["sector"], sectors)
            sectors.add(t["sector"])
            for x in (t["title"], t["impact"]):
                self.assertFalse(lifemap._unsafe(x), x)


if __name__ == "__main__":
    unittest.main()

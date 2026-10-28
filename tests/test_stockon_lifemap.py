"""뉴스 속 숨은 종목 오프라인 테스트. 외부 API·AI를 부르지 않는다(가짜 응답 사용).

실행: python -B -m unittest tests.test_stockon_lifemap -v
"""

import json
import time
import unittest
from datetime import datetime
from unittest import mock

from services.stockon import ai, kiwoom_collector, lifemap, news, store
from services.stockon.public_data import KST
from tests.test_stockon import TempStore

STOCKS = {
    "004370": {"name": "농심", "market": "KOSPI", "close": 400000, "change": 4000, "rate": 1.01, "cap": 2e12, "value": 1e10},
    "007310": {"name": "오뚜기", "market": "KOSPI", "close": 380000, "change": -3800, "rate": -0.99, "cap": 1.4e12, "value": 5e9},
    "139480": {"name": "이마트", "market": "KOSPI", "close": 70000, "change": 700, "rate": 1.0, "cap": 2e12, "value": 1e10},
    "042510": {"name": "라온시큐어", "market": "KOSDAQ", "close": 3000, "change": 460, "rate": 18.1, "cap": 1e11, "value": 9e10},
    "053800": {"name": "안랩", "market": "KOSDAQ", "close": 70000, "change": 6000, "rate": 9.4, "cap": 7e11, "value": 5e10},
    "030200": {"name": "KT", "market": "KOSPI", "close": 50000, "change": -1500, "rate": -2.9, "cap": 1.3e13, "value": 6e10},
    "017670": {"name": "SK텔레콤", "market": "KOSPI", "close": 55000, "change": -3500, "rate": -6.0, "cap": 1.2e13, "value": 9e10},
    "012450": {"name": "한화에어로스페이스", "market": "KOSPI", "close": 900000, "change": -50000, "rate": -5.3, "cap": 4e13, "value": 8e11},
}

MARKET = {"as_of": "20261027", "indices": [{"name": "코스피", "series": [{"d": "20261024", "c": 1}, {"d": "20261027", "c": 1}]}],
          "movers": {"up": [], "down": [], "value": []}}

INTERP = {
    "interpretation": ["통신사 개인정보 유출이 알려지면서 기업들의 보안 투자 수요가 늘 수 있다.",
                       "유출 기업은 보상·과징금 비용이 생길 수 있다."],
    "paths": [
        {"label": "보안 수요 증가", "detail": "인증·백신 투자", "companies": [
            {"name": "라온시큐어", "direction": "긍정", "relevance": "강", "reason": "모바일 인증 보안 솔루션을 만든다"},
            {"name": "없는보안", "direction": "긍정", "relevance": "강", "reason": "보안"},
            {"name": "안랩", "direction": "긍정", "relevance": "강", "reason": "백신 보안 솔루션을 만든다"},
            {"name": "이마트", "direction": "긍정", "relevance": "약", "reason": "세 번째라 빠짐"}]},
        {"label": "보상 비용", "detail": "과징금·보상", "companies": [
            {"name": "SK텔레콤", "direction": "부정", "relevance": "강", "reason": "유출이 알려진 통신사다"},
            {"name": "라온시큐어", "direction": "부정", "relevance": "강", "reason": "중복 회사"},
            {"name": "KT", "direction": "중립", "relevance": "중", "reason": "방향이 없으면 빠짐"},
            {"name": "KT", "direction": "부정", "relevance": "중", "reason": "같은 통신 업종이다"}]},
        {"label": "보안 수요 증가", "detail": "중복 경로", "companies": [{"name": "농심", "direction": "긍정", "relevance": "약", "reason": "x"}]},
        {"label": "주가 기회", "detail": "", "companies": [{"name": "오뚜기", "direction": "긍정", "relevance": "약", "reason": "x"}]},
    ],
}

ARTICLES = [{"title": f"기사 {i}", "url": f"https://news.example/{i}", "press": f"press{i % 4}.kr",
             "pub": "2026-10-27T10:00:00+09:00", "snippet": "요약"} for i in range(1, 13)]

EXAMPLE_ITEM = {"name": "예시이슈", "title": "예시 제목", "summary": "예시 요약", "sector": "보안",
                "articles": [{"title": "예시 기사", "url": "https://news.example/x", "press": "ex.kr", "pub": "2026-10-24T09:00:00+09:00", "rep": True}],
                "map": {"word": "예시이슈", "interpretation": ["예시 해석이다."], "basis_label": "10/24 장 기준", "ai": True,
                        "stages": [{"key": "p0", "label": "수요 증가", "detail": "", "companies": [
                            {"code": "053800", "name": "안랩", "relevance": "강", "reason": "보안 솔루션을 만든다", "direction": "pos", "rate": 9.4}]}]}}


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
            "topics": [EXAMPLE_ITEM], "sectors": {"보안": {**EXAMPLE_ITEM, "name": "보안"}},
        }
        self.pool = FakePool()
        for p in (mock.patch.object(lifemap, "_pool", self.pool), mock.patch.object(ai, "available", return_value=True),
                  mock.patch.object(news, "configured", return_value=True)):
            p.start()
            self.patches.append(p)

    def tearDown(self):
        lifemap._examples_cache["value"] = None
        super().tearDown()

    def basis(self):
        return lifemap.topic_basis(datetime(2026, 10, 28, 14, 0, tzinfo=KST))


class ValidateTest(LifemapBase):
    def test_paths_need_listed_company_direction_and_unique(self):
        stocks, index, _ = lifemap.directory()
        paths, removed = lifemap.validate_paths(INTERP, index, stocks)
        self.assertEqual([p["label"] for p in paths], ["보안 수요 증가", "보상 비용"])  # 같은 이름 경로·금지 표현('기회') 제외
        self.assertEqual(removed, ["없는보안"])
        self.assertEqual([(c["name"], c["direction"]) for c in paths[0]["companies"]], [("라온시큐어", "pos"), ("안랩", "pos")])
        self.assertEqual([(c["name"], c["direction"]) for c in paths[1]["companies"]], [("SK텔레콤", "neg"), ("KT", "neg")])
        self.assertEqual(paths[1]["key"], "p1")
        self.assertEqual(paths[0]["companies"][0]["code"], "042510")  # 코드는 목록에서 붙인다

    def test_interpret_retries_when_single_path_and_keeps_better(self):
        one = {"interpretation": ["해석 한 줄이다."], "paths": [INTERP["paths"][0]]}
        with mock.patch.object(lifemap, "_ask", side_effect=[one, INTERP]) as ask:
            m = lifemap.interpret("개인정보 유출", ARTICLES[:2])
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(ask.call_args_list[0].args[0], "claude-sonnet-5-5")
        self.assertIn("없는보안", ask.call_args_list[1].args[2])  # 지운 회사 이름을 알려 준다
        self.assertEqual(len(m["stages"]), 2)
        self.assertEqual(len(m["interpretation"]), 2)
        self.assertEqual(ask.call_args_list[0].args[3]["기사"][0]["제목"], "기사 1")
        with mock.patch.object(lifemap, "_ask", side_effect=[INTERP, one]) as ask:
            lifemap.interpret("개인정보 유출", [])
        self.assertEqual(ask.call_count, 1)  # 처음 결과가 충분하면(경로 2·회사 3 이상) 지운 회사가 있어도 다시 부르지 않음

    def test_unsafe_interpretation_lines_are_dropped(self):
        raw = {**INTERP, "interpretation": ["보안주가 오를 것이다.", "매수 기회다.", "보안 투자 수요가 늘 수 있다."]}
        with mock.patch.object(lifemap, "_ask", return_value=raw):
            m = lifemap.interpret("유출", [])
        self.assertEqual(m["interpretation"], ["보안 투자 수요가 늘 수 있다."])

    def test_banned_words(self):
        for text in ("보안 수혜주", "매수 추천", "주가 상승이 기대된다", "지금이 기회", "아직 덜 올랐다", "숨은 기회", "앞으로 오를 것", "매도"):
            self.assertTrue(lifemap._unsafe(text), text)
        for text in ("보안 사고 터지자 보안주 급등", "방산주가 급락했다", "보안 투자 수요가 늘 수 있다"):
            self.assertFalse(lifemap._unsafe(text), text)
        self.assertTrue(lifemap.check_word("급등주"))
        self.assertEqual(lifemap.check_word("붕어빵"), "")


class BasisTest(LifemapBase):
    def test_public_basis_uses_market_date_and_its_news_window(self):
        b = self.basis()
        self.assertEqual((b["key"], b["label"]), ("public:20261027", "10/27 장 기준"))
        self.assertEqual(b["window"][0].isoformat(), "2026-10-24T15:30:00+09:00")
        self.assertEqual(b["window"][1].isoformat(), "2026-10-28T08:00:00+09:00")
        self.assertEqual(b["rates"]["042510"], 18.1)

    def test_kiwoom_basis_only_when_today_and_fresh(self):
        now = datetime(2026, 11, 17, 11, 20, tzinfo=KST)
        kw = {"as_of": "20261117", "session": "open", "fetched_ts": now.timestamp(),
              "movers": {"up": [{"code": "042510", "rate": 22.0}], "down": [], "value": []},
              "heatmap": {"KOSPI": [{"code": "004370", "rate": 2.0}]}}
        store.write("market_kiwoom", kw)
        store.write("kiwoom_status", {"price_source": "kiwoom"})
        with mock.patch.object(lifemap.time, "time", return_value=now.timestamp()):
            self.assertEqual(lifemap.topic_basis(now.replace(hour=9, minute=30))["source"], "public")  # 10시 전
            b = lifemap.topic_basis(now)
            self.assertEqual((b["key"], b["label"]), ("kiwoom:20261117:open", "11/17 장중 11:20 기준"))
            self.assertEqual(b["rates"], {"004370": 2.0, "042510": 22.0})
            self.assertEqual(b["window"][1], now)  # 오늘 뉴스(지금까지)
        with mock.patch.object(lifemap.time, "time", return_value=now.timestamp() + 3600):
            self.assertEqual(lifemap.topic_basis(now)["source"], "public")  # 1시간 갱신 안 됨 → 공공데이터

    def test_topics_due_once_per_basis(self):
        b = self.basis()
        self.assertTrue(lifemap.topics_due(b))
        store.write("lifemap", {"basis": {"key": b["key"]}, "fresh": 3})
        self.assertFalse(lifemap.topics_due(b))
        store.write("market", {**MARKET, "as_of": "20261028"})
        self.assertTrue(lifemap.topics_due(lifemap.topic_basis()))
        self.assertFalse(lifemap.topics_due(None))


class IssuesTest(LifemapBase):
    def test_collect_issue_news_uses_issue_queries_not_movers(self):
        with mock.patch.object(news, "search_window", return_value=[]) as sw:
            lifemap.collect_issue_news(self.basis())
        queries = [c.args[0] for c in sw.call_args_list]
        self.assertIn("기준금리", queries)
        self.assertIn("해킹 개인정보 유출", queries)
        self.assertFalse([q for q in queries if "특징주" in q or "급등" in q])  # 등락·특징주에서 출발하지 않는다
        self.assertEqual(sw.call_args_list[0].args[1:3], self.basis()["window"])
        self.assertEqual(sw.call_args_list[0].kwargs["extra_queries"], ["정부 정책 발표 10월 27일"])

    def test_pick_issues_rules(self):
        raw = {"topics": [
            {"title": "통신사 개인정보 유출", "summary": "통신사 고객 정보가 유출됐다", "keyword": "개인정보 유출", "sector": "보안",
             "articles": [1, 2, 3, 4, 5, 6, 7, 99], "representative": 3},
            {"title": "유가 급등", "summary": "국제유가가 올랐다", "keyword": "유가", "sector": "정유",
             "articles": [7, 8], "representative": 8},  # 앞 이슈가 6개(3,1,2,4,5,6)만 써서 7은 겹치지 않음 → 통과
            {"title": "보안 인증 확대", "summary": "인증 규제", "keyword": "인증", "sector": "보안솔루션",
             "articles": [9, 10], "representative": 9},  # 같은 섹터
            {"title": "수출 호조", "summary": "수출이 늘어 기회", "keyword": "수출", "sector": "무역",
             "articles": [9, 10], "representative": 9},  # 금지 표현
            {"title": "환율 하락", "summary": "원달러 환율이 내렸다", "keyword": "환율", "sector": "항공",
             "articles": [4, 12], "representative": 12},  # 기사 4가 첫 이슈와 겹침
            {"title": "관세 발표", "summary": "미국이 관세를 발표했다", "keyword": "관세", "sector": "자동차",
             "articles": [9, 11], "representative": 12},  # 대표 기사가 목록에 없음
            {"title": "조선 수주", "summary": "조선사가 수주했다", "keyword": "조선 수주", "sector": "조선",
             "articles": [9, 1], "representative": 9},  # 1은 첫 이슈 기사
            {"title": "금리 동결", "summary": "기준금리를 동결했다", "keyword": "금리", "sector": "금융",
             "articles": [11], "representative": 11},  # 기사 1개뿐
            {"title": "반도체 수출", "summary": "반도체 수출이 늘었다", "keyword": "반도체 수출", "sector": "반도체",
             "articles": [9, 9], "representative": 9},  # 중복 제거 후 1개
            {"title": "AI 해킹", "summary": "AI 해킹으로 정보가 새어 나갔다", "keyword": "AI 해킹 유출", "sector": "IT",
             "articles": [11, 12], "representative": 11},  # '유출'이 앞 이슈와 겹침 → 같은 이슈
            {"title": "방산 계약", "summary": "방산 수출 계약을 맺었다", "keyword": "방산", "sector": "방산",
             "articles": [9, 10], "representative": 10},
        ]}
        with mock.patch.object(lifemap, "_ask", return_value=raw) as ask:
            topics = lifemap.pick_issues(self.basis(), ARTICLES)
        self.assertEqual(ask.call_args.args[0], "claude-haiku-5-5")
        self.assertEqual(ask.call_args.args[3]["기사"][0]["언론사"], "press1.kr")
        self.assertEqual([t["name"] for t in topics], ["개인정보 유출", "유가", "방산"])
        first = topics[0]
        self.assertEqual(len(first["articles"]), 6)  # 최대 6개
        self.assertEqual(first["articles"][0]["url"], "https://news.example/3")  # 대표 기사가 맨 앞
        self.assertEqual([a["rep"] for a in first["articles"]], [True, False, False, False, False, False])
        self.assertEqual(lifemap._last_rejects, {"sector": 1, "text": 1, "articles": 5, "word": 1})

    def test_pick_issues_needs_two_presses(self):
        same_press = [{**a, "press": "one.kr"} for a in ARTICLES]
        raw = {"topics": [{"title": "유가 급등", "summary": "국제유가가 올랐다", "keyword": "유가", "sector": "정유",
                           "articles": [1, 2], "representative": 1}]}
        with mock.patch.object(lifemap, "_ask", return_value=raw):
            self.assertEqual(lifemap.pick_issues(self.basis(), same_press), [])
            self.assertEqual(lifemap._last_rejects, {"press": 1})
            self.assertEqual(len(lifemap.pick_issues(self.basis(), same_press, min_press=1)), 1)  # 섹터는 한 언론도 허용

    def test_run_topics_interprets_and_marks_reaction(self):
        issue = {"topics": [{"title": "통신사 개인정보 유출", "summary": "통신사 고객 정보가 유출됐다", "keyword": "개인정보 유출",
                             "sector": "보안", "articles": [1, 2], "representative": 1}]}

        def fake_ask(model, *args, **kw):
            return issue if model == lifemap.TOPIC_MODEL else INTERP

        with mock.patch.object(lifemap, "collect_issue_news", return_value=ARTICLES), \
                mock.patch.object(lifemap, "_ask", side_effect=fake_ask):
            data = lifemap.run_topics(self.basis())
        self.assertEqual([t["name"] for t in data["topics"]], ["개인정보 유출"])  # 하나라도 만들면 다른 날 예시를 섞지 않음
        t = data["topics"][0]
        self.assertNotIn("_context", t)
        self.assertEqual(t["map"]["interpretation"][0][:3], "통신사")
        companies = {c["name"]: c for s in t["map"]["stages"] for c in s["companies"]}
        self.assertEqual((companies["라온시큐어"]["rate"], companies["라온시큐어"]["moved"]), (18.1, True))
        self.assertEqual((companies["KT"]["rate"], companies["KT"]["moved"]), (-2.9, False))
        self.assertEqual(data["basis"]["label"], "10/27 장 기준")

    def test_run_topics_falls_back_to_examples_when_ai_fails(self):
        with mock.patch.object(lifemap, "collect_issue_news", return_value=ARTICLES), \
                mock.patch.object(lifemap, "_ask", side_effect=RuntimeError("down")):
            data = lifemap.run_topics(self.basis())
        self.assertEqual(data["fresh"], 0)
        self.assertTrue(data["topics"][0]["carried"])
        view = lifemap.overview()
        self.assertEqual(view["hot"], ["예시이슈"])
        self.assertTrue(view["sector_items"]["보안"]["example"])

    def test_sectors_use_sector_news_and_keep_old_on_failure(self):
        store.write("lifemap_sectors", {"items": {"조선": {**EXAMPLE_ITEM, "name": "조선"}}})
        issue = {"topics": [{"title": "업계 이슈", "summary": "업계 소식", "keyword": "업계 이슈", "sector": "x",
                             "articles": [1], "representative": 1}]}

        def fake_ask(model, system, task, payload, *a, **kw):
            if model == lifemap.TOPIC_MODEL:
                if "'조선'" in task:
                    raise RuntimeError("down")
                return issue
            return INTERP

        with mock.patch.object(news, "search_window", return_value=ARTICLES[:2]) as sw, \
                mock.patch.object(lifemap, "_ask", side_effect=fake_ask):
            made = lifemap.run_sectors(self.basis())
        self.assertEqual(made, len(lifemap.SECTORS) - 1)
        self.assertEqual(sw.call_args_list[0].args[0], "금융 업계")
        items = store.read("lifemap_sectors")["items"]
        self.assertEqual(items["조선"]["name"], "조선")  # 실패한 섹터는 이전 것
        self.assertEqual(items["보안"]["sector"], "보안")
        self.assertEqual(len(items["보안"]["articles"]), 1)


class ReactionTest(LifemapBase):
    def _item(self):
        return {"name": "x", "title": "t", "articles": [], "map": {"word": "x", "basis_label": "10/27 장 기준", "stages": [
            {"key": "p0", "label": "수요", "detail": "", "companies": [
                {"code": "053800", "name": "안랩", "relevance": "강", "reason": "r", "direction": "pos", "rate": 3.0},
                {"code": "042510", "name": "라온시큐어", "relevance": "강", "reason": "r", "direction": "pos"},
                {"code": "000000", "name": "상폐", "relevance": "강", "reason": "r", "direction": "neg"}]}]}}

    def test_stored_then_directory_rate(self):
        out = lifemap.with_reaction(self._item())
        c = out["map"]["stages"][0]["companies"]
        self.assertEqual([x["name"] for x in c], ["안랩", "라온시큐어"])  # 목록에서 빠진 회사는 숨김
        self.assertEqual((c[0]["rate"], c[0]["moved"]), (3.0, False))  # 생성 때 기준 값
        self.assertEqual((c[1]["rate"], c[1]["moved"]), (18.1, True))  # 없으면 최신 종가
        self.assertEqual(out["map"]["reaction_label"], "10/27 장 등락률")

    def test_live_kiwoom_rates_override_when_fresh(self):
        now = datetime.now(KST)
        lifemap.save_live_rates({"053800": 7.5}, now)
        out = lifemap.with_reaction(self._item(), lifemap._live_rates())
        c = out["map"]["stages"][0]["companies"]
        self.assertEqual((c[0]["rate"], c[0]["moved"]), (7.5, True))
        self.assertTrue(out["map"]["reaction_label"].endswith("장중 등락률"))
        store.write("lifemap_rates", {**store.read("lifemap_rates"), "ts": time.time() - 3600})
        self.assertIsNone(lifemap._live_rates())  # 45분 넘게 갱신 안 되면 쓰지 않음

    def test_collector_refreshes_rates_with_ka10095_only(self):
        store.write("lifemap", {"topics": [self._item()]})

        class FakeClient:
            def __init__(self):
                self.calls = []

            def query(self, api_id, body):
                self.calls.append((api_id, body))
                return {"atn_stk_infr": [{"stk_cd": "053800", "flu_rt": "+7.50"}, {"stk_cd": "042510", "flu_rt": "-1.20"}]}

        client = FakeClient()
        now = datetime.now(KST)
        self.assertTrue(lifemap.rates_due(now))
        self.assertEqual(kiwoom_collector.refresh_lifemap_rates(client, now), 2)
        self.assertEqual(client.calls, [("ka10095", {"stk_cd": "053800|042510|000000"})])
        self.assertEqual(store.read("lifemap_rates")["rates"], {"053800": 7.5, "042510": -1.2})
        self.assertFalse(lifemap.rates_due(now))  # 30분 안에는 다시 하지 않음


class LiveQueueTest(LifemapBase):
    def test_cached_word_returns_immediately(self):
        store.write("lifemap_words", {"붕어빵": {**EXAMPLE_ITEM, "name": "붕어빵"}})
        r = lifemap.request_word(" 붕어빵 ", "s1")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["item"]["name"], "붕어빵")
        self.assertEqual(self.pool.calls, [])

    def test_queue_dedup_and_word_uses_recent_news(self):
        r1 = lifemap.request_word("원전", "s1")
        r2 = lifemap.request_word("원전", "s2")
        self.assertEqual((r1["status"], r2["status"]), ("queued", "queued"))
        self.assertEqual(len(self.pool.calls), 1)
        recent = [{**ARTICLES[0], "pub": datetime.now(KST).isoformat()}, {**ARTICLES[1], "pub": "2020-01-01T00:00:00+09:00"}]
        with mock.patch.object(news, "search", return_value=recent), mock.patch.object(lifemap, "_ask", return_value=INTERP) as ask:
            self.pool.run_all()
        self.assertEqual(len(ask.call_args.args[3]["기사"]), 1)  # 3일 지난 기사는 빼고 해석
        done = lifemap.word_status("원전")
        self.assertEqual(done["status"], "ready")
        self.assertTrue(done["item"]["articles"][0]["rep"])
        self.assertEqual(done["item"]["map"]["stages"][0]["companies"][0]["rate"], 18.1)

    def test_failure_shows_example(self):
        lifemap.request_word("원전", "s1")
        with mock.patch.object(news, "search", return_value=[]), mock.patch.object(lifemap, "_ask", side_effect=RuntimeError("timeout")):
            self.pool.run_all()
        r = lifemap.word_status("원전")
        self.assertEqual(r["status"], "failed")
        self.assertTrue(r["item"]["example"])
        self.assertTrue(r["item"]["map"]["stages"])

    def test_limits(self):
        for i in range(lifemap.LIVE_PER_SESSION):
            self.assertEqual(lifemap.request_word(f"단어{i}", "same")["status"], "queued")
        self.assertEqual(lifemap.request_word("단어x", "same")["status"], "limited")
        for i in range(lifemap.LIVE_QUEUE_MAX - lifemap.LIVE_PER_SESSION):
            lifemap.request_word(f"다른{i}", f"s{i}")
        busy = lifemap.request_word("넘침", "new")
        self.assertEqual(busy["status"], "busy")
        self.assertTrue(busy["item"]["map"]["stages"])
        self.assertEqual(lifemap.request_word("<b>", "new")["status"], "invalid")
        lifemap._jobs.clear()
        store.write("lifemap_live_count", {"day": datetime.now(KST).strftime("%Y-%m-%d"), "n": lifemap.LIVE_DAILY_MAX})
        lifemap._live_count.clear()
        self.assertEqual(lifemap.request_word("상한", "other")["status"], "daily_limit")
        with mock.patch.object(ai, "available", return_value=False):
            self.assertEqual(lifemap.request_word("키없음", "other")["status"], "unavailable")


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
            return INTERP

        with mock.patch.object(lifemap, "_pool", real_pool), mock.patch.object(lifemap, "_ask", side_effect=slow_ask), \
                mock.patch.object(news, "search", return_value=[]):
            with ThreadPoolExecutor(max_workers=30) as people:
                results = list(people.map(lambda i: lifemap.request_word(f"단어{i:02d}", f"person{i}"), range(30)))
                t0 = time.time()
                list(people.map(lambda i: lifemap.overview(), range(30)))
                read_sec = time.time() - t0
            real_pool.shutdown(wait=True)
        statuses = [r["status"] for r in results]
        self.assertEqual(statuses.count("queued"), lifemap.LIVE_QUEUE_MAX)
        self.assertEqual(statuses.count("busy"), 30 - lifemap.LIVE_QUEUE_MAX)
        self.assertTrue(all(r["item"]["map"]["stages"] for r in results if r["status"] == "busy"))
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
        with mock.patch.object(lifemap, "_ask", side_effect=blocked), mock.patch("requests.get", side_effect=blocked), \
                mock.patch.object(news, "search", side_effect=blocked), mock.patch.object(news, "search_window", side_effect=blocked):
            r = client.get("/api/stock/lifemap")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["sectors"], lifemap.SECTORS)
            self.assertEqual(body["topics"][0]["map"]["interpretation"], ["예시 해석이다."])
            self.assertEqual(body["basis"]["label"], "10/24 장 기준")
            self.assertEqual(client.get("/api/stock/lifemap/word", params={"w": "보안"}).json()["status"], "ready")
        r = client.post("/api/stock/lifemap/word", json={"word": "원전"}, headers={"X-Stockon-Session": "abcdef12-3456"})
        self.assertEqual(r.json()["status"], "queued")
        self.assertIn("s:abcdef12-3456", lifemap._sessions)
        self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "x" * 21}).status_code, 422)

    def test_disabled_server(self):
        client = self._client()
        with mock.patch.dict("os.environ", {"STOCKON_ENABLED": ""}):
            self.assertEqual(client.get("/api/stock/lifemap").status_code, 404)
            self.assertEqual(client.post("/api/stock/lifemap/word", json={"word": "보안"}).status_code, 404)


class ScreenWordsTest(unittest.TestCase):
    """화면 문구(따옴표 안 한글)에 추천·수혜·기회·매수 표현이 없고, '숨은'은 탭 이름에만 쓴다. 주석·AI 지시문은 제외."""

    def test_no_recommendation_words_on_screen(self):
        import re
        from pathlib import Path

        root = Path(lifemap.__file__).resolve().parents[2]
        files = [root / "services/stockon/lifemap.py", *(root / "web/src/components/stock").glob("Life*.tsx"),
                 root / "web/src/components/stock/MindMap.tsx", root / "web/src/components/stock/StockTabs.tsx",
                 root / "web/src/app/stock/page.tsx"]
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                code = re.sub(r"(^\s*(#|//|\*|/\*).*$)|(\{/\*.*?\*/\})", "", line)
                for text in re.findall(r"[\"'`>]([^\"'`<>]*[가-힣][^\"'`<>]*)[\"'`<]", code):
                    if "쓰지 않는다" in line or "금지" in line or "re.compile" in line or 'r"' in line:
                        continue  # 금지 규칙을 설명하는 문장(AI 지시·문서)
                    self.assertNotRegex(text, r"추천|수혜|기회|매수|덜 올", f"{f.name}: {text}")
                    if "숨은" in text:
                        self.assertIn("뉴스 속 숨은 종목", text, f"{f.name}: '숨은'은 탭 이름에만 — {text}")


class ExamplesFileTest(unittest.TestCase):
    def test_repo_examples_are_complete_and_safe(self):
        data = json.loads(lifemap.EXAMPLES_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["sectors"]), 8)
        self.assertGreaterEqual(len(data["topics"]), lifemap.TOPICS_MIN)
        self.assertTrue(data["basis"]["label"].endswith("기준"))
        items = list(data["sectors"].values()) + data["topics"]
        for it in items:
            m = it["map"]
            self.assertTrue(m["stages"])
            self.assertTrue(m["interpretation"])
            self.assertLessEqual(len(m["stages"]), lifemap.MAX_PATHS)
            self.assertTrue(it["articles"] and it["articles"][0]["rep"])
            self.assertLessEqual(len(it["articles"]), lifemap.ARTICLES_MAX)
            for line in m["interpretation"] + [it["title"], it["summary"]]:
                self.assertFalse(lifemap._unsafe(line), line)
            for st in m["stages"]:
                self.assertLessEqual(len(st["companies"]), lifemap.PER_PATH)
                for c in st["companies"]:
                    self.assertRegex(c["code"], r"^[0-9A-Z]{6}$")
                    self.assertIn(c["direction"], ("pos", "neg"))
                    self.assertFalse(lifemap._unsafe(c["reason"]), c["reason"])
        sectors = [t["sector"] for t in data["topics"]]
        self.assertEqual(len(sectors), len(set(sectors)))


if __name__ == "__main__":
    unittest.main()

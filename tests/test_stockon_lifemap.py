"""뉴스 속 숨은 종목 오프라인 테스트. 외부 API·AI를 부르지 않는다(가짜 응답 사용).

실행: python -B -m unittest tests.test_stockon_lifemap -v
"""

import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from services.stockon import ai, kiwoom_collector, lifemap, news, rss, store
from services.stockon.public_data import KST
from tests.test_stockon import TempStore

REAL_RSS_COLLECT = rss.collect  # LifemapBase가 rss.collect를 막아 두므로 RSS 수집 자체 테스트는 원래 함수로

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

# 제목에 이슈 이름의 말이 있어야 '핵심 사건'으로 통과한다(centered)
ARTICLE_TOPICS = "개인정보 유출·유가 급등·방산·업계 이슈"
ARTICLES = [{"title": f"{ARTICLE_TOPICS} 기사 {i}", "url": f"https://news.example/{i}", "press": f"press{i % 4}.kr",
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
        lifemap._ind_cache.update(value=None)
        lifemap._pulse_cache.update(value=None)
        lifemap._examples_cache["value"] = {
            "basis": {"key": "public:20261024", "source": "public", "as_of": "20261024", "label": "10/24 장 기준"},
            "topics": [EXAMPLE_ITEM], "sectors": {"보안": {**EXAMPLE_ITEM, "name": "보안"}},
        }
        self.pool = FakePool()
        for p in (mock.patch.object(lifemap, "_pool", self.pool), mock.patch.object(ai, "available", return_value=True),
                  mock.patch.object(news, "configured", return_value=True), mock.patch.object(news, "search", return_value=[]),
                  mock.patch.object(news, "search_window", return_value=[]),  # 완화 ①(NAVER 검색어)도 실제로 부르지 않는다
                  mock.patch.dict("os.environ", {"LIFEMAP_VERIFY": "0"}),  # 기업 연관성 검증은 VerifyTest에서
                  mock.patch.object(lifemap.public_data, "stock_history", return_value={}),
                  # RSS를 부르지 않는다(기사가 없으면 예전 방식 = NAVER 검색어로 만든다). RSS 경로는 RssIssuesTest에서
                  mock.patch.object(rss, "collect", return_value=([], []))):
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
        self.assertEqual(ask.call_args_list[0].args[3]["기사"][0]["제목"], ARTICLES[0]["title"])
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
        self.assertEqual(sw.call_args_list[0].kwargs["extra_queries"], ["해킹 개인정보 유출 10월 27일"])
        # 일상 뉴스면(결함·날씨·질병·생활·기술)에서 출발한다. 실적 검색은 하지 않는다
        for q in ("리콜 결함", "폭염 한파 폭우 피해", "감염병 확산", "소비 트렌드 인기", "신기술 공개 발표"):
            self.assertIn(q, queries)
        self.assertFalse([q for q in queries if "실적" in q])

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

    def test_run_topics_keeps_same_basis_topics_when_nothing_new(self):
        # 10-30 13:26: 이슈 묶기가 max_tokens로 실패 → 같은 기준의 5개가 3개로 줄던 것. 하나도 못 만들면 그대로 둔다
        prev = [{"name": f"이슈{i}", "title": f"이슈{i}"} for i in range(5)]
        store.write("lifemap", {"basis": lifemap.basis_info(self.basis()), "topics": prev, "fresh": 5})
        with mock.patch.object(lifemap, "collect_issue_news", return_value=ARTICLES), \
                mock.patch.object(lifemap, "_ask", side_effect=RuntimeError("stop_reason=max_tokens")):
            data = lifemap.run_topics(self.basis())
        self.assertEqual([t["name"] for t in data["topics"]], [t["name"] for t in prev])
        self.assertEqual(store.read("lifemap")["topics"], prev)
        status = store.read("lifemap_status")
        self.assertEqual((status["ok"], status["error"]), (False, "topics:RuntimeError: stop_reason=max_tokens"))

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
                if api_id == "ka20001":
                    return {"flu_rt": "+6.63" if body["inds_cd"] == "001" else "+3.69"}
                return {"atn_stk_infr": [{"stk_cd": "053800", "flu_rt": "+7.50"}, {"stk_cd": "042510", "flu_rt": "-1.20"}]}

        client = FakeClient()
        now = datetime.now(KST)
        self.assertTrue(lifemap.rates_due(now))
        self.assertEqual(kiwoom_collector.refresh_lifemap_rates(client, now), 2)
        # 회사 등락률(ka10095) 바로 뒤에 지수(ka20001) — 시장 대비는 같은 때 값끼리
        self.assertEqual([c[0] for c in client.calls], ["ka10095", "ka20001", "ka20001"])
        self.assertEqual(client.calls[0], ("ka10095", {"stk_cd": "053800|042510|000000"}))
        saved = store.read("lifemap_rates")
        self.assertEqual(saved["rates"], {"053800": 7.5, "042510": -1.2})
        self.assertEqual(saved["indices"], {"KOSPI": 6.63, "KOSDAQ": 3.69})
        self.assertFalse(lifemap.rates_due(now))  # 30분 안에는 다시 하지 않음


class LinkAndOppositeTest(LifemapBase):
    """같은 업종만으로 넣은 회사는 연관도 '약', 해석과 반대로 ±3% 이상 움직인 회사는 같은 날 뉴스로 다른 이유 한 줄."""

    def test_same_industry_forced_weak_and_prompt_rules(self):
        stocks, index, _ = lifemap.directory()
        raw = {"paths": [{"label": "신뢰 하락", "detail": "", "companies": [
            {"name": "KT", "direction": "부정", "link": "같은 업종", "relevance": "강", "reason": "같은 통신 업종이다"},
            {"name": "SK텔레콤", "direction": "부정", "link": "직접 당사자", "relevance": "강", "reason": "유출이 알려진 통신사다"}]}]}
        paths, _ = lifemap.validate_paths(raw, index, stocks)
        got = {c["name"]: (c["relevance"], c.get("link")) for c in paths[0]["companies"]}
        self.assertEqual(got, {"KT": ("약", "같은 업종"), "SK텔레콤": ("강", "직접 당사자")})
        self.assertIn("'같은 업종'이라는 이유만으로는 넣지 않는다", lifemap.INTERP_SYSTEM)
        self.assertIn("relation", lifemap.INTERP_SCHEMA["properties"]["paths"]["items"]["properties"]["companies"]["items"]["required"])

    def test_opposite_rule(self):
        o = lifemap.opposite
        self.assertTrue(o({"direction": "neg", "rate": 7.1}))
        self.assertTrue(o({"direction": "pos", "rate": -3.0}))
        self.assertFalse(o({"direction": "neg", "rate": 2.9}))   # 3% 미만
        self.assertFalse(o({"direction": "neg", "rate": -6.0}))  # 같은 방향
        self.assertFalse(o({"direction": "pos", "rate": None}))

    def _topic_with_opposites(self, answers):
        # KT(부정 해석, +7.1%)·이마트(긍정 해석, -4%)는 반대, SK텔레콤(부정, -6%)은 같은 방향
        rates = {"030200": 7.1, "139480": -4.0, "017670": -6.0}
        interp = {"interpretation": ["유출 기업은 보상 비용이 생길 수 있다."], "paths": [
            {"label": "보상 비용", "detail": "", "companies": [
                {"name": "SK텔레콤", "direction": "부정", "link": "직접 당사자", "relevance": "강", "reason": "유출이 알려진 통신사다"},
                {"name": "KT", "direction": "부정", "link": "같은 업종", "relevance": "중", "reason": "같은 통신 업종이다"}]},
            {"label": "소비 위축", "detail": "", "companies": [
                {"name": "이마트", "direction": "긍정", "link": "사업 연결", "relevance": "약", "reason": "통신 결합 할인 고객이 많다"}]}]}
        issue = {"topics": [{"title": "통신사 개인정보 유출", "summary": "고객 정보가 유출됐다", "keyword": "개인정보 유출",
                             "sector": "통신", "articles": [1, 2], "representative": 1}]}
        company_news = {
            "KT": [{"title": "KT 3분기 실적 발표, 영업이익 증가", "url": "https://news.example/kt", "press": "a.kr",
                    "pub": "2026-10-27T11:00:00+09:00", "snippet": ""},
                   {"title": "기사 1 KT", "url": ARTICLES[0]["url"], "press": "b.kr", "pub": None, "snippet": ""}],
            "이마트": [],
        }
        calls = []

        def fake_ask(model, system, task, payload, schema, *a, **kw):
            if schema is lifemap.OTHER_SCHEMA:
                calls.append(payload)
                return answers[payload["회사"]]
            return issue if model == lifemap.TOPIC_MODEL else interp

        def fake_window(q, start, end, **kw):
            return company_news.get(q, [])

        basis = {**self.basis(), "rates": rates}
        with mock.patch.object(lifemap, "collect_issue_news", return_value=ARTICLES),                 mock.patch.object(lifemap, "_ask", side_effect=fake_ask),                 mock.patch.object(news, "search_window", side_effect=fake_window) as sw:
            data = lifemap.run_topics(basis)
        return data, calls, sw

    def test_opposite_companies_get_other_reason_once_at_creation(self):
        data, calls, sw = self._topic_with_opposites({"KT": {"article": 1, "reason": "3분기 실적 발표"}})
        companies = {c["name"]: c for s in data["topics"][0]["map"]["stages"] for c in s["companies"]}
        self.assertEqual(companies["KT"]["other"], {"text": "다른 이유로 움직였을 수 있어요: 3분기 실적 발표",
                                                    "title": "KT 3분기 실적 발표, 영업이익 증가", "url": "https://news.example/kt"})
        self.assertEqual(companies["이마트"]["other"], {"text": lifemap.OTHER_FALLBACK})  # 같은 날 기사가 없으면 기본 문구
        self.assertNotIn("other", companies["SK텔레콤"])  # 해석과 같은 방향
        self.assertEqual(len(calls), 1)  # 기사가 있는 회사만 Haiku
        self.assertEqual([x["제목"] for x in calls[0]["기사"]], ["KT 3분기 실적 발표, 영업이익 증가"])  # 이슈 기사는 빼고
        self.assertEqual(sorted(c.args[0] for c in sw.call_args_list), ["KT", "이마트"])

        # 화면을 읽을 때는 AI·검색을 다시 부르지 않고 저장된 것을 쓴다
        with mock.patch.object(lifemap, "_ask", side_effect=AssertionError),                 mock.patch.object(news, "search_window", side_effect=AssertionError):
            view = lifemap.overview()
        shown = {c["name"]: c for s in view["topics"][0]["map"]["stages"] for c in s["companies"]}
        self.assertTrue(shown["KT"]["opposite"])
        self.assertEqual(shown["KT"]["other"]["url"], "https://news.example/kt")
        self.assertFalse(shown["SK텔레콤"]["opposite"])
        self.assertNotIn("other", shown["SK텔레콤"])

    def test_bad_or_unsafe_answer_falls_back(self):
        for answer in ({"article": 0, "reason": "없음"}, {"article": 9, "reason": "실적"}, {"article": 1, "reason": "매수 기회"}):
            data, _, _ = self._topic_with_opposites({"KT": answer})
            kt = next(c for s in data["topics"][0]["map"]["stages"] for c in s["companies"] if c["name"] == "KT")
            self.assertEqual(kt["other"], {"text": lifemap.OTHER_FALLBACK}, answer)

    def test_live_rate_decides_whether_note_shows(self):
        item = {"name": "x", "title": "t", "articles": [], "map": {"word": "x", "basis_label": "10/27 장 기준", "stages": [
            {"key": "p0", "label": "비용", "detail": "", "companies": [
                {"code": "030200", "name": "KT", "relevance": "약", "reason": "r", "direction": "neg", "rate": 7.1,
                 "other": {"text": "다른 이유로 움직였을 수 있어요: 3분기 실적 발표", "url": "https://news.example/kt", "title": "t"}},
                {"code": "017670", "name": "SK텔레콤", "relevance": "강", "reason": "r", "direction": "pos", "rate": 1.0}]}]}}
        lifemap.save_live_rates({"030200": 1.2, "017670": -3.5}, datetime.now(KST))
        out = lifemap.with_reaction(item, lifemap._live_rates())
        kt, skt = out["map"]["stages"][0]["companies"]
        self.assertFalse(kt["opposite"])
        self.assertNotIn("other", kt)  # 장중에 반대가 아니게 되면 숨김
        self.assertTrue(skt["opposite"])
        self.assertEqual(skt["other"], {"text": lifemap.OTHER_FALLBACK})  # 새로 반대가 되면 기본 문구(AI 재호출 없음)


class VersusMarketTest(LifemapBase):
    """시장 대비 = 회사 등락률 − 그 회사 시장 지수 등락률(같은 시각). 10/28처럼 지수가 크게 오른 날 해석이 틀린 것처럼 보이지 않게."""

    IDX = {"KOSPI": 6.63, "KOSDAQ": 3.69}

    def _market(self, kospi=6.63, kosdaq=3.69, as_of="20261027"):
        return {**MARKET, "as_of": as_of, "breadth": {"up": 1729, "down": 818, "flat": 112, "total": 2659},
                "indices": [{"name": "코스피", "as_of": as_of, "same_day": True, "rate": kospi},
                            {"name": "코스닥", "as_of": as_of, "same_day": True, "rate": kosdaq}]}

    def test_basis_carries_same_snapshot_indices_and_breadth(self):
        store.write("market", self._market())
        b = self.basis()
        self.assertEqual(b["indices"], self.IDX)
        self.assertEqual(lifemap.basis_info(b)["indices"], self.IDX)
        self.assertEqual(lifemap.basis_info(b)["breadth"]["up"], 1729)
        # 지수 자료가 종목 시세보다 늦으면(전날 값) 쓰지 않는다
        late = self._market()
        late["indices"][0].update(as_of="20261024", same_day=False)
        self.assertEqual(lifemap.index_rates(late), {"KOSDAQ": 3.69})

    def test_mark_reaction_uses_each_company_market_index(self):
        m = {"stages": [{"companies": [{"code": "030200", "direction": "neg"}, {"code": "042510", "direction": "pos"},
                                        {"code": "053800", "direction": "pos"}]}]}
        basis = {"source": "public", "label": "10/28 장 기준", "rates": {"030200": 2.9, "042510": 18.1, "053800": 5.0},
                 "indices": self.IDX}
        lifemap.mark_reaction(m, basis)
        kt, raon, ahn = m["stages"][0]["companies"]
        self.assertEqual((kt["market_rate"], kt["vs_market"], kt["moved"]), (6.63, -3.73, True))  # KOSPI: 2.9 − 6.63
        self.assertEqual((raon["market_rate"], raon["vs_market"], raon["moved"]), (3.69, 14.41, True))  # KOSDAQ
        self.assertEqual((ahn["vs_market"], ahn["moved"]), (1.31, False))  # 단순 +5%여도 시장 대비 3%p 미만이면 강조 없음
        self.assertEqual(m["indices"], self.IDX)

    def test_opposite_and_other_reason_use_versus_market(self):
        o = lifemap.opposite
        self.assertFalse(o({"direction": "neg", "rate": 2.9, "vs_market": -3.73}))  # 다 오른 날 덜 움직인 '부정 가능'은 반대 아님
        self.assertTrue(o({"direction": "neg", "rate": 10.0, "vs_market": 3.37}))
        self.assertTrue(o({"direction": "pos", "rate": 3.5, "vs_market": -3.13}))   # 올랐어도 시장보다 3%p 넘게 약하면 반대
        self.assertFalse(o({"direction": "pos", "rate": -2.0, "vs_market": -2.9}))  # 3%p 미만
        self.assertTrue(o({"direction": "neg", "rate": 7.1}))  # 지수를 모르면 단순 등락률

        # 이슈를 만들 때: KT(부정, +7.1%)는 단순으론 반대지만 KOSPI +6.63% 대비 +0.47%p → 다른 이유를 찾지 않는다
        interp = {"interpretation": ["유출 기업은 보상 비용이 생길 수 있다."], "paths": [{"label": "보상 비용", "detail": "", "companies": [
            {"name": "KT", "direction": "부정", "link": "직접 당사자", "relevance": "강", "reason": "유출이 알려진 통신사다"},
            {"name": "이마트", "direction": "긍정", "link": "사업 연결", "relevance": "약", "reason": "통신 결합 할인 고객이 많다"}]}]}
        issue = {"topics": [{"title": "통신사 정보 유출", "summary": "고객 정보가 유출됐다", "keyword": "개인정보 유출",
                             "sector": "통신", "articles": [1, 2], "representative": 1}]}
        fake = lambda model, system, task, payload, schema, *a, **kw: (  # noqa: E731
            {"article": 0, "reason": ""} if schema is lifemap.OTHER_SCHEMA else issue if model == lifemap.TOPIC_MODEL else interp)
        basis = {**self.basis(), "rates": {"030200": 7.1, "139480": 2.0}, "indices": self.IDX}
        with mock.patch.object(lifemap, "collect_issue_news", return_value=ARTICLES), \
                mock.patch.object(lifemap, "_ask", side_effect=fake), \
                mock.patch.object(news, "search_window", return_value=[]) as sw:
            data = lifemap.run_topics(basis)
        companies = {c["name"]: c for s in data["topics"][0]["map"]["stages"] for c in s["companies"]}
        self.assertNotIn("other", companies["KT"])
        self.assertEqual(companies["이마트"]["vs_market"], -4.63)  # 긍정 해석, 시장보다 4.63%p 약함 → 반대
        self.assertEqual(companies["이마트"]["other"], {"text": lifemap.OTHER_FALLBACK})
        self.assertEqual([c.args[0] for c in sw.call_args_list], ["이마트"])

    def test_with_reaction_pairs_rates_with_same_time_indices(self):
        item = {"name": "x", "title": "t", "articles": [], "map": {"word": "x", "basis_label": "10/28 종가 기준", "indices": self.IDX,
                "stages": [{"key": "p0", "label": "수요", "detail": "", "companies": [
                    {"code": "030200", "name": "KT", "relevance": "강", "reason": "r", "direction": "neg", "rate": 2.9,
                     "market_rate": 6.63, "vs_market": -3.73},
                    {"code": "053800", "name": "안랩", "relevance": "강", "reason": "r", "direction": "pos"}]}]}}
        out = lifemap.with_reaction(item, None, {"KOSDAQ": 1.0})
        kt, ahn = out["map"]["stages"][0]["companies"]
        self.assertEqual((kt["vs_market"], kt["moved"], kt["opposite"]), (-3.73, True, False))  # 생성 때 값 + 생성 때 지수
        self.assertEqual((ahn["rate"], ahn["market_rate"], ahn["vs_market"]), (9.4, 1.0, 8.4))  # 최신 종가 + 그날 공공 지수
        # 키움 장중: 같이 읽은 지수로
        lifemap.save_live_rates({"030200": 1.0}, datetime.now(KST), indices={"KOSPI": -2.0})
        kt = lifemap.with_reaction(item, lifemap._live_rates())["map"]["stages"][0]["companies"][0]
        self.assertEqual((kt["rate"], kt["vs_market"], kt["opposite"]), (1.0, 3.0, True))
        self.assertEqual(kt["other"], {"text": lifemap.OTHER_FALLBACK})
        # 지수 없이 저장된 장중 값은 시장 대비를 비우고(단순 기준), 수집기가 한 번 다시 읽는다
        store.write("lifemap", {"topics": [item]})
        lifemap.save_live_rates({"030200": 1.0, "053800": 1.0}, datetime.now(KST))
        saved = store.read("lifemap_rates")
        saved.pop("indices")
        store.write("lifemap_rates", saved)
        self.assertIsNone(lifemap.with_reaction(item, lifemap._live_rates())["map"]["stages"][0]["companies"][0]["vs_market"])
        self.assertTrue(lifemap.rates_due(datetime.now(KST)))

    def test_index_news_goes_to_mood_band_not_issue_cards(self):
        self.assertTrue(lifemap.index_news({"name": "코스피 6000 탈환", "title": "코스피 6000 탈환, 반도체 급등"}))
        self.assertTrue(lifemap.index_news({"name": "증시 급락", "title": "증시 급락 마감"}))
        self.assertFalse(lifemap.index_news({"name": "유가 급등", "title": "국제유가 급등"}))
        issue = {"topics": [{"title": "코스피 6000 탈환, 반도체 급등", "summary": "코스피 6.63% 급등", "keyword": "코스피 6000 탈환",
                             "sector": "반도체", "articles": [1, 2], "representative": 1},
                            {"title": "국제유가 급등", "summary": "중동 정세로 유가가 올랐다", "keyword": "유가 급등",
                             "sector": "정유", "articles": [3, 4], "representative": 3}]}
        with mock.patch.object(lifemap, "_ask", return_value=issue):
            picked = lifemap.pick_issues(self.basis(), ARTICLES)
        self.assertEqual([t["name"] for t in picked], ["유가 급등"])
        self.assertEqual(lifemap._last_rejects, {"market": 1})
        self.assertIn("지수 등락 자체", lifemap.TOPIC_SYSTEM)
        # 예전에 저장된 지수 시황 이슈도 화면 후보에서 뺀다
        idx = _topic("코스피 6000 탈환", "코스피 6000 탈환", "반도체", "u:kospi")
        store.write("lifemap", {"basis": {"key": "public:20261027"}, "topics": [
            idx, _topic("유가 급등", "국제유가 급등", "정유", "u:oil"), _topic("관세 협상", "관세 협상", "자동차", "u:car"),
            _topic("LNG 수주", "LNG선 수주", "조선", "u:ship")]})
        self.assertEqual(lifemap.overview()["hot"], ["유가 급등", "관세 협상", "LNG 수주"])

    def test_market_mood_band(self):
        store.write("market", self._market())
        store.write("lifemap", {"basis": lifemap.basis_info(self.basis()), "topics": []})
        mood = lifemap.overview()["market"]
        self.assertEqual(mood["text"], "코스피 +6.63% · 코스닥 +3.69% · 대부분 종목이 올랐어요")
        self.assertEqual([i["name"] for i in mood["indices"]], ["코스피", "코스닥"])
        down = lifemap.market_mood({"indices": {"KOSPI": -2.1}, "breadth": {"up": 100, "down": 900, "total": 1000}, "label": "x"}, None)
        self.assertEqual(down["text"], "코스피 -2.10% · 대부분 종목이 내렸어요")
        mixed = lifemap.market_mood({"indices": {"KOSPI": 0.3, "KOSDAQ": -0.2}, "breadth": {"up": 500, "down": 450, "total": 1000}}, None)
        self.assertEqual(mixed["crowd"], "오른 종목과 내린 종목이 섞여 있어요")
        self.assertIsNone(lifemap.market_mood({"label": "x"}, None))  # 지수가 없으면 띠를 숨긴다
        live = {"indices": {"KOSPI": 1.2, "KOSDAQ": 0.4}, "label": "10/29 11:00 장중", "as_of": "20261029"}
        self.assertEqual(lifemap.market_mood({"indices": self.IDX}, live)["label"], "10/29 11:00 장중")  # 장중 갱신값 우선


class SectorScheduleTest(LifemapBase):
    """섹터 이슈 10개는 하루 한 번(장 마감 뒤 기준)만. 키움 장중 재생성은 오늘의 이슈만."""

    def _run(self, basis):
        ran = []

        class SyncThread:
            def __init__(self, target, **kw):
                self.target = target

            def start(self):
                self.target()

        with mock.patch.object(lifemap, "topic_basis", return_value=basis), \
                mock.patch.object(lifemap, "run_topics", side_effect=lambda b, **k: ran.append("topics")), \
                mock.patch.object(lifemap, "run_sectors", side_effect=lambda b, **k: (ran.append("sectors"), store.write(
                    "lifemap_sectors", {"basis": lifemap.basis_info(b), "items": {}}))), \
                mock.patch.object(lifemap.budget, "allowed", return_value=True), \
                mock.patch.object(lifemap.threading, "Thread", SyncThread):
            started = lifemap.maybe_run_daily()
        return started, ran

    def test_open_makes_topics_only_close_makes_sectors_once(self):
        def kb(kind):
            return {"key": f"kiwoom:20261029:{kind}", "source": "kiwoom", "as_of": "20261029", "label": "x", "window": None, "rates": {}}

        store.write("lifemap_sectors", {"basis": {"key": "kiwoom:20261028:close", "as_of": "20261028"}, "items": {}})
        self.assertEqual(self._run(kb("open")), (True, ["topics"]))       # 장중: 오늘의 이슈만
        self.assertFalse(lifemap.sectors_due(kb("open")))
        store.write("lifemap_status", {})  # 실제로는 장중(10시)과 마감(15:35) 사이가 30분보다 길다
        self.assertEqual(self._run(kb("close")), (True, ["topics", "sectors"]))  # 마감 뒤: 이슈 + 섹터
        store.write("lifemap", {"basis": {"key": "kiwoom:20261029:close"}, "fresh": 5})
        self.assertEqual(self._run(kb("close")), (False, []))             # 같은 날 다시 만들지 않음
        public_same_day = {"key": "public:20261029", "source": "public", "as_of": "20261029", "label": "x", "window": None, "rates": {}}
        self.assertFalse(lifemap.sectors_due(public_same_day))  # 다음 날 공공 기준(같은 날 시세)으로도 다시 만들지 않음
        self.assertTrue(lifemap.sectors_due({**public_same_day, "key": "public:20261030", "as_of": "20261030"}))


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
        limited = lifemap.request_word("단어x", "same")
        self.assertEqual(limited["status"], "limited")
        self.assertIn("지금 뜨는 이슈", limited["message"])
        for i in range(lifemap.LIVE_QUEUE_MAX - lifemap.LIVE_PER_SESSION):
            lifemap.request_word(f"다른{i}", f"s{i}")
        busy = lifemap.request_word("넘침", "new")
        self.assertEqual(busy["status"], "busy")
        self.assertTrue(busy["item"]["map"]["stages"])
        self.assertEqual(lifemap.request_word("<b>", "new")["status"], "invalid")
        lifemap._jobs.clear()
        store.write("lifemap_live_count", {"day": datetime.now(KST).strftime("%Y-%m-%d"), "n": lifemap.live_daily_limit()["max"]})
        lifemap._live_count.clear()
        over = lifemap.request_word("상한", "other")
        self.assertEqual(over["status"], "daily_limit")
        self.assertIn("지금 뜨는 이슈", over["message"])
        with mock.patch.object(ai, "available", return_value=False):
            self.assertEqual(lifemap.request_word("키없음", "other")["status"], "unavailable")


class DailyLimitByDateTest(LifemapBase):
    """직접 입력 하루 상한: 평소 50개, 시연 주간(11/14~11/17 KST) 400개 — 날짜로 자동 전환."""

    def test_switches_by_kst_date(self):
        def at(y, m, d, h=12):
            return datetime(y, m, d, h, tzinfo=KST)
        self.assertEqual(lifemap.live_daily_limit(at(2026, 11, 13, 23))["max"], 50)
        self.assertEqual(lifemap.live_daily_limit(at(2026, 11, 14, 0))["max"], 400)
        self.assertEqual(lifemap.live_daily_limit(at(2026, 11, 17, 23))["max"], 400)
        self.assertEqual(lifemap.live_daily_limit(at(2026, 11, 18, 0))["max"], 50)
        # UTC 11/13 15:00 = KST 11/14 00:00 → 시연 주간
        utc = datetime(2026, 11, 13, 15, tzinfo=timezone.utc)
        self.assertTrue(lifemap.live_daily_limit(utc)["demo_week"])

    def test_request_uses_todays_limit(self):
        today = datetime.now(KST).strftime("%Y-%m-%d")
        for limit, n, expect in ((50, 50, "daily_limit"), (50, 49, "queued"), (400, 50, "queued"), (400, 400, "daily_limit")):
            lifemap._jobs.clear()
            lifemap._sessions.clear()
            lifemap._live_count.clear()
            store.write("lifemap_live_count", {"day": today, "n": n})
            with mock.patch.object(lifemap, "live_daily_limit", return_value={"max": limit}):
                self.assertEqual(lifemap.request_word(f"단어{limit}{n}", f"p{limit}{n}")["status"], expect, (limit, n))

    def test_admin_status_shows_current_limit(self):
        from services.stockon import service
        live = service._lifemap_status()["live_limit"]
        self.assertIn(live["max"], (50, 400))
        self.assertEqual((live["normal"], live["demo"], live["demo_from"], live["demo_to"]), (50, 400, "2026-11-14", "2026-11-17"))


class HundredPeopleTest(LifemapBase):
    """시연 기준(11/17, 100명): 100명이 동시에 서로 다른 새 단어를 누르고, 동시에 화면을 읽는다."""

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
            with ThreadPoolExecutor(max_workers=100) as people:
                results = list(people.map(lambda i: lifemap.request_word(f"단어{i:02d}", f"person{i}"), range(100)))
                t0 = time.time()
                list(people.map(lambda i: lifemap.overview(), range(100)))
                read_sec = time.time() - t0
            real_pool.shutdown(wait=True)
        statuses = [r["status"] for r in results]
        self.assertEqual(statuses.count("queued"), lifemap.LIVE_QUEUE_MAX)
        self.assertEqual(statuses.count("busy"), 100 - lifemap.LIVE_QUEUE_MAX)
        self.assertTrue(all(r["item"]["map"]["stages"] for r in results if r["status"] == "busy"))
        self.assertTrue(all("지금 뜨는 이슈" in r["message"] for r in results if r["status"] == "busy"))
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
            self.assertEqual(client.get("/api/stock/lifemap/pulse").status_code, 200)
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


def _topic(name, title, sector, url, summary="요약"):
    return {**EXAMPLE_ITEM, "name": name, "title": title, "summary": summary, "sector": sector,
            "articles": [{"title": f"{title} 기사", "url": url, "press": "a.kr", "pub": None, "rep": True}],
            "map": {**EXAMPLE_ITEM["map"], "word": name}}


class CurationTest(LifemapBase):
    """시연 안전장치: 숨기기·순서·제외 키워드·금융회사 사고 이슈는 첫 카드 아님. 설정은 수집기가 다시 만들어도 남는다."""

    def setUp(self):
        super().setUp()
        self.bank = _topic("은행 정보 유출", "A은행 고객정보 유출 제재", "금융", "u:bank")
        self.chip = _topic("HBM 수출", "반도체 수출 증가", "반도체", "u:chip")
        self.car = _topic("관세 협상", "자동차 관세 협상 타결", "자동차", "u:car")
        self.oil = _topic("유가 급등", "국제유가 급등", "정유", "u:oil")
        self.ship = _topic("LNG 수주", "조선 LNG선 수주", "조선", "u:ship")
        self.write([self.bank, self.chip, self.car], [self.oil, self.ship])

    def write(self, topics, reserve=()):
        store.write("lifemap", {"day": "2026-10-28", "basis": {"key": "public:20261027"}, "topics": topics, "reserve": list(reserve)})

    def names(self):
        return lifemap.overview()["hot"]

    def test_fin_incident_not_first_by_default_and_toggle(self):
        self.assertTrue(lifemap.fin_incident(self.bank))
        self.assertFalse(lifemap.fin_incident(self.chip))
        self.assertTrue(lifemap.fin_incident(_topic("카드 과징금", "신한카드 과징금", "기타", "u:x")))
        self.assertFalse(lifemap.fin_incident(_topic("공장 화재", "배터리 공장 화재 사고", "2차전지", "u:y")))
        self.assertFalse(lifemap.fin_incident(_topic("금리 인하", "은행 대출 금리 인하", "금융", "u:z")))
        self.assertEqual(self.names(), ["HBM 수출", "은행 정보 유출", "관세 협상"])
        lifemap.set_fin_first(False)
        self.assertEqual(self.names(), ["은행 정보 유출", "HBM 수출", "관세 협상"])

    def test_admin_order_wins_and_resets_next_day(self):
        lifemap.set_order(["u:car", "u:bank"])
        self.assertEqual(self.names(), ["관세 협상", "은행 정보 유출", "HBM 수출"])
        lifemap.set_order(["u:ship"])  # 다음 후보도 첫 화면으로 끌어올 수 있다
        self.assertEqual(self.names(), ["LNG 수주", "은행 정보 유출", "HBM 수출"])  # 지정하지 않은 것은 원래 순서
        tomorrow = (datetime.now(KST) + timedelta(days=1)).strftime("%Y-%m-%d")  # 실제 오늘과 겹치지 않게
        with mock.patch.object(lifemap, "_today", return_value=tomorrow):
            self.assertEqual(self.names(), ["HBM 수출", "은행 정보 유출", "관세 협상"])  # 날짜가 바뀌면 순서만 초기화

    def test_hide_fills_from_reserve_then_sectors_and_survives_regeneration(self):
        lifemap.set_hidden("u:chip", True)
        self.assertEqual(self.names(), ["관세 협상", "은행 정보 유출", "유가 급등"])
        # 수집기가 다시 만들어 대표 기사가 바뀌어도 같은 이름이면 숨김 유지
        self.write([{**self.chip, "articles": [{**self.chip["articles"][0], "url": "u:chip2"}]}, self.bank, self.car], [self.oil])
        self.assertNotIn("HBM 수출", self.names())
        lifemap.set_hidden("u:oil", True)
        lifemap.set_hidden("u:car", True)
        store.write("lifemap_sectors", {"basis": {"key": "public:20261027"}, "items": {"조선": self.ship}})
        self.assertEqual(self.names(), ["LNG 수주", "은행 정보 유출", "예시이슈"])  # 오늘 후보로 모자라면 예시까지, 3개 유지
        with mock.patch.object(lifemap, "_today", return_value="2026-11-02"):
            self.assertNotIn("관세 협상", self.names())  # 숨김은 날짜가 바뀌어도 남는다
        lifemap.set_hidden("u:chip2", False)
        self.assertIn("HBM 수출", self.names())
        with self.assertRaises(KeyError):
            lifemap.set_hidden("u:none", True)

    def test_exclude_words_hide_by_title_or_rep_article(self):
        lifemap.set_words(["a은행", " 반도체 수출 "])
        self.assertEqual(self.names(), ["관세 협상", "유가 급등", "LNG 수주"])
        lifemap.set_words(["관세 협상 타결 기사"])  # 대표 기사 제목도 본다(띄어쓰기 무시)
        self.assertNotIn("관세 협상", self.names())
        store.write("lifemap_sectors", {"basis": {"key": "public:20261027"}, "items": {"보안": {**self.car, "name": "보안"}}})
        self.assertEqual(lifemap.overview()["sector_items"]["보안"]["name"], "보안")
        self.assertTrue(lifemap.overview()["sector_items"]["보안"].get("example"))  # 걸린 섹터 이슈는 예시로
        admin = lifemap.admin_curation()
        by = {i["key"]: i for i in admin["items"]}
        self.assertEqual(by["u:car"]["excluded_by"], "관세 협상 타결 기사")
        self.assertTrue(by["u:bank"]["fin_incident"])
        self.assertEqual([by[k]["source"] for k in ("u:chip", "u:oil")], ["topic", "reserve"])

    def test_run_topics_keeps_reserve(self):
        issues = {"topics": [{"title": f"이슈 {i}", "summary": "요약", "keyword": f"이슈{i}", "sector": f"섹터{i}",
                              "articles": [2 * i + 1, 2 * i + 2], "representative": 2 * i + 1} for i in range(6)]}
        arts = [{**a, "press": f"p{i}.kr", "title": f"이슈{i // 2} 소식 {i}"} for i, a in enumerate(ARTICLES)]
        with mock.patch.object(lifemap, "collect_issue_news", return_value=arts), \
                mock.patch.object(lifemap, "_ask", side_effect=lambda m, *a, **k: issues if m == lifemap.TOPIC_MODEL else INTERP):
            data = lifemap.run_topics(self.basis())
        self.assertEqual(len(data["topics"]), lifemap.TOPICS_MAX)
        self.assertEqual([t["name"] for t in data["reserve"]], ["이슈5"])
        self.assertEqual(len(lifemap.overview()["topics"]), lifemap.TOPICS_MAX)

    def test_admin_api_requires_admin(self):
        from fastapi.testclient import TestClient
        from api.main import app
        from services import access as ac

        with mock.patch.dict("os.environ", {"ADMIN_PASSWORD": "pw-test", "ACCESS_SECRET": "test-secret"}):
            client = TestClient(app)
            self.assertEqual(client.get("/api/stock/admin/lifemap").status_code, 401)
            self.assertEqual(client.post("/api/stock/admin/lifemap", json={"action": "hide", "key": "u:chip"}).status_code, 401)
            h = {"Authorization": f"Bearer {ac._sign({'r': 'admin', 'exp': 9999999999})}"}
            r = client.post("/api/stock/admin/lifemap", json={"action": "hide", "key": "u:chip"}, headers=h)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(next(i for i in r.json()["items"] if i["key"] == "u:chip")["hidden"])
            self.assertEqual(client.post("/api/stock/admin/lifemap", json={"action": "hide", "key": "u:no"}, headers=h).status_code, 404)
            r = client.post("/api/stock/admin/lifemap", json={"action": "words", "words": ["관세"]}, headers=h)
            self.assertEqual(r.json()["words"], ["관세"])
            self.assertEqual(client.get("/api/stock/admin/lifemap", headers=h).json()["fin_first"], True)


def _art(title, press, pub="2026-10-27T10:00:00+09:00", url=None):
    return {"title": title, "press": press, "pub": pub, "url": url or f"https://news.example/{abs(hash(title))}", "snippet": ""}


class PurposeTest(LifemapBase):
    """핵심 목적: 일상 뉴스 → 연결된 상장사. 증권 기사 제외·핵심 사건 중심·거시 이슈 1개·오늘 실제 방향·시점·누적·잡음 구간."""

    def test_stock_articles_are_excluded_and_kept_as_examples(self):
        sa = lifemap.stock_article
        self.assertEqual(sa({"title": "현대차 3분기 영업익 2조6772억, 판매 11% 감소"}), "실적·공시")
        self.assertEqual(sa({"title": "한화솔루션 3분기 흑자전환"}), "실적·공시")
        self.assertEqual(sa({"title": "[특징주] 안랩, 해킹 소식에 상한가"}), "특징주·관련주")
        self.assertEqual(sa({"title": "코스피, 외국인 매도에 2% 하락"}), "시황·지수")
        for ok in ("금융권 해킹 잇따라, 가상자산 1억 탈취", "아이폰 듀오 화면 결함 논란", "국제유가 3% 하락", "공시가격 현실화 발표"):
            self.assertEqual(sa({"title": ok}), "", ok)
        arts = [_art("금융권 해킹 잇따라", "a.kr"), _art("금융권 해킹 피해 확산", "b.kr"),
                _art("현대차 3분기 영업익 2조6772억", "c.kr"), _art("[특징주] 보안주 급등", "d.kr")]
        raw = {"topics": [{"title": "금융권 해킹", "summary": "해킹이 잇따랐다", "keyword": "금융권 해킹", "field": "보안 사고",
                           "macro": False, "sector": "금융", "articles": [1, 2], "representative": 1},
                          {"title": "현대차 실적", "summary": "영업익이 줄었다", "keyword": "현대차 실적", "field": "산업 동향",
                           "macro": False, "sector": "자동차", "articles": [1, 2], "representative": 1}]}
        with mock.patch.object(lifemap, "_ask", return_value=raw) as ask:
            topics = lifemap.pick_issues(self.basis(), arts)
        sent = [a["제목"] for a in ask.call_args.args[3]["기사"]]
        self.assertEqual(sent, ["금융권 해킹 잇따라", "금융권 해킹 피해 확산"])  # 증권 기사는 AI에 주지도 않는다
        self.assertEqual([t["name"] for t in topics], ["금융권 해킹"])
        self.assertEqual((topics[0]["field"], topics[0]["macro"]), ("보안 사고", False))
        self.assertEqual(lifemap._last_rejects, {"stock": 1})  # 이슈 이름이 실적이면 빠진다
        self.assertEqual([(e["rule"], e["title"]) for e in lifemap._last_excluded],
                         [("실적·공시", "현대차 3분기 영업익 2조6772억"), ("특징주·관련주", "[특징주] 보안주 급등")])
        self.assertIn("일상 뉴스", lifemap.TOPIC_SYSTEM)
        self.assertIn("부수 주제", lifemap.TOPIC_SYSTEM)

    def test_center_must_be_the_core_event_and_one_macro(self):
        arts = [_art("정유업계 정제마진 개선", "a.kr"), _art("화학 업황 바닥 신호", "b.kr"),
                _art("한은 기준금리 동결", "c.kr"), _art("기준금리 3연속 동결", "d.kr"),
                _art("원달러 환율 1400원 돌파", "e.kr"), _art("환율 급등에 수입물가 비상", "f.kr")]
        raw = {"topics": [
            {"title": "유가 하락", "summary": "요약문에만 국제유가가 나온다", "keyword": "국제유가 하락", "field": "유가·원자재",
             "macro": False, "sector": "화학", "articles": [1, 2], "representative": 1},  # 제목에 없는 부수 주제
            {"title": "기준금리 동결", "summary": "한은이 동결했다", "keyword": "기준금리 동결", "field": "환율·금리",
             "macro": True, "sector": "은행", "articles": [3, 4], "representative": 3},
            {"title": "환율 급등", "summary": "환율이 올랐다", "keyword": "환율 급등", "field": "환율·금리",
             "macro": False, "sector": "항공", "articles": [5, 6], "representative": 5},  # 거시 두 번째(이름으로 판단)
        ]}
        with mock.patch.object(lifemap, "_ask", return_value=raw):
            topics = lifemap.pick_issues(self.basis(), arts)
        self.assertEqual([(t["name"], t["macro"]) for t in topics], [("기준금리 동결", True)])
        self.assertEqual(lifemap._last_rejects, {"center": 1, "macro": 1})
        self.assertTrue(lifemap.centered("아이폰 듀오 결함", ["아이폰 듀오 화면 결함", "듀오 결함 리콜"]))
        self.assertFalse(lifemap.centered("국제유가", ["한화솔루션 흑자", "국제유가 하락"]))  # 대표 기사 제목에 없음

    def test_macro_expectation_line_and_weak_relevance(self):
        raw = {"interpretation": ["대출 이자 부담이 이어질 수 있다."], "move": {"subject": "금리", "today": "보합"},
               "expected": "예상대로", "paths": [{"label": "이자 부담", "detail": "", "companies": [
                   {"name": "KT", "direction": "부정", "link": "사업 연결", "relevance": "강", "reason": "차입금이 많은 통신사다"},
                   {"name": "이마트", "direction": "부정", "link": "사업 연결", "relevance": "중", "reason": "소비 위축 영향을 받는다"}]}]}
        arts = [_art("기준금리 동결, KT 등 차입 많은 기업 이자 부담 지속", "a.kr")]
        with mock.patch.object(lifemap, "_ask", return_value=raw) as ask:
            m = lifemap.interpret("기준금리 동결", arts, macro=True)
        self.assertTrue(ask.call_args.args[3]["거시 이슈"])
        self.assertEqual(m["interpretation"][0], lifemap.EXPECTED_LINE["예상대로"])  # 첫 줄 = 시장 예상과 같았는지
        self.assertEqual((m["macro"], m["expected"], m["move"]), (True, "예상대로", {"subject": "금리", "today": "보합"}))
        rel = {c["name"]: c["relevance"] for c in m["stages"][0]["companies"]}
        self.assertEqual(rel, {"KT": "강", "이마트": "약"})  # 기사에 직접 나온 회사만 AI 연관도, 나머지는 '약'
        with mock.patch.object(lifemap, "_ask", return_value={**raw, "expected": "해당 없음"}):
            m = lifemap.interpret("유가 하락", arts)  # 거시 이슈가 아니면 그대로
        self.assertNotIn("macro", m)
        self.assertEqual(m["interpretation"], ["대출 이자 부담이 이어질 수 있다."])

    def test_two_way_issue_direction(self):
        raw = {**INTERP, "move": {"subject": "유가", "today": "하락"}, "expected": "해당 없음"}
        with mock.patch.object(lifemap, "_ask", return_value=raw):
            m = lifemap.interpret("국제유가 하락", [])
        self.assertEqual(m["move"], {"subject": "유가", "today": "하락"})
        self.assertIn("실제 방향 기준", lifemap.INTERP_SYSTEM)
        with mock.patch.object(lifemap, "_ask", return_value={**raw, "move": {"subject": "환율", "today": "불확실"}}):
            m = lifemap.interpret("환율", [])
        self.assertEqual({c["direction"] for s in m["stages"] for c in s["companies"]}, {"unk"})  # 방향 불확실 → '영향 가능'만
        self.assertFalse(lifemap.opposite({"direction": "unk", "rate": 9.0, "vs_market": 9.0}))
        with mock.patch.object(lifemap, "_ask", return_value={**raw, "move": {"subject": "", "today": "해당 없음"}}):
            self.assertNotIn("move", lifemap.interpret("해킹", []))

    def test_reaction_day_after_close_weekend_and_holiday(self):
        rd = lambda s: lifemap.reaction_day(datetime.fromisoformat(s))  # noqa: E731
        self.assertEqual(rd("2026-10-29T15:19:00+09:00"), ("20261029", False))
        self.assertEqual(rd("2026-10-29T15:20:00+09:00"), ("20261030", True))
        self.assertEqual(rd("2026-10-30T18:00:00+09:00"), ("20261102", True))  # 금요일 저녁 → 월요일
        self.assertEqual(rd("2026-10-31T10:00:00+09:00"), ("20261102", True))  # 토요일
        self.assertEqual(rd("2026-12-24T16:00:00+09:00"), ("20261228", True))  # 성탄절 휴장·주말
        self.assertEqual(rd("2026-10-29T06:19:00Z"), ("20261029", False))  # UTC로 저장돼도 KST로 본다(15:19 KST)
        self.assertEqual(rd("2026-10-29T06:20:00Z"), ("20261030", True))

    def test_first_report_uses_earliest_matching_article(self):
        context = [_art("금융권 해킹 잇따라", "a.kr", "2026-10-29T15:17:00+09:00")]
        searched = [_art("금융권 해킹 첫 신고", "b.kr", "2026-10-27T18:05:00+09:00"),
                    _art("해킹 보험 출시", "c.kr", "2026-10-26T09:00:00+09:00"),  # '금융권'이 없음 → 다른 사건
                    _art("[특징주] 금융권 해킹에 보안주 상한가", "d.kr", "2026-10-25T09:00:00+09:00"),  # 증권 기사
                    _art("금융권 해킹 옛 기사", "e.kr", "2026-10-10T09:00:00+09:00")]  # 7일 밖
        end = datetime(2026, 10, 29, 16, 0, tzinfo=KST)
        with mock.patch.object(news, "search", return_value=searched) as s:
            first = lifemap.first_report("금융권 해킹", context, end)
        self.assertEqual(s.call_args.args[0], "금융권 해킹")
        self.assertEqual((first["pub"], first["press"]), ("2026-10-27T18:05:00+09:00", "b.kr"))
        with mock.patch.object(news, "search", side_effect=news.NewsError("network")):
            self.assertEqual(lifemap.first_report("금융권 해킹", context, end)["press"], "a.kr")  # 검색 실패 → 이슈 기사 중 가장 이른 것

    def _item(self, first_pub, as_of="20261029", rate=-9.74, hist=None):
        c = {"code": "053800", "name": "안랩", "relevance": "강", "reason": "r", "direction": "pos", "rate": rate}
        if hist is not None:
            c["hist"] = hist
        return {"name": "금융권 해킹", "title": "t", "articles": [], "first": {"pub": first_pub, "title": "첫 기사", "url": "u", "press": "p"},
                "map": {"word": "x", "basis_label": "10/29 종가 기준", "as_of": as_of, "indices": {"KOSDAQ": -2.41},
                        "stages": [{"key": "p0", "label": "보안 수요", "detail": "", "companies": [c]}]}}

    def test_after_close_news_waits_for_next_trading_day(self):
        item = self._item("2026-10-29T15:26:00+09:00")
        out = lifemap.with_reaction(item)
        c = out["map"]["stages"][0]["companies"][0]
        t = out["map"]["timing"]
        self.assertEqual((t["after_close"], t["reaction_day"], t["waiting"], t["first"]), (True, "20261030", True, "10/29 15:26"))
        self.assertEqual((c["waiting"], c["moved"], c["opposite"]), (True, False, False))  # 반응 대기 중: 등락으로 판단하지 않음
        self.assertNotIn("since", c)
        # 다음 거래일 키움 장중 값이 들어오면 그 값과 비교
        live = {"as_of": "20261030", "rates": {"053800": 1.5}, "indices": {"KOSDAQ": -0.5}, "label": "10/30 10:00 장중"}
        out = lifemap.with_reaction(item, live)
        c = out["map"]["stages"][0]["companies"][0]
        self.assertEqual((c["waiting"], c["vs_market"], out["map"]["timing"]["waiting"]), (False, 2.0, False))
        self.assertEqual(c["since"], {"rate": 1.5, "vs": 2.0, "days": 1, "from": "10/30", "to": "10/30",
                                      "trail": [{"d": "10/30", "vs": 2.0}]})
        self.assertFalse(c["reflected"])

    def test_cumulative_since_first_report_and_already_reflected(self):
        # 10/27 18:05 첫 보도 → 반응 10/28. 10/28 공공데이터(+8%, 코스닥 +2%) + 10/29 기준 값(−9.74%, 코스닥 −2.41%)
        item = self._item("2026-10-27T18:05:00+09:00", hist=[{"d": "20261028", "r": 8.0, "i": 2.0}])
        c = lifemap.with_reaction(item)["map"]["stages"][0]["companies"][0]
        self.assertEqual(c["vs_market"], -7.33)
        self.assertEqual(c["since"]["days"], 2)
        self.assertEqual(c["since"]["from"], "10/28")
        self.assertAlmostEqual(c["since"]["rate"], round((1.08 * (1 - 0.0974) - 1) * 100, 2))
        self.assertAlmostEqual(c["since"]["vs"], round((1.08 * (1 - 0.0974) - 1.02 * (1 - 0.0241)) * 100, 2))
        self.assertFalse(c["reflected"])  # 둘 다 시장보다 약함(같은 방향)
        up = lifemap.with_reaction(self._item("2026-10-27T18:05:00+09:00", rate=-5.0, hist=[{"d": "20261028", "r": 15.0, "i": 0.0}]))
        c = up["map"]["stages"][0]["companies"][0]
        self.assertTrue(c["since"]["vs"] > 0 > c["vs_market"])
        self.assertTrue(c["reflected"])  # 오늘은 시장보다 약하지만 첫 보도 이후로는 강함 → 이미 반영됐을 수 있어요
        gap = lifemap.with_reaction(self._item("2026-10-26T18:05:00+09:00", hist=[{"d": "20261028", "r": 1.0, "i": 0.0}]))
        self.assertNotIn("since", gap["map"]["stages"][0]["companies"][0])  # 10/27 값이 빠지면 누적을 비운다
        self.assertNotIn("hist", gap["map"]["stages"][0]["companies"][0])  # 일별 값은 화면에 보내지 않는다
        five = lifemap.since_first([{"d": d, "r": 1.0, "i": 0.0} for d in ("20261020", "20261021", "20261022", "20261023", "20261026", "20261027")],
                                   "20261028", 1.0, 0.0, "20261020")
        self.assertEqual((five["days"], five["to"]), (5, "10/26"))  # 최대 5거래일

    def test_add_history_uses_public_daily_rates(self):
        store.write("market", {**MARKET, "as_of": "20261028", "indices": [
            {"name": "코스닥", "series": [{"d": "20261026", "c": 100.0}, {"d": "20261027", "c": 102.0}, {"d": "20261028", "c": 101.0}]}]})
        m = {"as_of": "20261029", "stages": [{"companies": [{"code": "053800"}]}]}
        with mock.patch.object(lifemap.public_data, "stock_history", return_value={"20261027": 3.0, "20261028": -1.0}) as h:
            self.assertEqual(lifemap.add_history(m, "20261027"), 1)
        self.assertEqual(h.call_args.args, ("053800", "20261027", "20261028"))
        self.assertEqual(m["stages"][0]["companies"][0]["hist"], [{"d": "20261027", "r": 3.0, "i": 2.0}, {"d": "20261028", "r": -1.0, "i": -0.98}])
        with mock.patch.object(lifemap.public_data, "stock_history") as h:
            self.assertEqual(lifemap.add_history(m, "20261029"), 0)  # 반응 거래일 = 기준일이면 부르지 않음
        h.assert_not_called()

    def test_run_topics_stores_first_report_and_skips_opposites_while_waiting(self):
        late = [{**a, "pub": "2026-10-27T16:00:00+09:00"} for a in ARTICLES]  # 10/27 장 마감 뒤 → 반응 10/28, 기준은 10/27
        issue = {"topics": [{"title": "통신사 개인정보 유출", "summary": "고객 정보가 유출됐다", "keyword": "개인정보 유출",
                             "field": "보안 사고", "macro": False, "sector": "보안", "articles": [1, 2], "representative": 1}]}
        with mock.patch.object(lifemap, "collect_issue_news", return_value=late), \
                mock.patch.object(lifemap, "_ask", side_effect=lambda m, *a, **k: issue if m == lifemap.TOPIC_MODEL else INTERP), \
                mock.patch.object(lifemap, "explain_opposites") as ex:
            data = lifemap.run_topics(self.basis())
        t = data["topics"][0]
        self.assertEqual(t["first"]["pub"], "2026-10-27T16:00:00+09:00")
        ex.assert_not_called()
        view = lifemap.overview()["topics"][0]
        self.assertEqual(view["map"]["timing"]["reaction_day"], "20261028")
        self.assertTrue(view["map"]["timing"]["waiting"])
        self.assertEqual(store.read("lifemap_status")["excluded"], 0)

    def test_noise_band(self):
        self.assertTrue(lifemap.similar(2.0))
        self.assertTrue(lifemap.similar(-1.5))
        self.assertFalse(lifemap.similar(2.1))
        self.assertFalse(lifemap.similar(None))
        self.assertFalse(lifemap.opposite({"direction": "pos", "rate": -2.0, "vs_market": -2.0}))  # 잡음 구간은 반대 아님
        self.assertTrue(lifemap.big_move(1.0, 3.0))  # 빛나는 테두리 기준 ±3%p 유지

    def test_screen_has_no_simple_rate_wording(self):
        from pathlib import Path
        root = Path(lifemap.__file__).resolve().parents[2] / "web/src/components/stock"
        for name in ("LifeFinder.tsx", "MindMap.tsx"):
            for line in (root / name).read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("//"):
                    continue
                self.assertNotIn("단순", line, f"{name}: {line.strip()}")
        text = (root / "LifeFinder.tsx").read_text(encoding="utf-8")
        for phrase in ("시장보다 = 그 회사 주가 등락 − 시장 지수 등락", "시장과 비슷해요", "시장보다 많이 올랐어요", "첫 보도 이후",
                       "장 마감 후 뉴스 · 다음 거래일 반응을 보여드려요", "반응 대기 중", "시장 전체 영향 이슈", "예상대로",
                       "첫 보도 때 이미 반영됐을 수 있어요", "주가는 기대·선반영·차익실현 등 여러 이유로 움직여요"):
            self.assertIn(phrase, text)


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


# ---------------------------------------------------------
# 2026-10-30 개편: 종합지·방송사 RSS로 이슈 발견, NAVER로 기사 수·언론사 수, 뉴스 당사자·숨은 연결
# ---------------------------------------------------------

RSS_XML = """<?xml version="1.0"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title><![CDATA[빗썸 고객 개인정보 유출…3만 명 피해]]></title><link>https://www.yna.co.kr/view/AKR1</link>
<pubDate>Fri, 30 Oct 2026 09:10:00 +0900</pubDate><description><![CDATA[<b>빗썸</b>에서 고객 정보가]]></description></item>
<item><title>발행 시각 없는 기사</title><link>https://www.yna.co.kr/view/AKR2</link></item>
<item><title>dc 날짜 기사</title><link>https://www.khan.co.kr/article/1</link><dc:date>2026-10-30T08:00:00+09:00</dc:date></item>
</channel></rss>"""

REF = datetime(2026, 10, 30, 10, 0, tzinfo=KST)


def _rss_art(n, title, press_name="연합뉴스", host="www.yna.co.kr", hours=2):
    return {"title": title, "url": f"https://{host}/view/{n}", "press": host, "press_name": press_name, "section": "사회",
            "pub": (REF - timedelta(hours=hours)).isoformat(), "snippet": "", "source": "rss"}


RSS_ARTS = [_rss_art(1, "빗썸 개인정보 유출 3만 명"), _rss_art(2, "빗썸 개인정보 유출 경찰 수사", "SBS", "news.sbs.co.kr"),
            _rss_art(3, "은행 해킹 피해 확산"), _rss_art(4, "아이폰 듀오 결함 리콜"), _rss_art(5, "국회 여야 공방 계속"),
            _rss_art(6, "전기차 배터리 리콜 확대", "JTBC", "news.jtbc.co.kr"), _rss_art(7, "코스피 급락 마감")] + \
           [_rss_art(10 + i, f"기타 기사 {i}") for i in range(20)]


def _rss_topic(keyword, label, kind, nums, rep, title=None, summary="사실 한 줄", linked=True, query=None):
    return {"title": title or f"{keyword} 소식", "summary": summary, "keyword": keyword, "label": label, "kind": kind,
            "field": "보안 사고", "macro": False, "linked": linked, "query": query or keyword, "articles": nums, "representative": rep}


class RssIssuesTest(LifemapBase):
    def test_parse_rss_dates_press_and_sources_file(self):
        items = rss.parse(RSS_XML.encode(), {"press": "연합뉴스", "section": "사회"})
        self.assertEqual([a["title"] for a in items], ["빗썸 고객 개인정보 유출…3만 명 피해", "dc 날짜 기사"])  # 발행 시각 없으면 뺀다
        self.assertEqual(items[0]["pub"], "2026-10-30T09:10:00+09:00")
        self.assertEqual(items[0]["snippet"], "빗썸에서 고객 정보가")
        self.assertEqual((items[0]["press_name"], items[0]["section"]), ("연합뉴스", "사회"))
        self.assertTrue(rss.general("https://www.donga.com/news/1"))
        self.assertTrue(rss.general("https://news.sbs.co.kr/news/endPage.do?news_id=1"))
        self.assertFalse(rss.general("https://www.sentv.co.kr/news/1"))  # 경제지는 대표 기사가 아니다
        src = rss.sources()
        self.assertGreaterEqual(len(src["rss"]), 10)
        for f in src["rss"]:  # 경제·증권 섹션은 넣지 않는다
            self.assertNotRegex(f["section"] + f["url"], r"경제|증권|economy|stock|market")

    def test_collect_keeps_window_and_reports_feeds(self):
        class R:
            status_code = 200
            content = RSS_XML.encode()
        with mock.patch.object(rss, "sources", return_value={"rss": [{"press": "연합뉴스", "section": "사회", "url": "https://x/1"},
                                                                     {"press": "동아일보", "section": "사회", "url": "https://x/2"}],
                                                             "general_press": {}}):
            arts, report = REAL_RSS_COLLECT(REF - timedelta(hours=24), REF, http=lambda *a, **k: R())
        self.assertEqual(len(arts), 2)  # 두 피드 같은 제목은 한 번만
        self.assertEqual([r["items"] for r in report], [2, 2])

    def test_pick_rules_linked_kind_and_card_words(self):
        raw = {"topics": [
            _rss_topic("빗썸 정보유출", "개인정보 유출", "해킹·정보유출", [1, 2], 1, query="빗썸 개인정보 유출"),
            _rss_topic("은행 해킹", "은행 해킹", "해킹·정보유출", [3], 3),            # 사건 종류가 같다 → 하나만
            _rss_topic("아이폰 듀오 결함", "스마트폰 결함", "제품 결함·리콜", [4], 4, title="아이폰 듀오 결함에 부품주 급등"),  # 증권 표현
            _rss_topic("국회 공방", "정치", "기타", [5], 5, linked=False),             # 기업과 이어지지 않음
            _rss_topic("전기차 배터리 리콜", "전기차 리콜", "제품 결함·리콜", [6], 6),
            _rss_topic("코스피 급락", "증시", "기타", [7], 7),                        # 지수 시황
        ]}
        more = {"topics": [_rss_topic("빗썸 정보유출", "개인정보 유출", "해킹·정보유출", [1, 2], 1),  # 이미 고른 사건 → 뺀다
                           _rss_topic("기타 기사", "생활 소식", "재난·날씨", [8, 9], 8)]}
        with mock.patch.object(lifemap, "_ask", side_effect=[raw, more]) as ask:
            topics = lifemap.pick_rss_issues(self.basis(), RSS_ARTS)
        self.assertIn("1|연합뉴스|사회|", ask.call_args.args[3]["기사"][0])
        self.assertIn("2개뿐이었다", ask.call_args.args[2])  # 통과한 이슈가 3개 미만이면 한 번 더 묻는다
        self.assertNotIn("코스피 급락 마감", " ".join(ask.call_args.args[3]["기사"]))  # 증권 기사는 AI에 보내기 전에 뺀다
        self.assertEqual([(t["name"], t["label"]) for t in topics],
                         [("빗썸 정보유출", "개인정보 유출"), ("전기차 배터리 리콜", "전기차 리콜"), ("기타 기사", "생활 소식")])
        self.assertEqual(topics[0]["query"], "빗썸 개인정보 유출")
        self.assertEqual(lifemap._last_rejects, {"kind": 1, "text": 1, "unlinked": 1, "market": 1, "word": 1})
        self.assertTrue(lifemap.card_unsafe("부품주 급등"))
        self.assertFalse(lifemap.card_unsafe("빗썸 고객 3만 명 정보 유출"))

    def test_cover_counts_presses_first_report_and_related_articles(self):
        t = {"name": "빗썸 정보유출", "query": "빗썸 개인정보 유출", "_context": RSS_ARTS[:2]}
        naver = [{"title": "빗썸 개인정보 유출 파장", "url": "https://www.sentv.co.kr/1", "press": "www.sentv.co.kr",
                  "pub": (REF - timedelta(hours=1)).isoformat(), "snippet": ""},
                 {"title": "빗썸 개인정보 유출 관련주 급등", "url": "https://stock.example/2", "press": "stock.example",
                  "pub": (REF - timedelta(hours=1)).isoformat(), "snippet": ""},  # 증권 기사 → 세지 않음
                 {"title": "빗썸 첫 유출 의심 신고", "url": "https://www.donga.com/3", "press": "www.donga.com",
                  "pub": (REF - timedelta(hours=40)).isoformat(), "snippet": ""},  # 24시간 밖 → 첫 보도
                 {"title": "날씨 기사", "url": "https://www.donga.com/4", "press": "www.donga.com",
                  "pub": (REF - timedelta(hours=1)).isoformat(), "snippet": ""}]  # 같은 사건이 아님
        with mock.patch.object(news, "search", return_value=naver) as search:
            lifemap.cover(t, REF)
        self.assertEqual([c.kwargs["sort"] for c in search.call_args_list], ["date", "sim"])
        self.assertEqual(search.call_args.args[0], "빗썸 개인정보 유출")
        self.assertEqual(t["coverage"], {"articles": 3, "presses": 3, "hours": 24})  # 연합·SBS(RSS) + 서울경제TV
        self.assertTrue(t["ongoing"])
        self.assertEqual(t["first"]["url"], "https://www.donga.com/3")
        self.assertEqual([a["rep"] for a in t["articles"]], [True, False, False])
        self.assertEqual(t["articles"][0]["press_name"], "연합뉴스")  # 대표 기사는 종합지·방송사
        self.assertEqual(t["articles"][2]["url"], "https://www.sentv.co.kr/1")  # 경제지는 관련 기사에만
        self.assertNotIn("press_name", t["articles"][2])

    def test_rank_today_first_one_ongoing_and_two_presses(self):
        def topic(name, presses, ongoing, n=10):
            return {"name": name, "coverage": {"presses": presses, "articles": n}, "ongoing": ongoing}
        lifemap._last_rejects.clear()
        got = lifemap.rank_issues([topic("a", 3, False), topic("old1", 9, True), topic("b", 8, False), topic("one", 1, False),
                                   topic("old2", 5, True), topic("c", 2, False)], 3)
        self.assertEqual([t["name"] for t in got], ["b", "a", "old1"])
        self.assertEqual(lifemap._last_rejects, {"press": 1, "ongoing": 1})

    def test_run_topics_from_rss_end_to_end(self):
        issues = {"topics": [_rss_topic("빗썸 정보유출", "개인정보 유출", "해킹·정보유출", [1, 2], 1)]}
        interp = {"interpretation": ["거래소 정보 유출이 알려지면 보안 프로그램 수요가 늘 수 있어요."], "move": {"subject": "", "today": "해당 없음"},
                  "expected": "해당 없음", "paths": [{"label": "보안 수요", "detail": "", "companies": [
                      {"name": "라온시큐어", "direction": "긍정", "relation": "사고 대응", "relevance": "강", "reason": "인증 보안 솔루션을 만든다",
                       "industry": "IT 서비스", "evidence": 1},
                      {"name": "안랩", "direction": "긍정", "relation": "사고 대응", "relevance": "중", "reason": "백신 보안 솔루션을 만든다",
                       "industry": "모름", "evidence": 9}]}]}

        def fake_ask(model, system, *a, **k):
            if system is lifemap.RSS_TOPIC_SYSTEM:
                return issues
            if system is lifemap.INTRO_SYSTEM:
                return {"companies": [{"code": "042510", "intro": "모바일 인증 보안을 만드는 회사"}, {"code": "053800", "intro": "주가가 오를 회사"}]}
            return interp

        ref = lifemap._ref_time(self.basis())
        naver = [{"title": "빗썸 정보유출 후폭풍", "url": "https://www.hankookilbo.com/1", "press": "www.hankookilbo.com",
                  "pub": (ref - timedelta(hours=1)).isoformat(), "snippet": ""}]
        now_arts = [{**a, "pub": (ref - timedelta(hours=2)).isoformat()} for a in RSS_ARTS]
        with mock.patch.object(rss, "collect", return_value=(now_arts, [{"press": "연합뉴스", "ok": True, "items": 27}])), \
                mock.patch.object(news, "search", return_value=naver), \
                mock.patch.object(lifemap, "_ask", side_effect=fake_ask) as ask:
            data = lifemap.run_topics(self.basis())
        self.assertEqual(data["news_source"], "rss")
        topic_call = next(c for c in ask.call_args_list if c.args[1] is lifemap.RSS_TOPIC_SYSTEM)
        self.assertGreaterEqual(topic_call.args[5], 12000)  # 기사 수백 건 묶기는 4000토큰이면 잘린다(10-30 서버 491건)
        t = data["topics"][0]
        self.assertEqual((t["label"], t["kind"], t["ongoing"]), ("개인정보 유출", "해킹·정보유출", False))
        self.assertEqual(t["coverage"]["presses"], 3)
        self.assertNotIn("query", t)
        cs = {c["name"]: c for s in t["map"]["stages"] for c in s["companies"]}
        self.assertEqual((cs["라온시큐어"]["hop"], cs["라온시큐어"]["industry"]), (1, "IT 서비스"))
        self.assertEqual(cs["라온시큐어"]["evidence"]["press_name"], "연합뉴스")
        self.assertNotIn("industry", cs["안랩"])  # '모름'은 비운다
        self.assertNotIn("evidence", cs["안랩"])  # 없는 기사 번호
        self.assertEqual(lifemap.intros(), {"042510": "모바일 인증 보안을 만드는 회사"})  # 권유·주가 표현 소개는 버린다
        self.assertEqual(store.read("lifemap_status")["news_source"], "rss")
        view = lifemap.overview()["topics"][0]
        vc = {c["code"]: c for s in view["map"]["stages"] for c in s["companies"]}
        self.assertEqual(vc["042510"]["intro"], "모바일 인증 보안을 만드는 회사")
        # 같은 회사 소개는 다시 만들지 않는다(안랩만 다시 묻는다)
        calls = [c for c in ask.call_args_list if c.args[1] is lifemap.INTRO_SYSTEM]
        self.assertEqual(len(calls), 1)
        with mock.patch.object(lifemap, "_ask", return_value={"companies": []}) as again:
            lifemap.ensure_intros([{"code": "042510", "name": "라온시큐어"}, {"code": "053800", "name": "안랩"}])
        self.assertEqual([c["code"] for c in again.call_args.args[3]["회사"]], ["053800"])


class PartyAndHiddenTest(LifemapBase):
    def test_named_company_becomes_party_caps_and_order(self):
        stocks, index, _ = lifemap.directory()
        context = [{"title": "SK텔레콤·KT 고객 정보 유출", "snippet": "이마트 앱도", "url": "https://www.yna.co.kr/1", "press": "www.yna.co.kr"}]
        comp = lambda n, rel, r="강", ind="통신": {"name": n, "direction": "부정", "relation": rel, "relevance": r,  # noqa: E731
                                                "reason": f"{n} 사업 연결", "industry": ind, "evidence": 1}
        raw = {"paths": [
            {"label": "보상 비용", "detail": "", "companies": [comp("SK텔레콤", "당사자"), comp("KT", "경쟁사")]},
            {"label": "보안 수요", "detail": "", "companies": [comp("라온시큐어", "사고 대응", "중", "IT 서비스"), comp("안랩", "사고 대응", "약", "IT 서비스")]},
            {"label": "소비 위축", "detail": "", "companies": [comp("이마트", "고객사"), comp("농심", "같은 업종", "약", "음식료/담배")]},
            {"label": "원가 부담", "detail": "", "companies": [comp("오뚜기", "대체재", "약", "음식료/담배"), comp("한화에어로스페이스", "공급사", "약", "운송장비/부품")]},
        ]}
        paths, _ = lifemap.validate_paths(raw, index, stocks, context=context)
        cs = {c["name"]: c for p in paths for c in p["companies"]}
        # 기사에 이름이 나온 KT·이마트도 당사자 → 당사자 3곳 중 2곳만(SK텔레콤·KT), 이마트는 빠진다
        self.assertEqual(sorted(n for n, c in cs.items() if c["party"]), ["KT", "SK텔레콤"])
        self.assertNotIn("이마트", cs)
        self.assertEqual(len(cs), lifemap.COMPANIES_MAX)
        self.assertNotIn("오뚜기", cs)  # 넘치면 2차·연관도 약한 것부터(같으면 뒤에 나온 것)
        self.assertEqual((cs["KT"]["relation"], cs["KT"]["link"], cs["KT"]["hop"]), ("당사자", "직접 당사자", 0))
        self.assertEqual((cs["라온시큐어"]["hop"], cs["농심"]["hop"]), (1, 2))
        self.assertEqual(cs["SK텔레콤"]["evidence"]["press_name"], "연합뉴스")
        self.assertEqual([p["key"] for p in paths], [f"p{i}" for i in range(len(paths))])

    def test_retry_once_when_fewer_than_two_links_outside_the_article(self):
        ctx = [{"title": "SK텔레콤 고객 정보 유출", "snippet": "", "url": "https://www.yna.co.kr/1", "press": "www.yna.co.kr"}]
        co = lambda n, rel: {"name": n, "direction": "부정" if rel == "당사자" else "긍정", "relation": rel, "relevance": "중",  # noqa: E731
                             "reason": f"{n} 사업 연결", "industry": "통신", "evidence": 1}
        base = {"interpretation": ["통신사 정보 유출 소식이에요."], "move": {"subject": "", "today": "해당 없음"}, "expected": "해당 없음"}
        only_party = {**base, "paths": [{"label": "보상 비용", "detail": "", "companies": [co("SK텔레콤", "당사자")]},
                                        {"label": "보안 수요", "detail": "", "companies": [co("라온시큐어", "사고 대응")]}]}
        better = {**base, "paths": [{"label": "보상 비용", "detail": "", "companies": [co("SK텔레콤", "당사자")]},
                                    {"label": "보안 수요", "detail": "", "companies": [co("라온시큐어", "사고 대응"), co("안랩", "사고 대응")]}]}
        with mock.patch.object(lifemap, "_ask", side_effect=[only_party, better]) as ask:
            m = lifemap.interpret("통신사 정보유출", ctx)
        self.assertEqual(ask.call_count, 2)
        self.assertIn("기사에 이름이 없는", ask.call_args_list[1].args[2])
        self.assertEqual(sum(1 for p in m["stages"] for c in p["companies"] if not c["party"]), 2)

    def test_prompts_plain_words_and_hidden_links(self):
        self.assertIn("일반인", lifemap.INTERP_SYSTEM)
        self.assertIn("기사에는 이름이 안 나왔지만", lifemap.INTERP_SYSTEM)
        self.assertIn("업종명이 아니라", lifemap.RSS_TOPIC_SYSTEM)
        self.assertIn("'가상자산 거래소'", lifemap.RSS_TOPIC_SYSTEM)


EXTRA = {"as_of": "20261030", "fetched_ts": datetime(2026, 10, 30, 10, 42, tzinfo=KST).timestamp(), "final": False,
         "sectors": {"KOSPI": [{"code": "1", "name": "통신", "rate": -1.0}, {"code": "2", "name": "IT 서비스", "rate": 2.5},
                               {"code": "3", "name": "음식료/담배", "rate": 0.4}],
                     "KOSDAQ": [{"code": "4", "name": "IT 서비스", "rate": 4.9}]}}
LIVE_WS = {"day": "20261030", "indices": {"KOSPI": {"rate": -2.0}, "KOSDAQ": {"rate": 1.0}}}


class IndustryChipsTest(LifemapBase):
    NOW = datetime(2026, 10, 30, 10, 45, tzinfo=KST)

    def _stages(self):
        c = lambda code, ind=None: {"code": code, "name": STOCKS[code]["name"], "relevance": "중", "reason": "r", "direction": "pos",  # noqa: E731
                                    **({"industry": ind} if ind else {})}
        return [{"key": "p0", "label": "보안 수요", "detail": "", "companies": [c("042510", "IT 서비스"), c("053800", "IT 서비스")]},
                {"key": "p1", "label": "보상 비용", "detail": "", "companies": [c("030200", "통신"), c("004370")]}]

    def test_live_label_vs_market_and_chip_rules(self):
        store.write("market_extra", EXTRA)
        store.write("market_live", LIVE_WS)
        ir = lifemap.industry_rates(self.NOW)
        self.assertEqual((ir["label"], ir["live"]), ("10:42 기준", True))
        chips = lifemap.industry_chips(self._stages(), ir)
        # IT 서비스: 두 회사 모두 코스닥 → 코스닥 업종 4.9 − 코스닥 1.0 = 3.9%p, 통신: 코스피 −1.0 − (−2.0) = 1.0%p, 업종 없는 농심은 칩 없음
        self.assertEqual([(x["name"], x["market"], x["vs"], x["codes"]) for x in chips],
                         [("IT 서비스", "KOSDAQ", 3.9, ["042510", "053800"]), ("통신", "KOSPI", 1.0, ["030200"])])

    def test_close_weekend_stale_and_missing_index(self):
        store.write("market_extra", {**EXTRA, "final": True})
        store.write("market_live", LIVE_WS)
        self.assertEqual(lifemap.industry_rates(datetime(2026, 11, 1, 12, 0, tzinfo=KST))["label"], "10/30 종가 기준")  # 주말
        self.assertIsNone(lifemap.industry_rates(datetime(2026, 11, 6, 12, 0, tzinfo=KST)))  # 5일보다 오래됨
        store.write("market_live", {"day": "20261029", "indices": LIVE_WS["indices"]})
        self.assertIsNone(lifemap.industry_rates(self.NOW))  # 같은 날 지수가 없으면 칩을 숨긴다
        store.write("market_kiwoom", {"as_of": "20261030", "indices": [{"name": "코스피", "rate": -2.0}, {"name": "코스닥", "rate": 1.0}]})
        self.assertEqual(lifemap.industry_rates(self.NOW)["indices"], {"KOSPI": -2.0, "KOSDAQ": 1.0})
        self.assertEqual(lifemap.industry_chips(self._stages(), None), [])

    def test_pulse_carries_rates_and_chips_without_ai(self):
        today = datetime.now(KST).strftime("%Y%m%d")
        store.write("market_live", {**LIVE_WS, "day": today})
        store.write("market_extra", {**EXTRA, "as_of": today})
        item = {**EXAMPLE_ITEM, "name": "보안 사고", "map": {**EXAMPLE_ITEM["map"], "stages": self._stages()}}
        store.write("lifemap", {"basis": {"key": "public:20261027"}, "topics": [item]})
        with mock.patch.object(lifemap, "_ask", side_effect=AssertionError), mock.patch.object(news, "search", side_effect=AssertionError):
            p = lifemap.pulse()
            self.assertIs(lifemap.pulse(), p)  # 5초 안 같은 결과
        t = p["topics"]["보안 사고"]
        self.assertEqual([x["name"] for x in t["industries"]], ["IT 서비스", "통신"])
        self.assertEqual(t["companies"]["042510"]["rate"], 18.1)
        self.assertEqual(p["refresh_sec"], 15)
        view = lifemap.overview()["topics"][0]["map"]
        self.assertEqual(view["industries"][0]["name"], "IT 서비스")
        self.assertTrue(view["industries_label"].endswith("기준"))


if __name__ == "__main__":
    unittest.main()


def _made(name, title, urls, first, query=None, label="", parties=(), ongoing=False, presses=5):
    """생성이 끝난 이슈(화면용)."""
    return {"name": name, "title": title, "query": query or name, "label": label, "ongoing": ongoing,
            "articles": [{"title": f"{title} {i}", "url": u, "press": "www.donga.com", "rep": i == 0} for i, u in enumerate(urls)],
            "first": {"pub": first, "title": title, "url": urls[0], "press": "www.donga.com"},
            "coverage": {"articles": presses * 2, "presses": presses, "hours": 24},
            "map": {"stages": [{"label": "x", "companies": [{"code": "1", "name": p, "party": True} for p in parties]}],
                    "interpretation": []}}


class SameEventAndRelaxTest(LifemapBase):
    """0단계: 같은 사건 합치기(유지하던 이슈 포함), 이슈가 모자랄 때 단계적 완화와 기록, 억지로 채우지 않기."""

    def test_ticketing_outage_twins_merge_with_earlier_first_report(self):
        a = _made("발권 시스템 장애", "인천공항 항공권 발권 시스템 먹통", ["https://www.chosun.com/1"], "2026-10-30T13:47:00+09:00")
        b = _made("인천공항 발권 장애", "인천공항 중국 항공사 발권 장애", ["https://www.donga.com/2"], "2026-10-30T12:10:00+09:00")
        self.assertTrue(lifemap.same_event(a, b))  # 사건 말 '발권'·'장애' 두 개가 겹친다
        hack = _made("가상자산 해킹", "거래소 해킹 피해", ["https://www.donga.com/3"], "2026-10-30T10:00:00+09:00")
        bank = _made("은행 해킹", "시중은행 전산 해킹 시도", ["https://www.yna.co.kr/4"], "2026-10-30T10:00:00+09:00")
        self.assertFalse(lifemap.same_event(hack, bank))  # '해킹' 하나만 겹치고 당사자·제목이 다르면 다른 사건
        self.assertFalse(lifemap.same_event(a, hack))
        # 같은 기사가 겹치면 같은 사건
        self.assertTrue(lifemap.same_event(hack, _made("코인 탈취", "다른 제목", ["https://www.donga.com/3"], "2026-10-30T10:00:00+09:00")))
        # 말 하나 + 같은 당사자
        self.assertTrue(lifemap.same_event(_made("빗썸 해킹", "t1", ["u1"], "2026-10-30T10:00:00+09:00", parties=["빗썸"]),
                                           _made("거래소 해킹", "t2", ["u2"], "2026-10-30T10:00:00+09:00", parties=["빗썸"])))
        ref = datetime(2026, 10, 30, 17, 0, tzinfo=KST)
        merged = lifemap.merge_event(a, b, ref)
        self.assertEqual(merged["first"]["pub"], "2026-10-30T12:10:00+09:00")  # 첫 보도는 더 이른 쪽
        self.assertEqual([x["url"] for x in merged["articles"]], ["https://www.chosun.com/1", "https://www.donga.com/2"])
        self.assertFalse(merged["ongoing"])
        self.assertEqual(merged["merged"], ["인천공항 발권 장애"])

    def test_kept_previous_issue_is_merged_not_shown_twice(self):
        carried = {**_made("인천공항 발권 장애", "인천공항 중국 항공사 발권 장애", ["https://www.donga.com/2"],
                           "2026-10-30T12:10:00+09:00"), "basis_label": "x"}
        store.write("lifemap", {"basis": {"key": self.basis()["key"]}, "topics": [carried]})
        new = _made("발권 시스템 장애", "인천공항 항공권 발권 시스템 먹통", ["https://www.chosun.com/1"], "2026-10-30T13:47:00+09:00")
        with mock.patch.object(lifemap, "rss_issues", return_value=[{**new, "_context": []}]), \
                mock.patch.object(lifemap, "_finish", side_effect=lambda t, *a, **k: {k2: v for k2, v in t.items() if k2 != "_context"}), \
                mock.patch.object(lifemap, "naver_general_issues", return_value=[]):
            data = lifemap.run_topics(self.basis())
        self.assertEqual([t["name"] for t in data["topics"]], ["발권 시스템 장애"])
        self.assertEqual(data["topics"][0]["first"]["pub"], "2026-10-30T12:10:00+09:00")
        status = store.read("lifemap_status")
        self.assertEqual(status["rejects"].get("same_event"), 1)
        self.assertEqual(status["relax"], ["naver_general", "ongoing48", "short"])  # 1개뿐 → 완화 단계를 모두 거치고 기록

    def test_relax_steps_naver_general_then_ongoing48_and_no_forced_fill(self):
        ref = lifemap._ref_time(self.basis())
        iso = lambda h: (ref - timedelta(hours=h)).isoformat()  # noqa: E731
        first = _made("울산 붕괴", "울산화력 보일러 타워 붕괴", ["https://www.yna.co.kr/1"], iso(3))
        naver = _made("전기차 화재", "지하주차장 전기차 화재", ["https://www.donga.com/9"], iso(5))
        old30 = _made("열차 참사", "스페인 고속열차 참사", ["https://www.donga.com/7"], iso(30), ongoing=True)
        old60 = _made("태풍 피해", "필리핀 태풍 피해", ["https://www.donga.com/8"], iso(60), ongoing=True)
        lifemap._last_overflow[:] = [old30, old60]
        finished = []
        with mock.patch.object(lifemap, "rss_issues", return_value=[first]), \
                mock.patch.object(lifemap, "naver_general_issues", return_value=[naver]) as ng, \
                mock.patch.object(lifemap, "_finish", side_effect=lambda t, *a, **k: finished.append(t["name"]) or t):
            data = lifemap.run_topics(self.basis())
        self.assertEqual(finished, ["울산 붕괴", "전기차 화재", "열차 참사"])  # 48시간 밖 태풍은 넣지 않는다
        self.assertEqual(ng.call_args.args[1][0]["name"], "울산 붕괴")  # 이미 있는 사건을 넘겨 겹치지 않게
        self.assertEqual(data["relax"], ["naver_general", "ongoing48"])
        self.assertEqual(data["fresh"], 3)

        # 그래도 2개뿐이면 2개 그대로(예시·다른 이슈로 채우지 않는다), 화면도 2개
        lifemap._last_overflow[:] = []
        with mock.patch.object(lifemap, "rss_issues", return_value=[{**first, "articles": first["articles"]}]), \
                mock.patch.object(lifemap, "naver_general_issues", return_value=[naver]), \
                mock.patch.object(lifemap, "_finish", side_effect=lambda t, *a, **k: t):
            store.write("lifemap", {})
            data = lifemap.run_topics(self.basis())
        self.assertEqual(data["relax"], ["naver_general", "ongoing48", "short"])
        self.assertEqual(len(data["topics"]), 2)
        self.assertEqual(len(lifemap.overview()["topics"]), 2)

    def test_naver_general_keeps_only_general_press_in_24h(self):
        ref = lifemap._ref_time(self.basis())
        arts = [{"title": "전기차 화재 지하주차장", "url": "https://www.donga.com/a", "press": "www.donga.com", "pub": (ref - timedelta(hours=2)).isoformat()},
                {"title": "전기차 화재 원인", "url": "https://www.sentv.co.kr/b", "press": "www.sentv.co.kr", "pub": (ref - timedelta(hours=2)).isoformat()},
                {"title": "전기차 화재 첫날", "url": "https://www.chosun.com/c", "press": "www.chosun.com", "pub": (ref - timedelta(hours=30)).isoformat()},
                {"title": "전기차 화재 대책", "url": "https://news.sbs.co.kr/d", "press": "news.sbs.co.kr", "pub": (ref - timedelta(hours=1)).isoformat()}]
        seen = {}

        def fake_pick(basis, articles, *a, **k):
            seen["arts"] = articles
            return []
        with mock.patch.object(lifemap, "collect_issue_news", return_value=arts), mock.patch.object(lifemap, "pick_rss_issues", side_effect=fake_pick):
            lifemap.naver_general_issues(self.basis(), [], 5)
        self.assertEqual([a["url"] for a in seen["arts"]], ["https://www.donga.com/a", "https://news.sbs.co.kr/d"])
        self.assertEqual(seen["arts"][0]["press_name"], "동아일보")

"""뉴스 속 숨은 종목 오프라인 테스트. 외부 API·AI를 부르지 않는다(가짜 응답 사용).

실행: python -B -m unittest tests.test_stockon_lifemap -v
"""

import json
import time
import unittest
from datetime import datetime, timedelta, timezone
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
        self.assertIn("link", lifemap.INTERP_SCHEMA["properties"]["paths"]["items"]["properties"]["companies"]["items"]["required"])

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
        arts = [{**a, "press": f"p{i}.kr"} for i, a in enumerate(ARTICLES)]
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

"""STOCK:ON 키움 모드 무인 운영(12/31까지) 오프라인 테스트. 키움·AI·뉴스를 부르지 않는다(가짜 응답).

실행: python -B -m unittest tests.test_stockon_kiwoom_ops -v
"""

import os
import time
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from services.stockon import ai, budget, kiwoom_collector as kc, lifemap, public_data, service, store
from services.stockon.kiwoom_client import KiwoomClient, KiwoomError
from services.stockon.public_data import KST
from tests.test_stockon import FakeKiwoomHttp, FakeResp, TempStore, fake_http

CFG = {"mode": "mock", "price_source": "kiwoom", "appkey": "a", "secret": "b", "mock_key_expires": "2026-11-27"}


class TokenHttp:
    """au10001은 만료 시각을 바꿔 가며 주고, ka20001은 지정한 횟수만큼 8005(토큰 무효)를 낸다."""

    def __init__(self, expires="20261028100000", invalid=0):
        self.calls, self.expires, self.invalid, self.n = [], expires, invalid, 0

    def __call__(self, url, json=None, headers=None, timeout=None):
        api = headers["api-id"]
        self.calls.append(api)
        if api == "au10001":
            self.n += 1
            payload = {"expires_dt": self.expires, "token": f"T{self.n}", "return_code": 0}
        elif self.invalid:
            self.invalid -= 1
            payload = {"return_code": 8005, "return_msg": "Token이 유효하지 않습니다"}
        else:
            payload = FakeKiwoomHttp.RESP[api]
        r = FakeResp(payload, 200)
        r.headers = {}
        return r


class KiwoomTokenTest(TempStore):
    def _client(self, http, now):
        return KiwoomClient("mock", "a", "b", http=http, clock=lambda: 0.0, sleep=lambda s: None, now=lambda: now[0])

    def test_token_renews_by_kst_even_when_container_clock_is_utc(self):
        http = TokenHttp(expires="20261028100000")  # 키움 만료 시각(KST)
        now = [datetime(2026, 10, 28, 9, 40)]  # KST 09:40 → 아직 유효
        c = self._client(http, now)
        c.query("ka20001", {})
        c.query("ka20001", {})
        self.assertEqual(http.calls.count("au10001"), 1)
        now[0] = datetime(2026, 10, 28, 9, 51)  # 만료 10분 전 안 → 새로 발급
        c.query("ka20001", {})
        self.assertEqual(http.calls.count("au10001"), 2)
        self.assertEqual(c.token_issued, 2)
        # 기본 시계는 KST(컨테이너 TZ가 UTC여도 9시간 어긋나지 않게)
        default = KiwoomClient("mock", "a", "b")
        self.assertLess(abs((default._now() - datetime.now(KST).replace(tzinfo=None)).total_seconds()), 5)

    def test_invalid_token_is_dropped_and_retried_once(self):
        http = TokenHttp(expires="20991231235959", invalid=1)
        c = self._client(http, [datetime(2026, 10, 28, 10, 0)])
        c.query("ka20001", {})
        self.assertEqual(http.calls, ["au10001", "ka20001", "au10001", "ka20001"])
        http.invalid = 2  # 다시 받아도 무효면 한 번만 다시 하고 오류
        with self.assertRaises(KiwoomError) as cm:
            c.query("ka20001", {})
        self.assertEqual(cm.exception.code, "8005")

    def test_one_call_per_second_across_all_trs(self):
        t, slept = [0.0], []
        c = KiwoomClient("mock", "a", "b", http=FakeKiwoomHttp(), clock=lambda: t[0],
                         sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
        for api in ("ka20001", "ka10095", "ka10027", "ka10032"):
            c.query(api, {})
        self.assertEqual(len(slept), 4)  # 토큰 + 서로 다른 TR 4개 → 매번 1.1초 간격
        self.assertTrue(all(abs(s - 1.1) < 1e-9 for s in slept))


class CollectorTickTest(TempStore):
    def setUp(self):
        super().setUp()
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, directory = public_data.fetch_market(http=fake_http)
        store.write("market", {**market, "fetched_ts": 1})
        store.write("stocks", directory)
        p = mock.patch.object(lifemap, "rate_source", None)
        p.start()
        self.patches.append(p)

    def _box(self, override=None):
        http = FakeKiwoomHttp(override)
        return {"client": KiwoomClient("mock", "a", "b", http=http, clock=lambda: 0.0, sleep=lambda s: None)}, http

    def test_public_mode_and_pre_market_never_call_kiwoom(self):
        box, http = self._box()
        self.assertFalse(kc.tick(box, {**CFG, "price_source": "public"}, datetime(2026, 11, 17, 11, 0, tzinfo=KST), {}))
        self.assertFalse(kc.tick(box, CFG, datetime(2026, 11, 17, 8, 30, tzinfo=KST), {}))
        self.assertFalse(kc.tick(box, CFG, datetime(2026, 11, 15, 11, 0, tzinfo=KST), {}))  # 일요일
        self.assertEqual(http.calls, [])

    def test_closed_snapshot_made_once_even_after_restart_in_the_evening(self):
        box, http = self._box()
        evening = datetime(2026, 11, 17, 17, 30, tzinfo=KST)
        self.assertTrue(kc.tick(box, CFG, evening, {}))
        snap = store.read("market_kiwoom")
        self.assertEqual((snap["as_of"], snap["session"], snap["final"], snap["session_label"]), ("20261117", "closed", True, "종가 기준"))
        n = len(http.calls)
        box2, http2 = self._box()  # 수집기를 다시 켜도
        self.assertFalse(kc.tick(box2, CFG, evening.replace(minute=40), {}))
        self.assertEqual((len(http.calls), http2.calls), (n, []))  # 다시 묻지 않음

    def test_holiday_keeps_last_snapshot_and_stops_for_the_day(self):
        store.write("market_kiwoom", {"as_of": "20261116", "session": "closed", "final": True, "fetched_ts": 1})
        old = FakeKiwoomHttp.RESP["ka10095"]
        holiday = {**old, "atn_stk_infr": [{**r, "dt": "20261116"} for r in old["atn_stk_infr"]]}
        box, http = self._box({"ka10095": holiday})
        state = {}
        self.assertTrue(kc.tick(box, CFG, datetime(2026, 11, 17, 9, 30, tzinfo=KST), state))
        self.assertEqual(state, {"holiday": "20261117"})
        self.assertEqual(store.read("market_kiwoom")["as_of"], "20261116")  # 덮지 않음
        self.assertEqual(store.read("kiwoom_status")["session"], "holiday")
        n = len(http.calls)
        self.assertFalse(kc.tick(box, CFG, datetime(2026, 11, 17, 10, 30, tzinfo=KST), state))
        self.assertEqual(len(http.calls), n)
        with mock.patch.object(service, "_now", lambda: datetime(2026, 11, 17, 10, 30, tzinfo=KST)):
            self.assertEqual(service.active_market()[1], "public")  # 화면은 공공데이터

    def test_three_failures_raise_admin_alert_and_success_resets(self):
        box, _ = self._box({"ka20001": {"return_code": 1, "return_msg": "x"}})
        now = datetime(2026, 11, 17, 11, 0, tzinfo=KST)
        for i in range(3):
            kc.tick(box, CFG, now, {}, sleep=lambda s: None)
            self.assertEqual(service.kiwoom_status()["alert"], i == 2)
        self.assertEqual(service.kiwoom_status()["fails"], 3)
        box["client"]._http = lambda *a, **k: (_ for _ in ()).throw(ValueError("bad"))  # 예상 밖 오류도 센다
        kc.tick(box, CFG, now, {}, sleep=lambda s: None)
        st = service.kiwoom_status()
        self.assertEqual((st["fails"], st["last_error"]), (4, "unexpected ValueError"))
        good, _ = self._box()
        kc.tick(good, CFG, now, {})
        self.assertEqual((service.kiwoom_status()["fails"], service.kiwoom_status()["alert"]), (0, False))

    def test_watchlist_prices_follow_kiwoom_and_footer_note(self):
        store.write("watch", {"items": [{"code": "005930", "name": "삼성전자", "price": {"close": 1, "rate": 0.1}, "news": [], "disclosures": []}],
                              "fetched_ts": time.time()})
        box, _ = self._box()
        now = datetime(2026, 11, 17, 11, 0, tzinfo=KST)
        kc.tick(box, CFG, now, {})
        with mock.patch.dict(os.environ, {"STOCKON_ENABLED": "1"}), mock.patch.object(service, "_now", lambda: now):
            view = service.overview()
            self.assertEqual(view["price_source"], "kiwoom")
            self.assertEqual((view["watch"]["items"][0]["price"]["close"], view["watch"]["items"][0]["price"]["rate"]), (156600.0, 28.68))
            self.assertEqual(view["price_note"], "시세: 키움증권 모의투자 API · 지연될 수 있으며 참고용입니다")
            kc.write_status({**CFG, "price_source": "public"})  # 설정 한 줄로 공공데이터 복귀
            view = service.overview()
            self.assertEqual(view["price_source"], "public")
            self.assertEqual(view["watch"]["items"][0]["price"]["close"], 1)
            self.assertTrue(view["price_note"].startswith("시세: 금융위원회 공공데이터"))


class LifemapKiwoomBasisTest(TempStore):
    def setUp(self):
        super().setUp()
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, directory = public_data.fetch_market(http=fake_http)
        self.public_as_of = market["as_of"]
        store.write("market", {**market, "fetched_ts": 1})
        store.write("stocks", directory)
        lifemap._dir_cache.update(mtime=None)

    def test_closed_basis_label_and_never_goes_backwards(self):
        now = datetime(2026, 11, 17, 17, 0, tzinfo=KST)
        kc.write_status(CFG)
        store.write("market_kiwoom", {"as_of": "20261117", "session": "closed", "final": True, "fetched_ts": time.time(),
                                      "heatmap": {}, "movers": {}})
        b = lifemap.topic_basis(now)
        self.assertEqual((b["key"], b["label"]), ("kiwoom:20261117:close", "11/17 종가 기준"))
        store.write("lifemap", {"basis": lifemap.basis_info(b), "fresh": 5, "topics": []})
        weekend = lifemap.topic_basis(datetime(2026, 11, 21, 11, 0, tzinfo=KST))  # 토요일 → 공공 기준(더 오래된 날)
        self.assertEqual(weekend["source"], "public")
        self.assertFalse(lifemap.topics_due(weekend))  # 종가 기준 이슈를 오래된 기준으로 바꾸지 않음
        newer = {**weekend, "key": "public:20261118", "as_of": "20261118"}
        store.write("lifemap_status", {})
        self.assertTrue(lifemap.topics_due(newer))  # 더 새 기준이면 만든다

    def test_missing_company_rates_come_from_kiwoom_at_creation(self):
        asked = []
        m = {"stages": [{"companies": [{"code": "005930"}, {"code": "000660"}]}]}
        basis = {"source": "kiwoom", "label": "11/17 종가 기준", "rates": {"005930": 1.5}}
        with mock.patch.object(lifemap, "rate_source", lambda codes: (asked.append(codes), {"000660": -6.2})[1]):
            lifemap.mark_reaction(m, basis)
        self.assertEqual(asked, [["000660"]])
        self.assertEqual([c["rate"] for c in m["stages"][0]["companies"]], [1.5, -6.2])

    def test_closed_rates_last_all_day_and_refresh_when_companies_change(self):
        now = datetime.now(KST)
        store.write("lifemap", {"topics": [{"map": {"stages": [{"companies": [{"code": "005930"}]}]}}]})
        self.assertTrue(lifemap.rates_due(now, closed=True))
        lifemap.save_live_rates({"005930": 1.0}, now, closed=True, codes=["005930"])
        self.assertFalse(lifemap.rates_due(now, closed=True))
        saved = store.read("lifemap_rates")
        store.write("lifemap_rates", {**saved, "ts": time.time() - 5 * 3600})
        self.assertEqual(lifemap._live_rates()["label"], f"{now.month}/{now.day} 종가")  # 종가 값은 그날 하루
        store.write("lifemap", {"topics": [{"map": {"stages": [{"companies": [{"code": "005930"}, {"code": "000660"}]}]}}]})
        self.assertTrue(lifemap.rates_due(now, closed=True))  # 새 이슈 회사가 생기면 바로


class BudgetTest(TempStore):
    def _usage(self, tin, tout):
        return SimpleNamespace(input_tokens=tin, output_tokens=tout)

    def test_cost_sums_both_processes_and_resets_by_day(self):
        budget.record("claude-sonnet-5-5", self._usage(1_000_000, 100_000))  # 2 + 1 = 3달러
        with mock.patch.object(budget, "BUCKET", "collector"):
            budget.record("claude-haiku-5-5", self._usage(1_000_000, 1_000_000))  # 0.1 + 0.5
        self.assertAlmostEqual(budget.spent_today(), 3.6)
        with mock.patch.dict(os.environ, {"STOCKON_AI_DAILY_USD": "3.5"}):
            self.assertFalse(budget.allowed())
            self.assertTrue(budget.status()["exceeded"])
        with mock.patch.dict(os.environ, {"STOCKON_AI_DAILY_USD": ""}):
            self.assertEqual(budget.limit_usd(), 5.0)
            self.assertTrue(budget.allowed())
        store.write("ai_cost_app", {"day": "2000-01-01", "usd": 99})
        self.assertAlmostEqual(budget.spent_today(), 0.6)

    def test_over_limit_reuses_stored_results(self):
        budget.record("claude-sonnet-5-5", self._usage(3_000_000, 0))  # 6달러 > 기본 5달러
        client = mock.MagicMock()
        with mock.patch.object(ai, "_claude_client", return_value=client):
            self.assertIsNone(ai._call("t", {}, {}, model=ai.WHY_MODEL))  # 앱: 부르지 않음 → 고정 문장·요약 없이
            with self.assertRaises(budget.BudgetExceeded):
                lifemap._ask(lifemap.CHAIN_MODEL, "s", "t", {}, {}, 100)
        client.messages.create.assert_not_called()
        with mock.patch.object(ai, "available", return_value=True), mock.patch("services.stockon.news.configured", return_value=True), \
                mock.patch.object(lifemap, "topic_basis", side_effect=AssertionError("must not run")):
            self.assertFalse(lifemap.maybe_run_daily(datetime(2026, 11, 17, 17, 0, tzinfo=KST)))  # 저장된 이슈 유지
        store.write("market", {"as_of": "20261117", "fetched_ts": time.time()})
        self.assertNotIn("briefing", service.due_tasks())
        self.assertNotIn("why", service.due_tasks())

    def test_calls_are_recorded(self):
        resp = SimpleNamespace(usage=self._usage(1000, 100), stop_reason="end_turn", content=[SimpleNamespace(type="text", text="{}")])
        client = mock.MagicMock()
        client.messages.create.return_value = resp
        with mock.patch.object(ai, "_claude_client", return_value=client):
            lifemap._ask(lifemap.TOPIC_MODEL, "s", "t", {}, {}, 100)
            ai._call("t", {}, {}, model=ai.NEWS_MODEL)
        self.assertEqual(store.read("ai_cost_app")["calls"], 2)
        self.assertGreater(budget.spent_today(), 0)

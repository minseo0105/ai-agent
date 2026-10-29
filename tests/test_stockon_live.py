"""STOCK:ON '오늘 시장' 실시간 장중 동향 오프라인 테스트. 키움·AI를 부르지 않는다(가짜 웹소켓·가짜 클라이언트).

실행: python -B -m unittest tests.test_stockon_live -v
"""

import asyncio
import json
import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from services.stockon import ai, budget, kiwoom_collector as kc, kiwoom_realtime as rt, lifemap, live, store
from services.stockon.public_data import KST
from tests.test_stockon import TempStore

TODAY = datetime.now(KST).strftime("%Y%m%d")
OPEN_NOW = datetime(2026, 11, 17, 10, 30, tzinfo=KST)  # 화요일 장중


def real(kind, item, **values):
    return {"trnm": "REAL", "data": [{"type": kind, "item": item, "values": values}]}


class FeedParseTest(unittest.TestCase):
    def test_messages_update_state_and_ping_is_echoed(self):
        f = rt.RealtimeFeed("mock", lambda: "t")
        self.assertEqual(f.handle({"trnm": "PING"}), {"trnm": "PING"})
        f.handle(real("0B", "005930", **{"10": "+243500", "11": "+1500", "12": "+0.62", "20": "091116"}))
        f.handle(real("0J", "001", **{"10": "+6038.96", "11": "+26.52", "12": "+0.44", "20": "091120"}))
        f.handle(real("0U", "101", **{"10": "-765.34", "11": "-5.94", "12": "-0.77", "20": "091120", "251": "4", "252": "451",
                                      "253": "124", "254": "0", "255": "1125"}))
        f.handle(real("00", "x", **{"10": "1"}))  # 허용 밖 타입은 무시
        s = f.snapshot()
        self.assertEqual(s["stocks"]["005930"], {**s["stocks"]["005930"], "close": 243500, "change": 1500, "rate": 0.62, "t": "091116"})
        self.assertEqual((s["indices"]["KOSPI"]["close"], s["indices"]["KOSPI"]["rate"]), (6038.96, 0.44))
        self.assertEqual(s["indices"]["KOSDAQ"]["rate"], -0.77)
        self.assertEqual(s["breadth"]["KOSDAQ"], {"upper": 4, "up": 451, "flat": 124, "lower": 0, "down": 1125, "t": "091120"})
        self.assertNotIn("x", s["stocks"])
        with self.assertRaises(ConnectionError):
            f.handle({"trnm": "LOGIN", "return_code": 100, "return_msg": "bad"})

    def test_register_message_caps_items_and_only_quote_types(self):
        msg = rt.register_message([f"{i:06d}" for i in range(400)])
        self.assertEqual(msg["data"][0], {"item": ["001", "101"], "type": ["0J", "0U"]})
        self.assertEqual(len(msg["data"][1]["item"]), rt.MAX_ITEMS - 2)


class FakeWS:
    def __init__(self, script, sent):
        self.script, self.sent = list(script), sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def recv(self):
        if not self.script:
            raise ConnectionResetError("closed")
        item = self.script.pop(0)
        if item == "wait":
            await asyncio.sleep(5)
        return json.dumps(item)


class FeedConnectionTest(unittest.TestCase):
    def test_login_register_ping_and_reconnect_after_drop(self):
        sent, sessions = [], []
        scripts = [[{"trnm": "LOGIN", "return_code": 0}, {"trnm": "REG", "return_code": 0}, {"trnm": "PING"},
                    real("0J", "001", **{"10": "+6000", "11": "+1", "12": "+0.10", "20": "100000"})],
                   [{"trnm": "LOGIN", "return_code": 0}, real("0J", "001", **{"10": "+6010", "11": "+11", "12": "+0.30", "20": "100005"})]]

        def connect(url, **kw):
            sessions.append(url)
            return FakeWS(scripts[min(len(sessions) - 1, 1)] if len(sessions) <= 2 else [], sent)

        f = rt.RealtimeFeed("mock", lambda: "tok", connect=connect)
        f.set_items(["005930"])

        async def run():
            task = asyncio.create_task(f._run())
            for _ in range(60):
                await asyncio.sleep(0.05)
                if len(sessions) >= 2 and f.state["indices"].get("KOSPI", {}).get("rate") == 0.30:
                    break
            f._stop.set()
            await task

        with mock.patch.object(rt, "BACKOFF", (0, 0)):
            asyncio.run(run())
        self.assertEqual(sessions[0], "wss://mockapi.kiwoom.com:10000/api/dostk/websocket")
        self.assertEqual(sent[0], {"trnm": "LOGIN", "token": "tok"})
        self.assertEqual(sent[1]["trnm"], "REG")
        self.assertIn({"trnm": "PING"}, sent)  # PING을 그대로 돌려보냄
        self.assertGreaterEqual(len(sessions), 2)  # 끊기면 다시 연결
        self.assertGreaterEqual(f.state["reconnects"], 1)
        self.assertEqual(f.state["indices"]["KOSPI"]["rate"], 0.30)

    def test_items_change_triggers_reregister(self):
        f = rt.RealtimeFeed("mock", lambda: "t")
        self.assertTrue(f.set_items(["005930"]))
        self.assertFalse(f.set_items(["005930"]))
        self.assertTrue(f.set_items(["005930", "000660"]))


SECT = {"all_inds_idex": [
    {"stk_cd": "001", "stk_nm": "종합(KOSPI)", "flu_rt": "+0.26", "upl": "1", "rising": "202", "stdns": "51", "fall": "637", "lst": "0", "flo_stk_num": "940"},
    {"stk_cd": "002", "stk_nm": "대형주", "flu_rt": "+0.38", "flo_stk_num": "100"},
    {"stk_cd": "013", "stk_nm": "전기전자", "flu_rt": "+1.90", "flo_stk_num": "60"},
    {"stk_cd": "005", "stk_nm": "음식료품", "flu_rt": "-0.50", "flo_stk_num": "30"},
    {"stk_cd": "027", "stk_nm": "제조", "flu_rt": "+1.38", "flo_stk_num": "600"},
    {"stk_cd": "605", "stk_nm": "코스피배당성장50", "flu_rt": "-0.79", "flo_stk_num": "0"}]}
INV = {"inds_netprps": [{"inds_cd": "001", "inds_nm": "종합(KOSPI)", "ind_netprps": "+1577", "frgnr_netprps": "+1884", "orgn_netprps": "-3502"},
                        {"inds_cd": "002", "ind_netprps": "+1"}]}
MIN = {"inds_min_pole_qry": [{"cur_prc": "+602794", "cntr_tm": f"{TODAY}091000"}, {"cur_prc": "+603768", "cntr_tm": f"{TODAY}090500"},
                             {"cur_prc": "-593310", "cntr_tm": "20261013115000"}]}


class FakeClient:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def query(self, api_id, body):
        from services.stockon.kiwoom_client import KiwoomError
        self.calls.append((api_id, body))
        if api_id in self.fail:
            raise KiwoomError("1700", "x")
        return {"ka20003": SECT, "ka10051": INV, "ka20005": MIN}[api_id]


class ExtraTest(TempStore):
    def test_parsers(self):
        sectors, whole = live.parse_sectors(SECT)
        self.assertEqual([s["name"] for s in sectors], ["전기전자", "음식료품"])  # 시장 전체·규모별·지수 묶음 제외
        self.assertEqual(whole, {"upper": 1, "up": 202, "flat": 51, "down": 637, "lower": 0})
        self.assertEqual(live.parse_investors(INV, "001"), {"foreign": 18.8, "inst": -35.0, "indiv": 15.8})  # 백만 원 → 억 원
        self.assertEqual(live.parse_intraday(MIN, TODAY), [{"t": "0905", "c": 6037.68}, {"t": "0910", "c": 6027.94}])

    def test_collect_extra_six_calls_keeps_previous_on_failure(self):
        now = datetime.now(KST)
        c = FakeClient()
        out = live.collect_extra(c, now)
        self.assertEqual([a for a, _ in c.calls], ["ka20003", "ka10051", "ka20005"] * 2)
        self.assertEqual(out["investors"]["KOSPI"]["foreign"], 18.8)
        self.assertFalse(live.extra_due(now))  # 2분 안에는 다시 하지 않음
        self.assertTrue(live.extra_due(now, final=True))  # 마감 뒤 1번
        out2 = live.collect_extra(FakeClient(fail={"ka10051"}), now, final=True)
        self.assertEqual(out2["investors"]["KOSPI"]["foreign"], 18.8)  # 실패한 항목은 이전 값
        self.assertFalse(live.extra_due(now, final=True))


def market_snapshot(session="open", fetched=None):
    return {"kind": "kiwoom", "as_of": TODAY, "session": session, "final": session == "closed", "fetched_ts": fetched or time.time(),
            "source": {"name": "KRX 기준 · 키움증권 API"},
            "indices": [{"name": "코스피", "close": 6000.0, "change": 10.0, "rate": 0.17}, {"name": "코스닥", "close": 770.0, "change": -1.0, "rate": -0.13}],
            "heatmap": {"KOSPI": [{"code": "005930", "name": "삼성전자", "market": "KOSPI", "close": 240000, "rate": 0.1, "cap": 9e14}], "KOSDAQ": []},
            "movers": {"up": [], "down": [], "value": [{"code": "005930", "name": "삼성전자", "close": 240000, "rate": 0.1, "value": 9e11}]},
            "breadth": {"up": 1, "down": 2, "flat": 3, "total": 6}}


class ViewBase(TempStore):
    def setUp(self):
        super().setUp()
        store.write("kiwoom_status", {"price_source": "kiwoom", "mode": "mock", "session": "open"})
        store.write("market", {"as_of": "20261116", "source": {"name": "공공데이터"}, "indices": [{"name": "코스피", "close": 5900.0, "rate": -1.0}],
                               "heatmap": {"KOSPI": [], "KOSDAQ": []}, "movers": {"value": []}, "breadth": {"up": 9, "down": 9, "flat": 1}})
        store.write("market_kiwoom", market_snapshot())
        live._cache.update(ts=0.0, value=None)
        self.now = datetime.now(KST)
        p = mock.patch.object(live, "_session_now", return_value="open")
        p.start()
        self.patches.append(p)

    def ws(self, age=1):
        store.write("market_live", {"day": TODAY, "connected": True, "last_msg_ts": time.time() - age, "reconnects": 0,
                                    "indices": {"KOSPI": {"close": 6012.5, "change": 22.5, "rate": 0.38, "t": "103000"},
                                                "KOSDAQ": {"close": 771.0, "change": 0.0, "rate": 0.0, "t": "103000"}},
                                    "breadth": {"KOSPI": {"up": 500, "down": 300, "flat": 50, "upper": 2, "lower": 0},
                                                "KOSDAQ": {"up": 900, "down": 600, "flat": 100, "upper": 3, "lower": 1}},
                                    "stocks": {"005930": {"close": 243500, "change": 3500, "rate": 1.46}}})



class ViewTest(ViewBase):
    def test_live_overlays_websocket_values(self):
        self.ws()
        live.collect_extra(FakeClient(), self.now)
        store.write("market_ai", {"as_of": TODAY, "kind": "intraday", "text": "외국인 매수에 전기전자 강세, 코스피 +0.4%", "ai": True, "ts": time.time()})
        v = live.build_view(self.now)
        self.assertEqual((v["state"], v["label"], v["source"]), ("live", "실시간", "kiwoom"))
        kospi = v["indices"][0]
        self.assertEqual((kospi["close"], kospi["rate"]), (6012.5, 0.38))  # 웹소켓 값
        self.assertEqual([p["t"] for p in kospi["series"]], ["0905", "0910", "1030"])  # 5분봉 + 지금 값
        self.assertEqual(v["heatmap"]["KOSPI"][0]["rate"], 1.46)
        self.assertEqual(v["value_top"][0]["close"], 243500)
        self.assertEqual(v["breadth"], {"up": 1400, "down": 900, "flat": 150, "upper": 5, "lower": 1, "total": 2450})
        self.assertEqual(v["sectors"]["KOSPI"]["top"][0]["name"], "전기전자")
        self.assertEqual(v["investors"]["KOSPI"]["inst"], -35.0)
        self.assertTrue(v["ai"]["ai"])
        self.assertEqual(v["price_note"], "시세: 키움증권 모의투자 API · 지연될 수 있으며 참고용입니다")

    def test_delayed_after_one_minute_keeps_last_values(self):
        self.ws(age=90)
        v = live.build_view(self.now)
        self.assertEqual((v["state"], v["label"]), ("delayed", "지연"))
        self.assertEqual(v["indices"][0]["close"], 6012.5)  # 마지막 값 유지

    def test_closed_uses_closing_snapshot(self):
        self.ws()
        store.write("market_kiwoom", market_snapshot("closed"))
        v = live.build_view(self.now)
        self.assertEqual((v["state"], v["label"]), ("closed", "장 마감 · 종가 기준"))
        self.assertEqual(v["indices"][0]["close"], 6000.0)  # 웹소켓 값이 아니라 종가 스냅샷

    def test_kiwoom_failure_falls_back_to_public_never_empty(self):
        store.write("market_kiwoom", market_snapshot(fetched=time.time() - 3600))  # 1시간 갱신 없음 → 공공데이터
        v = live.build_view(self.now)
        self.assertEqual((v["source"], v["state"]), ("public", "delayed"))
        self.assertEqual(v["label"], "지연 · 11/16 종가 기준 · 공공데이터")
        self.assertEqual(v["indices"][0]["close"], 5900.0)
        self.assertIsNone(v["investors"])
        with mock.patch.object(live, "_session_now", return_value="holiday"):
            store.write("kiwoom_status", {"price_source": "kiwoom", "session": "holiday"})
            self.assertEqual(live.build_view(self.now)["state"], "closed")

    def test_thirty_visitors_read_files_not_kiwoom(self):
        self.ws()
        with mock.patch.object(live, "build_view", wraps=live.build_view) as bv:
            for _ in range(30):
                live.view()
        self.assertEqual(bv.call_count, 1)  # 2초 캐시

    def test_api_endpoint(self):
        from fastapi.testclient import TestClient

        from api.main import app
        self.ws()
        with mock.patch.dict("os.environ", {"STOCKON_ENABLED": "1"}):
            r = TestClient(app).get("/api/stock/live")  # lifespan(스케줄러)은 띄우지 않는다
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "live")


class SummaryTest(ViewBase):
    def test_keep_when_small_change_new_when_top_sector_changes(self):
        self.ws()
        live.collect_extra(FakeClient(), self.now)
        f = live.summary_facts(live.build_view(self.now))
        self.assertEqual(f["_top"], "전기전자")
        prev = {"as_of": TODAY, "kind": "intraday", "ts": time.time() - 700, "facts": {"코스피 등락률(%)": 0.30, "코스닥 등락률(%)": 0.05, "_top": "전기전자"}}
        self.assertEqual(live.summary_due(prev, f, self.now, False), "keep")  # 0.08%p·0.05%p 변화, 1위 같음
        self.assertEqual(live.summary_due({**prev, "ts": time.time() - 60}, f, self.now, False), "")  # 10분 안
        self.assertEqual(live.summary_due({**prev, "facts": {**prev["facts"], "_top": "음식료품"}}, f, self.now, False), "new")
        self.assertEqual(live.summary_due({**prev, "facts": {**prev["facts"], "코스피 등락률(%)": 0.1}}, f, self.now, False), "new")
        self.assertEqual(live.summary_due(prev, f, self.now, True), "new")  # 마감 요약
        self.assertEqual(live.summary_due({**prev, "kind": "close"}, f, self.now, True), "")  # 하루 1번

    def _fake_ai(self, line):
        resp = SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=900, output_tokens=40),
                               content=[SimpleNamespace(type="text", text=json.dumps({"line": line}))])
        return SimpleNamespace(messages=SimpleNamespace(create=mock.Mock(return_value=resp)))

    def test_maybe_summarize_ai_then_keep_and_budget(self):
        self.ws()
        live.collect_extra(FakeClient(), self.now)
        fake = self._fake_ai("외국인 매수에 전기전자 강세, 코스피 +0.4%")
        with mock.patch.object(ai, "available", return_value=True), mock.patch.object(ai, "_claude_client", return_value=fake):
            self.assertEqual(live.maybe_summarize(self.now), "ai")
            saved = store.read("market_ai")
            self.assertEqual((saved["text"], saved["ai"], saved["kind"]), ("외국인 매수에 전기전자 강세, 코스피 +0.4%", True, "intraday"))
            self.assertEqual(live.maybe_summarize(self.now), "")  # 10분 안에는 부르지 않음
            self.assertEqual(fake.messages.create.call_count, 1)
            self.assertGreater(budget.spent_today(), 0)  # 하루 비용 상한 계산에 들어간다
            store.write("market_ai", {**saved, "ts": time.time() - 700, "checked_ts": 0})
            self.assertEqual(live.maybe_summarize(self.now), "keep")  # 변화가 작으면 이전 것 유지(AI 안 부름)
            self.assertEqual(fake.messages.create.call_count, 1)
        # 상한을 넘으면 AI 없이 숫자 문장
        store.write("market_ai", {})
        with mock.patch.object(ai, "available", return_value=True), mock.patch.object(budget, "allowed", return_value=False), \
                mock.patch.object(ai, "_claude_client", return_value=fake):
            self.assertEqual(live.maybe_summarize(self.now), "rule")
        self.assertEqual(store.read("market_ai")["text"], "코스피 +0.38%, 코스닥 +0.00%, 전기전자 강세")
        self.assertFalse(live.build_view(self.now)["ai"]["ai"])

    def test_bad_ai_line_falls_back_to_rule(self):
        self.ws()
        live.collect_extra(FakeClient(), self.now)
        for line in ("반도체 매수 기회, 코스피 +0.4%", "코스피 +3.5% 급등"):  # 권유 표현 / 자료에 없는 숫자
            store.write("market_ai", {})
            with mock.patch.object(ai, "available", return_value=True), mock.patch.object(ai, "_claude_client", return_value=self._fake_ai(line)):
                self.assertEqual(live.maybe_summarize(self.now), "rule", line)

    def test_close_summary_once_after_final(self):
        self.ws()
        store.write("market_kiwoom", market_snapshot("closed"))
        live.collect_extra(FakeClient(), self.now, final=True)
        with mock.patch.object(ai, "available", return_value=False), mock.patch.object(live, "_session_now", return_value="closed"):
            self.assertEqual(live.maybe_summarize(self.now), "rule")
            self.assertEqual(store.read("market_ai")["kind"], "close")
            self.assertEqual(live.maybe_summarize(self.now), "")


class LifemapFromLiveTest(TempStore):
    def test_lifemap_rates_and_versus_market_from_same_websocket(self):
        store.write("lifemap", {"topics": [{"map": {"stages": [{"companies": [{"code": "005930"}, {"code": "000660"}]}]}}]})
        snap = {"indices": {"KOSPI": {"rate": 1.0}, "KOSDAQ": {"rate": -0.5}}, "stocks": {"005930": {"rate": 3.0}}}
        now = datetime.now(KST)
        self.assertEqual(live.lifemap_rates_from_live(snap, now), 1)
        saved = store.read("lifemap_rates")
        self.assertEqual((saved["rates"], saved["indices"]), ({"005930": 3.0}, {"KOSPI": 1.0, "KOSDAQ": -0.5}))
        self.assertTrue(lifemap.rates_due(now))  # 아직 값이 없는 회사(000660)는 REST로 한 번 채운다
        self.assertEqual(live.lifemap_rates_from_live({"indices": {"KOSPI": {"rate": 1.0}}, "stocks": {}}, now), 0)  # 지수 없으면 안 씀


class CollectorScheduleTest(TempStore):
    CFG = {"price_source": "kiwoom", "mode": "mock", "appkey": "k", "secret": "s", "mock_key_expires": None}

    def test_feed_hours_and_codes(self):
        self.assertTrue(kc.feed_wanted(self.CFG, OPEN_NOW, {}))
        self.assertTrue(kc.feed_wanted(self.CFG, OPEN_NOW.replace(hour=8, minute=58), {}))
        self.assertFalse(kc.feed_wanted(self.CFG, OPEN_NOW.replace(hour=8, minute=50), {}))
        self.assertFalse(kc.feed_wanted(self.CFG, OPEN_NOW.replace(hour=15, minute=40), {}))
        self.assertFalse(kc.feed_wanted(self.CFG, datetime(2026, 11, 21, 10, 0, tzinfo=KST), {}))  # 토요일
        self.assertFalse(kc.feed_wanted(self.CFG, OPEN_NOW, {"holiday": "20261117"}))
        self.assertFalse(kc.feed_wanted({**self.CFG, "price_source": "public"}, OPEN_NOW, {}))
        store.write("lifemap", {"topics": [{"map": {"stages": [{"companies": [{"code": "111111"}]}]}}]})
        store.write("watch", {"items": [{"code": "222222"}]})
        codes = kc.feed_codes({"heatmap": {"KOSPI": [{"code": "333333", "cap": 1}, {"code": "444444", "cap": 9}], "KOSDAQ": []}})
        self.assertEqual(codes, ["111111", "222222", "444444", "333333"])  # 뉴스 속 회사 → 관심 종목 → 시가총액 순

    def test_tick_collects_extra_every_two_minutes(self):
        calls = []

        class Client(FakeClient):
            token_issued = 1

        snap = market_snapshot()
        with mock.patch.object(kc, "collect_once", return_value=snap), \
                mock.patch.object(live, "collect_extra", side_effect=lambda c, n, final=False: calls.append(final)), \
                mock.patch.object(kc.lifemap, "rates_due", return_value=False):
            box = {"client": Client()}
            now = datetime.now(KST).replace(hour=10, minute=30)
            with mock.patch.object(kc, "session_state", return_value="open"):
                kc.tick(box, self.CFG, now, {})
                store.write("market_extra", {"as_of": now.strftime("%Y%m%d"), "fetched_ts": time.time()})
                kc.tick(box, self.CFG, now, {})
        self.assertEqual(calls, [False])  # 두 번째는 2분이 안 지나 건너뜀


if __name__ == "__main__":
    unittest.main()

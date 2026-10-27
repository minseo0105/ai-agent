"""STOCK:ON 1단계 오프라인 테스트. 외부 API·AI를 부르지 않는다(가짜 응답 사용).

실행: .venv\\Scripts\\python.exe -B -m unittest tests.test_stockon -v
"""

import json
import os
import re
import shutil
import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from services import access as ac
from services.stockon import ai, events, public_data, safety, service, store
from services.stockon.public_data import KST

ROOT = Path(__file__).resolve().parent.parent


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self):
        return self.payload


def _body(items, total=None):
    return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                         "body": {"totalCount": total if total is not None else len(items), "items": {"item": items}}}}


def _stock(code, name, market, close, rate, cap, value):
    return {"basDt": "20261026", "srtnCd": code, "itmsNm": name, "mrktCtg": market, "clpr": str(close),
            "vs": "100", "fltRt": str(rate), "trqu": "1000", "trPrc": str(value), "mrktTotAmt": str(cap)}


STOCKS = {
    "KOSPI": [
        _stock("005930", "삼성전자", "KOSPI", 70000, 1.5, 400_000_000_000_000, 900_000_000_000),
        _stock("000660", "SK하이닉스", "KOSPI", 200000, -2.1, 150_000_000_000_000, 700_000_000_000),
        _stock("999990", "작은종목", "KOSPI", 500, 29.9, 5_000_000_000, 50_000_000),  # 거래대금 5천만 → 등락 순위 제외
    ],
    "KOSDAQ": [
        _stock("247540", "에코프로비엠", "KOSDAQ", 150000, 3.2, 15_000_000_000_000, 300_000_000_000),
        _stock("123450", "하락종목", "KOSDAQ", 1000, -9.5, 100_000_000_000, 2_000_000_000),
    ],
}


def fake_http(url, params=None, timeout=None, headers=None):
    params = params or {}
    if url == public_data.STOCK_URL and params.get("likeSrtnCd") == "005930":
        return FakeResp(_body([{"basDt": "20261023"}, {"basDt": "20261026"}]))
    if url == public_data.STOCK_URL:
        assert params["basDt"] == "20261026"
        return FakeResp(_body(STOCKS[params["mrktCls"]]))
    if url == public_data.INDEX_URL:
        name = params["idxNm"]
        rows = [{"basDt": d, "idxNm": name, "clpr": str(2500 + i), "vs": "10", "fltRt": "0.4"} for i, d in enumerate(["20261023", "20261026"])]
        rows.append({"basDt": "20261026", "idxNm": f"{name} 200", "clpr": "1", "vs": "0", "fltRt": "0"})  # 이름이 다른 지수는 버린다
        # 실제 API처럼 endBasDt는 미포함
        rows = [r for r in rows if not params.get("endBasDt") or r["basDt"] < params["endBasDt"]]
        return FakeResp(_body(rows))
    raise AssertionError(url)


class SafetyTest(unittest.TestCase):
    def test_blocks_advice_and_forecast(self):
        for text in ["삼성전자 매수 추천", "목표가 9만원", "저평가 구간", "지금이 기회입니다", "내일 상승할 것으로 보인다", "비중 확대가 필요", "분할 매수 하세요"]:
            self.assertTrue(safety.banned_hits(text), text)

    def test_allows_facts(self):
        for text in ["외국인이 3거래일 연속 순매도했다", "코스피가 1.2% 올라 마감했다", "규제 우려가 사라지며 반등했다", "실적 공시 후 거래가 늘었다"]:
            self.assertFalse(safety.banned_hits(text), text)

    def test_clean_and_sources(self):
        self.assertEqual(safety.clean_text("<b>삼성</b>전자 &amp; 하이닉스"), "삼성전자 & 하이닉스")
        self.assertEqual(safety.keep_valid_sources([3, 1, 1, 9, "2"], 3), [3, 1])


class PublicDataTest(unittest.TestCase):
    def test_fetch_market_builds_heatmap_movers_directory(self):
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "test-key"}):
            market, directory = public_data.fetch_market(http=fake_http, now=datetime(2026, 10, 27, 14, tzinfo=KST))
        self.assertEqual(market["as_of"], "20261026")
        self.assertEqual([s["code"] for s in market["heatmap"]["KOSPI"]], ["005930", "000660", "999990"])
        self.assertEqual(market["movers"]["up"][0]["code"], "247540")  # 작은종목(+29.9%)은 거래대금 기준 미달로 제외
        self.assertEqual(market["movers"]["down"][0]["code"], "123450")
        self.assertEqual(market["breadth"], {"up": 3, "down": 2, "flat": 0, "total": 5})
        self.assertEqual(len(directory["stocks"]), 5)
        idx = {i["name"]: i for i in market["indices"]}
        self.assertEqual(idx["코스피"]["close"], 2501.0)  # 기준일(10/26) 값. endBasDt를 기준일로 주면 10/23 값이 나오던 버그
        self.assertEqual(idx["코스피"]["as_of"], "20261026")
        self.assertTrue(idx["코스피"]["same_day"])
        self.assertEqual(len(idx["코스닥"]["series"]), 2)

    def test_lagging_index_is_not_used_as_base_day(self):
        market = {"as_of": "20261026", "indices": [{"name": "코스피", "as_of": "20261023", "close": 5550.3, "rate": 0.3}],
                  "breadth": {"up": 1, "down": 2, "flat": 0, "total": 3}, "movers": {"value": []}}
        self.assertEqual(ai.same_day_indices(market), [])
        lines = ai.fallback_briefing(market, None)
        self.assertFalse(any("5,550" in s["text"] for s in lines))

    def test_unregistered_key_is_reported_by_code_only(self):
        resp = FakeResp({"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}, 403)
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "secret-value-123"}):
            with self.assertRaises(public_data.PublicDataError) as cm:
                public_data.latest_trading_day(http=lambda *a, **k: resp)
        self.assertEqual(cm.exception.code, "not_registered")
        self.assertNotIn("secret-value-123", str(cm.exception))


class EventsTest(unittest.TestCase):
    def test_second_thursday(self):
        self.assertEqual(events._second_thursday(2026, 11), date(2026, 11, 12))
        self.assertEqual(events._second_thursday(2026, 10), date(2026, 10, 8))

    def test_week_window_includes_file_and_rule_events(self):
        week = events.week_events(date(2026, 11, 24))  # 화요일
        titles = {(e["date"], e["title"]) for e in week["events"]}
        self.assertIn(("2026-11-26", "한국은행 금융통화위원회 통화정책방향 결정"), titles)
        self.assertEqual(week["from"], "2026-11-23")
        for e in week["events"]:
            self.assertTrue(e["source"]["name"])


class TempStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(store, "DATA_DIR", self.tmp / "stockon"),
                        mock.patch.object(store, "SETTINGS_PATH", self.tmp / "stockon_settings.json"),
                        mock.patch.object(ac, "_supabase", lambda: None),
                        mock.patch.object(ac, "ADMIN_DIR", self.tmp)]
        for p in self.patches:
            p.start()
        store._settings_cache.update(at=0.0, value=None)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class ServiceTest(TempStore):
    def _seed(self):
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, directory = public_data.fetch_market(http=fake_http)
        store.write("market", {**market, "fetched_ts": 1})
        store.write("stocks", directory)

    def test_disabled_overview_has_no_data(self):
        with mock.patch.dict(os.environ, {"STOCKON_ENABLED": ""}):
            out = service.overview()
        self.assertFalse(out["enabled"])
        self.assertNotIn("market", out)
        self.assertEqual(out["disclaimer"], "정보 제공용이며 투자 권유가 아닙니다")

    def test_overview_never_leaks_keys(self):
        self._seed()
        secrets = {"STOCKON_ENABLED": "1", "PUBLIC_DATA_API_KEY": "PUBKEY-SENTINEL", "NAVER_SEARCH_CLIENT_ID": "NAVERID-SENTINEL",
                   "NAVER_SEARCH_CLIENT_SECRET": "NAVERSECRET-SENTINEL", "DART_API_KEY": "DART-SENTINEL", "ANTHROPIC_API_KEY": "ANT-SENTINEL"}
        with mock.patch.dict(os.environ, secrets), mock.patch.object(service, "refresh_in_background", lambda *a: False):
            text = json.dumps(service.overview(), ensure_ascii=False) + json.dumps(service.admin_status(), ensure_ascii=False)
        for v in secrets.values():
            if v != "1":
                self.assertNotIn(v, text)

    def test_why_is_prebuilt_by_task_and_only_read_by_visitors(self):
        self._seed()
        store.save_watchlist([{"code": "123450", "name": "하락종목"}])
        calls = []

        def fake_why(stock, as_of, news, dart):
            calls.append(stock["code"])
            return {"sentences": [{"text": "실적 공시 뒤 거래가 늘었습니다.", "sources": [1]}], "note": "", "sources": [{"name": "n", "url": "https://x"}], "ai": True}

        # 방문자 요청: 아직 만든 설명이 없으면 ready=False, 새로 만들지 않는다
        with mock.patch.object(ai, "why_moved", side_effect=AssertionError("visitor must not call AI")):
            self.assertFalse(service.why("005930")["ready"])
        # 수집 작업이 대상(관심 종목 → 히트맵 상위 → 등락 상위)을 미리 만든다
        targets = service.why_targets(store.read("market"))
        self.assertEqual(targets[0], "123450")
        # 관심 종목 + 상승·하락 상위(거래대금 기준 통과 종목만). 히트맵 전용 종목(999990)은 대상이 아니다
        self.assertEqual(set(targets), {"123450", "005930", "000660", "247540"})
        with mock.patch.object(ai, "why_moved", fake_why), mock.patch("services.stockon.news.configured", lambda: False), \
                mock.patch("services.stockon.disclosures.recent", lambda *a, **k: []):
            service._task_why()
            service._task_why()  # 이미 만든 종목은 다시 만들지 않는다
        self.assertEqual(sorted(calls), sorted(targets))
        with mock.patch.object(ai, "why_moved", side_effect=AssertionError("visitor must not call AI")):
            got = service.why("005930")
        self.assertTrue(got["ready"])
        self.assertEqual(got["sentences"][0]["sources"], [1])
        self.assertNotIn("why", service.due_tasks())
        with self.assertRaises(KeyError):
            service.why("000000")

    def test_watchlist_validates_codes(self):
        self._seed()
        with mock.patch.object(service, "refresh_in_background", lambda *a: False):
            saved = service.save_watchlist(["005930", "247540"])
            self.assertEqual([w["name"] for w in saved["watchlist"]], ["삼성전자", "에코프로비엠"])
            with self.assertRaises(ValueError):
                service.save_watchlist(["005930", "NOPE01"])
        self.assertEqual(service.search_stocks("삼성")[0]["code"], "005930")

    def test_kiwoom_expiry_days_left(self):
        store.write("kiwoom_status", {"mode": "mock", "price_source": "public", "mock_key_expires": "2026-11-27"})
        with mock.patch.object(service, "_now", lambda: datetime(2026, 11, 22, 9, tzinfo=KST)):
            self.assertEqual(service.kiwoom_status()["days_left"], 5)
        self.assertEqual(service.kiwoom_status()["connected"], True)

    def test_briefing_falls_back_without_ai(self):
        self._seed()
        with mock.patch.object(ai, "_claude_client", lambda: None):
            out = ai.briefing(store.read("market"), None, [])
        self.assertFalse(out["ai"])
        self.assertEqual(len(out["sentences"]), 3)
        for s in out["sentences"]:
            self.assertTrue(safety.is_safe(s["text"]))
            self.assertEqual(s["sources"], [1])

    def test_ai_failures_are_recorded_for_admin_only(self):
        import anthropic
        import httpx2

        self._seed()
        market = store.read("market")
        req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        err = anthropic.BadRequestError("secret prompt text sk-ant-SENTINEL", response=httpx2.Response(400, request=req),
                                        body={"type": "error", "error": {"type": "invalid_request_error", "message": "sk-ant-SENTINEL"}})

        class FailingClient:
            class messages:
                @staticmethod
                def create(**kw):
                    raise err

        with mock.patch.object(ai, "_claude_client", lambda: FailingClient):
            out = ai.briefing(market, None, [])
            ai.summarize_news([{"title": "t", "url": "https://x", "snippet": ""}])
        self.assertFalse(out["ai"])  # 고정 문장으로 대체
        with mock.patch.dict(os.environ, {"STOCKON_ENABLED": "1"}):
            status = service.admin_status()["ai"]
            visitor = json.dumps(service.overview(), ensure_ascii=False)
        b = status["briefing"]
        self.assertEqual((b["fails_today"], b["fallbacks_today"], b["consecutive"]), (1, 1, 1))  # 호출 실패는 재시도 없이 바로 대체
        self.assertEqual(b["last_error"], "BadRequestError 400 invalid_request_error")
        self.assertEqual(status["news_summary"]["fails_today"], 1)
        self.assertNotIn("SENTINEL", json.dumps(status, ensure_ascii=False))
        self.assertNotIn("last_error", visitor)  # 방문자 화면에는 AI 오류가 나가지 않는다

        good = {"sentences": [{"text": "코스피가 올랐습니다", "sources": [1]}]}
        with mock.patch.object(ai, "_call", lambda *a, **k: good):
            self.assertTrue(ai.briefing(market, None, [])["ai"])
        with mock.patch.dict(os.environ, {"STOCKON_ENABLED": "1"}):
            b = service.admin_status()["ai"]["briefing"]
        self.assertEqual(b["consecutive"], 0)
        self.assertEqual(b["fails_today"], 1)  # 오늘 실패 횟수는 성공해도 남는다
        self.assertIsNotNone(b["ok_ts"])

    def test_unsafe_ai_sentences_are_dropped(self):
        outputs = iter([
            {"sentences": [{"text": "반도체주 매수 기회입니다", "sources": [1]}, {"text": "코스피가 올랐습니다", "sources": [1]}]},
            {"sentences": [{"text": "목표가 상향", "sources": [1]}, {"text": "코스피가 올랐습니다", "sources": [9]}]},
        ])
        with mock.patch.object(ai, "_call", lambda *a, **k: next(outputs)):
            out = ai._safe_sentences("t", {}, n_sources=2, max_items=3)
        self.assertEqual(out, [])  # 두 번째 결과도 금지 표현 + 없는 출처 번호 → 모두 버림


class NewsWindowTest(unittest.TestCase):
    def _market(self, as_of, days):
        return {"as_of": as_of, "indices": [{"name": "코스피", "series": [{"d": d, "c": 1} for d in days]}]}

    def test_window_uses_previous_trading_day_from_series(self):
        # 월요일 기준일 → 직전 거래일은 금요일(시계열), 창은 금 15:30 ~ 화 08:00
        start, end = service.news_window(self._market("20261026", ["20261022", "20261023", "20261026"]))
        self.assertEqual((start.isoformat(), end.isoformat()), ("2026-10-23T15:30:00+09:00", "2026-10-27T08:00:00+09:00"))
        # 목요일이 휴장이면(시계열에 없음) 금요일 기준일의 직전 거래일은 수요일
        start, _ = service.news_window(self._market("20261009", ["20261007", "20261008"][:1] + ["20261009"]))
        self.assertEqual(start.date().isoformat(), "2026-10-07")

    def test_search_window_filters_and_stops_paging(self):
        pages = []

        def fake(url, params=None, headers=None, timeout=None):
            start = params["start"]
            pages.append(start)
            # 1쪽: 창 뒤(다음 날 오후) 2건 + 창 안 1건, 2쪽: 창 안 1건 + 창 앞 1건 → 3쪽은 부르지 않는다
            rows = {1: [("2026-10-27 14:00", "삼성 오늘 기사"), ("2026-10-27 09:00", "다른 회사"), ("2026-10-26 16:10", "증시 마감 정리")],
                    101: [("2026-10-26 10:00", "삼성전자 장중 강세"), ("2026-10-23 12:00", "지난주 기사")]}[start]
            items = [{"title": t, "originallink": f"https://n/{start}/{i}", "description": "",
                      "pubDate": datetime.strptime(p, "%Y-%m-%d %H:%M").replace(tzinfo=KST).strftime("%a, %d %b %Y %H:%M:%S +0900")}
                     for i, (p, t) in enumerate(rows)]
            items += [{"title": f"pad{start}-{k}", "originallink": f"https://pad/{start}/{k}", "description": "",
                       "pubDate": "Tue, 27 Oct 2026 13:00:00 +0900"} for k in range(100 - len(items))] if start == 1 else []
            if start == 101:
                items += [{"title": f"old{k}", "originallink": f"https://old/{k}", "description": "", "pubDate": "Thu, 22 Oct 2026 10:00:00 +0900"} for k in range(98)]
            return FakeResp({"items": items})

        win = (datetime(2026, 10, 23, 15, 30, tzinfo=KST), datetime(2026, 10, 27, 8, 0, tzinfo=KST))
        with mock.patch.dict(os.environ, {"NAVER_SEARCH_CLIENT_ID": "i", "NAVER_SEARCH_CLIENT_SECRET": "s"}):
            from services.stockon import news
            got = news.search_window('"삼성전자"', *win, limit=8, must_contain="삼성전자", http=fake)
        self.assertEqual([n["title"] for n in got], ["삼성전자 장중 강세", "증시 마감 정리"])
        self.assertEqual(pages, [1, 101])


class WatchFiltersTest(TempStore):
    def test_only_company_filed_disclosures(self):
        from services.stockon import disclosures
        rows = [{"rcept_no": "1", "rcept_dt": "20261026", "corp_name": "삼성전자", "flr_nm": "이헌", "report_nm": "임원ㆍ주요주주특정증권등소유상황보고서"},
                {"rcept_no": "2", "rcept_dt": "20261023", "corp_name": "삼성전자", "flr_nm": "삼성물산", "report_nm": "주식등의대량보유상황보고서(일반)"},
                {"rcept_no": "3", "rcept_dt": "20261022", "corp_name": "삼성전자", "flr_nm": "삼성전자", "report_nm": "분기보고서"}]
        with mock.patch.dict(os.environ, {"DART_API_KEY": "k"}), mock.patch.object(disclosures, "corp_codes_for", lambda n: ["00126380"]):
            got = disclosures.recent("삼성전자", http=lambda *a, **k: FakeResp({"status": "000", "list": rows}))
        self.assertEqual([d["title"] for d in got], ["분기보고서"])

    def test_watch_news_needs_name_in_title(self):
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, directory = public_data.fetch_market(http=fake_http)
        store.write("stocks", directory)
        store.save_watchlist([{"code": "005930", "name": "삼성전자"}])
        found = [{"title": "[기획] AI 투자 부채의 역습…반도체 중심 경고등", "url": "https://n/1", "press": "", "pub": None},
                 {"title": "삼성전자, HBM5 전시", "url": "https://n/2", "press": "", "pub": None}]
        with mock.patch("services.stockon.news.configured", lambda: True), mock.patch("services.stockon.news.search", lambda *a, **k: found), \
                mock.patch("services.stockon.disclosures.recent", lambda *a, **k: []):
            service._task_watch()
        self.assertEqual([n["title"] for n in store.read("watch")["items"][0]["news"]], ["삼성전자, HBM5 전시"])


class BriefingNewsRuleTest(TempStore):
    def test_briefing_retries_until_a_news_sentence_exists(self):
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, _ = public_data.fetch_market(http=fake_http)
        news_items = [{"title": "반도체 수출 증가 보도", "url": "https://n/1", "snippet": ""}]
        tasks = []
        outs = iter([
            {"sentences": [{"text": "코스피가 올랐습니다", "sources": [1]}, {"text": "상승 종목이 많았습니다", "sources": [1]}]},
            {"sentences": [{"text": "코스피가 올랐습니다", "sources": [1]}, {"text": "반도체 수출이 늘었다는 보도가 나왔습니다", "sources": [3]}]},
        ])

        def fake_call(task, payload, schema, max_tokens=2000, model=ai.MODEL):
            tasks.append(task)
            return next(outs)

        with mock.patch.object(ai, "_call", fake_call):
            out = ai.briefing(market, None, news_items)
        self.assertEqual(len(tasks), 2)
        self.assertIn("뉴스·공시", tasks[1].split("주의:")[-1])
        self.assertTrue(any(3 in s["sources"] for s in out["sentences"]))
        self.assertTrue(out["ai"])


class FakeKiwoomHttp:
    """키움 공식 스펙 예시 응답을 돌려주는 가짜 전송기. 호출 기록만 남긴다(키 값은 비교만)."""

    RESP = {
        "au10001": {"expires_dt": "20991231235959", "token_type": "bearer", "token": "TOKEN-SENTINEL", "return_code": 0},
        "au10002": {"return_code": 0},
        "ka20001": {"cur_prc": "-2394.49", "pred_pre": "-278.47", "flu_rt": "-10.42", "rising": "17", "upl": "0",
                    "stdns": "183", "fall": "130", "lst": "3", "return_code": 0},
        "ka10095": {"atn_stk_infr": [{"stk_cd": "005930", "stk_nm": "삼성전자", "cur_prc": "+156600", "pred_pre": "+34900",
                                      "flu_rt": "+28.68", "trde_prica": "14889", "dt": "20261117"},
                                     {"stk_cd": "000660", "stk_nm": "SK하이닉스", "cur_prc": "-200000", "pred_pre": "-1000",
                                      "flu_rt": "-0.50", "trde_prica": "9000", "dt": "20261117"}], "return_code": 0},
        "ka10027": {"pred_pre_flu_rt_upper": [{"stk_cd": "247540", "stk_nm": "에코프로비엠", "cur_prc": "+74800",
                                               "pred_pre": "+17200", "flu_rt": "+29.86"}], "return_code": 0},
        "ka10032": {"trde_prica_upper": [{"stk_cd": "005930", "stk_nm": "삼성전자", "cur_prc": "-152000", "pred_pre": "-100",
                                          "flu_rt": "-0.07", "trde_prica": "5308092"}], "return_code": 0},
        "ka90009": {"frgnr_orgn_trde_upper": [{"for_netprps_stk_nm": "삼성전자", "for_netprps_amt": "130811",
                                               "for_netslmt_stk_nm": "SK하이닉스", "for_netslmt_amt": "-5000",
                                               "orgn_netprps_stk_nm": "에코프로비엠", "orgn_netprps_amt": "800",
                                               "orgn_netslmt_stk_nm": "삼성전자", "orgn_netslmt_amt": "-300"}], "return_code": 0},
    }

    def __init__(self, override=None):
        self.calls, self.override = [], override or {}

    def __call__(self, url, json=None, headers=None, timeout=None):
        api = headers["api-id"]
        self.calls.append((url, api, dict(headers)))
        payload = self.override.get(api, self.RESP[api])
        resp = FakeResp(payload, 200)
        resp.headers = {}
        return resp


class KiwoomClientTest(unittest.TestCase):
    def _client(self, http, mode="mock"):
        from services.stockon.kiwoom_client import KiwoomClient
        self.t = [0.0]
        self.slept = []
        return KiwoomClient(mode, "APPKEY-SENTINEL", "SECRET-SENTINEL", http=http, clock=lambda: self.t[0],
                            sleep=lambda s: (self.slept.append(s), self.t.__setitem__(0, self.t[0] + s)))

    def test_allowlist_blocks_before_network(self):
        from services.stockon.kiwoom_client import KiwoomError
        http = FakeKiwoomHttp()
        c = self._client(http)
        for bad in ("ka99999", "au10001", "../ordr", ""):
            with self.assertRaises(KiwoomError) as cm:
                c.query(bad, {})
            self.assertEqual(cm.exception.code, "not_allowed")
        self.assertEqual(http.calls, [])

    def test_host_token_reuse_and_throttle(self):
        http = FakeKiwoomHttp()
        c = self._client(http)
        c.query("ka20001", {"mrkt_tp": "0", "inds_cd": "001"})
        c.query("ka20001", {"mrkt_tp": "1", "inds_cd": "101"})  # 같은 TR → 1.1초 기다림(모의)
        self.assertEqual([a for _, a, _ in http.calls], ["au10001", "ka20001", "ka20001"])  # 토큰은 한 번만
        self.assertTrue(all(u.startswith("https://mockapi.kiwoom.com/") for u, _, _ in http.calls))
        self.assertEqual(http.calls[1][2]["authorization"], "Bearer TOKEN-SENTINEL")
        self.assertAlmostEqual(sum(self.slept), 1.1, places=3)
        real = FakeKiwoomHttp()
        self._client(real, "real").query("ka10032", {})
        self.assertTrue(real.calls[-1][0].startswith("https://api.kiwoom.com/api/dostk/rkinfo"))

    def test_errors_carry_code_only(self):
        from services.stockon.kiwoom_client import KiwoomError, price
        http = FakeKiwoomHttp({"au10001": {"return_code": 8010, "return_msg": "Token을 발급받은 IP와 서비스를 요청한 IP가 동일하지 않습니다"}})
        c = self._client(http)
        with self.assertRaises(KiwoomError) as cm:
            c.check_token()
        self.assertEqual(cm.exception.code, "8010")
        text = str(cm.exception) + repr(c)
        self.assertNotIn("APPKEY-SENTINEL", text)
        self.assertNotIn("SECRET-SENTINEL", text)
        self.assertEqual((price("+156600"), price("-2394.49")), (156600.0, 2394.49))


class KiwoomCollectorTest(TempStore):
    def test_session_boundaries(self):
        from services.stockon.kiwoom_collector import session_state
        at = lambda h, m: datetime(2026, 11, 17, h, m, tzinfo=KST)  # 화요일
        self.assertEqual([session_state(at(8, 59)), session_state(at(9, 0)), session_state(at(15, 19)),
                          session_state(at(15, 20)), session_state(at(15, 29)), session_state(at(15, 30))],
                         ["pre", "open", "open", "closing_auction", "closing_auction", "closed"])
        self.assertEqual(session_state(datetime(2026, 11, 15, 10, 0, tzinfo=KST)), "holiday")

    def test_snapshot_shape_and_auto_fallback(self):
        from services.stockon import kiwoom_collector as kc
        from services.stockon.kiwoom_client import KiwoomClient
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, directory = public_data.fetch_market(http=fake_http)
        store.write("market", {**market, "fetched_ts": 1})
        client = KiwoomClient("mock", "a", "b", http=FakeKiwoomHttp(), clock=lambda: 0.0, sleep=lambda s: None)
        now = datetime(2026, 11, 17, 14, 30, tzinfo=KST)
        snap = kc.build_snapshot(client, market, directory["stocks"], now)
        self.assertEqual((snap["kind"], snap["session"], snap["as_of"]), ("kiwoom", "open", "20261117"))
        self.assertEqual(snap["source"]["name"], "KRX 기준 · 키움증권 API")
        kospi = {s["code"]: s for s in snap["heatmap"]["KOSPI"]}
        self.assertEqual((kospi["005930"]["close"], kospi["005930"]["rate"]), (156600.0, 28.68))
        self.assertEqual(kospi["005930"]["cap"], 400_000_000_000_000)  # 칸 크기는 공공데이터 시가총액
        self.assertEqual(snap["movers"]["up"][0]["name"], "에코프로비엠")
        self.assertEqual(snap["flows"]["foreign_buy"][0], {"code": None, "name": "삼성전자", "amount": 1_308_110_000_000})
        self.assertEqual(snap["indices"][0]["close"], 2394.49)
        self.assertEqual(snap["breadth"]["total"], 2 * (17 + 183 + 130 + 3))

        snap["fetched_ts"] = time.time()
        store.write("market_kiwoom", snap)
        cfg = {"mode": "mock", "price_source": "kiwoom", "mock_key_expires": "2026-11-27"}
        kc.write_status(cfg)
        with mock.patch.object(service, "_now", lambda: now):
            self.assertEqual(service.active_market()[1], "kiwoom")
            store.write("market_kiwoom", {**snap, "fetched_ts": time.time() - 11 * 60})  # 10분 넘게 갱신 없음
            self.assertEqual(service.active_market()[1], "public")
            store.write("market_kiwoom", {**snap, "session": "closed", "fetched_ts": time.time() - 3 * 3600})
            self.assertEqual(service.active_market()[1], "kiwoom")  # 마감 기준은 그날 하루 유지
            kc.write_status({**cfg, "price_source": "public"})
            self.assertEqual(service.active_market()[1], "public")  # 설정 하나로 복귀
        with mock.patch.object(service, "_now", lambda: datetime(2026, 11, 18, 9, 5, tzinfo=KST)):
            kc.write_status(cfg)
            self.assertEqual(service.active_market()[1], "public")  # 다음 날 → 어제 키움 스냅샷은 쓰지 않음

    def test_public_mode_never_calls_kiwoom(self):
        from services.stockon import kiwoom_collector as kc
        with mock.patch.dict(os.environ, {"STOCKON_PRICE_SOURCE": "public", "KIWOOM_MOCK_APP_KEY": "a", "KIWOOM_MOCK_APP_SECRET": "b",
                                          "KIWOOM_MOCK_KEY_EXPIRES": "2026-11-27"}):
            cfg = kc.config()
        self.assertEqual((cfg["price_source"], cfg["mode"]), ("public", "mock"))
        kc.write_status(cfg, session="open")
        st = store.read("kiwoom_status")
        self.assertEqual(st["mock_key_expires"], "2026-11-27")
        self.assertNotIn("a", [st.get("appkey"), st.get("secret")])
        self.assertEqual(set(st) & {"appkey", "secret", "token"}, set())


class AccessTest(unittest.TestCase):
    def test_stockon_follows_site_setting_and_admin_can_restrict(self):
        self.assertEqual(ac.service_for_path("/api/stock/overview"), "stockon")
        self.assertEqual(ac.service_level(ac._normalize({"site_mode": "public"}), "stockon"), "public")
        restricted = ac._normalize({"site_mode": "public", "services": {"stockon": "members"}})
        self.assertEqual(ac.service_level(restricted, "stockon"), "members")  # 관리자 '서비스별 공개'로 다시 막을 수 있다


class VisitorRequestsAreReadOnlyTest(TempStore):
    """비로그인 방문자 요청이 외부 API·LLM·뉴스를 부르지 않고, 관리 API는 관리자만 쓰는지 HTTP로 확인한다."""

    def setUp(self):
        super().setUp()
        with mock.patch.dict(os.environ, {"PUBLIC_DATA_API_KEY": "k"}):
            market, directory = public_data.fetch_market(http=fake_http)
        store.write("market", {**market, "fetched_ts": 1})  # 오래된 스냅샷 → 갱신 주기가 된 상태
        store.write("stocks", directory)

    def test_public_visitor_reads_snapshots_without_outbound_calls(self):
        from fastapi.testclient import TestClient
        from api.main import app

        blocked = AssertionError("outbound call during visitor request")
        with mock.patch.dict(os.environ, {"STOCKON_ENABLED": "1", "ADMIN_PASSWORD": "pw-test", "ACCESS_SECRET": "test-secret"}), \
                mock.patch("requests.get", side_effect=blocked), mock.patch("requests.post", side_effect=blocked), \
                mock.patch.object(ai, "_call", side_effect=blocked), mock.patch("services.stockon.news.search", side_effect=blocked), \
                mock.patch.object(service, "refresh_in_background", side_effect=blocked), \
                mock.patch.object(ac, "_read_raw", lambda fresh=False: {"site_mode": "public"}):
            client = TestClient(app)  # lifespan(스케줄러)은 띄우지 않는다
            r = client.get("/api/stock/overview")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["market"]["as_of"], "20261026")
            r = client.get("/api/stock/why/005930")
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json()["ready"])
            for method, path, body in [("get", "/api/stock/admin/status", None), ("get", "/api/stock/admin/search?q=삼성", None),
                                       ("put", "/api/stock/admin/watchlist", {"codes": ["005930"]}),
                                       ("post", "/api/stock/admin/refresh", {"tasks": ["market"]})]:
                r = getattr(client, method)(path, **({"json": body} if body else {}))
                self.assertEqual(r.status_code, 401, path)
            member = ac._sign({"r": "member", "m": "x", "v": 1, "exp": 9999999999})
            r = client.get("/api/stock/admin/status", headers={"Authorization": f"Bearer {member}"})
            self.assertEqual(r.status_code, 401)


class NoOrderOrAccountCodeTest(unittest.TestCase):
    """STOCK:ON 코드에 증권사 주문·계좌·실시간 API 흔적이 없어야 한다(2단계 허용 목록 원칙)."""

    FORBIDDEN = [r"/ordr\b", r"/crdordr", r"/acnt\b", r"/dostk/watchlist", r"/websocket", r"/api/us/", r"\bkt1\d{4}\b", r"\bkt5\d{4}\b", r"\bust2\d{4}\b", r"wss://"]

    def test_sources_are_clean(self):
        files = list((ROOT / "services" / "stockon").glob("*.py")) + [ROOT / "api" / "stock.py"]
        files += list((ROOT / "web" / "src" / "components" / "stock").glob("*.tsx")) + [ROOT / "web" / "src" / "lib" / "stock.ts"]
        for f in files:
            text = f.read_text(encoding="utf-8")
            for pat in self.FORBIDDEN:
                self.assertIsNone(re.search(pat, text), f"{f.name}: {pat}")

    def test_no_browser_side_secrets(self):
        for f in [ROOT / "web" / "src" / "lib" / "stock.ts", *(ROOT / "web" / "src" / "components" / "stock").glob("*.tsx")]:
            text = f.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"NEXT_PUBLIC_(KIWOOM|NAVER_SEARCH|PUBLIC_DATA|DART)")
            self.assertNotRegex(text, r"(?i)appkey|secretkey|X-NCP-APIGW")


if __name__ == "__main__":
    unittest.main()

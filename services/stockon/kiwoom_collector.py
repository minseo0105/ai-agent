"""STOCK:ON 키움 수집기(2단계). 별도 컨테이너에서 `python -m services.stockon.kiwoom_collector`로 돈다.

- 설정·키는 .env.stockon에서만 받는다(AI LAB 웹 컨테이너에는 없음).
- STOCKON_PRICE_SOURCE=public(기본)이면 키움을 한 번도 부르지 않고 상태 파일(만료일 등)만 쓴다.
- kiwoom이면 평일 장중 1분마다 지수·히트맵 종목·등락 상위·거래대금·외국인/기관을 모아
  data/admin/stockon/market_kiwoom.json에 쓴다. AI LAB 앱은 이 파일이 새것일 때만 화면에 쓴다(아니면 공공데이터).
- 장 마감(15:30) 뒤 15:35 이후 값을 '종가 기준' 스냅샷(final)으로 남기고 그날은 멈춘다. 수집기를 저녁에 다시 켜도
  그날 종가 스냅샷이 없으면 한 번 만든다. 받은 일자가 오늘이 아니면(공휴일) 파일을 덮지 않고 그날은 쉰다.
- 실패(키움 오류·예상 밖 응답)는 상태 파일 fails에 연속 횟수로 남긴다(관리자 화면 3회부터 경고). 성공하면 0.
- 뉴스 속 숨은 종목(lifemap.py): 새 기준(공공 새 기준일·키움 장중·마감)이 생기면 토픽·섹터를 만든다
  (키는 .env.lifemap의 ANTHROPIC·NAVER 검색 키. 키움 설정과 무관하게 돈다). 키움 장중에는 30분마다
  화면에 나온 회사들의 등락률(ka10095)과 코스피·코스닥 등락률(ka20001)을 같은 때 갱신한다(시장 대비 계산, AI 재호출 없음).

첫 시험:
  python -m services.stockon.kiwoom_collector --check   # 토큰 발급 1회 + 즉시 폐기(시세 조회 없음, IP 등록 필요 여부 판별)
  python -m services.stockon.kiwoom_collector --once    # 시간과 관계없이 1회 수집(장외면 직전 값)
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime

from services.stockon import budget, lifemap, store
from services.stockon.kiwoom_client import KiwoomClient, KiwoomError, num, price
from services.stockon.public_data import KST, MARKETS, MOVER_MIN_VALUE, MOVERS_N

log = logging.getLogger("stockon.kiwoom")

SOURCE = {"name": "KRX 기준 · 키움증권 API", "url": "https://openapi.kiwoom.com"}
OPEN, AUCTION, CLOSE = (9, 0), (15, 20), (15, 30)
FINAL_FROM = (15, 35)  # 이 시각 이후 마감 값을 그날 '종가 기준'(final)으로 확정
HOLIDAY_FROM = (9, 10)  # 장 시작 직후에는 일자가 아직 어제일 수 있어 이때부터 휴장으로 본다
TICK_ACTIVE, TICK_IDLE = 60, 120
SESSION_LABEL = {"pre": "장 시작 전", "open": "장중", "closing_auction": "마감 동시호가", "closed": "종가 기준", "holiday": "휴장"}
INDEX_BODIES = {"코스피": {"mrkt_tp": "0", "inds_cd": "001"}, "코스닥": {"mrkt_tp": "1", "inds_cd": "101"}}
CHUNK = 20  # ka10095 한 번에 묻는 종목 수


def session_state(now: datetime) -> str:
    """평일 기준 장 상태. 공휴일 휴장은 수집한 일자(dt)로 다시 확인한다."""
    if now.weekday() >= 5:
        return "holiday"
    hm = (now.hour, now.minute)
    if hm < OPEN:
        return "pre"
    if hm < AUCTION:
        return "open"
    if hm < CLOSE:
        return "closing_auction"
    return "closed"


def config() -> dict:
    env = os.environ
    mode = (env.get("KIWOOM_MODE") or "mock").strip()
    prefix = "KIWOOM_REAL_" if mode == "real" else "KIWOOM_MOCK_"
    return {
        "price_source": (env.get("STOCKON_PRICE_SOURCE") or "public").strip(),
        "mode": mode,
        "appkey": (env.get(prefix + "APP_KEY") or "").strip(),
        "secret": (env.get(prefix + "APP_SECRET") or "").strip(),
        "mock_key_expires": (env.get("KIWOOM_MOCK_KEY_EXPIRES") or "").strip() or None,
    }


def write_status(cfg: dict, **kw) -> None:
    """관리자 화면용. 날짜·횟수·코드만(키·토큰 없음)."""
    prev = store.read("kiwoom_status", {}) or {}
    status = {"mode": cfg["mode"], "price_source": cfg["price_source"], "mock_key_expires": cfg["mock_key_expires"],
              "last_ok": prev.get("last_ok"), "fails": prev.get("fails", 0), "last_error": prev.get("last_error"),
              "session": prev.get("session"), "updated": datetime.now(KST).isoformat(timespec="seconds")}
    status.update(kw)
    store.write("kiwoom_status", status)


# ---------------------------------------------------------
# 수집 → 화면 스냅샷 (공공데이터 market.json과 같은 모양)
# ---------------------------------------------------------

def _stock(code: str, name: str, market: str, cur, change, rate, value_million, cap=None) -> dict:
    return {"code": code, "name": name, "market": market, "close": price(cur), "change": num(change, int) if change else None,
            "rate": num(rate), "volume": None, "value": int(num(value_million) * 1_000_000) if num(value_million) is not None else None,
            "cap": cap}


def _rows(data: dict, key: str) -> list[dict]:
    rows = data.get(key)
    return rows if isinstance(rows, list) else []


def build_snapshot(client: KiwoomClient, public_market: dict, directory: dict, now: datetime) -> dict:
    session = session_state(now)
    indices, breadth = [], {"up": 0, "down": 0, "flat": 0, "total": 0}
    pub_idx = {i["name"]: i for i in public_market.get("indices", [])}
    for name, body in INDEX_BODIES.items():
        d = client.query("ka20001", body)
        up = (num(d.get("rising"), int) or 0) + (num(d.get("upl"), int) or 0)
        down = (num(d.get("fall"), int) or 0) + (num(d.get("lst"), int) or 0)
        flat = num(d.get("stdns"), int) or 0
        breadth = {"up": breadth["up"] + up, "down": breadth["down"] + down, "flat": breadth["flat"] + flat,
                   "total": breadth["total"] + up + down + flat}
        series = list((pub_idx.get(name) or {}).get("series") or [])
        today = now.strftime("%Y%m%d")
        series = [p for p in series if p.get("d") != today] + [{"d": today, "c": price(d.get("cur_prc"))}]
        indices.append({"name": name, "as_of": today, "same_day": True, "close": price(d.get("cur_prc")),
                        "change": num(d.get("pred_pre")), "rate": num(d.get("flu_rt")), "series": series[-30:], "source": SOURCE})

    # 히트맵: 칸 크기는 공공데이터 시가총액(전일), 가격·등락은 키움
    heatmap, as_of = {}, now.strftime("%Y%m%d")
    for market in MARKETS:
        base = (public_market.get("heatmap") or {}).get(market) or []
        quotes = {}
        for i in range(0, len(base), CHUNK):
            codes = "|".join(s["code"] for s in base[i:i + CHUNK])
            for q in _rows(client.query("ka10095", {"stk_cd": codes}), "atn_stk_infr"):
                quotes[str(q.get("stk_cd"))] = q
                if q.get("dt"):
                    as_of = str(q["dt"])
        heatmap[market] = [
            _stock(s["code"], s["name"], market, q.get("cur_prc"), q.get("pred_pre"), q.get("flu_rt"), q.get("trde_prica"), s.get("cap"))
            for s in base if (q := quotes.get(s["code"]))
        ]

    # 팀 관심 종목: 히트맵에 없는 종목만 따로 묻는다(오늘 시장 관심 종목 가격도 같은 시점으로)
    have = {s["code"] for lst in heatmap.values() for s in lst}
    # (관심 종목 목록은 앱이 쓰는 watch.json에서 — 수집기는 설정 저장소 키가 없다)
    watch = [w for w in (store.read("watch") or {}).get("items") or [] if w.get("code") and w["code"] not in have]
    quotes_extra = {}
    for i in range(0, len(watch), CHUNK):
        for q in _rows(client.query("ka10095", {"stk_cd": "|".join(w["code"] for w in watch[i:i + CHUNK])}), "atn_stk_infr"):
            code = str(q.get("stk_cd"))
            d = directory.get(code) or {}
            quotes_extra[code] = _stock(code, d.get("name", code), d.get("market", ""), q.get("cur_prc"), q.get("pred_pre"),
                                        q.get("flu_rt"), q.get("trde_prica"), d.get("cap"))

    def mover_rows(sort_tp: str) -> list[dict]:
        data = client.query("ka10027", {"mrkt_tp": "000", "sort_tp": sort_tp, "trde_qty_cnd": "0000", "stk_cnd": "1",
                                        "crd_cnd": "0", "updown_incls": "1", "pric_cnd": "0", "trde_prica_cnd": "100", "stex_tp": "1"})
        out = []
        for r in _rows(data, "pred_pre_flu_rt_upper")[:MOVERS_N]:
            code = str(r.get("stk_cd"))
            d = directory.get(code) or {}
            out.append(_stock(code, r.get("stk_nm") or d.get("name", code), d.get("market", ""), r.get("cur_prc"),
                              r.get("pred_pre"), r.get("flu_rt"), None, d.get("cap")))
        return out

    value_rows = []
    for r in _rows(client.query("ka10032", {"mrkt_tp": "000", "mang_stk_incls": "0", "stex_tp": "1"}), "trde_prica_upper")[:MOVERS_N]:
        code = str(r.get("stk_cd"))
        d = directory.get(code) or {}
        value_rows.append(_stock(code, r.get("stk_nm") or d.get("name", code), d.get("market", ""), r.get("cur_prc"),
                                 r.get("pred_pre"), r.get("flu_rt"), r.get("trde_prica"), d.get("cap")))

    flows = {}
    rows = _rows(client.query("ka90009", {"mrkt_tp": "000", "amt_qty_tp": "1", "qry_dt_tp": "0", "stex_tp": "1"}), "frgnr_orgn_trde_upper")
    for key, (code_f, name_f, amt_f) in {
        "foreign_buy": ("for_netprps_stk_cd", "for_netprps_stk_nm", "for_netprps_amt"),
        "foreign_sell": ("for_netslmt_stk_cd", "for_netslmt_stk_nm", "for_netslmt_amt"),
        "inst_buy": ("orgn_netprps_stk_cd", "orgn_netprps_stk_nm", "orgn_netprps_amt"),
        "inst_sell": ("orgn_netslmt_stk_cd", "orgn_netslmt_stk_nm", "orgn_netslmt_amt"),
    }.items():
        # 금액 단위: 천만 원
        flows[key] = [{"code": r.get(code_f), "name": r.get(name_f), "amount": abs(num(r.get(amt_f)) or 0) * 10_000_000}
                      for r in rows[:5] if r.get(name_f)]

    return {
        "kind": "kiwoom", "as_of": as_of, "session": session, "session_label": SESSION_LABEL[session],
        "source": SOURCE, "indices": indices, "heatmap": heatmap,
        "movers": {"up": mover_rows("1"), "down": mover_rows("3"), "value": value_rows},
        "breadth": breadth, "mover_min_value": MOVER_MIN_VALUE, "flows": flows, "quotes": quotes_extra,
        "final": session == "closed" and (now.hour, now.minute) >= FINAL_FROM, "fetched_ts": time.time(),
    }


# ---------------------------------------------------------
# 실행
# ---------------------------------------------------------

def fetch_rates(client: KiwoomClient, codes: list[str]) -> dict[str, float]:
    """지정종목 정보(ka10095)로 등락률만."""
    rates: dict[str, float] = {}
    for i in range(0, len(codes), CHUNK):
        for q in _rows(client.query("ka10095", {"stk_cd": "|".join(codes[i:i + CHUNK])}), "atn_stk_infr"):
            if q.get("stk_cd") and num(q.get("flu_rt")) is not None:
                rates[str(q["stk_cd"])] = num(q.get("flu_rt"))
    return rates


def fetch_index_rates(client: KiwoomClient) -> dict[str, float]:
    """코스피·코스닥 등락률(ka20001) → {"KOSPI": rate, "KOSDAQ": rate}. 회사 등락률을 읽은 바로 뒤에 불러 같은 때 값으로 쓴다."""
    out = {}
    for name, body in INDEX_BODIES.items():
        rate = num(client.query("ka20001", body).get("flu_rt"))
        if rate is not None:
            out[lifemap.INDEX_MARKET[name]] = rate
    return out


def fetch_live(client: KiwoomClient, codes: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    """회사 등락률과 지수 등락률을 같은 때(연달아) 읽는다."""
    return fetch_rates(client, codes), fetch_index_rates(client)


def refresh_lifemap_rates(client: KiwoomClient, now: datetime, closed: bool = False) -> int:
    """뉴스 속 숨은 종목의 '실제 등락': 화면에 나온 회사 등락률(ka10095)과 지수 등락률(ka20001)을 같은 때 다시 읽는다."""
    codes = lifemap.reaction_codes()
    rates, indices = fetch_live(client, codes)
    lifemap.save_live_rates(rates, now, closed=closed, codes=codes, indices=indices)
    return len(rates)


def final_today(now: datetime) -> bool:
    """오늘 종가 기준(final) 스냅샷이 이미 있나(수집기를 다시 켜도 다시 만들지 않게 파일로 본다)."""
    snap = store.read("market_kiwoom") or {}
    return snap.get("as_of") == now.strftime("%Y%m%d") and bool(snap.get("final"))


def collect_once(client: KiwoomClient, cfg: dict, now: datetime) -> dict:
    """한 번 수집. 받은 일자가 오늘이면 market_kiwoom.json에 쓰고, 아니면(휴장·장 시작 직후) 덮지 않는다."""
    public_market = store.read("market") or {}
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    if not public_market:
        raise KiwoomError("no_public_market", "공공데이터 시세(종목 목록·시가총액)가 아직 없음")
    snap = build_snapshot(client, public_market, directory, now)
    today = snap["as_of"] == now.strftime("%Y%m%d")
    if today:
        store.write("market_kiwoom", snap)
    write_status(cfg, last_ok=datetime.now(KST).isoformat(timespec="seconds"), fails=0, last_error=None,
                 session=snap["session"] if today else "holiday", tokens_issued=client.token_issued)
    return snap


def _fail(cfg: dict, code: str, message: str, session: str) -> int:
    prev = store.read("kiwoom_status", {}) or {}
    fails = prev.get("fails", 0) + 1
    write_status(cfg, fails=fails, last_error=f"{code} {message}"[:80], session=session,
                 last_fail=datetime.now(KST).isoformat(timespec="seconds"))
    return fails


def tick(client_box: dict, cfg: dict, now: datetime, state: dict, sleep=time.sleep) -> bool:
    """수집 루프 한 번. 키움을 불렀으면 True. state = {"holiday": 휴장으로 본 날짜}."""
    session = session_state(now)
    today = now.strftime("%Y%m%d")
    if cfg["price_source"] != "kiwoom" or session in ("pre", "holiday") or state.get("holiday") == today:
        write_status(cfg, session="holiday" if state.get("holiday") == today else session)  # 키움 호출 없음
        return False
    try:
        client = client_box.get("client") or KiwoomClient(cfg["mode"], cfg["appkey"], cfg["secret"])
        client_box["client"] = client
        lifemap.rate_source = lambda codes: fetch_live(client, codes)  # 새 이슈의 회사·지수 등락률(같은 때)
        if session == "closed" and final_today(now):
            if lifemap.rates_due(now, closed=True):
                refresh_lifemap_rates(client, now, closed=True)  # 새 이슈가 생기면 그 회사들 종가 등락률만
                return True
            write_status(cfg, session="closed")
            return False
        snap = collect_once(client, cfg, now)
        if snap["as_of"] != today:
            if (now.hour, now.minute) >= HOLIDAY_FROM:
                state["holiday"] = today  # 공휴일: 그날은 더 부르지 않는다(화면은 공공데이터)
            return True
        if lifemap.rates_due(now, closed=bool(snap.get("final"))):
            try:
                refresh_lifemap_rates(client, now, closed=bool(snap.get("final")))  # 장중 30분마다, AI 호출 없음
            except KiwoomError as e:
                log.warning("lifemap rates failed: %s", e.code)
        return True
    except KiwoomError as e:
        _fail(cfg, e.code, e.message, session)
        log.warning("kiwoom collect failed: %s", e.code)
        if e.code in ("8001", "8002", "8010", "8030", "not_configured"):
            sleep(600)  # 키·IP 문제는 반복 호출해도 해결되지 않는다(토큰 무효 8005는 클라이언트가 다시 받는다)
        return True
    except Exception as e:  # 예상 밖 응답 등으로 루프가 멈추지 않게
        _fail(cfg, "unexpected", type(e).__name__, session)
        log.warning("kiwoom collect error: %s", type(e).__name__)
        return True


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    budget.BUCKET = "collector"  # AI 하루 비용은 앱·수집기 파일을 합쳐 본다
    cfg = config()
    write_status(cfg)
    if "--check" in argv or "--once" in argv:
        try:
            client = KiwoomClient(cfg["mode"], cfg["appkey"], cfg["secret"])
            client.check_token()
            print(f"토큰 발급: 성공 (mode={cfg['mode']})")
            if "--once" in argv:
                snap = collect_once(client, cfg, datetime.now(KST))
                print(f"수집: 성공 · 기준 {snap['as_of']} · {snap['session_label']} · 히트맵 "
                      f"{sum(len(v) for v in snap['heatmap'].values())}종목 · 상승상위 {len(snap['movers']['up'])}")
            client.revoke()
            print("토큰 폐기: 완료")
            return 0
        except KiwoomError as e:
            print(f"실패: {e.code} {e.message}")  # 8010 등 IP 관련이면 키움 포털 IP 등록 확인
            write_status(cfg, last_error=f"{e.code} {e.message}"[:80])
            return 1

    client_box: dict = {}
    state: dict = {}
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    while not stop["flag"]:
        now = datetime.now(KST)
        try:
            lifemap.maybe_run_daily(now)  # 할 때가 됐을 때만 별도 스레드로(키움 수집을 막지 않음)
        except Exception as e:
            log.warning("lifemap check failed: %s", type(e).__name__)
        active = tick(client_box, cfg, now, state)
        for _ in range(TICK_ACTIVE if active else TICK_IDLE):
            if stop["flag"]:
                break
            time.sleep(1)
    if client_box.get("client"):
        client_box["client"].revoke()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

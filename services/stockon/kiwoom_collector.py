"""STOCK:ON 키움 수집기(2단계). 별도 컨테이너에서 `python -m services.stockon.kiwoom_collector`로 돈다.

- 설정·키는 .env.stockon에서만 받는다(AI LAB 웹 컨테이너에는 없음).
- STOCKON_PRICE_SOURCE=public(기본)이면 키움을 한 번도 부르지 않고 상태 파일(만료일 등)만 쓴다.
- kiwoom이면 평일 장중 1분마다 지수·히트맵 종목·등락 상위·거래대금·외국인/기관을 모아
  data/admin/stockon/market_kiwoom.json에 쓴다. AI LAB 앱은 이 파일이 새것일 때만 화면에 쓴다(아니면 공공데이터).
- 장 마감(15:30) 뒤 한 번 더 모아 '마감 기준' 스냅샷을 남기고 그날은 멈춘다.
- 뉴스 속 숨은 종목(lifemap.py): 새 기준(공공 새 기준일·키움 장중·마감)이 생기면 토픽·섹터를 만든다
  (키는 .env.lifemap의 ANTHROPIC·NAVER 검색 키. 키움 설정과 무관하게 돈다). 키움 장중에는 30분마다
  화면에 나온 회사들의 등락률만 ka10095로 갱신한다(AI 재호출 없음).

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

from services.stockon import lifemap, store
from services.stockon.kiwoom_client import KiwoomClient, KiwoomError, num, price
from services.stockon.public_data import KST, MARKETS, MOVER_MIN_VALUE, MOVERS_N

log = logging.getLogger("stockon.kiwoom")

SOURCE = {"name": "KRX 기준 · 키움증권 API", "url": "https://openapi.kiwoom.com"}
OPEN, AUCTION, CLOSE = (9, 0), (15, 20), (15, 30)
CLOSED_SNAPSHOT_UNTIL = (16, 30)  # 마감 기준 스냅샷을 만드는 마지막 시각
TICK_ACTIVE, TICK_IDLE = 60, 120
SESSION_LABEL = {"pre": "장 시작 전", "open": "장중", "closing_auction": "마감 동시호가", "closed": "마감 기준", "holiday": "휴장"}
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
        "breadth": breadth, "mover_min_value": MOVER_MIN_VALUE, "flows": flows, "fetched_ts": time.time(),
    }


# ---------------------------------------------------------
# 실행
# ---------------------------------------------------------

def refresh_lifemap_rates(client: KiwoomClient, now: datetime) -> int:
    """뉴스 속 숨은 종목의 '실제 반응': 화면에 나온 회사 등락률만 지정종목 정보(ka10095)로 다시 읽는다."""
    codes = lifemap.reaction_codes()
    rates: dict[str, float] = {}
    for i in range(0, len(codes), CHUNK):
        for q in _rows(client.query("ka10095", {"stk_cd": "|".join(codes[i:i + CHUNK])}), "atn_stk_infr"):
            if q.get("stk_cd") and num(q.get("flu_rt")) is not None:
                rates[str(q["stk_cd"])] = num(q.get("flu_rt"))
    lifemap.save_live_rates(rates, now)
    return len(rates)


def collect_once(client: KiwoomClient, cfg: dict, now: datetime) -> dict:
    public_market = store.read("market") or {}
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    if not public_market:
        raise KiwoomError("no_public_market", "공공데이터 시세(종목 목록·시가총액)가 아직 없음")
    snap = build_snapshot(client, public_market, directory, now)
    store.write("market_kiwoom", snap)
    write_status(cfg, last_ok=datetime.now(KST).isoformat(timespec="seconds"), fails=0, last_error=None, session=snap["session"])
    return snap


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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

    client = None
    closed_done = None
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    while not stop["flag"]:
        now = datetime.now(KST)
        try:
            lifemap.maybe_run_daily(now)  # 할 때가 됐을 때만 별도 스레드로(키움 수집을 막지 않음)
        except Exception as e:
            log.warning("lifemap check failed: %s", type(e).__name__)
        session = session_state(now)
        active = False
        if cfg["price_source"] != "kiwoom":
            write_status(cfg, session=session)  # 키움 호출 없음
        elif session in ("open", "closing_auction") or (
                session == "closed" and closed_done != now.date() and (now.hour, now.minute) < CLOSED_SNAPSHOT_UNTIL):
            active = True
            try:
                client = client or KiwoomClient(cfg["mode"], cfg["appkey"], cfg["secret"])
                snap = collect_once(client, cfg, now)
                if snap["as_of"] == now.strftime("%Y%m%d") and lifemap.rates_due(now):
                    try:
                        refresh_lifemap_rates(client, now)  # 30분마다(장중), AI 호출 없음
                    except KiwoomError as e:
                        log.warning("lifemap rates failed: %s", e.code)
                if session == "closed" and (now.hour, now.minute) >= (15, 35):
                    closed_done = now.date()  # 마감 5분 뒤 값을 '마감 기준'으로 확정하고 그날은 멈춤
                if snap["as_of"] != now.strftime("%Y%m%d"):
                    write_status(cfg, session="holiday")  # 일자가 오늘이 아니면 휴장
            except KiwoomError as e:
                prev = store.read("kiwoom_status", {}) or {}
                write_status(cfg, fails=prev.get("fails", 0) + 1, last_error=f"{e.code} {e.message}"[:80], session=session)
                log.warning("kiwoom collect failed: %s", e.code)
                if e.code in ("8001", "8002", "8005", "8010", "8030", "not_configured"):
                    time.sleep(600)  # 키·IP 문제는 반복 호출해도 해결되지 않는다
        else:
            write_status(cfg, session=session)
        for _ in range(TICK_ACTIVE if active else TICK_IDLE):
            if stop["flag"]:
                break
            time.sleep(1)
    if client:
        client.revoke()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

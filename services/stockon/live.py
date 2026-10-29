"""STOCK:ON '오늘 시장' 실시간 장중 동향.

수집기(stockon-collector)가 쓰고 → AI LAB 앱이 읽기만 한다(방문자 수와 키움 호출 수는 무관).
- market_live.json   : 키움 웹소켓 값(지수 0J·업종등락 0U·종목 0B). 수집기가 5초마다 쓴다(kiwoom_realtime).
- market_extra.json  : REST 2분 주기 — 업종별 등락(ka20003), 투자자별 순매수(ka10051), 지수 5분봉(ka20005).
- market_kiwoom.json : REST 1분 주기 스냅샷(지수·히트맵·등락 상위·거래대금 상위) — 웹소켓이 안 될 때의 바탕.
- market_ai.json     : AI 장중 한 줄 요약(Haiku 5.5, 10분마다. 지수 변화 ±0.2%p 미만이고 업종 1위가 같으면 이전 것 유지),
                       장 마감 뒤 '오늘 마감 요약' 1번. 하루 비용 상한(budget)을 넘으면 만들지 않고 숫자 문장으로.
화면 상태(state): live = 웹소켓 값이 1분 안에 들어옴('● 실시간') / delayed = 장중인데 1분 넘게 끊김('지연', 마지막 값 유지)
                  / closed = 장 마감·주말·공휴일('장 마감 · 종가 기준'). 키움 자료가 없으면 공공데이터(전일 종가)로 채운다.
"""

import json
import logging
import re
import threading
import time
from datetime import datetime

from services.stockon import ai, budget, store
from services.stockon.kiwoom_client import num, price
from services.stockon.public_data import KST
from services.stockon.safety import banned_hits

log = logging.getLogger("stockon.live")

LIVE_FRESH_SEC = 60        # 웹소켓 값이 이보다 오래되면 '지연'
EXTRA_EVERY_SEC = 120      # 업종·투자자·5분봉 REST 주기
SUMMARY_MODEL = "claude-haiku-5-5"
SUMMARY_EVERY_SEC = 600    # AI 장중 요약 확인 간격
SUMMARY_SAME_PP = 0.2      # 지수 변화가 이보다 작고 업종 1위가 같으면 이전 요약 유지
MARKETS = ("KOSPI", "KOSDAQ")
INDEX_NAME = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}
COMPOSITE = {"KOSPI": "001", "KOSDAQ": "101"}
# 업종 순위에서 빼는 것: 시장 전체·규모별·지수 묶음(코스피200 등)·여러 업종을 묶은 상위 분류(제조 등)
NOT_SECTOR = re.compile(r"종합|대형주|중형주|소형주|KOSPI|KOSDAQ|KRX|코스피|코스닥|\d|인버스|레버리지|우량|벤처|기술성장|글로벌|F-|^제조$|^일반서비스$")


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(KST)).strftime("%Y%m%d")


def _rows(data: dict, key: str) -> list[dict]:
    rows = (data or {}).get(key)
    return rows if isinstance(rows, list) else []


# ---------------------------------------------------------
# 수집기: REST 2분 주기(업종·투자자·5분봉)
# ---------------------------------------------------------

def parse_sectors(data: dict) -> tuple[list[dict], dict]:
    """ka20003 전업종지수 → (업종 [{code,name,rate}], 시장 전체 행의 상한·하한·상승·보합·하락 수)."""
    sectors, whole = [], {}
    for r in _rows(data, "all_inds_idex"):
        code, name, rate = str(r.get("stk_cd") or ""), str(r.get("stk_nm") or "").strip(), num(r.get("flu_rt"))
        if code in COMPOSITE.values():
            whole = {k: int(num(r.get(f)) or 0) for k, f in
                     (("upper", "upl"), ("up", "rising"), ("flat", "stdns"), ("down", "fall"), ("lower", "lst"))}
            continue
        if rate is None or not name or NOT_SECTOR.search(name) or not (num(r.get("flo_stk_num")) or 0):
            continue
        sectors.append({"code": code, "name": name, "rate": rate})
    return sectors, whole


def parse_investors(data: dict, composite: str) -> dict | None:
    """ka10051 업종별투자자순매수의 시장 전체 행 → 억 원(응답 단위 백만 원 ÷ 100). 개인+외국인+기관+기타 ≈ 0."""
    row = next((r for r in _rows(data, "inds_netprps") if str(r.get("inds_cd")) == composite), None)
    if not row:
        return None
    eok = lambda f: round((num(row.get(f)) or 0) / 100, 1)  # noqa: E731
    return {"foreign": eok("frgnr_netprps"), "inst": eok("orgn_netprps"), "indiv": eok("ind_netprps")}


def parse_intraday(data: dict, day: str) -> list[dict]:
    """ka20005 업종분봉(5분) → 오늘 [{t: 'HHMM', c: 지수}] 오래된 순. 응답 지수는 ×100 정수."""
    out = []
    for r in _rows(data, "inds_min_pole_qry"):
        tm = str(r.get("cntr_tm") or "")
        c = price(r.get("cur_prc"))
        if tm.startswith(day) and c is not None:
            out.append({"t": tm[8:12], "c": round(c / 100, 2)})
    return sorted(out, key=lambda p: p["t"])


def extra_due(now: datetime, final: bool = False) -> bool:
    saved = store.read("market_extra") or {}
    if saved.get("as_of") != _today(now):
        return True
    if final:
        return not saved.get("final")
    return time.time() - saved.get("fetched_ts", 0) >= EXTRA_EVERY_SEC


def collect_extra(client, now: datetime, final: bool = False) -> dict:
    """업종별 등락·투자자별 순매수·지수 5분봉을 REST로(TR 6번, 전체 1.1초 간격). 실패한 항목은 이전 값을 둔다."""
    from services.stockon.kiwoom_client import KiwoomError
    day = _today(now)
    prev = store.read("market_extra") or {}
    keep = prev if prev.get("as_of") == day else {}
    out = {"as_of": day, "fetched_ts": time.time(), "final": final,
           **{k: dict(keep.get(k) or {}) for k in ("sectors", "whole", "investors", "intraday")}}
    for market in MARKETS:
        comp = COMPOSITE[market]
        try:
            out["sectors"][market], out["whole"][market] = parse_sectors(client.query("ka20003", {"inds_cd": comp}))
        except KiwoomError as e:
            log.warning("extra sectors %s: %s", market, e.code)
        try:
            inv = parse_investors(client.query("ka10051", {"mrkt_tp": "0" if market == "KOSPI" else "1", "amt_qty_tp": "0",
                                                           "base_dt": day, "stex_tp": "1"}), comp)
            if inv:
                out["investors"][market] = inv
        except KiwoomError as e:
            log.warning("extra investors %s: %s", market, e.code)
        try:
            series = parse_intraday(client.query("ka20005", {"inds_cd": comp, "tic_scope": "5"}), day)
            if series:
                out["intraday"][market] = series
        except KiwoomError as e:
            log.warning("extra intraday %s: %s", market, e.code)
    store.write("market_extra", out)
    return out


# ---------------------------------------------------------
# 수집기: 웹소켓 값 저장(5초마다) + 뉴스 속 숨은 종목 실제 등락(1분마다)
# ---------------------------------------------------------

def write_live(snapshot: dict) -> None:
    store.write("market_live", {**snapshot, "written_ts": time.time()})


def lifemap_rates_from_live(snapshot: dict, now: datetime) -> int:
    """뉴스 속 숨은 종목의 회사 등락률을 웹소켓 값으로(지수도 같은 웹소켓 값 → 시장 대비가 같은 시각). AI 호출 없음.
    웹소켓에 아직 값이 없는 회사는 오늘 저장된 값을 둔다. 갱신한 회사 수."""
    from services.stockon import lifemap
    idx = {m: (snapshot.get("indices") or {}).get(m, {}).get("rate") for m in MARKETS}
    if any(v is None for v in idx.values()):
        return 0
    codes = lifemap.reaction_codes()
    stocks = snapshot.get("stocks") or {}
    got = {c: stocks[c]["rate"] for c in codes if c in stocks and stocks[c].get("rate") is not None}
    if not got:
        return 0
    prev = store.read("lifemap_rates") or {}
    same_day = prev.get("as_of") == _today(now)
    rates = {**(prev.get("rates") or {} if same_day else {}), **got}
    asked = set(prev.get("codes") or []) if same_day else set()
    lifemap.save_live_rates(rates, now, closed=False, codes=sorted(asked | set(rates)), indices=idx)
    return len(got)


# ---------------------------------------------------------
# 화면 데이터(앱이 읽는다) — 파일만 읽고, 2초 동안 같은 결과를 재사용
# ---------------------------------------------------------

_cache: dict = {"ts": 0.0, "value": None}
_cache_lock = threading.Lock()
CACHE_SEC = 2.0


def _session_now(now: datetime) -> str:
    from services.stockon.kiwoom_collector import session_state
    return session_state(now)


def _overlay(s: dict, q: dict | None) -> dict:
    if not q:
        return s
    return {**s, **{k: q[k] for k in ("close", "change", "rate") if q.get(k) is not None}}


def build_view(now: datetime | None = None) -> dict:
    from services.stockon import service
    now = now or datetime.now(KST)
    now_ts = time.time()
    day = _today(now)
    market, source = service.active_market()
    market = market or {}
    status = store.read("kiwoom_status") or {}
    ws = store.read("market_live") or {}
    extra = store.read("market_extra") or {}
    summary = store.read("market_ai") or {}
    ws_today = ws.get("day") == day
    extra_today = extra.get("as_of") == day and source == "kiwoom"
    clock = _session_now(now)
    session = market.get("session") if source == "kiwoom" else clock
    if status.get("session") == "holiday":
        session = "holiday"
    last = ws.get("last_msg_ts") if ws_today else None

    if source == "kiwoom" and session in ("open", "closing_auction"):
        fresh = bool(last and now_ts - last <= LIVE_FRESH_SEC)
        state = "live" if fresh else "delayed"
        updated = last if fresh else max(last or 0, market.get("fetched_ts") or 0) or None
    elif source == "public" and clock in ("open", "closing_auction") and status.get("price_source") == "kiwoom" \
            and status.get("session") != "holiday":
        state, updated = "delayed", market.get("fetched_ts")  # 키움이 안 될 때: 공공데이터(전일 종가)로 채우고 '지연'
    else:
        state, updated = "closed", market.get("fetched_ts")
    overlay = ws_today and state in ("live", "delayed") and source == "kiwoom"
    live_idx = (ws.get("indices") or {}) if overlay else {}
    live_stocks = (ws.get("stocks") or {}) if overlay else {}

    indices = []
    for m in MARKETS:
        card = next((i for i in market.get("indices") or [] if i.get("name") == INDEX_NAME[m]), {}) or {}
        card = _overlay({k: card.get(k) for k in ("name", "close", "change", "rate", "as_of")} | {"name": INDEX_NAME[m], "market": m},
                        live_idx.get(m))
        series = list((extra.get("intraday") or {}).get(m) or []) if extra_today else []
        if series and live_idx.get(m) and card.get("close") is not None:
            t = str(live_idx[m].get("t") or "")[:4]
            if t and t > series[-1]["t"]:
                series.append({"t": t, "c": card["close"]})  # 5분봉 뒤에 지금 값 한 점
        indices.append({**card, "series": series})

    heatmap = {m: [_overlay(s, live_stocks.get(s.get("code"))) for s in (market.get("heatmap") or {}).get(m) or []] for m in MARKETS}
    value_top = [_overlay(s, live_stocks.get(s.get("code"))) for s in ((market.get("movers") or {}).get("value") or [])[:5]]

    wsb = (ws.get("breadth") or {}) if overlay else {}
    whole = (extra.get("whole") or {}) if extra_today else {}
    if all(m in wsb for m in MARKETS):
        b = {k: sum(int(wsb[m].get(k) or 0) for m in MARKETS) for k in ("up", "down", "flat", "upper", "lower")}
    elif all(m in whole for m in MARKETS):
        b = {k: sum(int(whole[m].get(k) or 0) for m in MARKETS) for k in ("up", "down", "flat", "upper", "lower")}
    else:
        mb = market.get("breadth") or {}
        b = {k: mb.get(k) for k in ("up", "down", "flat")} | {"upper": None, "lower": None}
    if b.get("up") is not None:
        b["total"] = sum(int(b.get(k) or 0) for k in ("up", "down", "flat"))

    sectors = None
    if extra_today and extra.get("sectors"):
        sectors = {}
        for m in MARKETS:
            rows = sorted((extra["sectors"].get(m) or []), key=lambda r: r["rate"], reverse=True)
            if rows:
                sectors[m] = {"top": rows[:5], "bottom": list(reversed(rows[-5:]))[:5] if len(rows) > 5 else []}

    label = {"live": "실시간", "delayed": "지연", "closed": "장 마감 · 종가 기준"}[state]
    if source == "public":
        label = f"{'지연 · ' if state == 'delayed' else ''}{_md(market.get('as_of'))} 종가 기준 · 공공데이터"
    show_ai = summary.get("as_of") == day and source == "kiwoom"
    return {
        "state": state, "label": label, "updated_ts": updated, "session": session, "source": source,
        "as_of": market.get("as_of"), "source_name": (market.get("source") or {}).get("name"),
        "ws": {"connected": bool(ws.get("connected")) and ws_today, "reconnects": ws.get("reconnects"), "items": ws.get("items")},
        "indices": indices, "breadth": b, "heatmap": heatmap, "value_top": value_top,
        "investors": (extra.get("investors") or None) if extra_today else None,
        "extra_ts": extra.get("fetched_ts") if extra_today else None,
        "sectors": sectors,
        "ai": {k: summary.get(k) for k in ("text", "ai", "ts", "kind")} if show_ai and summary.get("text") else None,
        "price_note": service.price_note(source),
        "refresh_sec": 15,
    }


def _md(ymd: str | None) -> str:
    return f"{int(ymd[4:6])}/{int(ymd[6:8])}" if ymd and len(ymd) >= 8 else ""


def view() -> dict:
    """방문자용. 2초 안의 같은 요청은 같은 결과(30명이 15초마다 불러도 파일 읽기 몇 번)."""
    with _cache_lock:
        if _cache["value"] is not None and time.time() - _cache["ts"] < CACHE_SEC:
            return _cache["value"]
        value = build_view()
        _cache.update(ts=time.time(), value=value)
        return value


# ---------------------------------------------------------
# AI 장중 한 줄 요약(수집기)
# ---------------------------------------------------------

SUMMARY_SYSTEM = """너는 한국 증시 장중 상황을 한 줄로 전하는 편집자다.
규칙:
- line: 지금 시장을 한 줄(40자 이내)로. 예: '외국인 매수에 반도체 강세, 코스피 +1.2%'. 자료에 있는 사실과 숫자만 쓴다.
- 숫자는 자료의 값을 소수 첫째 자리까지(예: +1.2%). 자료에 없는 숫자·원인·종목은 쓰지 않는다.
- 주가 방향 예측('오를 것' 등), 매수·매도 권유, '추천', '수혜', '기회', '주목', '기대'를 쓰지 않는다. 한국어."""
SUMMARY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["line"], "properties": {"line": {"type": "string"}}}
EXTRA_BANNED = re.compile(r"수혜|추천|주목|기대|유망|매수\s*기회|기회|오를\s*것|내릴\s*것|사야|팔아야|목표가")


def summary_facts(v: dict) -> dict:
    idx = {i["market"]: i.get("rate") for i in v.get("indices") or []}
    sec = v.get("sectors") or {}
    top = [r for m in MARKETS for r in (sec.get(m) or {}).get("top", [])[:2]]
    bottom = [r for m in MARKETS for r in (sec.get(m) or {}).get("bottom", [])[:2]]
    inv = v.get("investors") or {}
    return {
        "코스피 등락률(%)": idx.get("KOSPI"), "코스닥 등락률(%)": idx.get("KOSDAQ"),
        "강한 업종": [f"{r['name']} {r['rate']:+.2f}%" for r in top], "약한 업종": [f"{r['name']} {r['rate']:+.2f}%" for r in bottom],
        "코스피 순매수(억 원)": inv.get("KOSPI"), "코스닥 순매수(억 원)": inv.get("KOSDAQ"),
        "상승 종목 수": (v.get("breadth") or {}).get("up"), "하락 종목 수": (v.get("breadth") or {}).get("down"),
        "거래대금 상위": [s.get("name") for s in v.get("value_top") or []][:3],
        "_top": (sorted(top, key=lambda r: r["rate"], reverse=True)[:1] or [{}])[0].get("name"),
    }


def rule_line(f: dict) -> str:
    parts = [f"{n} {f[k]:+.2f}%" for n, k in (("코스피", "코스피 등락률(%)"), ("코스닥", "코스닥 등락률(%)")) if f.get(k) is not None]
    if f.get("_top"):
        parts.append(f"{f['_top']} 강세")
    return ", ".join(parts)


def _numbers_ok(line: str, f: dict) -> bool:
    """문장의 % 숫자가 자료의 등락률(지수·업종) 중 하나와 맞는지(소수 첫째 자리 반올림 허용)."""
    vals = [f.get("코스피 등락률(%)"), f.get("코스닥 등락률(%)")]
    vals += [float(m) for s in f.get("강한 업종", []) + f.get("약한 업종", []) for m in re.findall(r"[+-]?\d+\.\d+", s)]
    vals = [abs(v) for v in vals if v is not None]
    for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", line):
        if not any(abs(float(m) - v) <= 0.051 for v in vals):
            return False
    return True


def summary_due(prev: dict, f: dict, now: datetime, closing: bool) -> str:
    """'' = 만들지 않음 / 'new' = 새로 / 'keep' = 10분이 지났지만 변화가 작아 이전 것 유지(확인 시각만)."""
    day = _today(now)
    if closing:
        return "" if prev.get("as_of") == day and prev.get("kind") == "close" else "new"
    if prev.get("as_of") != day or prev.get("kind") != "intraday":
        return "new"
    if time.time() - max(prev.get("ts") or 0, prev.get("checked_ts") or 0) < SUMMARY_EVERY_SEC:
        return ""
    old = prev.get("facts") or {}
    small = all(f.get(k) is not None and old.get(k) is not None and abs(f[k] - old[k]) < SUMMARY_SAME_PP
                for k in ("코스피 등락률(%)", "코스닥 등락률(%)"))
    return "keep" if small and f.get("_top") == old.get("_top") else "new"


def _ask_line(f: dict, closing: bool) -> str:
    client = ai._claude_client()
    if client is None:
        raise RuntimeError("AI 키 없음")
    budget.check()
    task = "오늘 장 마감 상황을 한 줄로 요약해라('오늘 마감' 기준)." if closing else "지금 장중 상황을 한 줄로 요약해라."
    payload = {k: v for k, v in f.items() if not k.startswith("_")}
    resp = client.messages.create(model=SUMMARY_MODEL, max_tokens=400, system=SUMMARY_SYSTEM, timeout=30,
                                  messages=[{"role": "user", "content": f"{task}\n\n자료(JSON):\n{json.dumps(payload, ensure_ascii=False)}"}],
                                  output_config={"effort": ai.EFFORT, "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}})
    budget.record(SUMMARY_MODEL, getattr(resp, "usage", None))
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={resp.stop_reason}")
    line = json.loads("".join(b.text for b in resp.content if getattr(b, "type", "") == "text")).get("line", "")
    return re.sub(r"\s+", " ", str(line)).strip()[:60]


def maybe_summarize(now: datetime | None = None) -> str:
    """수집기 루프에서 부른다. 장중 10분마다(변화가 작으면 유지), 마감 뒤 1번. 결과: '' / 'keep' / 'ai' / 'rule'."""
    now = now or datetime.now(KST)
    v = build_view(now)
    if v["source"] != "kiwoom":
        return ""
    closing = v["session"] == "closed" and bool((store.read("market_kiwoom") or {}).get("final"))
    if v["session"] not in ("open", "closing_auction") and not closing:
        return ""
    f = summary_facts(v)
    if f.get("코스피 등락률(%)") is None:
        return ""
    prev = store.read("market_ai") or {}
    due = summary_due(prev, f, now, closing)
    if not due:
        return ""
    if due == "keep":
        store.write("market_ai", {**prev, "checked_ts": time.time()})
        return "keep"
    line, used_ai = "", False
    if ai.available() and budget.allowed():
        try:
            line = _ask_line(f, closing)
            used_ai = bool(line) and not banned_hits(line) and not EXTRA_BANNED.search(line) and _numbers_ok(line, f)
        except Exception as e:
            log.warning("live summary failed: %s", type(e).__name__)
    if not used_ai:
        line = rule_line(f)  # AI가 안 되거나 문장이 규칙에 어긋나면 숫자 문장(화면에 'AI' 표시 없음)
    store.write("market_ai", {"as_of": _today(now), "kind": "close" if closing else "intraday", "text": line, "ai": used_ai,
                              "model": SUMMARY_MODEL if used_ai else None, "ts": time.time(), "checked_ts": time.time(),
                              "facts": {k: f[k] for k in ("코스피 등락률(%)", "코스닥 등락률(%)", "_top")}})
    return "ai" if used_ai else "rule"

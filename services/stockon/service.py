"""STOCK:ON 갱신 · 화면 데이터 조립.

방문자 요청(overview · why)은 저장된 스냅샷만 읽는다. 공공데이터·뉴스·DART·LLM(2단계 키움 포함) 호출은
앱 안의 스케줄러 스레드가 갱신 주기에 맞춰서만 한다(start_scheduler). 그래서 방문자가 몇 명이든,
누가 무엇을 누르든 외부 호출량은 주기로만 정해진다. '왜 움직였나'도 수집 때 미리 만들어 둔다.

켜기: STOCKON_ENABLED=1 (오라클 .env.docker). 없으면 '오라클 서버에서 제공' 안내만 보인다(HF 예비 서버).
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta

from services.stockon import ai, budget, disclosures, events, fx, news, public_data, store
from services.stockon.public_data import KST, PublicDataError
from services.stockon.safety import DISCLAIMER

log = logging.getLogger("stockon")

ORACLE_URL = "https://140-245-88-198.sslip.io/stock"
# '왜 움직였나'를 미리 만드는 대상: 팀 관심 종목(최대 30) + 상승률 상위 5 + 하락률 상위 5 (중복 제외)
WHY_MOVERS_TOP = 5
WHY_MAX_PER_DAY = 40
NEWS_PER_CATEGORY = 6
WATCH_NEWS = 3
SCHEDULER_TICK_SEC = 60

_refresh_lock = threading.Lock()
_scheduler: dict = {"thread": None}


def enabled() -> bool:
    return os.environ.get("STOCKON_ENABLED", "").strip() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(KST)


def _age(snapshot: dict | None) -> float:
    return time.time() - (snapshot or {}).get("fetched_ts", 0)


# ---------------------------------------------------------
# 갱신 주기
# ---------------------------------------------------------

def _market_due(market: dict | None, now: datetime) -> bool:
    if not market:
        return True
    age = _age(market)
    # 평일 13~19시는 전일 자료가 새로 올라오는 시간(T+1, 13시 이후)이라 30분마다 확인한다.
    if now.weekday() < 5 and 13 <= now.hour < 19:
        return age > 30 * 60
    return age > 6 * 3600


def _news_due(snapshot: dict | None, now: datetime) -> bool:
    if not snapshot:
        return True
    return _age(snapshot) > (30 * 60 if 7 <= now.hour < 23 else 3 * 3600)


def due_tasks(now: datetime | None = None) -> list[str]:
    now = now or _now()
    status = store.read("status", {}) or {}
    tasks = []
    if _market_due(store.read("market"), now):
        tasks.append("market")
    if _age(store.read("fx")) > 3 * 3600:
        tasks.append("fx")
    if _news_due(store.read("news"), now):
        tasks.append("news")
    if _news_due(store.read("watch"), now):
        tasks.append("watch")
    brief, market = store.read("briefing"), store.read("market")
    if market and (not brief or brief.get("as_of") != market.get("as_of") or _age(brief) > 3 * 3600):
        tasks.append("briefing")
    why_cache = store.read("why") or {}
    if market and (why_cache.get("as_of") != market.get("as_of") or set(why_targets(market)) - set(why_cache.get("items", {}))) \
            and _age({"fetched_ts": why_cache.get("tried_ts", 0)}) > 3600:
        tasks.append("why")
    if not budget.allowed():  # 하루 AI 비용 상한: AI 작업은 저장된 결과를 그대로 두고 다음 날 다시
        tasks = [t for t in tasks if t not in ("briefing", "why")]
    # 직전 실패 후 10분 안에는 같은 작업을 다시 부르지 않는다(키 미설정·한도 초과 때 반복 호출 방지).
    recent_fail = {t for t, s in status.items() if s.get("error") and time.time() - s.get("error_ts", 0) < 600}
    return [t for t in tasks if t not in recent_fail]


def _mark(task: str, ok: bool, error: str = "") -> None:
    status = store.read("status", {}) or {}
    s = status.get(task, {})
    if ok:
        s.update(ok_ts=time.time(), error="", fails=0)
    else:
        s.update(error=error[:80], error_ts=time.time(), fails=s.get("fails", 0) + 1)
    status[task] = s
    store.write("status", status)


# ---------------------------------------------------------
# 작업
# ---------------------------------------------------------

def _task_market():
    market, directory = public_data.fetch_market()
    market["fetched_ts"] = directory["fetched_ts"] = time.time()
    store.write("stocks", directory)
    store.write("market", market)


def _task_fx():
    data = fx.fetch_usdkrw()
    data["fetched_ts"] = time.time()
    store.write("fx", data)
    if data["status"] == "error":
        raise RuntimeError(f"fx_{data.get('error')}")


def _with_summaries(items: list[dict], old: dict) -> list[dict]:
    """이미 요약한 기사(같은 URL)는 다시 요약하지 않는다."""
    todo = [i for i in items if i["url"] not in old]
    if todo and ai.available():
        for item, summary in zip(todo, ai.summarize_news(todo)):
            if summary:
                old[item["url"]] = summary
    return [{**i, "summary": old.get(i["url"], "")} for i in items]


def _task_news():
    if not news.configured():
        store.write("news", {"status": "not_configured", "fetched_ts": time.time()})
        raise RuntimeError("news_not_configured")
    prev = store.read("news", {}) or {}
    cache = dict(prev.get("summaries") or {})
    cats = []
    for cid, label, query in news.CATEGORIES:
        items = news.search(query, display=NEWS_PER_CATEGORY)
        cats.append({"id": cid, "label": label, "query": query, "items": _with_summaries(items, cache)})
    keep = {i["url"] for c in cats for i in c["items"]}
    store.write("news", {"status": "ok", "categories": cats, "summaries": {u: s for u, s in cache.items() if u in keep},
                         "source": news.SOURCE, "fetched_ts": time.time()})


def _task_watch():
    settings = store.load_settings()
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    rows = []
    for w in settings["watchlist"]:
        item = {"code": w["code"], "name": w["name"], "price": directory.get(w["code"])}
        try:
            # 제목에 종목명이 직접 나오는 기사만(여러 종목을 한꺼번에 다룬 기사가 관심 종목마다 겹치지 않게)
            found = news.search(f'"{w["name"]}"', display=30) if news.configured() else []
            item["news"] = [n for n in found if w["name"] in n["title"]][:WATCH_NEWS]
        except news.NewsError:
            item["news"] = []
        item["disclosures"] = disclosures.recent(w["name"])
        rows.append(item)
    store.write("watch", {"items": rows, "fetched_ts": time.time()})


def _task_briefing():
    market = store.read("market")
    if not market:
        return
    fx_data = store.read("fx")
    window = news_window(market)
    headlines, dart = briefing_inputs(market, window)  # 숫자(기준일 D)와 같은 때의 뉴스·공시만
    brief = ai.briefing(market, fx_data, headlines, dart)
    brief["news_window"] = [window[0].isoformat(), window[1].isoformat()]
    brief.update(as_of=market["as_of"], fetched_ts=time.time())
    store.write("briefing", brief)


CLOSE_HHMM = (15, 30)    # KRX 정규장 마감
NEXT_MORNING_HH = 8      # 마감 정리 기사를 기준일에 넣는 한계(다음 날 08:00, 장 시작 전)


def news_window(market: dict) -> tuple[datetime, datetime]:
    """기준일 D의 뉴스 창 = [직전 거래일 15:30, D 다음 날 08:00) (한국시간).

    - 직전 거래일 마감 뒤 ~ D 장중: D 움직임의 '원인' 후보
    - D 마감 뒤 ~ 다음 날 아침: D를 정리한 '마감 기사'(○○ 3% 상승 마감 등)
    D 마감 뒤 기사는 다음 거래일 창의 시작(D 15:30)에도 들어간다. 장 마감 뒤 나온 공시·뉴스는
    D의 마감 정리이면서 다음 거래일 움직임의 원인일 수 있어서다. 직전 거래일은 지수 시계열의 실제
    거래일로 정한다(주말·휴일 자동 반영).
    """
    as_of = datetime.strptime(market["as_of"], "%Y%m%d").replace(tzinfo=KST)
    days = sorted({p["d"] for i in market.get("indices", []) for p in (i.get("series") or []) if p.get("d")})
    prev_days = [d for d in days if d < market["as_of"]]
    if prev_days:
        prev = datetime.strptime(prev_days[-1], "%Y%m%d").replace(tzinfo=KST)
    else:  # 시계열이 없으면 직전 평일
        prev = as_of - timedelta(days=3 if as_of.weekday() == 0 else 1)
    start = prev.replace(hour=CLOSE_HHMM[0], minute=CLOSE_HHMM[1])
    end = (as_of + timedelta(days=1)).replace(hour=NEXT_MORNING_HH)
    return start, end


def why_targets(market: dict) -> list[str]:
    """'왜 움직였나'를 미리 만들 종목 코드(순서 = 우선순위)."""
    codes = [w["code"] for w in store.load_settings()["watchlist"]]
    for kind in ("up", "down"):
        codes += [s["code"] for s in (market.get("movers") or {}).get(kind, [])[:WHY_MOVERS_TOP]]
    return list(dict.fromkeys(codes))[:WHY_MAX_PER_DAY]


def _in_window_dates(items: list[dict], window: tuple[datetime, datetime]) -> list[dict]:
    """DART 공시는 접수일(YYYYMMDD)만 있다. 창이 걸친 날짜(직전 거래일 ~ 기준일 다음 날)만 남긴다."""
    lo, hi = window[0].strftime("%Y%m%d"), window[1].strftime("%Y%m%d")
    return [d for d in items if lo <= str(d.get("date") or "") <= hi]


def why_inputs(name: str, as_of: str, window: tuple[datetime, datetime]) -> tuple[list[dict], list[dict]]:
    """'왜 움직였나' 입력: 기준일 창 안의 뉴스(최대 8)와 공시."""
    try:
        day = datetime.strptime(as_of, "%Y%m%d")
        found = news.search_window(f'"{name}"', *window, limit=8, must_contain=name,
                                   extra_queries=news.date_queries(name, day)) if news.configured() else []
    except news.NewsError:
        found = []
    return found, _in_window_dates(disclosures.recent(name, days=10), window)


def briefing_inputs(market: dict, window: tuple[datetime, datetime]) -> tuple[list[dict], list[dict]]:
    """브리핑 입력: 기준일 창 안의 시장 뉴스(최대 8)와 팀 관심 종목 공시. 화면의 '카테고리별 뉴스'(최신순)와 따로 찾는다."""
    try:
        day = datetime.strptime(market["as_of"], "%Y%m%d")
        headlines = news.search_window(news.CATEGORIES[0][2], *window, limit=8,
                                       extra_queries=news.date_queries("", day, "market")) if news.configured() else []
    except news.NewsError:
        headlines = []
    dart = []
    for w in (store.read("watch", {}) or {}).get("items") or []:
        dart += [{**d, "company": w["name"]} for d in _in_window_dates(w.get("disclosures") or [], window)]
    return headlines, dart


def _build_why(code: str, stock: dict, as_of: str, window: tuple[datetime, datetime]) -> dict:
    stock = {"code": code, **stock}
    found, dart = why_inputs(stock["name"], as_of, window)
    result = ai.why_moved(stock, as_of, found, dart)
    result.update(code=code, name=stock["name"], as_of=as_of, rate=stock.get("rate"), close=stock.get("close"),
                  news=[{k: n[k] for k in ("title", "url", "press", "pub")} for n in found[:5]], disclosures=dart[:3],
                  created_ts=time.time())
    return result


def _task_why():
    market = store.read("market")
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    if not market:
        return
    as_of = market["as_of"]
    cache = store.read("why", {}) or {}
    if cache.get("as_of") != as_of:
        cache = {"as_of": as_of, "items": {}, "count": 0}
    cache["tried_ts"] = time.time()
    window = news_window(market)
    for code in why_targets(market):
        if code in cache["items"] or code not in directory:
            continue
        cache["items"][code] = _build_why(code, directory[code], as_of, window)
        cache["count"] = len(cache["items"])
        if cache["count"] % 5 == 0:
            store.write("why", cache)  # 중간 저장: 도중에 멈춰도 만든 것은 바로 보인다
    store.write("why", cache)


TASKS = {"market": _task_market, "fx": _task_fx, "news": _task_news, "watch": _task_watch,
         "briefing": _task_briefing, "why": _task_why}
ORDER = ["market", "fx", "news", "watch", "briefing", "why"]


def run_tasks(tasks: list[str]) -> None:
    for name in [t for t in ORDER if t in tasks]:
        try:
            TASKS[name]()
            _mark(name, True)
        except PublicDataError as e:
            _mark(name, False, e.code)
        except news.NewsError as e:
            _mark(name, False, f"news_{e.code}")
        except Exception as e:
            log.warning("stockon task %s failed: %s", name, type(e).__name__)
            _mark(name, False, str(e) if str(e).startswith(("fx_", "news_")) else type(e).__name__)


def refresh_in_background(force: list[str] | None = None) -> bool:
    """갱신이 필요하면 스레드 하나로 돌린다. 이미 돌고 있으면 아무것도 하지 않는다."""
    if not enabled():
        return False
    tasks = force or due_tasks()
    if not tasks or not _refresh_lock.acquire(blocking=False):
        return False

    def work():
        try:
            run_tasks(tasks)
        finally:
            _refresh_lock.release()

    threading.Thread(target=work, name="stockon-refresh", daemon=True).start()
    return True


def refreshing() -> bool:
    return _refresh_lock.locked()


def start_scheduler() -> bool:
    """앱 시작 때 한 번. 1분마다 갱신 주기가 된 작업이 있는지만 보고, 있으면 백그라운드로 돌린다.
    STOCKON_SCHEDULER=0이면 켜지 않는다(로컬 미리보기에서 저장된 스냅샷을 그대로 볼 때)."""
    if not enabled() or os.environ.get("STOCKON_SCHEDULER", "1").strip() == "0":
        return False
    if _scheduler["thread"] and _scheduler["thread"].is_alive():
        return False

    def loop():
        while True:
            try:
                refresh_in_background()
            except Exception as e:  # 스케줄러는 죽지 않는다
                log.warning("stockon scheduler: %s", type(e).__name__)
            time.sleep(SCHEDULER_TICK_SEC)

    _scheduler["thread"] = threading.Thread(target=loop, name="stockon-scheduler", daemon=True)
    _scheduler["thread"].start()
    return True


# ---------------------------------------------------------
# 화면 데이터
# ---------------------------------------------------------

def _public(snapshot: dict | None) -> dict | None:
    if not snapshot:
        return None
    return {k: v for k, v in snapshot.items() if k not in ("summaries",)}


KIWOOM_STALE_SEC = 10 * 60  # 장중 키움 스냅샷이 이보다 오래되면 공공데이터로 자동 복귀
KIWOOM_ALERT_FAILS = 3  # 연속 실패가 이만큼이면 관리자 화면 상태 카드에 경고


def active_market() -> tuple[dict | None, str]:
    """화면에 쓸 시세 스냅샷과 그 출처('kiwoom' | 'public').

    키움은 수집기 상태의 price_source가 kiwoom이고, 오늘 날짜이며, 장중이면 10분 안에 갱신된 것만 쓴다.
    장 마감 뒤 '마감 기준' 스냅샷은 그날 하루 쓴다. 어느 하나라도 아니면 공공데이터(전일 기준)."""
    public = store.read("market")
    kiwoom = store.read("market_kiwoom")
    status = store.read("kiwoom_status", {}) or {}
    if status.get("price_source") == "kiwoom" and kiwoom and kiwoom.get("as_of") == _now().strftime("%Y%m%d"):
        if kiwoom.get("session") == "closed" or _age(kiwoom) <= KIWOOM_STALE_SEC:
            return kiwoom, "kiwoom"
    return public, "public"


def price_note(source: str) -> str:
    """화면 하단 시세 출처 한 줄. 지금 화면에 쓰는 출처 기준(키움이 실패해 공공데이터로 대체되면 공공데이터 문구)."""
    if source == "kiwoom":
        real = (store.read("kiwoom_status", {}) or {}).get("mode") == "real"
        return f"시세: 키움증권 {'' if real else '모의투자 '}API · 지연될 수 있으며 참고용입니다"
    return "시세: 금융위원회 공공데이터(거래일 종가, 다음 날 13시 이후 반영) · 참고용입니다"


def _with_quotes(watch: dict | None, market: dict | None, price_source: str) -> dict | None:
    """키움 시세를 쓰는 동안 팀 관심 종목 가격도 같은 시점(키움 스냅샷의 히트맵·관심 종목 시세)으로."""
    if not watch or price_source != "kiwoom" or not market:
        return watch
    quotes = {s["code"]: s for lst in (market.get("heatmap") or {}).values() for s in lst}
    quotes.update(market.get("quotes") or {})
    items = []
    for it in watch.get("items") or []:
        q = quotes.get(it.get("code"))
        items.append({**it, "price": {**(it.get("price") or {}), **{k: q[k] for k in ("close", "change", "rate", "value") if k in q}}}
                     if q else it)
    return {**watch, "items": items}


def overview() -> dict:
    base = {"enabled": enabled(), "disclaimer": DISCLAIMER, "oracle_url": ORACLE_URL}
    if not enabled():
        return base
    # 읽기만 한다. 갱신은 스케줄러(공공·뉴스·AI)와 키움 수집기(별도 컨테이너)가 한다.
    status = store.read("status", {}) or {}
    market, price_source = active_market()
    public = store.read("market") or {}
    return {
        **base,
        "refreshing": refreshing(),
        "market": market,
        "price_source": price_source,
        "public_as_of": public.get("as_of"),  # 브리핑·왜 움직였나의 기준일(전일)
        "fx": store.read("fx"),
        "briefing": store.read("briefing"),
        "news": _public(store.read("news")),
        "watch": _with_quotes(store.read("watch"), market, price_source),
        "price_note": price_note(price_source),
        "events": events.week_events(_now().date()),
        "errors": {t: s.get("error") for t, s in status.items() if s.get("error")},
    }


# ---------------------------------------------------------
# 왜 움직였나 (수집 때 미리 만든 것만 읽는다)
# ---------------------------------------------------------

def why(code: str) -> dict:
    """저장된 설명을 돌려준다. 없으면 ready=False(새로 만들지 않음 — 방문자 요청은 외부 호출을 하지 않는다)."""
    market = store.read("market")
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    stock = directory.get(code)
    if not market or not stock:
        raise KeyError(code)
    cache = store.read("why", {}) or {}
    if cache.get("as_of") == market["as_of"] and code in cache.get("items", {}):
        return {"ready": True, **cache["items"][code]}
    return {"ready": False, "code": code, "name": stock["name"], "as_of": market["as_of"],
            "rate": stock.get("rate"), "close": stock.get("close"), "sentences": [], "sources": [], "ai": False,
            "news": [], "disclosures": [],
            "note": "이 종목은 미리 정리된 설명이 없어요. 팀 관심 종목과 상승·하락 상위 5개만 매일 정리해요."}


# ---------------------------------------------------------
# 관리자
# ---------------------------------------------------------

def search_stocks(q: str, limit: int = 20) -> list[dict]:
    q = q.strip().lower()
    if not q:
        return []
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    hits = [{"code": c, **{k: s[k] for k in ("name", "market", "cap")}} for c, s in directory.items()
            if q in s["name"].lower() or c.startswith(q)]
    return sorted(hits, key=lambda s: (s["name"].lower() != q, -(s["cap"] or 0)))[:limit]


def save_watchlist(codes: list[str]) -> dict:
    directory = (store.read("stocks", {}) or {}).get("stocks", {})
    unknown = [c for c in codes if c not in directory]
    if unknown:
        raise ValueError(f"종목 목록에 없는 코드: {', '.join(unknown[:5])}")
    if len(codes) > store.WATCHLIST_MAX:
        raise ValueError(f"팀 관심 종목은 {store.WATCHLIST_MAX}개까지예요.")
    settings = store.save_watchlist([{"code": c, "name": directory[c]["name"]} for c in codes])
    refresh_in_background(["watch", "why"])  # 관리자 저장 때만: 새 관심 종목의 뉴스·공시와 설명을 만든다
    return settings


def kiwoom_status() -> dict:
    """2단계 키움 수집기가 쓰는 상태 파일(날짜·실패 횟수만, 키 없음). 없으면 '미연결'."""
    data = store.read("kiwoom_status")
    if not data:
        return {"connected": False}
    expires = data.get("mock_key_expires")
    days_left = None
    if expires:
        try:
            days_left = (datetime.strptime(expires, "%Y-%m-%d").date() - _now().date()).days
        except ValueError:
            pass
    _, showing = active_market()
    return {"connected": True, "mode": data.get("mode"), "price_source": data.get("price_source"), "showing": showing,
            "mock_key_expires": expires, "days_left": days_left, "last_ok": data.get("last_ok"), "fails": data.get("fails", 0),
            "last_error": data.get("last_error"), "session": data.get("session"), "updated": data.get("updated"),
            "last_fail": data.get("last_fail"), "tokens_issued": data.get("tokens_issued"),
            "alert": (data.get("fails") or 0) >= KIWOOM_ALERT_FAILS}


def _ai_status() -> dict:
    """작업별 AI 결과. 날짜가 바뀌었으면 '오늘' 횟수는 0으로 보인다."""
    raw = store.read("ai_status", {}) or {}
    today = _now().strftime("%Y-%m-%d")
    out = {}
    for kind in ai.KINDS:
        s = raw.get(kind, {})
        same_day = s.get("day") == today
        out[kind] = {
            "ok_ts": s.get("ok_ts"), "error_ts": s.get("error_ts"), "last_error": s.get("last_error"),
            "consecutive": s.get("consecutive", 0),
            "fails_today": s.get("fails_today", 0) if same_day else 0,
            "fallbacks_today": s.get("fallbacks_today", 0) if same_day else 0,
            "fails_total": s.get("fails_total", 0), "fallbacks_total": s.get("fallbacks_total", 0),
        }
    return out


def admin_status() -> dict:
    from services.config import get_secret

    status = store.read("status", {}) or {}
    why_cache = store.read("why", {}) or {}
    return {
        "enabled": enabled(),
        "refreshing": refreshing(),
        "configured": {
            "public_data": bool(get_secret("PUBLIC_DATA_API_KEY")),
            "naver_search": news.configured(),
            "dart": bool(get_secret("DART_API_KEY")),
            "exim_fx": bool(get_secret("KOREAEXIM_API_KEY")),
            "ai": ai.available(),
        },
        "tasks": {t: {k: status.get(t, {}).get(k) for k in ("ok_ts", "error", "error_ts", "fails")} for t in ORDER},
        "ai": _ai_status(),
        "models": {"briefing": ai.BRIEFING_MODEL, "why": ai.WHY_MODEL, "news_summary": ai.NEWS_MODEL},
        "as_of": (store.read("market") or {}).get("as_of"),
        "why_today": {"as_of": why_cache.get("as_of"), "count": len(why_cache.get("items", {})), "limit": WHY_MAX_PER_DAY},
        "watchlist": store.load_settings(fresh=True)["watchlist"],
        "kiwoom": kiwoom_status(),
        "lifemap": _lifemap_status(),
        "budget": budget.status(),
    }


def _lifemap_status() -> dict:
    """생활 속 종목 찾기: 오늘 토픽 생성 결과와 하루 AI 사용량(호출 수·토큰)."""
    from services.stockon import lifemap

    cur = store.read("lifemap", {}) or {}
    return {"status": store.read("lifemap_status", {}) or {}, "day": cur.get("day"), "fresh": cur.get("fresh"),
            "topics": [t.get("name") for t in cur.get("topics") or []],
            "usage_daily": store.read("lifemap_usage_daily"), "usage_live": store.read("lifemap_usage_live"),
            "live_today": lifemap._live_today(), "live_limit": lifemap.live_daily_limit(),
            "models": {"topics": lifemap.TOPIC_MODEL, "chain": lifemap.CHAIN_MODEL}}

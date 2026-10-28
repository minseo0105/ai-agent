"""생활 속 종목 찾기: 증시를 움직인 뉴스 → 밸류체인(원료·제조·물류·유통) → 관련 상장사 마인드맵.

- 토픽 = 기준 시점에 증시를 실제로 움직인 뉴스(3~5개, 서로 다른 섹터). 수집기(stockon-collector)가
  ① 기준일 급등락·거래대금 상위 종목을 먼저 보고 ② 그 기준일 뉴스 창 안의 '특징주·관련주·시황'과 해외 이슈
  (미국 증시·엔비디아·금리·환율·유가·관세) 기사, 많이 움직인 종목 이름 기사를 모아 ③ Haiku 5.5가 '움직임 ↔ 원인 기사'를
  짝지어 토픽을 만들고 ④ 토픽마다 Sonnet 5.5가 밸류체인을 그린다. 결과는 저장해서 모두가 같이 본다.
- 기준(basis): 공공데이터는 D일 시세가 D+1 13시 이후에 올라오므로 새 기준일 시세가 들어왔을 때 만들고, 뉴스도 그 기준일 창
  [직전 거래일 15:30, D+1 08:00)만 쓴다(화면 'n/n 장 기준'). 키움 모드로 오늘 시세가 들어오는 날은 10시 이후·마감 뒤
  한 번씩 오늘 등락률 상위(ka10027)·거래대금 상위(ka10032) 스냅샷으로 다시 만든다('n/n 장중 HH:MM 기준').
- 섹터 칩(금융·반도체·AI·…): 같은 기준으로 섹터별 이슈 기사를 찾아 미리 그려 둔다.
- 새 단어: AI LAB 앱(ailab)에서 같은 엔진으로 그린다. 동시 호출 상한·대기열·1인 횟수·하루 상한을 둔다.
  같은 단어는 한 번 그린 것을 모두가 재사용한다.
- AI가 낸 회사는 공공데이터 전 종목 목록(stocks.json)의 종목명과 맞춰 보고, 없는 회사는 지운다(종목코드는 목록에서 붙인다).
- 실제로 크게 움직인 회사(토픽 종목이거나 기준 등락률 ±5% 이상)는 moved로 표시한다. 등락률은 기준 시점 값을 저장한다.
- AI가 실패하면 저장된 예시(data/stockon/lifemap_examples.json)로 대체한다. 화면이 비지 않게.
- 문장에는 권유·평가·전망과 '추천·수혜' 같은 표현을 쓰지 않는다(safety.banned_hits + 이 파일의 EXTRA_BANNED).
"""

import json
import logging
import re
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from services.stockon import ai, news, store
from services.stockon.public_data import KST
from services.stockon.safety import banned_hits
from services.stockon.service import news_window

log = logging.getLogger("stockon.lifemap")

TOPIC_MODEL = "claude-haiku-5-5"
CHAIN_MODEL = "claude-sonnet-5-5"
SECTORS = ["금융", "반도체", "AI", "자동차", "보험", "보안", "2차전지", "바이오", "방산", "조선"]
EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "data" / "stockon" / "lifemap_examples.json"

# 단계 순서 = 화면 가지 순서. 색은 화면에서 정한다(원료 청록·제조 보라·물류 노랑·유통 연두).
STAGES = {"material": "원료", "making": "제조", "logistics": "물류", "retail": "유통"}
PER_STAGE = 2
RELEVANCE = ("강", "중", "약")
MIN_COMPANIES = 3          # 검증 뒤 회사가 이보다 적으면 한 번 다시 그린다
TOPICS_MIN, TOPICS_MAX = 3, 5
MOVED_PCT = 5.0            # 기준 등락률이 이 이상(절댓값)이면 '실제로 크게 움직인 회사'
TOPIC_TRIES = 3            # 같은 기준으로 최대 시도(실패 시 30분 간격)
KIWOOM_TOPIC_FROM = (10, 0)  # 키움 오늘 시세로 토픽을 만드는 가장 이른 시각(장 시작 1시간 뒤)
KIWOOM_FRESH_SEC = 15 * 60
MOVERS_FOR_AI = 10         # 상승·하락·거래대금 상위 각각 몇 개를 AI에 보여 줄지
MOVER_NEWS_N = 8           # 등락률 절댓값 상위 몇 종목의 이름으로 기사를 더 찾을지
# 증시를 움직인 뉴스 검색어(기준 뉴스 창 안 기사만 쓴다). 날짜 표현 검색어를 더해 하루 지난 기준일도 찾게 한다.
MARKET_QUERIES = ["특징주", "관련주 급등", "관련주 급락", "증시 마감 시황", "뉴욕증시", "엔비디아 주가",
                  "금리 환율 증시", "국제유가 증시", "관세 증시"]
DATED_QUERIES = {"특징주", "증시 마감 시황", "뉴욕증시"}

# 새 단어 실시간 생성 안전장치(30명 동시 접속 기준)
LIVE_CONCURRENCY = 3       # 동시에 AI를 부르는 수
LIVE_QUEUE_MAX = 12        # 대기열(그리는 중 포함). 넘치면 '지금 많이 그리고 있어요' + 예시
LIVE_PER_SESSION = 3       # 한 사람(브라우저)당 새 단어 10분에 3개
LIVE_SESSION_WINDOW = 600
LIVE_DAILY_MAX = 150       # 하루 새 단어 생성 상한(서버 전체). 넘으면 저장된 것·예시만
LIVE_TIMEOUT = 45          # AI 한 번 호출 최대 초
WORDS_KEEP = 300           # 저장해 두는 새 단어 수(오래된 것부터 지움)
RESULT_KEEP_SEC = 120      # 실패 결과를 폴링에 알려 주는 시간

# '급등·급락'은 이미 일어난 움직임을 쓰는 말이라 허용한다(방향 예측은 safety.banned_hits가 막는다).
EXTRA_BANNED = [re.compile(p) for p in (r"수혜", r"추천", r"주목", r"기대", r"유망", r"관심\s*종목", r"테마주")]
# 이유가 추측·약한 연결이면 그 회사를 넣지 않는다(예: '연계 가능', '직접 관련 낮음')
WEAK_REASON = re.compile(r"불확실|여부|가능성?|낮[음다은]|없[음다]|추정|예상|것으로\s*보")
WORD_RE = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣 ]{0,11}$")
BLOCKED_WORDS = re.compile(r"(시발|씨발|개새|병신|좆|섹스|자살|살인|마약|도박|급등주|작전주|리딩방|추천주|수혜주)")


def _read(name: str, default=None):
    """store.read + 잠깐의 파일 잠금(Windows에서 교체 중인 파일) 재시도. 서버(Linux)의 교체는 원자적이다."""
    for attempt in range(3):
        try:
            value = store.read(name, default)
            return value if value is not None else default
        except OSError:
            time.sleep(0.02 * (attempt + 1))
    return default


def _unsafe(text: str) -> bool:
    return bool(banned_hits(text)) or any(p.search(text or "") for p in EXTRA_BANNED)


def normalize_word(word: str) -> str:
    return re.sub(r"\s+", " ", (word or "").strip())


def check_word(word: str) -> str:
    """새 단어 입력 검사. 문제 없으면 빈 문자열, 있으면 화면에 보일 이유."""
    if not word:
        return "단어를 입력해 주세요."
    if not WORD_RE.match(word):
        return "한글·영문·숫자로 12자까지 입력해 주세요."
    if BLOCKED_WORDS.search(word.replace(" ", "")):
        return "다른 단어로 입력해 주세요."
    return ""


# ---------------------------------------------------------
# 종목 목록(공공데이터) 대조
# ---------------------------------------------------------

_dir_cache: dict = {"mtime": None, "directory": {}, "index": {}, "as_of": None}
_dir_lock = threading.Lock()


def _norm_name(name: str) -> str:
    name = re.sub(r"\(주\)|㈜|주식회사", "", name or "")
    return re.sub(r"[\s·.,\-]", "", name).lower()


def directory() -> tuple[dict, dict, str | None]:
    """(코드→종목, 정규화한 이름→코드, 기준일). stocks.json이 바뀔 때만 다시 읽는다(약 350KB, 방문자마다 읽지 않게)."""
    path = store.DATA_DIR / "stocks.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}, {}, None
    with _dir_lock:
        if _dir_cache["mtime"] != mtime:
            raw = _read("stocks", {})
            stocks = raw.get("stocks") or {}
            index: dict[str, str] = {}
            for code, s in stocks.items():
                key = _norm_name(s.get("name", ""))
                # 같은 이름이 둘이면 시가총액 큰 쪽(보통주)
                if key and (key not in index or (s.get("cap") or 0) > (stocks[index[key]].get("cap") or 0)):
                    index[key] = code
            _dir_cache.update(mtime=mtime, directory=stocks, index=index, as_of=raw.get("as_of"))
        return _dir_cache["directory"], _dir_cache["index"], _dir_cache["as_of"]


def match_company(name: str, index: dict) -> str | None:
    return index.get(_norm_name(name))


def validate_chain(raw: dict, index: dict, stocks: dict) -> tuple[list[dict], list[str]]:
    """AI가 낸 밸류체인 → (화면용 단계 목록, 지운 회사 이름). 단계는 정해진 순서, 단계당 2곳, 회사는 한 번만."""
    by_key: dict[str, dict] = {}
    removed: list[str] = []
    used: set[str] = set()
    for st in (raw or {}).get("stages") or []:
        key = st.get("key")
        if key not in STAGES or key in by_key:
            continue
        detail = str(st.get("detail") or "").strip()[:14]
        companies = []
        for c in st.get("companies") or []:
            name = str(c.get("name") or "").strip()
            reason = str(c.get("reason") or "").strip()
            code = match_company(name, index)
            if not code:
                if name:
                    removed.append(name)
                continue
            if code in used or not reason or _unsafe(reason) or WEAK_REASON.search(reason):
                continue
            used.add(code)
            rel = c.get("relevance") if c.get("relevance") in RELEVANCE else "약"
            companies.append({"code": code, "name": stocks[code]["name"], "relevance": rel, "reason": reason[:60]})
            if len(companies) == PER_STAGE:
                break
        if companies:
            by_key[key] = {"key": key, "label": STAGES[key], "detail": "" if _unsafe(detail) else detail, "companies": companies}
    return [by_key[k] for k in STAGES if k in by_key], removed


# ---------------------------------------------------------
# AI 호출
# ---------------------------------------------------------

CHAIN_SYSTEM = """너는 단어(증시 이슈·업종·생활 단어)를 한국 상장사의 밸류체인으로 이어 주는 경제 교육용 편집자다.
규칙:
- 한국거래소(코스피·코스닥)에 지금 상장된 회사만, 상장 종목명 그대로 쓴다. 비상장사·해외 회사·상장사의 비상장 자회사는 쓰지 않는다.
- 단계: 원료(material)=소재·부품·원천 기술, 제조(making)=제품·서비스를 만드는 회사, 물류(logistics)=운송·인프라·망,
  유통(retail)=판매·플랫폼·고객 접점. 이 단어에 실제로 해당하는 단계만 고른다. 억지로 채우지 않는다.
- 단계마다 이 단어와 가장 직접 이어지는 회사를 3곳까지, 연관이 큰 순서로 쓴다. 확실하지 않은 회사는 쓰지 않는다.
- 자료의 '실제로 움직인 종목'은 이 단어와 이어지면 맞는 단계의 앞쪽에 넣는다. '많이 움직인 종목'은 이 단어와 확실히 이어지는 것만 넣는다.
- 그 단계에서 이 단어와 확실히 이어지는 상장사가 없으면 그 단계를 통째로 뺀다. 연결이 약하거나 추측('~할 수 있다', '관련 낮음')인 회사는 넣지 않는다.
- relevance: 강 = 이 단어가 그 회사의 핵심 사업, 중 = 주요 사업 중 하나, 약 = 간접적으로 이어짐.
- reason: 그 회사가 이 단어와 어떻게 이어지는지 사업 사실만 한 줄(30자 이내).
- detail: 그 단계에서 이 단어와 관련된 것(예: '보안 솔루션·인증'), 12자 이내.
- 주가·실적·전망, 투자 판단, 좋고 나쁨 평가를 쓰지 않는다. '추천', '수혜', '유망', '기대', '주목' 같은 말을 쓰지 않는다.
- 한국어."""

CHAIN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["stages"],
    "properties": {"stages": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["key", "detail", "companies"],
        "properties": {
            "key": {"type": "string", "enum": list(STAGES)},
            "detail": {"type": "string"},
            "companies": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["name", "relevance", "reason"],
                "properties": {"name": {"type": "string"}, "relevance": {"type": "string", "enum": list(RELEVANCE)},
                               "reason": {"type": "string"}}}},
        }}}},
}

TOPIC_SYSTEM = """너는 증시 뉴스 편집자다. 기준 시점에 한국 증시에서 실제로 크게 움직인 종목·업종과 그 원인 기사를 짝지어
'증시를 움직인 뉴스' 토픽을 만든다.
규칙:
- 먼저 '많이 움직인 종목'에서 같은 이유로 함께 움직인 종목·업종을 찾고, 기사에서 그 원인을 확인한다. 기사로 원인이 확인되지 않는 움직임은 토픽으로 만들지 않는다.
- 해외 이슈(미국 증시, 엔비디아, 금리, 환율, 유가, 관세 등)도 국내 종목·업종의 실제 움직임과 기사로 이어지면 토픽이 된다.
- 토픽은 서로 다른 섹터(업종)에서 고른다. 같은 기사를 두 토픽의 근거로 쓰지 않는다. 영향이 큰 순서로 5개까지.
- title: 무슨 일이 있었나 한 줄(25자 이내, 예: '보안 사고 터지자 보안주 급등').
- impact: 증시 영향 한 줄(40자 이내, 예: '라온시큐어 등 보안 관련 종목이 크게 올랐다'). 이미 일어난 일만.
- keyword: 마인드맵 가운데 둘 핵심 단어 2~8자(예: '보안', '원전', '반도체 장비'). sector: 업종 이름 2~8자.
- stocks: 이 원인으로 실제로 움직인 종목을 '많이 움직인 종목'의 이름 그대로 1~3개.
- articles: 원인을 보여 주는 기사 번호 정확히 2개(주어진 번호만).
- 앞으로의 주가 방향 예측, 매수·매도 권유, '추천', '수혜', '유망', '기대', '주목' 같은 말을 쓰지 않는다. 한국어."""

TOPIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "impact", "keyword", "sector", "stocks", "articles"],
        "properties": {"title": {"type": "string"}, "impact": {"type": "string"}, "keyword": {"type": "string"},
                       "sector": {"type": "string"}, "stocks": {"type": "array", "items": {"type": "string"}},
                       "articles": {"type": "array", "items": {"type": "integer"}}}}}},
}


_usage_lock = threading.Lock()


def _record_usage(model: str, usage, live: bool) -> None:
    """하루 호출 수·토큰을 남긴다(비용 확인용). 프로세스가 둘(ailab·수집기)이라 파일을 따로 쓴다."""
    try:
        with _usage_lock:
            name = "lifemap_usage_live" if live else "lifemap_usage_daily"
            today = datetime.now(KST).strftime("%Y-%m-%d")
            data = _read(name, {})
            if data.get("day") != today:
                data = {"day": today, "models": {}}
            m = data["models"].setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
            m["calls"] += 1
            m["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
            m["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
            store.write(name, data)
    except Exception as e:
        log.warning("lifemap usage write failed: %s", type(e).__name__)


def _ask(model: str, system: str, task: str, payload, schema: dict, max_tokens: int, live: bool = False) -> dict | None:
    client = ai._claude_client()
    if client is None:
        raise RuntimeError("AI 키 없음")
    args = dict(model=model, max_tokens=max_tokens, system=system, timeout=LIVE_TIMEOUT,
                messages=[{"role": "user", "content": f"{task}\n\n자료(JSON):\n{json.dumps(payload, ensure_ascii=False)}"}],
                output_config={"effort": ai.EFFORT, "format": {"type": "json_schema", "schema": schema}})
    if model in ai.FALLBACK_MODELS:
        args.update(extra_headers={"anthropic-beta": ai.FALLBACK_BETA}, extra_body={"fallbacks": "default"})
    resp = client.messages.create(**args)
    _record_usage(model, getattr(resp, "usage", None), live)
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={resp.stop_reason}")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def build_chain(word: str, context: str = "", live: bool = False, movers: list[str] | None = None,
                must: list[str] | None = None) -> dict:
    """단어 하나의 마인드맵. 실패하면 예외(호출하는 쪽이 예시로 대체).
    context = 관련 뉴스, movers = 기준 시점에 많이 움직인 종목 이름, must = 이 토픽으로 실제로 움직인 종목 이름."""
    stocks, index, as_of = directory()
    if not stocks:
        raise RuntimeError("종목 목록 없음")
    task = f"'{word}'를 밸류체인 단계와 한국 상장사로 이어라."
    payload: dict = {"단어": word}
    if context:
        payload["관련 뉴스"] = context
    if must:
        payload["실제로 움직인 종목"] = must
    if movers:
        payload["많이 움직인 종목"] = movers
    removed_all: list[str] = []
    stages: list[dict] = []
    count = lambda st: sum(len(s["companies"]) for s in st)  # noqa: E731
    for attempt in range(2):
        raw = _ask(CHAIN_MODEL, CHAIN_SYSTEM, task, payload, CHAIN_SCHEMA, 1500, live)
        got, removed = validate_chain(raw, index, stocks)
        removed_all += removed
        if count(got) >= count(stages):
            stages = got  # 다시 그린 것이 더 적으면 처음 것을 둔다
        if (count(stages) >= MIN_COMPANIES and len(stages) >= 2) or attempt == 1:
            break
        if removed:
            task += (f"\n\n주의: 직전 결과의 {', '.join(removed[:6])}은(는) 상장 종목 목록에 없었다. "
                     "상장된 회사만 상장 종목명 그대로 다시 써라.")
        elif len(stages) == 1:
            task += ("\n\n주의: 직전 결과는 한 단계뿐이었다. 원료(소재·부품·기술)·물류(망·인프라)·유통(판매·플랫폼) 단계에서도 "
                     "이 단어와 확실히 이어지는 상장사가 있으면 더해라(없으면 그 단계는 빼라).")
        else:
            break  # 지운 회사 없이 적게 나왔으면 다시 불러도 비슷하다(빈 결과 = 이어지는 회사 없음)
    return {"word": word, "stages": stages, "removed": list(dict.fromkeys(removed_all))[:10], "ai": True,
            "model": CHAIN_MODEL, "directory_as_of": as_of, "created_ts": time.time()}


# ---------------------------------------------------------
# 기준(basis): 어느 시점의 움직임으로 토픽을 만드나
# ---------------------------------------------------------

def _md(ymd: str) -> str:
    return f"{int(ymd[4:6])}/{int(ymd[6:8])}"


def _mover_rows(market: dict) -> list[dict]:
    """상승·하락·거래대금 상위(중복 제외). 각 {code, name, rate, value}."""
    rows, seen = [], set()
    for kind in ("up", "down", "value"):
        for s in ((market.get("movers") or {}).get(kind) or [])[:MOVERS_FOR_AI]:
            if s.get("code") and s["code"] not in seen and s.get("rate") is not None:
                seen.add(s["code"])
                rows.append({k: s.get(k) for k in ("code", "name", "rate", "value")})
    return rows


def topic_basis(now: datetime | None = None) -> dict | None:
    """토픽을 만들 기준. 키움 오늘 시세(키움 모드·10시 이후·15분 안 갱신 또는 마감)가 있으면 그것, 아니면 공공데이터 최신 기준일.
    {key, source, as_of, label, window, movers, rates}. 시세가 하나도 없으면 None."""
    now = now or datetime.now(KST)
    public = _read("market", {})
    status = _read("kiwoom_status", {})
    kw = _read("market_kiwoom", {})
    today = now.strftime("%Y%m%d")
    session = kw.get("session")
    fresh = session == "closed" or (session in ("open", "closing_auction") and time.time() - kw.get("fetched_ts", 0) <= KIWOOM_FRESH_SEC)
    if status.get("price_source") == "kiwoom" and kw.get("as_of") == today and (now.hour, now.minute) >= KIWOOM_TOPIC_FROM and fresh:
        closed = session == "closed"
        start_day = public.get("as_of") or (now - timedelta(days=1)).strftime("%Y%m%d")
        start = datetime.strptime(start_day, "%Y%m%d").replace(tzinfo=KST, hour=15, minute=30)
        stamp = datetime.fromtimestamp(kw.get("fetched_ts") or time.time(), KST).strftime("%H:%M")
        rates = {s["code"]: s.get("rate") for lst in (kw.get("heatmap") or {}).values() for s in lst if s.get("code")}
        movers = _mover_rows(kw)
        rates.update({m["code"]: m["rate"] for m in movers})
        label = f"{_md(today)} 장 마감 기준" if closed else f"{_md(today)} 장중 {stamp} 기준"
        return {"key": f"kiwoom:{today}:{'close' if closed else 'open'}", "source": "kiwoom", "as_of": today,
                "label": label, "window": (start, now), "movers": movers, "rates": rates}
    if not public.get("as_of"):
        return None
    stocks, _, dir_as_of = directory()
    rates = {c: s.get("rate") for c, s in stocks.items()} if dir_as_of == public["as_of"] else {}
    movers = _mover_rows(public)
    rates.update({m["code"]: m["rate"] for m in movers})
    return {"key": f"public:{public['as_of']}", "source": "public", "as_of": public["as_of"],
            "label": f"{_md(public['as_of'])} 장 기준", "window": news_window(public), "movers": movers, "rates": rates}


def basis_info(basis: dict) -> dict:
    """화면·저장용(종목 표·뉴스 창 제외)."""
    return {k: basis[k] for k in ("key", "source", "as_of", "label")}


# ---------------------------------------------------------
# 토픽: 움직인 종목 → 원인 뉴스
# ---------------------------------------------------------

def collect_market_news(basis: dict, http=None) -> list[dict]:
    """기준 뉴스 창 안의 증시 기사: 특징주·관련주·시황·해외 이슈 검색어 + 많이 움직인 종목 이름 기사(제목 중복 제거)."""
    start, end = basis["window"]
    day = datetime.strptime(basis["as_of"], "%Y%m%d")
    kw = {"http": http} if http else {}
    out, seen = [], set()

    def add(items, category):
        for n in items:
            if n["title"] not in seen:
                seen.add(n["title"])
                out.append({**n, "category": category})

    for q in MARKET_QUERIES:
        try:
            extra = [f"{q} {day.month}월 {day.day}일"] if q in DATED_QUERIES else None
            add(news.search_window(q, start, end, limit=10, max_pages=2, extra_queries=extra, **kw), "시장")
        except news.NewsError as e:
            log.warning("lifemap news %s: %s", q, e.code)
    for m in sorted(basis["movers"], key=lambda r: -abs(r["rate"] or 0))[:MOVER_NEWS_N]:
        try:
            add(news.search_window(f'"{m["name"]}"', start, end, limit=3, max_pages=1, must_contain=m["name"], **kw), "종목")
        except news.NewsError:
            pass
    return out


def pick_topics(basis: dict, articles: list[dict]) -> list[dict]:
    """Haiku가 '움직임 ↔ 원인 기사'를 짝지은 토픽(최대 5). 종목·기사 번호·섹터 중복·표현을 검사해 통과한 것만."""
    stocks, index, _ = directory()
    payload = {
        "기준": basis["label"],
        "많이 움직인 종목": [{"이름": m["name"], "등락률": m["rate"], "거래대금_억": round((m.get("value") or 0) / 1e8)}
                       for m in basis["movers"]],
        "기사": [{"번호": i + 1, "제목": a["title"], "요약문": (a.get("snippet") or "")[:80], "발행": a.get("pub")}
               for i, a in enumerate(articles)],
    }
    raw = _ask(TOPIC_MODEL, TOPIC_SYSTEM, f"{basis['label']}으로 증시를 움직인 뉴스 토픽을 영향이 큰 순서로 5개까지 만들어라.",
               payload, TOPIC_SCHEMA, 3000)
    rates = basis["rates"]
    topics, keywords, sectors, used_articles = [], set(), set(), set()
    for t in (raw or {}).get("topics") or []:
        keyword = normalize_word(str(t.get("keyword") or ""))[:12]
        sector = normalize_word(str(t.get("sector") or ""))[:12]
        title = str(t.get("title") or "").strip()[:40]
        impact = str(t.get("impact") or "").strip()[:80]
        nums = [n for n in dict.fromkeys(t.get("articles") or []) if isinstance(n, int) and 1 <= n <= len(articles)][:2]
        moved: list[dict] = []
        for name in t.get("stocks") or []:
            code = match_company(str(name), index)
            if code and rates.get(code) is not None and code not in [m["code"] for m in moved]:
                moved.append({"code": code, "name": stocks[code]["name"], "rate": rates[code]})
        moved.sort(key=lambda m: -abs(m["rate"]))
        if (not keyword or check_word(keyword) or keyword in keywords or not sector or _norm_name(sector) in sectors
                or not title or not impact or any(_unsafe(x) for x in (title, impact, keyword, sector))
                or len(nums) < 2 or used_articles & set(nums) or not moved):
            continue  # 근거 기사 2개·실제로 움직인 종목 1개 이상·다른 섹터·다른 기사여야 토픽
        keywords.add(keyword)
        sectors.add(_norm_name(sector))
        used_articles.update(nums)
        topics.append({"name": keyword, "title": title, "impact": impact, "sector": sector, "stocks": moved[:3],
                       "articles": [{k: articles[n - 1].get(k) for k in ("title", "url", "press", "pub")} for n in nums]})
        if len(topics) == TOPICS_MAX:
            break
    return topics


def mark_moved(m: dict, basis: dict, topic_codes=frozenset()) -> dict:
    """기준 시점 등락률을 회사에 저장하고, 토픽 종목이거나 ±MOVED_PCT 이상이면 moved로 표시한다."""
    rates = basis["rates"]
    for st in m.get("stages") or []:
        for c in st.get("companies") or []:
            r = rates.get(c["code"])
            if r is not None:
                c["rate"] = r
                c["moved"] = c["code"] in topic_codes or abs(r) >= MOVED_PCT
    m["basis_label"] = basis["label"]
    return m


def _mover_names(basis: dict) -> list[str]:
    return [f"{m['name']}({m['rate']:+.1f}%)" for m in basis["movers"]]


# ---------------------------------------------------------
# 예시(대체용)
# ---------------------------------------------------------

_examples_cache: dict = {"value": None}


def examples() -> dict:
    if _examples_cache["value"] is None:
        try:
            _examples_cache["value"] = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _examples_cache["value"] = {"topics": [], "sectors": {}}
    return _examples_cache["value"]


def example_map(word: str = "") -> dict:
    """같은 단어 예시가 있으면 그것, 없으면 첫 섹터 예시."""
    ex = examples()
    sectors = ex.get("sectors") or {}
    topic = next((t["map"] for t in ex.get("topics") or [] if t.get("name") == word and t.get("map")), None)
    chosen = sectors.get(word) or topic or next(iter(sectors.values()), None)
    return {**chosen, "example": True} if chosen else {"word": word, "stages": [], "ai": False, "example": True}


# ---------------------------------------------------------
# 토픽·섹터 생성(수집기) — 새 기준이 생길 때마다
# ---------------------------------------------------------

def _status(**kw) -> None:
    try:
        s = _read("lifemap_status", {})
        s.update(kw)
        store.write("lifemap_status", s)
    except Exception:
        pass


def run_topics(basis: dict, http=None) -> dict:
    """증시를 움직인 뉴스 토픽 3~5개 + 토픽별 마인드맵. 3개가 안 되면 같은 기준의 이전 토픽, 그다음 예시로 채운다."""
    prev = _read("lifemap", {})
    topics: list[dict] = []
    error = ""
    try:
        for t in pick_topics(basis, collect_market_news(basis, http)):
            try:
                m = build_chain(t["name"], context=f"{t['title']} — {t['impact']}",
                                must=[f"{s['name']}({s['rate']:+.1f}%)" for s in t["stocks"]], movers=_mover_names(basis))
            except Exception as e:
                error = f"chain:{type(e).__name__}"
                continue
            if m["stages"]:
                topics.append({**t, "basis_label": basis["label"],
                               "map": mark_moved(m, basis, {s["code"] for s in t["stocks"]})})
    except Exception as e:
        error = f"topics:{type(e).__name__}"
        log.warning("lifemap topics failed: %s", error)
    names = {t["name"] for t in topics}
    same_basis = (prev.get("basis") or {}).get("key") == basis["key"]
    fillers = ((prev.get("topics") or []) if same_basis else []) + [{**t, "example": True} for t in examples().get("topics") or []]
    for t in fillers:
        if len(topics) >= TOPICS_MIN:
            break
        if t["name"] not in names and not t.get("carried"):
            names.add(t["name"])
            topics.append({**t, "carried": True})
    fresh = sum(1 for t in topics if not t.get("carried"))
    data = {"day": datetime.now(KST).strftime("%Y-%m-%d"), "basis": basis_info(basis), "topics": topics[:TOPICS_MAX],
            "fresh": fresh, "topic_model": TOPIC_MODEL, "chain_model": CHAIN_MODEL, "created_ts": time.time()}
    store.write("lifemap", data)
    _status(basis_key=basis["key"], ok=fresh >= TOPICS_MIN, fresh=fresh, error=error, ts=time.time())
    return data


def run_sectors(basis: dict, http=None) -> int:
    """섹터 칩 마인드맵: 같은 기준 뉴스 창의 '{섹터} 관련주' 기사와 많이 움직인 종목으로 그린다. 실패한 섹터는 이전 것을 둔다."""
    saved = _read("lifemap_sectors", {})
    maps = dict(saved.get("maps") or {})
    start, end = basis["window"]
    day = datetime.strptime(basis["as_of"], "%Y%m%d")
    kw = {"http": http} if http else {}
    made = 0
    for sector in SECTORS:
        try:
            found = news.search_window(f"{sector} 관련주", start, end, limit=5, max_pages=1,
                                       extra_queries=[f"{sector} 관련주 {day.month}월 {day.day}일", f"{sector}주 {day.day}일 특징주"],
                                       **kw) if news.configured() else []
        except news.NewsError:
            found = []
        try:
            m = build_chain(sector, context=" / ".join(a["title"] for a in found[:5]), movers=_mover_names(basis))
        except Exception as e:
            log.warning("lifemap sector %s failed: %s", sector, type(e).__name__)
            continue
        if m["stages"]:
            m["articles"] = [{k: a.get(k) for k in ("title", "url", "press", "pub")} for a in found[:3]]
            maps[sector] = mark_moved(m, basis)
            made += 1
    store.write("lifemap_sectors", {"basis": basis_info(basis), "maps": maps, "created_ts": time.time()})
    return made


_daily_lock = threading.Lock()


def topics_due(basis: dict | None) -> bool:
    """새 기준(새 공공 기준일, 키움 장중·마감)이 생겼고 아직 토픽을 못 만들었으면 True. 같은 기준은 30분 간격 최대 3번."""
    if not basis:
        return False
    cur = _read("lifemap", {})
    done = (cur.get("basis") or {}).get("key") == basis["key"]
    if done and cur.get("fresh", 0) >= TOPICS_MIN:
        return False
    s = _read("lifemap_status", {})
    tries = s.get("tries", 0) if s.get("try_key") == basis["key"] else 0
    if done and tries >= 1 and cur.get("fresh", 0) >= 1:
        return False  # 이 기준으로 일부라도 만들었으면 다시 부르지 않는다(비용)
    return tries < TOPIC_TRIES and time.time() - s.get("try_ts", 0) > 1800


def maybe_run_daily(now: datetime | None = None) -> bool:
    """수집기 루프에서 매번 부른다. 할 때가 됐으면 스레드 하나로 돌린다(키움 수집을 막지 않게)."""
    if not ai.available() or not news.configured():
        return False
    basis = topic_basis(now)
    if not topics_due(basis) or not _daily_lock.acquire(blocking=False):
        return False
    s = _read("lifemap_status", {})
    _status(try_key=basis["key"], tries=(s.get("tries", 0) if s.get("try_key") == basis["key"] else 0) + 1, try_ts=time.time())

    def work():
        try:
            run_topics(basis)
            run_sectors(basis)
        except Exception as e:
            log.warning("lifemap daily failed: %s", type(e).__name__)
        finally:
            _daily_lock.release()

    threading.Thread(target=work, name="lifemap-daily", daemon=True).start()
    return True


# ---------------------------------------------------------
# 화면 데이터(읽기 전용)
# ---------------------------------------------------------

def with_prices(m: dict) -> dict:
    """종목 목록에서 시장·종가·시총을 붙인다. 등락률은 저장된 기준 시점 값(토픽·섹터)을 쓰고, 없으면(새 단어) 최신 종가 기준."""
    stocks, _, as_of = directory()
    stages = []
    for st in m.get("stages") or []:
        companies = []
        for c in st.get("companies") or []:
            s = stocks.get(c.get("code"))
            if not s:  # 상장 폐지 등으로 목록에서 빠진 회사는 보이지 않는다
                continue
            rate = c["rate"] if "rate" in c else s.get("rate")
            moved = c["moved"] if "moved" in c else (rate is not None and abs(rate) >= MOVED_PCT)
            companies.append({**c, "name": s["name"], **{k: s.get(k) for k in ("market", "close", "cap", "value")},
                              "rate": rate, "moved": moved})
        if companies:
            stages.append({**st, "companies": companies})
    out = {k: v for k, v in m.items() if k != "removed"}
    label = m.get("basis_label") or (f"{_md(as_of)} 장 기준" if as_of else "")
    return {**out, "stages": stages, "basis_label": label}


def overview() -> dict:
    cur = _read("lifemap", {})
    ex = examples()
    topics = cur.get("topics") or [{**t, "carried": True, "example": True} for t in ex.get("topics") or []]
    saved = _read("lifemap_sectors", {}).get("maps") or {}
    ex_sectors = ex.get("sectors") or {}
    sector_maps = {}
    for sector in SECTORS:
        m = saved.get(sector) or ({**ex_sectors[sector], "example": True} if sector in ex_sectors else None)
        if m:
            sector_maps[sector] = with_prices(m)
    basis = cur.get("basis") or ex.get("basis") or {}
    return {
        "day": cur.get("day"),
        "basis": basis,
        "topics": [{**t, "map": with_prices(t["map"])} for t in topics if t.get("map")],
        "hot": [t["name"] for t in topics if t.get("map")],
        "sectors": SECTORS,
        "sector_maps": sector_maps,
        "live": live_config(),
    }


# ---------------------------------------------------------
# 새 단어 실시간 생성(ailab) — 대기열
# ---------------------------------------------------------

_pool = ThreadPoolExecutor(max_workers=LIVE_CONCURRENCY, thread_name_prefix="lifemap-live")
_jobs: dict[str, dict] = {}      # 단어 → {state: queued|running|failed, seq, done_ts, reason}
_jobs_lock = threading.Lock()
_words_lock = threading.Lock()
_sessions: dict[str, deque] = {}
_seq = {"n": 0}


def live_config() -> dict:
    return {"enabled": ai.available(), "concurrency": LIVE_CONCURRENCY, "queue_max": LIVE_QUEUE_MAX,
            "per_session": LIVE_PER_SESSION, "window_min": LIVE_SESSION_WINDOW // 60}


_live_count: dict = {}  # 오늘 새 단어 생성 수. ailab 프로세스만 쓰므로 메모리가 기준이고 파일은 재시작 대비


def _live_today() -> int:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if _live_count.get("day") != today:
        saved = _read("lifemap_live_count", {})
        _live_count.update(day=today, n=saved.get("n", 0) if saved.get("day") == today else 0)
    return _live_count["n"]


def _bump_live_today() -> None:
    """_jobs_lock 안에서 부른다(같은 프로세스 안에서 읽기·쓰기가 겹치지 않게)."""
    _live_today()
    _live_count["n"] += 1
    try:
        store.write("lifemap_live_count", dict(_live_count))
    except OSError as e:
        log.warning("lifemap live count write failed: %s", type(e).__name__)


def stored_map(word: str) -> dict | None:
    """섹터·토픽 키워드·전에 그린 새 단어·저장소 예시 중 같은 단어(AI를 다시 부르지 않음)."""
    sectors = _read("lifemap_sectors", {}).get("maps") or {}
    if word in sectors:
        return sectors[word]
    for t in _read("lifemap", {}).get("topics") or []:
        if t.get("name") == word and t.get("map"):
            return t["map"]
    m = _read("lifemap_words", {}).get(word)
    if m:
        return m
    ex = examples()
    found = (ex.get("sectors") or {}).get(word) or next((t["map"] for t in ex.get("topics") or [] if t.get("name") == word), None)
    return {**found, "example": True} if found else None


def _save_word(word: str, m: dict) -> None:
    with _words_lock:
        words = _read("lifemap_words", {})
        words[word] = m
        if len(words) > WORDS_KEEP:
            for old in sorted(words, key=lambda w: words[w].get("created_ts", 0))[: len(words) - WORDS_KEEP]:
                words.pop(old, None)
        store.write("lifemap_words", words)


def _run_job(word: str) -> None:
    with _jobs_lock:
        _jobs[word]["state"] = "running"
    try:
        m = build_chain(word, live=True)
        _save_word(word, m)  # 빈 결과(이어지는 회사 없음)도 저장해서 같은 단어로 다시 부르지 않는다
        with _jobs_lock:
            _jobs.pop(word, None)
    except Exception as e:
        log.warning("lifemap live %s failed: %s", word, type(e).__name__)
        with _jobs_lock:
            _jobs[word].update(state="failed", done_ts=time.time(), reason=type(e).__name__)


def _position(word: str) -> int:
    """앞에서 기다리는 단어 수(그리는 중인 것 제외)."""
    job = _jobs.get(word) or {}
    return sum(1 for j in _jobs.values() if j["state"] == "queued" and j["seq"] < job.get("seq", 0))


def _cleanup() -> None:
    now = time.time()
    for w in [w for w, j in _jobs.items() if j["state"] == "failed" and now - j.get("done_ts", now) > RESULT_KEEP_SEC]:
        _jobs.pop(w, None)


def _ready(word: str, m: dict) -> dict:
    return {"status": "ready", "word": word, "map": with_prices(m)}


def _fallback(word: str, status: str, message: str) -> dict:
    return {"status": status, "word": word, "message": message, "map": with_prices(example_map(word))}


def word_status(word: str) -> dict:
    """폴링용. 저장된 결과 → 진행 중 → 실패(예시로 대체) → 없음 순."""
    word = normalize_word(word)
    m = stored_map(word)
    if m:
        return _ready(word, m)
    with _jobs_lock:
        _cleanup()
        job = _jobs.get(word)
        if job and job["state"] in ("queued", "running"):
            return {"status": job["state"], "word": word, "position": _position(word)}
        if job and job["state"] == "failed":
            return _fallback(word, "failed", "AI가 지금 그리지 못해서 준비된 예시를 보여 드려요.")
    return {"status": "none", "word": word}


def request_word(word: str, session: str) -> dict:
    """새 단어 요청. 저장된 것이 있으면 바로, 없으면 대기열에 넣는다(같은 단어는 하나로 묶임)."""
    word = normalize_word(word)
    problem = check_word(word)
    if problem:
        return {"status": "invalid", "word": word, "message": problem}
    m = stored_map(word)
    if m:
        return _ready(word, m)
    with _jobs_lock:
        _cleanup()
        job = _jobs.get(word)
        if job and job["state"] in ("queued", "running"):
            return {"status": job["state"], "word": word, "position": _position(word)}  # 다른 사람이 이미 요청함
        if not ai.available():
            return _fallback(word, "unavailable", "지금은 새 단어를 그릴 수 없어서 준비된 예시를 보여 드려요.")
        if _live_today() >= LIVE_DAILY_MAX:
            return _fallback(word, "daily_limit", "오늘 새 단어 그리기를 다 써서 준비된 예시를 보여 드려요. 이슈·섹터는 계속 볼 수 있어요.")
        hits = _sessions.setdefault(session or "anon", deque())
        while hits and time.time() - hits[0] > LIVE_SESSION_WINDOW:
            hits.popleft()
        if len(hits) >= LIVE_PER_SESSION:
            return {"status": "limited", "word": word,
                    "message": f"새 단어는 {LIVE_SESSION_WINDOW // 60}분에 {LIVE_PER_SESSION}개까지 그릴 수 있어요. 조금 뒤에 다시 해 주세요."}
        active = sum(1 for j in _jobs.values() if j["state"] in ("queued", "running"))
        if active >= LIVE_QUEUE_MAX:
            return _fallback(word, "busy", "지금 그리는 단어가 많아요. 잠시 뒤에 다시 해 주세요.")
        hits.append(time.time())
        if len(_sessions) > 2000:  # 오래된 세션 정리
            for k in [k for k, v in _sessions.items() if not v or time.time() - v[-1] > LIVE_SESSION_WINDOW]:
                _sessions.pop(k, None)
        _seq["n"] += 1
        _jobs[word] = {"state": "queued", "seq": _seq["n"]}
        position = _position(word)
        _bump_live_today()
    _pool.submit(_run_job, word)
    return {"status": "queued", "word": word, "position": position}


# ---------------------------------------------------------
# 수동 실행
#   python -m services.stockon.lifemap --daily      지금 기준으로 토픽 + 섹터 다시 만들기(수집기와 같은 일)
#   python -m services.stockon.lifemap --sectors    섹터만 다시
#   python -m services.stockon.lifemap --examples   저장소 예시 파일(data/stockon/lifemap_examples.json) 다시 만들기
# ---------------------------------------------------------

def _strip(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "removed"}


def build_examples() -> dict:
    basis = topic_basis()
    if not basis:
        raise RuntimeError("시세 스냅샷 없음")
    topics = [t for t in run_topics(basis)["topics"] if not t.get("carried")]
    run_sectors(basis)
    sectors = {k: _strip(m) for k, m in (_read("lifemap_sectors", {}).get("maps") or {}).items()}
    data = {"note": "AI가 실패할 때 쓰는 예시. 같은 엔진(Haiku 5.5 토픽·Sonnet 5.5 밸류체인)으로 그리고 종목 목록과 대조함.",
            "built": datetime.now(KST).strftime("%Y-%m-%d"), "basis": basis_info(basis),
            "topics": [{**t, "map": _strip(t["map"])} for t in topics], "sectors": sectors}
    EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--examples" in sys.argv:
        d = build_examples()
        print(f"예시: {d['basis']['label']} · 토픽 {len(d['topics'])}개, 섹터 {len(d['sectors'])}개")
    else:
        b = topic_basis()
        if not b:
            print("시세 스냅샷이 없어 만들 수 없어요.")
            sys.exit(1)
        if "--daily" in sys.argv:
            d = run_topics(b)
            print(f"{b['label']} · 토픽: 새로 {d['fresh']}개 / {len(d['topics'])}개")
        if "--daily" in sys.argv or "--sectors" in sys.argv:
            print(f"섹터: {run_sectors(b)}개")

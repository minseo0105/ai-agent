"""생활 속 종목 찾기: 생활 단어 → 밸류체인(원료·제조·물류·유통) → 관련 상장사 마인드맵.

- 오늘의 토픽 3개: 수집기(stockon-collector)가 매일 아침 한 번 네이버 뉴스 헤드라인(사회·생활·IT·경제)을 모아
  Haiku 5.5가 토픽 3개를 고르고(근거 기사 2개), 토픽마다 Sonnet 5.5가 밸류체인을 그린다. 결과는 저장해서 모두가 같이 본다.
- 예시 칩(라면·독감·김장·버스·커피)도 수집기가 미리 그려 둔다(7일마다 다시).
- 새 단어: AI LAB 앱(ailab)에서 같은 엔진으로 그린다. 동시 호출 상한·대기열·1인 횟수·하루 상한을 둔다.
  같은 단어는 한 번 그린 것을 모두가 재사용한다.
- AI가 낸 회사는 공공데이터 전 종목 목록(stocks.json)의 종목명과 맞춰 보고, 없는 회사는 지운다(종목코드는 목록에서 붙인다).
- AI가 실패하면 저장된 예시(data/stockon/lifemap_examples.json)로 대체한다. 화면이 비지 않게.
- 전일 등락률은 저장하지 않고 읽을 때 종목 목록에서 붙인다(늘 최신 기준일).
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

log = logging.getLogger("stockon.lifemap")

TOPIC_MODEL = "claude-haiku-5-5"
CHAIN_MODEL = "claude-sonnet-5-5"
CHIPS = ["라면", "독감", "김장", "버스", "커피"]
EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "data" / "stockon" / "lifemap_examples.json"

# 단계 순서 = 화면 가지 순서. 색은 화면에서 정한다(원료 청록·제조 보라·물류 노랑·유통 연두).
STAGES = {"material": "원료", "making": "제조", "logistics": "물류", "retail": "유통"}
PER_STAGE = 2
RELEVANCE = ("강", "중", "약")
MIN_COMPANIES = 3          # 검증 뒤 회사가 이보다 적으면 한 번 다시 그린다
DAILY_HOUR = 7             # 한국시간 7시 이후 첫 확인 때 오늘 토픽을 만든다
DAILY_TRIES = 3            # 하루 최대 시도(실패 시 30분 간격)
CHIP_MAX_AGE = 7 * 86400
HEADLINE_QUERIES = [("사회", "사회 이슈"), ("생활", "생활 물가"), ("IT", "IT 신제품 서비스"), ("경제", "경제 소비")]
HEADLINES_PER_QUERY = 20
HEADLINE_MAX_AGE_H = 36

# 새 단어 실시간 생성 안전장치(30명 동시 접속 기준)
LIVE_CONCURRENCY = 3       # 동시에 AI를 부르는 수
LIVE_QUEUE_MAX = 12        # 대기열(그리는 중 포함). 넘치면 '지금 많이 그리고 있어요' + 예시
LIVE_PER_SESSION = 3       # 한 사람(브라우저)당 새 단어 10분에 3개
LIVE_SESSION_WINDOW = 600
LIVE_DAILY_MAX = 150       # 하루 새 단어 생성 상한(서버 전체). 넘으면 저장된 것·예시만
LIVE_TIMEOUT = 45          # AI 한 번 호출 최대 초
WORDS_KEEP = 300           # 저장해 두는 새 단어 수(오래된 것부터 지움)
RESULT_KEEP_SEC = 120      # 실패 결과를 폴링에 알려 주는 시간

EXTRA_BANNED = [re.compile(p) for p in (r"수혜", r"추천", r"주목", r"기대", r"유망", r"관심\s*종목", r"테마주", r"급등", r"급락")]
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
        return "다른 생활 단어로 입력해 주세요."
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

CHAIN_SYSTEM = """너는 생활 속 단어를 한국 상장사의 밸류체인으로 이어 주는 경제 교육용 편집자다.
규칙:
- 한국거래소(코스피·코스닥)에 지금 상장된 회사만, 상장 종목명 그대로 쓴다. 비상장사·해외 회사·상장사의 비상장 자회사는 쓰지 않는다.
- 단계는 원료(material)·제조(making)·물류(logistics)·유통(retail) 중 이 단어에 실제로 해당하는 것만 고른다. 억지로 채우지 않는다.
- 단계마다 이 단어와 가장 직접 이어지는 회사를 3곳까지, 연관이 큰 순서로 쓴다. 확실하지 않은 회사는 쓰지 않는다.
- 그 단계에서 이 단어와 확실히 이어지는 상장사가 없으면 그 단계를 통째로 뺀다. 연결이 약하거나 추측('~할 수 있다', '관련 낮음')인 회사는 넣지 않는다.
- relevance: 강 = 이 단어가 그 회사의 핵심 사업, 중 = 주요 사업 중 하나, 약 = 간접적으로 이어짐.
- reason: 그 회사가 이 단어와 어떻게 이어지는지 사업 사실만 한 줄(30자 이내).
- detail: 그 단계에서 이 단어와 관련된 것(예: '밀가루·팜유'), 12자 이내.
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

TOPIC_SYSTEM = """너는 오늘 뉴스 헤드라인에서 '생활 속 화제'를 고르는 편집자다.
규칙:
- 사람들이 일상에서 겪는 것(먹거리·날씨·건강·교통·가전·서비스·물가 등)으로, 만들고 나르고 파는 산업과 이어지는 화제를 고른다.
- 정치·범죄·사건사고·특정 회사 주가·증시 시황은 고르지 않는다.
- 후보는 서로 다른 기사·되도록 다른 분야(사회·생활·IT·경제)에서 고른다. 같은 기사에서 나온 화제를 여러 개 고르지 않는다.
- name은 누구나 아는 일반 생활 단어(명사) 2~8자, 서로 겹치지 않게. 회사·브랜드·제품 이름은 name에 쓰지 않는다(예: '갤럭시' 대신 '폴더블폰'). summary는 자료에 있는 사실만 한 줄(40자 이내).
- articles에는 그 화제의 근거가 되는 기사 번호를 정확히 2개 넣는다(주어진 번호만).
- 권유·전망·평가 표현, '추천', '수혜', '주목' 같은 말을 쓰지 않는다. 한국어."""

TOPIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["name", "summary", "articles"],
        "properties": {"name": {"type": "string"}, "summary": {"type": "string"},
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


def build_chain(word: str, context: str = "", live: bool = False) -> dict:
    """단어 하나의 마인드맵. 실패하면 예외(호출하는 쪽이 예시로 대체)."""
    stocks, index, as_of = directory()
    if not stocks:
        raise RuntimeError("종목 목록 없음")
    task = f"생활 단어 '{word}'를 밸류체인 단계와 한국 상장사로 이어라."
    if context:
        task += f"\n참고(오늘 뉴스 화제): {context}"
    removed_all: list[str] = []
    stages: list[dict] = []
    for attempt in range(2):
        raw = _ask(CHAIN_MODEL, CHAIN_SYSTEM, task, {"단어": word}, CHAIN_SCHEMA, 1500, live)
        stages, removed = validate_chain(raw, index, stocks)
        removed_all += removed
        if sum(len(s["companies"]) for s in stages) >= MIN_COMPANIES:
            break
        if attempt == 0 and removed:
            task += (f"\n\n주의: 직전 결과의 {', '.join(removed[:6])}은(는) 상장 종목 목록에 없었다. "
                     "상장된 회사만 상장 종목명 그대로 다시 써라.")
        elif attempt == 0:
            break  # 지운 회사 없이 적게 나왔으면 다시 불러도 비슷하다(빈 결과 = 이어지는 회사 없음)
    return {"word": word, "stages": stages, "removed": list(dict.fromkeys(removed_all))[:10], "ai": True,
            "model": CHAIN_MODEL, "directory_as_of": as_of, "created_ts": time.time()}


def collect_headlines(http=None) -> list[dict]:
    """사회·생활·IT·경제 최신 헤드라인(최근 36시간, 제목 중복 제거)."""
    cutoff = datetime.now(KST) - timedelta(hours=HEADLINE_MAX_AGE_H)
    out, seen = [], set()
    for label, query in HEADLINE_QUERIES:
        kwargs = {"http": http} if http else {}
        for n in news.search(query, display=HEADLINES_PER_QUERY, sort="date", **kwargs):
            pub = datetime.fromisoformat(n["pub"]) if n.get("pub") else None
            if n["title"] in seen or (pub and pub < cutoff):
                continue
            seen.add(n["title"])
            out.append({**n, "category": label})
    return out


def pick_topics(headlines: list[dict]) -> list[dict]:
    """Haiku가 고른 토픽 후보(최대 5, 근거 기사 2개씩). 번호·표현 검사를 통과한 것만. 앞의 3개를 쓰고 나머지는 예비."""
    payload = [{"번호": i + 1, "분야": h.get("category", ""), "제목": h["title"], "요약문": (h.get("snippet") or "")[:80]}
               for i, h in enumerate(headlines)]
    raw = _ask(TOPIC_MODEL, TOPIC_SYSTEM, "오늘의 생활 속 화제 후보 5개를 고를 만한 순서로 골라라.", payload, TOPIC_SCHEMA, 2000)
    topics, names, used_articles = [], set(), set()
    for t in (raw or {}).get("topics") or []:
        name = normalize_word(str(t.get("name") or ""))[:12]
        summary = str(t.get("summary") or "").strip()[:80]
        nums = [n for n in dict.fromkeys(t.get("articles") or []) if isinstance(n, int) and 1 <= n <= len(headlines)]
        if not name or name in names or check_word(name) or not summary or _unsafe(summary) or _unsafe(name) or len(nums) < 2:
            continue
        if used_articles & set(nums[:2]):
            continue  # 앞 토픽과 근거 기사가 겹치면 같은 뉴스에서 나온 화제(오늘의 토픽 3개가 한 기사로 쏠리지 않게)
        names.add(name)
        used_articles.update(nums[:2])
        topics.append({"name": name, "summary": summary,
                       "articles": [{k: headlines[n - 1].get(k) for k in ("title", "url", "press", "pub")} for n in nums[:2]]})
        if len(topics) == 5:
            break
    return topics


# ---------------------------------------------------------
# 예시(대체용)
# ---------------------------------------------------------

_examples_cache: dict = {"value": None}


def examples() -> dict:
    if _examples_cache["value"] is None:
        try:
            _examples_cache["value"] = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _examples_cache["value"] = {"topics": [], "words": {}}
    return _examples_cache["value"]


def example_map(word: str = "") -> dict:
    """같은 단어 예시가 있으면 그것, 없으면 첫 예시 칩 예시."""
    words = examples().get("words") or {}
    chosen = words.get(word) or words.get(CHIPS[0]) or next(iter(words.values()), None)
    return {**chosen, "example": True} if chosen else {"word": word, "stages": [], "ai": False, "example": True}


# ---------------------------------------------------------
# 매일 아침 생성(수집기)
# ---------------------------------------------------------

def _status(**kw) -> None:
    try:
        s = _read("lifemap_status", {})
        s.update(kw)
        store.write("lifemap_status", s)
    except Exception:
        pass


def run_chips(force: bool = False) -> int:
    """예시 칩 마인드맵을 7일마다 다시 그린다. 실패한 칩은 이전 것(없으면 예시)을 쓴다."""
    chips = _read("lifemap_chips", {})
    made = 0
    for word in CHIPS:
        old = chips.get(word)
        if not force and old and not old.get("example") and time.time() - old.get("created_ts", 0) < CHIP_MAX_AGE:
            continue
        try:
            m = build_chain(word)
            if m["stages"]:
                chips[word] = m
                made += 1
        except Exception as e:
            log.warning("lifemap chip %s failed: %s", word, type(e).__name__)
    store.write("lifemap_chips", chips)
    return made


def run_daily(http=None) -> dict:
    """오늘의 토픽 3개 + 토픽별 마인드맵. 모자란 토픽은 어제 것, 그다음 예시로 채운다."""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    prev = _read("lifemap", {})
    topics: list[dict] = []
    error = ""
    try:
        for t in pick_topics(collect_headlines(http)):
            if len(topics) == 3:
                break
            try:
                m = build_chain(t["name"], context=t["summary"])
            except Exception as e:
                error = f"chain:{type(e).__name__}"
                continue
            if m["stages"]:
                topics.append({**t, "map": m})
    except Exception as e:
        error = f"topics:{type(e).__name__}"
        log.warning("lifemap topics failed: %s", error)
    names = {t["name"] for t in topics}
    for t in (prev.get("topics") or []) + (examples().get("topics") or []):
        if len(topics) >= 3:
            break
        if t["name"] not in names:
            names.add(t["name"])
            topics.append({**t, "carried": True})
    fresh = sum(1 for t in topics if not t.get("carried"))
    data = {"day": today, "topics": topics[:3], "fresh": fresh, "topic_model": TOPIC_MODEL, "chain_model": CHAIN_MODEL,
            "created_ts": time.time()}
    store.write("lifemap", data)
    _status(day=today, ok=fresh == 3, fresh=fresh, error=error, ts=time.time())
    return data


_daily_lock = threading.Lock()


def daily_due(now: datetime) -> bool:
    if now.hour < DAILY_HOUR:
        return False
    today = now.strftime("%Y-%m-%d")
    cur = _read("lifemap", {})
    if cur.get("day") == today and cur.get("fresh", 0) >= 3:
        return False
    s = _read("lifemap_status", {})
    tries = s.get("tries", 0) if s.get("try_day") == today else 0
    if cur.get("day") == today and tries >= 1 and cur.get("fresh", 0) >= 1:
        return False  # 오늘 것이 일부라도 있으면 다시 부르지 않는다(비용)
    return tries < DAILY_TRIES and time.time() - s.get("try_ts", 0) > 1800


def maybe_run_daily(now: datetime | None = None) -> bool:
    """수집기 루프에서 매번 부른다. 할 때가 됐으면 스레드 하나로 돌린다(키움 수집을 막지 않게)."""
    now = now or datetime.now(KST)
    if not ai.available() or not news.configured() or not daily_due(now) or not _daily_lock.acquire(blocking=False):
        return False
    today = now.strftime("%Y-%m-%d")
    s = _read("lifemap_status", {})
    _status(try_day=today, tries=(s.get("tries", 0) if s.get("try_day") == today else 0) + 1, try_ts=time.time())

    def work():
        try:
            run_daily()
            run_chips()
        except Exception as e:
            log.warning("lifemap daily failed: %s", type(e).__name__)
        finally:
            _daily_lock.release()

    threading.Thread(target=work, name="lifemap-daily", daemon=True).start()
    return True


# ---------------------------------------------------------
# 화면 데이터(읽기 전용) — 등락률은 지금 종목 목록에서 붙인다
# ---------------------------------------------------------

def with_prices(m: dict) -> dict:
    stocks, _, as_of = directory()
    stages = []
    for st in m.get("stages") or []:
        companies = []
        for c in st.get("companies") or []:
            s = stocks.get(c.get("code"))
            if s:  # 상장 폐지 등으로 목록에서 빠진 회사는 보이지 않는다
                companies.append({**c, "name": s["name"], **{k: s.get(k) for k in ("market", "close", "rate", "cap", "value")}})
        if companies:
            stages.append({**st, "companies": companies})
    out = {k: v for k, v in m.items() if k != "removed"}
    return {**out, "stages": stages, "price_as_of": as_of}


def overview() -> dict:
    cur = _read("lifemap", {})
    topics = cur.get("topics") or [{**t, "carried": True} for t in examples().get("topics") or []]
    chips = _read("lifemap_chips", {})
    ex = examples().get("words") or {}
    chip_maps = {}
    for w in CHIPS:
        m = chips.get(w) or ({**ex[w], "example": True} if w in ex else None)
        if m:
            chip_maps[w] = with_prices(m)
    return {
        "day": cur.get("day"),
        "topics": [{**t, "map": with_prices(t["map"])} for t in topics if t.get("map")],
        "chips": CHIPS,
        "chip_maps": chip_maps,
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
    """칩·오늘 토픽·전에 그린 새 단어 중 같은 단어."""
    chips = _read("lifemap_chips", {})
    if word in chips:
        return chips[word]
    for t in _read("lifemap", {}).get("topics") or []:
        if t.get("name") == word and t.get("map"):
            return t["map"]
    m = _read("lifemap_words", {}).get(word)
    if m:
        return m
    ex = (examples().get("words") or {}).get(word)  # 칩을 아직 못 그렸으면 저장소 예시(AI를 다시 부르지 않음)
    return {**ex, "example": True} if ex else None


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
            return _fallback(word, "daily_limit", "오늘 새 단어 그리기를 다 써서 준비된 예시를 보여 드려요. 예시 단어는 계속 볼 수 있어요.")
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
#   python -m services.stockon.lifemap --daily      오늘 토픽 + 칩(수집기와 같은 일)
#   python -m services.stockon.lifemap --chips      칩만 다시
#   python -m services.stockon.lifemap --examples   저장소 예시 파일(data/stockon/lifemap_examples.json) 다시 만들기
# ---------------------------------------------------------

def build_examples() -> dict:
    words = {}
    for w in CHIPS:
        m = build_chain(w)
        if m["stages"]:
            words[w] = {k: v for k, v in m.items() if k != "removed"}
    daily = run_daily()
    topics = [{k: t[k] for k in ("name", "summary", "articles", "map")} for t in daily["topics"] if not t.get("carried")]
    data = {"note": "AI가 실패할 때 쓰는 예시. 같은 엔진(Sonnet 5.5)으로 그리고 종목 목록과 대조함.",
            "built": datetime.now(KST).strftime("%Y-%m-%d"), "topics": topics, "words": words}
    EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--examples" in sys.argv:
        d = build_examples()
        print(f"예시: 토픽 {len(d['topics'])}개, 단어 {len(d['words'])}개")
    elif "--chips" in sys.argv:
        print(f"칩: {run_chips(force=True)}개")
    elif "--daily" in sys.argv:
        d = run_daily()
        print(f"토픽: 새로 {d['fresh']}개 / {len(d['topics'])}개")
        print(f"칩: {run_chips()}개")

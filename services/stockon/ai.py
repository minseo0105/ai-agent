"""AI 문장: 아침 브리핑 3줄 · 뉴스 한 줄 요약 · '왜 움직였나'.

- 입력은 수집한 숫자 · 뉴스 제목/검색 요약문 · 공시 제목뿐이다. 기사 원문은 넣지 않는다.
- 출력은 JSON(문장 + 출처 번호). 출처 번호는 우리가 넘긴 목록의 번호만 인정한다.
- 금지 표현(safety.BANNED_PATTERNS)이 나오면 한 번 다시 만들고, 그래도 걸리면 그 문장을 버린다.
- AI를 못 쓰면(키 없음·오류·거절) 숫자로 만든 고정 문장을 쓴다(브리핑) 또는 요약 없이 보여 준다(뉴스).
"""

import json
import logging
import time
from datetime import datetime

from services.agent import _claude_client
from services.stockon import budget, store
from services.stockon.public_data import KST
from services.stockon.safety import banned_hits, keep_valid_sources

log = logging.getLogger("stockon.ai")

MODEL = "claude-opus-5-5"
# 작업별 모델. 2026-10-27 3모델 비교(실제 10/26 시세·뉴스·공시) 후 사용자 결정:
# 브리핑·왜 움직였나 = Sonnet 5.5, 뉴스 한 줄 요약 = Haiku 5.5(호출이 가장 많고 요약 품질은 동등).
WHY_MODEL = "claude-sonnet-5-5"
BRIEFING_MODEL = "claude-sonnet-5-5"
NEWS_MODEL = "claude-haiku-5-5"
EFFORT = "low"
# 안전 분류기가 거절하면 서버가 같은 요청을 대체 모델로 다시 돌린다(Haiku는 이 기능이 없다).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

RULES = """너는 한국 주식시장 정보를 사실대로 정리하는 편집자다.
규칙:
- 주어진 숫자와 자료에 있는 사실만 쓴다. 자료에 없는 원인·전망·추측을 만들지 않는다.
- 매수·매도·보유를 권하거나 그렇게 읽히는 표현, 목표가, 저평가·고평가 같은 평가, 앞으로의 방향 예측을 쓰지 않는다.
- '올랐다/내렸다/거래가 많았다/공시했다/보도됐다'처럼 이미 일어난 일만 서술한다.
- 문장마다 근거가 된 자료의 번호를 sources에 넣는다. 근거가 없는 문장은 쓰지 않는다.
- 뉴스에는 '발행' 시각이 있다. 기준일이 아닌 다른 날의 지수·주가 마감을 다룬 기사(예: 직전 거래일 마감 기사)는 쓰지 않는다.
  숫자(지수·종가·등락률)는 기사에 적힌 값이 아니라 함께 준 시장·종목 자료를 따른다.
- 한국어, 짧고 담백한 평서문."""


def available() -> bool:
    return _claude_client() is not None


# ---------------------------------------------------------
# AI 상태 기록 (관리자 화면 'AI 상태'). 오류는 종류·상태 코드만 남긴다(키·요청 내용 없음).
# ---------------------------------------------------------

KINDS = ("briefing", "why", "news_summary")
_last = {"error": ""}


def _error_label(e: Exception) -> str:
    status = getattr(e, "status_code", None)
    etype = ""
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        etype = str((body.get("error") or {}).get("type") or "")
    return " ".join(x for x in (type(e).__name__, str(status) if status else "", etype) if x)[:80]


def record(kind: str, ok: bool, error: str = "", fallback: bool = False) -> None:
    """작업 하나의 결과를 남긴다. 기록 실패가 화면 갱신을 막지 않게 예외는 삼킨다."""
    try:
        now = time.time()
        today = datetime.now(KST).strftime("%Y-%m-%d")
        status = store.read("ai_status", {}) or {}
        s = status.setdefault(kind, {})
        if s.get("day") != today:
            s.update(day=today, fails_today=0, fallbacks_today=0)
        if ok:
            s.update(ok_ts=now, consecutive=0)
        else:
            s.update(last_error=(error or "알 수 없는 오류")[:120], error_ts=now, consecutive=s.get("consecutive", 0) + 1,
                     fails_today=s.get("fails_today", 0) + 1, fails_total=s.get("fails_total", 0) + 1)
        if fallback:
            s.update(fallbacks_today=s.get("fallbacks_today", 0) + 1, fallbacks_total=s.get("fallbacks_total", 0) + 1)
        store.write("ai_status", status)
    except Exception as e:
        log.warning("stockon ai status write failed: %s", type(e).__name__)


def request_args(task: str, payload: dict, schema: dict, model: str = MODEL, max_tokens: int = 2000) -> dict:
    args = dict(
        model=model,
        max_tokens=max_tokens,
        system=RULES,
        messages=[{"role": "user", "content": f"{task}\n\n자료(JSON):\n{json.dumps(payload, ensure_ascii=False)}"}],
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
    )
    if model in FALLBACK_MODELS:
        args.update(extra_headers={"anthropic-beta": FALLBACK_BETA}, extra_body={"fallbacks": "default"})
    return args


def _call(task: str, payload: dict, schema: dict, max_tokens: int = 2000, model: str = MODEL) -> dict | None:
    client = _claude_client()
    if client is None:
        _last["error"] = "AI 키 없음(ANTHROPIC_API_KEY)"
        return None
    if not budget.allowed():  # 하루 비용 상한: 새로 부르지 않는다(브리핑은 숫자 문장, 뉴스는 요약 없이)
        _last["error"] = "하루 AI 비용 상한 도달"
        return None
    try:
        resp = client.messages.create(**request_args(task, payload, schema, model, max_tokens))
        budget.record(model, getattr(resp, "usage", None))
    except Exception as e:  # 키·네트워크·한도 오류: 화면은 고정 문장으로 계속 동작
        _last["error"] = _error_label(e)
        log.warning("stockon ai call failed: %s", _last["error"])
        return None
    if resp.stop_reason in ("refusal", "max_tokens"):
        _last["error"] = f"stop_reason={resp.stop_reason} ({model})"
        log.warning("stockon ai %s", _last["error"])
        return None
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        return json.loads(text)
    except ValueError:
        _last["error"] = f"JSON 파싱 실패 ({model})"
        return None


def _sentences_schema() -> dict:
    # 구조화 출력 스키마는 배열 maxItems를 받지 않는다(400). 문장 수는 프롬프트로 정하고 코드에서 자른다.
    return {
        "type": "object", "additionalProperties": False, "required": ["sentences"],
        "properties": {"sentences": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "sources"],
            "properties": {"text": {"type": "string"}, "sources": {"type": "array", "items": {"type": "integer"}}},
        }}},
    }


def _safe_sentences(task: str, payload: dict, n_sources: int, max_items: int, model: str = MODEL,
                    require=None, require_hint: str = "") -> list[dict] | None:
    """금지 표현·출처 없는 문장을 걸러 낸다. 걸리면 한 번 다시 만든다.
    require(good)가 False면(예: 뉴스 문장 빠짐) 그것도 한 번 다시 만든다. 두 번째에도 못 맞추면 있는 문장을 쓴다.
    실패(None)·전부 제외([])의 이유는 _last['error']에 남는다."""
    schema = _sentences_schema()
    _last["error"] = ""
    for attempt in range(2):
        out = _call(task, payload, schema, model=model)
        if out is None:
            return None
        good, bad = [], []
        for s in (out.get("sentences") or [])[:max_items]:
            text = str(s.get("text") or "").strip()
            sources = keep_valid_sources(s.get("sources"), n_sources)
            if not text or not sources or banned_hits(text):
                bad.append(text)
                continue
            good.append({"text": text[:160], "sources": sources})
        missing = bool(require) and not require(good)
        if (not bad and not missing) or attempt == 1:
            if bad and not good:
                _last["error"] = "금지 표현·출처 없는 문장만 나와 모두 제외"
            return good
        if bad:
            task += "\n\n주의: 직전 결과에 권유·평가·전망 표현이나 출처 없는 문장이 있었다. 규칙을 지켜 다시 써라."
        if missing:
            task += f"\n\n주의: {require_hint}"
    return None


# ---------------------------------------------------------
# 브리핑
# ---------------------------------------------------------

def _fmt_pct(v) -> str:
    return "보합" if not v else f"{v:+.2f}%"


def same_day_indices(market: dict) -> list[dict]:
    """종목 시세와 같은 기준일의 지수만. 지수 API가 하루 늦게 올라오는 경우를 거른다."""
    return [i for i in market.get("indices", []) if i.get("close") is not None and i.get("as_of") == market.get("as_of")]


def fallback_briefing(market: dict, fx: dict | None) -> list[dict]:
    """AI 없이 숫자로 만든 3줄. 출처는 1번(공공데이터)·2번(환율)."""
    idx = {i["name"]: i for i in same_day_indices(market)}
    lines = []
    parts = [f"{n} {idx[n]['close']:,.2f}({_fmt_pct(idx[n].get('rate'))})" for n in ("코스피", "코스닥") if n in idx]
    if parts:
        lines.append({"text": " · ".join(parts) + "로 마감했습니다.", "sources": [1]})
    b = market.get("breadth") or {}
    if b.get("total"):
        lines.append({"text": f"전체 {b['total']:,}개 종목 중 {b['up']:,}개가 오르고 {b['down']:,}개가 내렸습니다.", "sources": [1]})
    top = (market.get("movers") or {}).get("value") or []
    if top:
        lines.append({"text": f"거래대금은 {top[0]['name']}이(가) 가장 많았습니다({_fmt_pct(top[0].get('rate'))}).", "sources": [1]})
    if fx and fx.get("status") == "ok" and len(lines) < 3:
        lines.append({"text": f"원/달러 매매기준율은 {fx['close']:,.1f}원입니다.", "sources": [2]})
    return lines[:3]


BRIEFING_TASK = (
    "기준일 시장 브리핑을 정확히 3문장으로 써라. 각 문장 70자 이내.\n"
    "1문장: 코스피·코스닥 마감(출처 1).\n"
    "2문장: 눈에 띈 종목·업종 움직임(출처 1).\n"
    "3문장: 반드시 '뉴스·공시' 자료(번호 3 이상)로 확인되는 시장 이슈 하나. 이 문장의 sources에는 3 이상의 번호만 넣고, "
    "지수·환율·종목 수 같은 숫자 요약으로 대신하지 마라. 뉴스·공시가 하나도 없을 때만 환율이나 상승·하락 종목 수로 쓴다.\n"
    "3문장의 이슈는 지수 움직임이나 상승·하락 상위 종목과 관련된 뉴스를 먼저 고른다. 임원·주요주주 소유상황보고서, "
    "대량보유상황보고서 같은 정기 공시는 다른 뉴스·공시가 없을 때만 쓴다."
)
BRIEFING_NEWS_HINT = "3문장 중 하나는 반드시 뉴스·공시(번호 3 이상)를 출처로 하는 시장 이슈여야 한다. 직전 결과에 그런 문장이 없었다."


def briefing(market: dict, fx: dict | None, news: list[dict], dart: list[dict] | None = None) -> dict:
    """{'sentences': [...], 'sources': [...], 'ai': bool}. sources는 1부터 번호가 붙는 출처 목록.
    출처 번호: 1 시세 · 2 환율 · 3부터 뉴스, 그 뒤 공시."""
    payload, sources = briefing_payload(market, fx, news, dart)
    has_issue_source = len(sources) > 2
    sentences = _safe_sentences(
        BRIEFING_TASK, payload, len(sources), 3, model=BRIEFING_MODEL,
        require=(lambda good: any(any(n >= 3 for n in s["sources"]) for s in good)) if has_issue_source else None,
        require_hint=BRIEFING_NEWS_HINT)
    if sentences:
        record("briefing", True)
        return {"sentences": sentences[:3], "sources": sources, "ai": True}
    record("briefing", False, _last["error"] or "문장 없음", fallback=True)  # 고정 문장으로 대체
    return {"sentences": fallback_briefing(market, fx), "sources": sources, "ai": False}


def briefing_payload(market: dict, fx: dict | None, news: list[dict], dart: list[dict] | None = None) -> tuple[dict, list[dict]]:
    news, dart = news[:8], (dart or [])[:4]
    sources = [{"name": f"{market['source']['name']} · {market['as_of'][4:6]}/{market['as_of'][6:]} 종가", "url": market["source"]["url"]}]
    sources.append({"name": "한국수출입은행 매매기준율", "url": (fx or {}).get("source", {}).get("url", "")}
                   if fx and fx.get("status") == "ok" else {"name": "환율 자료 없음", "url": ""})
    for n in news:
        sources.append({"name": n["title"], "url": n["url"]})
    for d in dart:
        sources.append({"name": f"[공시] {d.get('company', '')} {d['title']}".replace("  ", " "), "url": d["url"]})
    payload = {
        "1_시장": {
            "기준일": market["as_of"],
            # 기준일 지수만 넣는다(지수 API가 늦으면 비어 있음 → 1문장은 상승·하락 종목 수로 쓴다).
            "지수": [{k: i.get(k) for k in ("name", "close", "change", "rate")} for i in same_day_indices(market)]
                    or "기준일 지수 자료 없음(지수는 쓰지 말고 상승·하락 종목 수로 시장 분위기를 쓴다)",
            "상승하락종목수": market.get("breadth"),
            "상승률상위": [{k: s[k] for k in ("name", "rate")} for s in market["movers"]["up"][:5]],
            "하락률상위": [{k: s[k] for k in ("name", "rate")} for s in market["movers"]["down"][:5]],
            "거래대금상위": [{k: s[k] for k in ("name", "rate", "value")} for s in market["movers"]["value"][:5]],
        },
        "2_환율": {k: fx.get(k) for k in ("as_of", "close", "change")} if fx and fx.get("status") == "ok" else None,
        "뉴스(번호=3부터)": [{"번호": i + 3, "제목": n["title"], "요약문": n.get("snippet", ""), "발행": n.get("pub")}
                         for i, n in enumerate(news)],
        "공시": [{"번호": i + 3 + len(news), "회사": d.get("company", ""), "제목": d["title"], "접수일": d.get("date")}
                for i, d in enumerate(dart)],
    }
    return payload, sources


# ---------------------------------------------------------
# 뉴스 한 줄 요약
# ---------------------------------------------------------

NEWS_TASK = "각 기사를 사실만 담아 한 줄(45자 이내)로 요약해라. 자료에 없는 내용은 쓰지 마라."
NEWS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summaries"],
               "properties": {"summaries": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False, "required": ["no", "text"],
                   "properties": {"no": {"type": "integer"}, "text": {"type": "string"}}}}}}


def news_payload(items: list[dict]) -> list[dict]:
    return [{"no": i + 1, "제목": n["title"], "요약문": n.get("snippet", "")} for i, n in enumerate(items)]


def summarize_news(items: list[dict]) -> list[str]:
    """제목+검색 요약문 → 한 줄 요약(40자 안팎). 실패·금지 표현이면 빈 문자열(화면은 제목·링크만)."""
    if not items:
        return []
    _last["error"] = ""
    out = _call(NEWS_TASK, news_payload(items), NEWS_SCHEMA, model=NEWS_MODEL)
    if out is None:
        record("news_summary", False, _last["error"], fallback=True)  # 요약 없이 제목·링크만 보인다
    else:
        record("news_summary", True)
    result = [""] * len(items)
    for s in (out or {}).get("summaries") or []:
        no, text = s.get("no"), str(s.get("text") or "").strip()
        if isinstance(no, int) and 1 <= no <= len(items) and text and not banned_hits(text):
            result[no - 1] = text[:90]
    return result


# ---------------------------------------------------------
# 왜 움직였나
# ---------------------------------------------------------

NO_CAUSE = "확인된 원인 없음 — 수급이나 시장 전반의 영향일 수 있습니다."


WHY_TASK = ("이 종목이 기준일에 왜 움직였는지 자료로 확인되는 사실만 2~3문장으로 써라. "
            "자료가 이 종목의 기준일 움직임과 관련이 없으면 sentences를 빈 배열로 둬라. "
            "'확인되지 않는다', '자료에 없다'처럼 모른다는 문장이나 종가·등락률만 되풀이하는 문장은 쓰지 마라"
            "(화면에 종가·등락률과 '확인된 원인 없음' 안내가 따로 나온다).")


def why_payload(stock: dict, as_of: str, news: list[dict], disclosures: list[dict]) -> tuple[dict, list[dict]]:
    sources = [{"name": n["title"], "url": n["url"], "kind": "news"} for n in news[:8]]
    sources += [{"name": f"[공시] {d['title']}", "url": d["url"], "kind": "dart"} for d in disclosures[:4]]
    payload = {
        "종목": {"이름": stock["name"], "기준일": as_of, "종가": stock.get("close"), "등락률": stock.get("rate")},
        "자료": [{"번호": i + 1, "제목": s["name"], "요약문": (news[i].get("snippet", "") if i < len(news[:8]) else ""),
                  "발행": (news[i].get("pub") if i < len(news[:8]) else None)}
                 for i, s in enumerate(sources)],
    }
    return payload, sources


def why_moved(stock: dict, as_of: str, news: list[dict], disclosures: list[dict]) -> dict:
    payload, sources = why_payload(stock, as_of, news, disclosures)
    if not sources:
        return {"sentences": [], "note": NO_CAUSE, "sources": [], "ai": False}
    sentences = _safe_sentences(WHY_TASK, payload, len(sources), 3, model=WHY_MODEL)
    if sentences is None or (not sentences and _last["error"]):  # 호출 실패, 또는 문장이 전부 규칙에 걸림
        record("why", False, _last["error"], fallback=True)
        return {"sentences": [], "note": "요약을 만들지 못했습니다. 아래 뉴스·공시를 직접 확인해 주세요.", "sources": sources, "ai": False}
    record("why", True)  # 빈 배열은 모델이 '관련 자료 없음'으로 판단한 정상 결과
    return {"sentences": sentences, "note": "" if sentences else NO_CAUSE, "sources": sources, "ai": True}

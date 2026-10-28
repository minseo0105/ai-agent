"""STOCK:ON AI 하루 비용 상한.

- 호출마다 응답 usage(입력·출력 토큰)로 비용을 어림해 그날 합계를 남긴다. 프로세스가 둘(ailab 앱·stockon-collector)이라
  파일을 따로 쓰고(ai_cost_app / ai_cost_collector) 확인할 때 더한다(KST 날짜가 바뀌면 0부터).
- 합계가 STOCKON_AI_DAILY_USD(기본 5달러)를 넘으면 그날은 새 AI 호출을 하지 않는다 → 저장된 결과를 그대로 쓴다
  (뉴스 속 숨은 종목 이슈·섹터는 이전 것, 직접 입력은 저장된 것·예시, 브리핑은 숫자 문장, 뉴스는 요약 없이).
- 가격은 1M 토큰당 달러(Anthropic API 표준 가격). 모르는 모델은 Sonnet 값으로 어림한다(넉넉하게).
"""

import logging
import os
import threading
from datetime import datetime

from services.stockon import store
from services.stockon.public_data import KST

log = logging.getLogger("stockon.budget")

PRICES = {  # (입력, 출력) 1M 토큰당 USD
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
DEFAULT_PRICE = PRICES["claude-sonnet-5-5"]
DEFAULT_LIMIT_USD = 5.0
BUCKETS = ("app", "collector")
BUCKET = "app"  # 수집기는 시작할 때 "collector"로 바꾼다

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    def __init__(self):
        super().__init__("budget_exceeded")


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def limit_usd() -> float:
    try:
        return max(0.0, float(os.environ.get("STOCKON_AI_DAILY_USD", "") or DEFAULT_LIMIT_USD))
    except ValueError:
        return DEFAULT_LIMIT_USD


def cost(model: str, usage) -> float:
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    tin = int(getattr(usage, "input_tokens", 0) or 0) + int(getattr(usage, "cache_creation_input_tokens", 0) or 0) \
        + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    tout = int(getattr(usage, "output_tokens", 0) or 0)
    return (tin * pin + tout * pout) / 1_000_000


def record(model: str, usage) -> None:
    """호출 한 번의 비용을 그날 합계에 더한다. 기록 실패가 화면 갱신을 막지 않게 예외는 삼킨다."""
    try:
        with _lock:
            name = f"ai_cost_{BUCKET}"
            data = store.read(name, {}) or {}
            if data.get("day") != _today():
                data = {"day": _today(), "usd": 0.0, "calls": 0, "models": {}}
            c = cost(model, usage)
            data["usd"] = round(data["usd"] + c, 6)
            data["calls"] += 1
            m = data["models"].setdefault(model, {"calls": 0, "usd": 0.0})
            m["calls"] += 1
            m["usd"] = round(m["usd"] + c, 6)
            store.write(name, data)
    except Exception as e:
        log.warning("budget record failed: %s", type(e).__name__)


def spent_today() -> float:
    today = _today()
    total = 0.0
    for b in BUCKETS:
        data = store.read(f"ai_cost_{b}", {}) or {}
        if data.get("day") == today:
            total += float(data.get("usd") or 0)
    return total


def allowed() -> bool:
    return spent_today() < limit_usd()


def check() -> None:
    """상한을 넘었으면 BudgetExceeded(부르는 쪽은 저장된 결과로 대신한다)."""
    if not allowed():
        raise BudgetExceeded()


def status() -> dict:
    today = _today()
    buckets = {}
    for b in BUCKETS:
        data = store.read(f"ai_cost_{b}", {}) or {}
        buckets[b] = data if data.get("day") == today else {"day": today, "usd": 0.0, "calls": 0, "models": {}}
    spent = sum(float(x.get("usd") or 0) for x in buckets.values())
    return {"day": today, "spent_usd": round(spent, 4), "limit_usd": limit_usd(), "exceeded": spent >= limit_usd(),
            "buckets": buckets}

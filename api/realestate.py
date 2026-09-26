"""부동산 모니터 API (services/realestate_monitor.py 래핑)."""

import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from services import realestate_monitor as rm

router = APIRouter(prefix="/api/realestate", tags=["realestate"])
BASE_DIR = Path(__file__).resolve().parents[1]
rm.init_db(BASE_DIR)

SUPPLY_TYPES = ["공공", "민간", "미분류"]
KINDS = ["일반분양", "사전청약", "신혼희망타운", "무순위/잔여세대"]
STATUSES = ["접수예정", "접수중", "접수마감", "일정확인"]
EVENT_TYPES = ["신규청약", "무순위청약", "신규실거래"]
MAX_TRADE_COMBOS = 40  # 지역 × 주택유형 조합 상한 (공공데이터 호출량 보호)

_cache = {}


def _cached(key, loader, ttl=600):
    """청약 목록은 자주 바뀌지 않아 10분간 재사용한다."""
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = loader()
    _cache[key] = (time.monotonic(), value)
    return value


def _clean(item):
    return {k: v for k, v in item.items() if k != "raw"}


def _error(e):
    raise HTTPException(502, f"공공데이터 조회 실패: {rm.safe_error(e)}")


@router.get("/options")
def options():
    status = rm.get_api_status()
    return {
        "regions": {"서울": rm.SEOUL_REGIONS, "경기": rm.GYEONGGI_REGIONS},
        "property_types": rm.PROPERTY_TYPES,
        "supply_types": SUPPLY_TYPES,
        "kinds": KINDS,
        "statuses": STATUSES,
        "event_types": EVENT_TYPES,
        "api_key": status["public_data_key"],
        "storage": "supabase" if status["persistent_storage"] else "local",
    }


class SubscriptionQuery(BaseModel):
    kind: Literal["apt", "unsold"] = "apt"
    regions: list[str] = Field(default_factory=list, max_length=100)
    supply_types: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


@router.post("/subscriptions")
async def subscriptions(q: SubscriptionQuery):
    loader = rm.fetch_apt_subscriptions if q.kind == "apt" else rm.fetch_unsold_subscriptions
    try:
        rows = await run_in_threadpool(_cached, f"sub:{q.kind}", lambda: loader(per_page=100))
    except Exception as e:
        _error(e)
    filtered = rm.filter_subscriptions(rows, regions=q.regions, supply_types=q.supply_types,
                                       subscription_kinds=q.kinds, statuses=q.statuses)
    return {"total": len(rows), "items": [_clean(x) for x in filtered]}


class TradeQuery(BaseModel):
    regions: list[str] = Field(min_length=1, max_length=40)
    property_types: list[str] = Field(min_length=1)
    month: str = Field(pattern=r"^\d{6}$")
    max_price_100m: float | None = Field(None, gt=0, le=10000, allow_inf_nan=False)


@router.post("/trades")
async def trades(q: TradeQuery):
    if len(q.regions) * len(q.property_types) > MAX_TRADE_COMBOS:
        raise HTTPException(400, f"지역 × 주택유형 조합은 최대 {MAX_TRADE_COMBOS}개까지 조회할 수 있어요.")
    try:
        rows, errors = await run_in_threadpool(rm.fetch_trades_multi, q.regions, q.property_types, q.month)
    except Exception as e:
        _error(e)
    rows = rm.filter_trade_price(rows, q.max_price_100m)
    rows = sorted(rows, key=lambda x: (x.get("date") or ""), reverse=True)
    for row in rows:
        row["naver_url"] = rm.build_naver_land_url(row)
    counts = {}
    for row in rows:
        counts[row.get("property_type", "기타")] = counts.get(row.get("property_type", "기타"), 0) + 1
    return {"items": rows, "errors": errors, "counts": counts, "requests": len(q.regions) * len(q.property_types)}


@router.get("/monitor")
def monitor():
    return {
        "auto_enabled": rm.get_auto_monitor_enabled(BASE_DIR),
        "usage": rm.estimate_monitor_api_calls(BASE_DIR),
        "rules": rm.get_alert_rules(BASE_DIR),
    }


class AutoToggle(BaseModel):
    enabled: bool


@router.put("/monitor/auto")
def set_auto(body: AutoToggle):
    rm.set_auto_monitor_enabled(BASE_DIR, body.enabled)
    return monitor()


class RuleInput(BaseModel):
    regions: list[str] = Field(min_length=1, max_length=40)
    event_types: list[Literal["신규청약", "무순위청약", "신규실거래"]] = Field(min_length=1)
    property_types: list[str] = Field(default_factory=list)
    supply_types: list[str] = Field(default_factory=list)
    max_price_100m: float = Field(20.0, ge=0, le=100)
    min_area: float = Field(40.0, ge=0, le=500)


@router.post("/rules")
def add_rules(body: RuleInput):
    if "신규실거래" in body.event_types and not body.property_types:
        raise HTTPException(400, "신규실거래를 선택했다면 주택유형도 1개 이상 선택해주세요.")
    rm.save_alert_rules(BASE_DIR, body.regions, body.event_types, body.max_price_100m, body.min_area,
                        body.supply_types, body.property_types)
    return monitor()


@router.post("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: int):
    rm.toggle_alert_rule(BASE_DIR, rule_id)
    return monitor()


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int):
    rm.delete_alert_rule(BASE_DIR, rule_id)
    return monitor()


@router.post("/monitor/run")
async def run_now():
    try:
        return await run_in_threadpool(rm.run_monitoring_once, BASE_DIR)
    except Exception as e:
        _error(e)


@router.get("/notifications")
def notifications(limit: int = 100):
    items = rm.get_notifications(BASE_DIR, min(max(limit, 1), 300))
    return {"items": items, "unread": sum(1 for x in items if not x.get("is_read"))}


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int):
    rm.mark_notification_read(BASE_DIR, notification_id)
    return notifications()

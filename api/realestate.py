"""부동산 모니터 API (services/realestate_monitor.py 래핑)."""

import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from services import realestate_monitor as rm
from services import development
from services import development_presentation as presentation
from services import map_providers
from services import development_geocode as geocode
from services import trade_geocode
from services import development_canary
from services import development_bulk_geocode as bulk_geocode

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
    max_area: float | None = Field(None, gt=0, le=100000, allow_inf_nan=False)
    include_development: bool = False
    # 실거래 주소 지오코딩은 유료 쿼터를 쓰므로 명시적으로 켤 때만 동작한다.
    include_coordinates: bool = False


@router.post("/trades")
async def trades(q: TradeQuery):
    if len(q.regions) * len(q.property_types) > MAX_TRADE_COMBOS:
        raise HTTPException(400, f"지역 × 주택유형 조합은 최대 {MAX_TRADE_COMBOS}개까지 조회할 수 있어요.")
    try:
        rows, errors = await run_in_threadpool(rm.fetch_trades_multi, q.regions, q.property_types, q.month)
    except Exception as e:
        _error(e)
    rows = rm.filter_trade_price(rows, q.max_price_100m)
    rows = rm.filter_trade_area(rows, q.max_area)
    rows = sorted(rows, key=lambda x: (x.get("date") or ""), reverse=True)
    for row in rows:
        row["naver_url"] = rm.build_naver_land_url(row)
    geocode_summary = None
    if q.include_coordinates:
        # 개발사업과 같은 provider·같은 판정 기준. 검증된 좌표만 붙는다.
        resolved = await run_in_threadpool(_geocode_trades, rows)
        rows, geocode_summary = resolved['items'], _clean_geocode_summary(resolved)
    if q.include_development:
        rows = await run_in_threadpool(development.attach_context, rows)
        for row in rows:
            # 화면에는 내부 enum 대신 사용자 문구를 내려준다.
            context = presentation.present_context(row.get('development_context'))
            row['development'] = context
            row['development_impact'] = presentation.impact(
                context, trade_has_point=row.get('latitude') is not None
                and row.get('longitude') is not None)
    counts = {}
    for row in rows:
        counts[row.get("property_type", "기타")] = counts.get(row.get("property_type", "기타"), 0) + 1
    return {"items": rows, "errors": errors, "counts": counts,
            "requests": len(q.regions) * len(q.property_types), "geocode": geocode_summary}


TRADE_GEOCODE_CACHE = BASE_DIR / 'data/development/cache/geocode'


def _geocode_trades(rows):
    """실거래 주소를 개발사업과 같은 캐시·같은 판정으로 좌표화한다. DB write는 없다."""
    cache = geocode.GeocodeCache(TRADE_GEOCODE_CACHE)
    return trade_geocode.resolve_trades(rows, cache, rm._secret, geocode.requests_get)


def _clean_geocode_summary(resolved):
    return {k: v for k, v in resolved.items() if k != 'items'}


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


class DevelopmentQuery(BaseModel):
    longitude: float | None = Field(None, ge=-180, le=180, allow_inf_nan=False)
    latitude: float | None = Field(None, ge=-90, le=90, allow_inf_nan=False)
    sigungu: str | None = Field(None, max_length=40)
    radius_m: float = Field(1000, ge=0, le=10000, allow_inf_nan=False)
    limit: int = Field(30, ge=1, le=100)


@router.get('/development/summary')
async def development_summary():
    result = await run_in_threadpool(development.district_summary)
    districts = [dict(bucket, type_labels={presentation.TYPE_LABELS.get(k, '기타'): v
                                           for k, v in bucket['by_type'].items()})
                 for bucket in result.get('districts') or []]
    return dict(result, districts=districts)


@router.get('/map/config')
def map_config():
    """쓸 수 있는 basemap과 한글 표기 여부. 지도 키 값은 담지 않는다."""
    return map_providers.config(rm._secret)


@router.get('/geocode/status')
def geocode_status(probe: bool = False):
    """지오코딩 provider 연결 상태. Client ID/Secret 값은 어떤 필드에도 담지 않는다.

    probe=false면 자격증명 유무만 보고 네트워크를 건드리지 않는다. probe=true면
    개발사업 데이터와 무관한 샘플 주소 한 건으로 연결과 좌표 축을 확인한다.
    유료 쿼터를 쓰므로 결과는 5분간 재사용한다.
    """
    if not probe:
        return _cached('geocode-status',
                       lambda: geocode.status(rm._secret), ttl=60)
    return _cached('geocode-status-probe',
                   lambda: geocode.status(rm._secret, geocode.requests_get,
                                          geocode.SAMPLE_ADDRESS), ttl=300)


@router.get('/geocode/canary')
def geocode_canary():
    """개발사업 10건만 실제 geocode해서 좌표 품질과 지도 표시 가능성을 본다.

    149건 전체 실행이 아니고, 데이터베이스에는 아무것도 쓰지 않는다. 유료 호출이라
    결과는 한 시간 재사용하고, 주소 캐시가 있으면 provider를 다시 부르지 않는다.
    """
    return _cached('geocode-canary',
                   lambda: development_canary.run(rm._secret, geocode.requests_get), ttl=3600)


@router.get('/geocode/bulk')
def geocode_bulk(offset: int = 0, size: int = bulk_geocode.DEFAULT_SLICE,
                 aggregate: bool = False):
    """주소가 확보된 개발사업을 slice 단위로 지오코딩한다. 데이터베이스에는 쓰지 않는다.

    한 번에 전부 호출하면 요청이 너무 길어지므로 slice로 나눈다. 같은 slice를 다시
    부르면 1시간 동안 같은 결과를 돌려주고, 주소 캐시가 있으면 provider를 부르지 않는다.
    aggregate=true는 provider를 아예 부르지 않고 캐시만 읽어 전체 보고서를 만든다.
    """
    if not 1 <= size <= bulk_geocode.MAX_SLICE:
        raise HTTPException(422, f'size는 1~{bulk_geocode.MAX_SLICE} 사이여야 합니다.')
    if offset < 0:
        raise HTTPException(422, 'offset은 0 이상이어야 합니다.')
    if aggregate:
        return _cached('geocode-bulk-aggregate',
                       lambda: bulk_geocode.run(rm._secret, geocode.requests_get,
                                                cache_only=True), ttl=60)
    return _cached(f'geocode-bulk:{offset}:{size}',
                   lambda: bulk_geocode.run(rm._secret, geocode.requests_get,
                                            offset=offset, size=size), ttl=3600)


@router.get('/development/map')
async def development_map(sigungu: str | None = None, limit: int = 200,
                          north: float | None = None, south: float | None = None,
                          east: float | None = None, west: float | None = None):
    if not 1 <= limit <= 500:
        raise HTTPException(422, 'limit은 1~500 사이여야 합니다.')
    corners = (north, south, east, west)
    if any(v is not None for v in corners) and not all(v is not None for v in corners):
        raise HTTPException(422, '지도 범위는 north·south·east·west를 함께 보내주세요.')
    bbox = None if north is None else {'north': north, 'south': south, 'east': east, 'west': west}
    try:
        result = await run_in_threadpool(development.map_projects, sigungu, limit, bbox)
    except ValueError:
        raise HTTPException(422, '지도 범위 값이 올바르지 않습니다.')
    points = [presentation.map_point(row) for row in result.get('projects') or []]
    return {'status': result['status'], 'reason': result['reason'], 'points': points,
            'total': len(points), 'mappable': sum(1 for p in points if p['mappable']),
            'bbox_filtered': result.get('bbox_filtered', False),
            'layers': presentation.MAP_LAYERS, 'legend': presentation.LOCATION_ACCURACY,
            'location_notice': presentation.NO_LOCATION_NOTICE}


@router.post('/development/nearby')
async def development_nearby(q: DevelopmentQuery):
    if q.longitude is None or q.latitude is None:
        raise HTTPException(422, '주변 개발사업을 찾으려면 좌표가 필요합니다.')
    result = await run_in_threadpool(development.search_projects, **q.model_dump())
    projects = [presentation.present_project(row) for row in result.get('nearby_projects') or []]
    return dict(result, projects=projects, total=len(projects),
                impact=presentation.impact({'projects': projects}, trade_has_point=True))


@router.post('/development/search')
async def development_search(q: DevelopmentQuery):
    if (q.longitude is None) != (q.latitude is None):
        raise HTTPException(422, '위도와 경도를 함께 입력해주세요.')
    if q.longitude is None and not q.sigungu:
        raise HTTPException(422, '좌표 또는 자치구를 입력해주세요.')
    result = await run_in_threadpool(development.search_projects, **q.model_dump())
    projects = [presentation.present_project(row) for row in result.get('nearby_projects') or []]
    return dict(result, projects=projects, total=len(projects),
                located=sum(1 for p in projects if p['has_location']),
                location_notice=presentation.NO_LOCATION_NOTICE)

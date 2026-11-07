"""부동산 모니터 API (services/realestate_monitor.py 래핑)."""

import asyncio
import copy
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from api.access import require_admin
from services import realestate_monitor as rm
from services import development
from services import development_presentation as presentation
from services import development_detail as detail
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
_key_locks = {}
_key_locks_guard = threading.Lock()
logger = logging.getLogger('ailab.realestate')


def _key_lock(key):
    with _key_locks_guard:
        lock = _key_locks.get(key)
        if lock is None:
            lock = _key_locks[key] = threading.Lock()
        return lock


def _cached(key, loader, ttl=600, store_if=None, copy_value=False, on_result=None):
    """청약 목록은 자주 바뀌지 않아 10분간 재사용한다. 지도 원자료도 같은 구조를 쓴다.

    같은 키의 MISS가 동시에 오면 키별 잠금으로 한 요청만 loader를 부르고, 나머지는 잠금이 풀린 뒤
    캐시를 다시 확인한다. 다른 키는 서로 기다리지 않는다. store_if가 False를 돌려주는 값(실패·잘림)은
    저장하지 않는다. copy_value=True면 깊은 복사본을 돌려줘 요청이 캐시 원본을 바꾸지 못하게 한다.
    on_result('HIT'|'MISS')로 측정 콜백을 받을 수 있다.
    """
    def fresh():
        hit = _cache.get(key)
        return hit if hit and time.monotonic() - hit[0] < ttl else None

    def out(value, outcome):
        if on_result:
            on_result(outcome)
        return copy.deepcopy(value) if copy_value else value

    hit = fresh()
    if hit:
        return out(hit[1], 'HIT')
    with _key_lock(key):   # 예외가 나도 with가 잠금을 푼다
        hit = fresh()
        if hit:
            return out(hit[1], 'HIT')
        value = loader()
        if store_if is None or store_if(value):
            _cache[key] = (time.monotonic(), value)
        return out(value, 'MISS')


MAP_CACHE_TTL = 300


def _map_cache_key(sigungu, limit, bbox):
    box = None if bbox is None else tuple(bbox[k] for k in ('north', 'south', 'east', 'west'))
    # include_completed는 키에 넣지 않는다. 같은 원자료에서 필터만 다르게 건다.
    return ('devmap', sigungu or 'ALL', limit, box)


def _map_rows_cacheable(result):
    return result.get('status') == 'ok' and not result.get('truncated')


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


# 모니터링 조건은 관리 기능이다. 화면에서 감추는 것만으로는 엔드포인트가 열려 있다.
# 기존 require_admin을 그대로 쓰고 새 인증체계는 만들지 않는다. 예약 모니터는 HTTP가
# 아니라 services.realestate_monitor를 직접 호출하므로 영향을 받지 않는다.
@router.get("/monitor", dependencies=[Depends(require_admin)])
def monitor():
    return {
        "auto_enabled": rm.get_auto_monitor_enabled(BASE_DIR),
        "usage": rm.estimate_monitor_api_calls(BASE_DIR),
        "rules": rm.get_alert_rules(BASE_DIR),
    }


class AutoToggle(BaseModel):
    enabled: bool


@router.put("/monitor/auto", dependencies=[Depends(require_admin)])
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


@router.post("/rules", dependencies=[Depends(require_admin)])
def add_rules(body: RuleInput):
    if "신규실거래" in body.event_types and not body.property_types:
        raise HTTPException(400, "신규실거래를 선택했다면 주택유형도 1개 이상 선택해주세요.")
    rm.save_alert_rules(BASE_DIR, body.regions, body.event_types, body.max_price_100m, body.min_area,
                        body.supply_types, body.property_types)
    return monitor()


@router.post("/rules/{rule_id}/toggle", dependencies=[Depends(require_admin)])
def toggle_rule(rule_id: int):
    rm.toggle_alert_rule(BASE_DIR, rule_id)
    return monitor()


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_admin)])
def delete_rule(rule_id: int):
    rm.delete_alert_rule(BASE_DIR, rule_id)
    return monitor()


@router.post("/monitor/run", dependencies=[Depends(require_admin)])
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


_response_locks = {}


def _response_lock(key):
    lock = _response_locks.get(key)
    if lock is None:
        lock = _response_locks[key] = asyncio.Lock()
    return lock


def _fresh(key, ttl):
    hit = _cache.get(key)
    return hit[1] if hit and time.monotonic() - hit[0] < ttl else None


@router.get('/development/map')
async def development_map_route(sigungu: str | None = None, limit: int = 500,
                                north: float | None = None, south: float | None = None,
                                east: float | None = None, west: float | None = None,
                                include_completed: bool = False):
    """지도 API. 서울 전체 응답은 직렬화된 본문까지 5분 캐시한다(가공·인코딩 반복 제거).

    캐시 키: 서울 전체 · limit · bbox · 완료사업 포함 여부. 실패·잘림 응답은 저장하지 않는다.
    원자료는 development_map 안에서 같은 TTL·키별 잠금으로 따로 캐시되므로, MISS여도 DB 재조회는 한 번뿐이다.
    """
    if sigungu is not None:
        return await development_map(sigungu, limit, north, south, east, west, include_completed)
    started = time.monotonic()
    box = None if north is None else (north, south, east, west)
    key = ('devmap-resp', limit, box, include_completed)
    body = _fresh(key, MAP_CACHE_TTL)
    outcome = 'HIT'
    if body is None:
        # 같은 키의 첫 요청이 동시에 몰려도 가공·직렬화는 한 번만 한다(나머지는 기다렸다가 캐시를 읽는다).
        async with _response_lock(key):
            body = _fresh(key, MAP_CACHE_TTL)
            if body is None:
                payload = await development_map(sigungu, limit, north, south, east, west, include_completed)
                body = await run_in_threadpool(lambda: json.dumps(
                    jsonable_encoder(payload), ensure_ascii=False, allow_nan=False,
                    separators=(',', ':')).encode('utf-8'))
                if payload.get('status') == 'ok' and not payload.get('truncated'):
                    # 응답 본문은 원자료보다 오래 살지 않는다. 원자료를 캐시한 시각으로 저장해 만료를 맞춘다.
                    raw = _cache.get(_map_cache_key(sigungu, limit, None if box is None else
                                                    dict(zip(('north', 'south', 'east', 'west'), box))))
                    _cache[key] = (raw[0] if raw else time.monotonic(), body)
                outcome = 'MISS'
    logger.info(json.dumps({'event': 'zipon_map_response', 'scope': 'ALL', 'cache': outcome,
                            'ms': round((time.monotonic() - started) * 1000, 1), 'bytes': len(body),
                            'include_completed': include_completed}))
    return Response(content=body, media_type='application/json')


async def development_map(sigungu: str | None = None, limit: int = 500,
                          north: float | None = None, south: float | None = None,
                          east: float | None = None, west: float | None = None,
                          include_completed: bool = False):
    """목록과 지도 마커의 공통 기준. 한 응답에서 둘을 같이 내려준다.

    화면이 자치구별 응답을 합쳐 '전체'를 만들면, 한 자치구가 실패했을 때 그 사업들이
    조용히 빠진 합계가 전체로 보인다. 그래서 여기서 한 번에 내려주고, 실패는
    status로만 알린다. 좌표가 없는 사업은 목록에는 남고 마커만 만들지 않는다.
    """
    if not 1 <= limit <= 500:
        raise HTTPException(422, 'limit은 1~500 사이여야 합니다.')
    corners = (north, south, east, west)
    if any(v is not None for v in corners) and not all(v is not None for v in corners):
        raise HTTPException(422, '지도 범위는 north·south·east·west를 함께 보내주세요.')
    bbox = None if north is None else {'north': north, 'south': south, 'east': east, 'west': west}
    started = time.monotonic()
    outcome = {'cache': 'BYPASS'}
    try:
        if sigungu is None:
            # 서울 전체(약 50회 DB 조회)만 원자료를 5분 캐시한다. 자치구 조회는 기존대로.
            result = await run_in_threadpool(
                _cached, _map_cache_key(sigungu, limit, bbox),
                lambda: development.map_projects(sigungu, limit, bbox), MAP_CACHE_TTL,
                _map_rows_cacheable, True, lambda o: outcome.update(cache=o))
        else:
            result = await run_in_threadpool(development.map_projects, sigungu, limit, bbox)
    except ValueError:
        raise HTTPException(422, '지도 범위 값이 올바르지 않습니다.')
    # 구조화된 성능 로그. 개인정보·키·접속정보는 넣지 않는다.
    logger.info(json.dumps({'event': 'zipon_map', 'scope': 'ALL' if sigungu is None else 'DISTRICT',
                            'cache': outcome['cache'],
                            'db_calls': 0 if outcome['cache'] == 'HIT' else result.get('db_calls'),
                            'ms': round((time.monotonic() - started) * 1000, 1),
                            'status': result.get('status'), 'truncated': bool(result.get('truncated')),
                            'include_completed': include_completed}))
    rows = result.get('projects') or []
    points = [presentation.map_point(row) for row in rows]
    projects = [presentation.present_project(row) for row in rows]
    all_projects = projects
    # 기본 지도는 앞으로 변화가 남은 사업만 그린다. 완료·취소는 [완료사업 보기]에서만.
    # 판정 근거가 없는 UNKNOWN은 숨기지 않는다. 확인 못 한 것을 끝난 것으로 다루지 않는다.
    by_id = {point['project_id']: point for point in points}
    hidden = [point for point in points if not point['in_default_map']]
    if not include_completed:
        points = [point for point in points if point['in_default_map']]
        projects = [row for row in projects if by_id.get(row['project_id'], {}).get('in_default_map', True)]
    mappable = sum(1 for point in points if point['mappable'])
    lifecycles = {}
    for point in by_id.values():
        lifecycles[point['lifecycle']] = lifecycles.get(point['lifecycle'], 0) + 1
    return {'status': result['status'], 'reason': result['reason'], 'points': points,
            'projects': projects, 'total': len(points), 'mappable': mappable,
            # 완료·취소로 가려진 사업까지 포함해 가장 최근 공식 확인일을 본다.
            # 가장 최근 한 건이 전체를 대표하지 않게 중앙값으로 판정하고, DB 반영은 건수로 적는다.
            'freshness': presentation.map_freshness(all_projects),
            # DB 반영일(갱신 작업이 실제로 쓴 날). 없으면 None — 화면은 '미기록'.
            'db_reflected_latest': max((p['data_dates']['db_reflected'] for p in all_projects
                                        if p['data_dates']['db_reflected']), default=None),
            'coordinateless': len(points) - mappable,
            'include_completed': include_completed,
            'lifecycle_counts': lifecycles,
            'hidden_completed': len(hidden),
            'lifecycle_labels': presentation.LIFECYCLE_LABELS,
            'default_lifecycles': list(presentation.DEFAULT_LIFECYCLES),
            'bbox_filtered': result.get('bbox_filtered', False),
            # limit에 닿은 응답은 더 있을 수 있다. 화면이 잘린 목록을 전체라고 말하지 않게 한다.
            'truncated': result.get('truncated', False),
            'layers': presentation.MAP_LAYERS, 'legend': presentation.LOCATION_ACCURACY,
            'location_notice': presentation.NO_LOCATION_NOTICE,
            # 검증된 경계가 없으므로 대표 좌표로 구역 내부를 판정하지 않는다.
            'inside_enabled': False}


@router.get('/development/projects/{project_id}')
async def development_project_detail(project_id: str):
    """개발사업 1건의 상세(읽기 전용). 면적·세대수·고시일·출처·이력·타임라인·연결 상태.

    DB·RPC를 바꾸지 않는다. 접근 범위는 /api/realestate 서비스 규칙(AccessMiddleware)을 그대로 따른다.
    """
    try:
        return await run_in_threadpool(detail.project_detail, project_id)
    except detail.DetailError as exc:
        raise HTTPException(exc.status, exc.message)


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


# ---------- 경기도 정비사업(경기데이터드림, 읽기 전용) ----------
# 서울 사업 경로·캐시와 분리한다. 키는 서버 환경변수 GYEONGGI_API_KEY로만 읽고 응답·오류에 담지 않는다.
from services import gyeonggi_projects as gg  # noqa: E402

GG_GEOCODE_CACHE = BASE_DIR / 'data/development/cache/geocode-gyeonggi'


def _gg_http_get(url, params=None, timeout=None):
    import requests
    return requests.get(url, params=params, timeout=timeout)


def _gg_coordinate_lookup():
    """관리자가 미리 검증해 둔 좌표만 읽는다(이 경로는 외부 지오코더를 부르지 않는다)."""
    def lookup(address):
        path = GG_GEOCODE_CACHE / (geocode.cache_key(address) + '.json')
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
    return lookup


def _gg_collect():
    records, meta = gg.collect(_gg_http_get, rm._secret)
    gg.attach_coordinates(records, _gg_coordinate_lookup())
    if not records and meta and all(m.get('code') == 'NOT_CONFIGURED' for m in meta.values()):
        raise HTTPException(503, '경기데이터드림 인증키가 서버에 설정되지 않았어요.')
    return records, meta


GG_TYPES = {'재개발': lambda p: p['type_label'] == '재개발', '재건축': lambda p: p['type_label'] == '재건축',
            '주거환경개선': lambda p: p['type_label'] == '주거환경개선',
            '소규모정비': lambda p: p.get('program_label') == '소규모주택정비'}


@router.get('/gyeonggi/projects')
async def gyeonggi_projects(sigun: str | None = None, dataset: str | None = None, q: str | None = None,
                            type: str | None = None, include_completed: bool = True,
                            mappable_only: bool = False, limit: int = 1000, offset: int = 0):
    """경기도 정비사업 목록. 서울 사업 화면과 같은 모양(DevelopmentProject)에 경기 원본 정보(gyeonggi)를 붙인다."""
    if sigun and sigun not in gg.GYEONGGI_SIGUN:
        raise HTTPException(400, '경기도 31개 시·군 이름으로 조회해 주세요.')
    if dataset and dataset not in gg.DATASETS:
        raise HTTPException(400, f'dataset은 {", ".join(gg.DATASETS)} 중 하나예요.')
    if type and type not in GG_TYPES:
        raise HTTPException(400, f'type은 {", ".join(GG_TYPES)} 중 하나예요.')
    limit, offset = max(1, min(limit, 2000)), max(0, offset)
    records, meta = await run_in_threadpool(_gg_collect)
    projects = [gg.to_project(r) for r in records
                if (not sigun or r['sigun'] == sigun) and (not dataset or r['source_dataset'] == dataset)
                and (include_completed or not r['completed']) and (not mappable_only or r['mappable'])]
    if type:
        projects = [p for p in projects if GG_TYPES[type](p)]
    if q and q.strip():
        needle = q.strip()
        projects = [p for p in projects if needle in ' '.join(filter(None, [p['name'], p['address'], p['district'], p['dong']]))]
    return {'status': 'OK' if all(m.get('status') == 'OK' for m in meta.values()) else 'PARTIAL',
            'total': len(projects), 'items': projects[offset:offset + limit],
            'completed': sum(1 for p in projects if p['completed']),
            'datasets': {k: {kk: vv for kk, vv in v.items() if kk != 'mapping'} for k, v in meta.items()},
            'notes': ['경기데이터드림 목록 자료예요. 판매 중인 매물이 아니에요.',
                      '면적·세대수·날짜는 원본 값 그대로이며 단위·형식은 확인되지 않았어요.',
                      '좌표는 검증된 주소만 표시하고, 정비구역 경계는 아직 연결하지 않았어요.']}


@router.get('/gyeonggi/projects/{project_id}')
async def gyeonggi_project_detail(project_id: str):
    """경기 사업 상세(서울 상세와 같은 모양). 실거래 연결 상태는 서울과 같은 규칙(connections_for)으로 계산한다."""
    if not project_id.startswith('gg-'):
        raise HTTPException(422, '경기 사업 번호 형식이 올바르지 않아요.')
    records, _ = await run_in_threadpool(_gg_collect)
    record = next((r for r in records if r['project_id'] == project_id), None)
    if record is None:
        raise HTTPException(404, '해당 경기 정비사업을 찾을 수 없어요.')
    connections = await run_in_threadpool(lambda: detail.connections_for(
        {'geometry_verified': False}, api_status=rm.get_api_status(),
        coordinate_provider=detail._coordinate_provider_configured()))
    return gg.detail_for(gg.to_project(record), connections)


@router.get('/gyeonggi/regions')
async def gyeonggi_regions():
    """경기도 31개 시·군별 사업 수·지도 표시 가능 수·검증 좌표 범위."""
    records, meta = await run_in_threadpool(_gg_collect)
    return {'regions': gg.region_summary(records), 'excluded': ['인천광역시'],
            'datasets': {k: {kk: vv for kk, vv in v.items() if kk != 'mapping'} for k, v in meta.items()}}


@router.get('/gyeonggi/quality', dependencies=[Depends(require_admin)])
async def gyeonggi_quality(include_raw: bool = False, limit: int = 20):
    """관리자용: 응답 필드·매핑 근거·결측·중복·시군 분포. 키 값은 포함하지 않는다."""
    records, meta = await run_in_threadpool(_gg_collect)
    report = gg.quality_report(records, meta)
    if include_raw:
        report['samples'] = [gg.public_record(r, include_raw=True) for r in records[:max(1, min(limit, 100))]]
        report['duplicate_samples'] = [gg.public_record(r, include_raw=True) for r in records if r['duplicate_of']][:max(1, min(limit, 100))]
    return report


@router.post('/gyeonggi/geocode', dependencies=[Depends(require_admin)])
async def gyeonggi_geocode(limit: int = 10, retry_failed: bool = False, dry_run: bool = False):
    """관리자용: 경기 주소를 지오코딩해 검증 규칙을 통과한 좌표만 지도에 쓴다(자동 실행 없음).

    - 원본 주소는 바꾸지 않고, 정리한 질의 주소(gg.geocode_target)로 provider를 부른다.
    - 성공 캐시는 그대로 쓰고, 실패 캐시는 주소 규칙 버전이 바뀌었거나 retry_failed=true일 때만 다시 시도한다.
    - dry_run=true는 provider를 부르지 않고 질의 주소·파싱 실패 사유·시도 예정 건수만 돌려준다.
    """
    def run():
        records, _ = gg.collect(_gg_http_get, rm._secret)
        addresses = list(dict.fromkeys(r['address'] for r in records if r['address']))
        lookup = _gg_coordinate_lookup()
        cap = max(1, min(limit, 500))
        todo = [a for a in addresses if gg.needs_geocode(lookup(a), retry_failed)]
        if dry_run:
            reasons, samples = {}, []
            for address in todo:
                target = gg.geocode_target(address)
                key = target['reason'] or 'QUERY_READY'
                reasons[key] = reasons.get(key, 0) + 1
                if len(samples) < 20:
                    samples.append({'address': address, 'query': target['query'], 'reason': target['reason']})
            return {'status': 'DRY_RUN', 'parser_version': gg.PARSER_VERSION, 'addresses': len(addresses),
                    'pending': len(todo), 'would_attempt': min(cap, sum(1 for a in todo if not gg.geocode_target(a)['reason'])),
                    'parse_results': reasons, 'samples': samples}
        selected = geocode.select_provider(rm._secret, geocode.requests_get)
        provider = selected['provider']
        if provider is None:
            return {'status': 'NO_PROVIDER', 'blocker': selected['blocker']}
        GG_GEOCODE_CACHE.mkdir(parents=True, exist_ok=True)
        done, verified, failed, parse_failed, reasons = 0, 0, 0, 0, {}
        for address in todo:
            if done >= cap:
                break
            target = gg.geocode_target(address)
            if target['reason']:
                # 질의를 만들 수 없는 주소는 provider를 부르지 않고 사유만 남긴다.
                result = gg.verify_coordinate(address, None)
                parse_failed += 1
            else:
                done += 1
                try:
                    result = gg.verify_coordinate(address, provider(target['query']))
                except Exception as exc:  # 망 오류는 캐시에 남기지 않고 다음 실행에서 다시 시도
                    failed += 1
                    logger.warning('gyeonggi geocode failed: %s', type(exc).__name__)
                    continue
                verified += bool(result.get('coordinate_verified'))
            key = result.get('reason') or 'VERIFIED'
            reasons[key] = reasons.get(key, 0) + 1
            entry = dict(result, address=address, status='VERIFIED' if result.get('coordinate_verified') else 'FAILED',
                         checked_at=datetime.now(timezone.utc).isoformat())
            (GG_GEOCODE_CACHE / (geocode.cache_key(address) + '.json')).write_text(
                json.dumps(entry, ensure_ascii=False), encoding='utf-8')
        return {'status': 'OK', 'provider': selected['name'], 'parser_version': gg.PARSER_VERSION, 'attempted': done,
                'verified': verified, 'network_failures': failed, 'unparseable': parse_failed, 'reasons': reasons,
                'pending_after': max(0, len(todo) - done - parse_failed - failed)}
    return await run_in_threadpool(run)

"""Read-only, bounded dashboard queries. Independent of the telemetry writer/core APIs."""
import asyncio
import json
import re
import time
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

from services.config import get_secret
from services.supabase_auth import supabase_headers

KST = ZoneInfo('Asia/Seoul')
PERIODS = {'today': 1, '7d': 7, '30d': 30}
PAGES = {
    '/': ('home', 'AI LAB 홈'), '/realestate': ('realestate', 'ZIP:ON'),
    '/golf': ('golf', 'Golf'), '/golf/club': ('golf', 'Golf · 골프장 상세'),
    '/dreamcar': ('dreamcar', '내차에서 드림카까지'), '/report': ('report', '보고서 작성기'),
    '/saju': ('saju', 'AI 사주 · 대운 분석'), '/car-selector': ('car-selector', '차량 선택기'),
    '/gif': ('gif', 'GIF 변환기'), '/other': ('other', '기타 페이지 (/other)'),
}
LABELS = {service: label for route, (service, label) in PAGES.items() if route != '/golf/club'}
FEATURE_LABELS = {'realestate': '부동산 검색', 'golf': '골프장 검색'}
FEATURE_ROUTES = {'/realestate', '/golf'}
HEADERS = {'Cache-Control': 'private, no-store', 'Vary': 'Authorization'}


class DashboardUnavailable(Exception):
    def __init__(self, code='unavailable'):
        self.code = code


async def read_json(url, key, params=None, limit=524288):
    """GET only: never writes, follows redirects, or retries. Limit response bytes too."""
    async with httpx.AsyncClient(timeout=2.0, follow_redirects=False,
                                 limits=httpx.Limits(max_connections=1)) as client:
        async with client.stream('GET', url, headers=supabase_headers(key), params=params) as response:
            if response.status_code == 404:
                raise DashboardUnavailable('setup_required')
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > limit:
                    raise DashboardUnavailable()
                body.extend(chunk)
            return json.loads(body)


class Totals(BaseModel):
    visits: int = Field(ge=0)
    page_views: int = Field(ge=0)
    features: int = Field(ge=0)
    external: int = Field(ge=0)
    errors: int = Field(ge=0)


class PageCounts(BaseModel):
    service: str = Field(max_length=64)
    route: str = Field(max_length=256)
    visits: int = Field(ge=0)
    page_views: int = Field(ge=0)
    features: int = Field(ge=0)


class ServiceCounts(Totals):
    service: str = Field(max_length=64)
    map_clicks: int = Field(ge=0)
    project_clicks: int = Field(ge=0)
    naver: int = Field(ge=0)
    used_sessions: int = Field(ge=0)
    funnel_entered: int = Field(ge=0)
    funnel_searched: int = Field(ge=0)
    funnel_engaged: int = Field(ge=0)
    funnel_external: int = Field(ge=0)


class DayCounts(BaseModel):
    day: date
    service: str = Field(max_length=64)
    visits: int = Field(ge=0)
    page_views: int = Field(ge=0)
    features: int = Field(ge=0)


class Activity(BaseModel):
    created_at: datetime
    service: str = Field(max_length=64)
    route: str = Field(max_length=256)
    event_type: str = Field(max_length=64)
    action: str | None = Field(default=None, max_length=64)


class RawSummary(BaseModel):
    status: Literal['ok']
    start_at: datetime
    end_at: datetime
    totals: Totals
    pages: list[PageCounts] = Field(max_length=1000)
    services: list[ServiceCounts] = Field(max_length=100)
    daily: list[DayCounts] = Field(max_length=3000)
    recent: list[Activity] = Field(max_length=20)


def safe_route(route):
    # Existing intake only accepts static routes. Future stored static routes get a safe fallback.
    if route in PAGES or re.fullmatch(r'/[a-z][a-z-]{0,39}', route):
        return route
    return '/other'


def feature_status(service):
    return 'COLLECTED' if service in FEATURE_LABELS else 'NOT_INSTRUMENTED'


def activity_label(row):
    if row.event_type == 'search':
        if row.service == 'realestate' and row.action in {'address_search', 'trade_search', 'subscription_search'}:
            return '부동산 검색'
        if row.service == 'golf' and row.action == 'golf_search':
            return '골프장 검색'
        return '기록된 활동'
    if row.event_type == 'external_link_click':
        if row.action == 'naver_land_click':
            return '네이버부동산 이동'
        if row.action == 'official_source_click':
            return '공식 자료 이동'
        return '외부 이동'
    return {'page_view': '페이지 방문', 'map_click': '지도에서 개발사업 확인',
            'project_click': '개발사업 상세 확인', 'api_error': '서비스 오류'}.get(row.event_type, '기록된 활동')


def present_summary(raw, period):
    """Strict output projection: no session id, raw metadata, request id or arbitrary labels."""
    summary = RawSummary.model_validate(raw)
    if summary.start_at.tzinfo is None or summary.end_at.tzinfo is None:
        raise ValueError('missing timezone')
    today = summary.end_at.astimezone(KST).date()
    start = today - timedelta(days=PERIODS[period] - 1)
    if summary.start_at.astimezone(KST).date() != start:
        raise ValueError('wrong period')
    pages = {route: {'route': route, 'service': sid, 'label': label,
                    'visits': 0, 'page_views': 0,
                    'features': 0 if route in FEATURE_ROUTES else None,
                    'feature_status': 'COLLECTED' if route in FEATURE_ROUTES else 'NOT_INSTRUMENTED'}
             for route, (sid, label) in PAGES.items()}
    for row in summary.pages:
        route = safe_route(row.route)
        target = pages.setdefault(route, {'route': route, 'service': 'other', 'label': route,
                                         'visits': 0, 'page_views': 0, 'features': None,
                                         'feature_status': 'NOT_INSTRUMENTED'})
        target['visits'] += row.visits
        target['page_views'] += row.page_views
        if route in FEATURE_ROUTES:
            target['features'] += row.features
    # Known services with no events are real zeroes; unsupported functionality is null.
    zero = {key: 0 for key in ServiceCounts.model_fields if key != 'service'}
    counts = {sid: ServiceCounts(service=sid, **zero) for sid in LABELS}
    for row in summary.services:
        if row.service in LABELS:
            counts[row.service] = row
    services = []
    for sid, row in counts.items():
        collected = sid in FEATURE_LABELS
        used = row.used_sessions if collected else None
        if row.used_sessions > row.visits:
            raise ValueError('inconsistent cohort')
        flow = [row.funnel_entered, row.funnel_searched, row.funnel_engaged, row.funnel_external]
        if collected and any(a < b for a, b in zip(flow, flow[1:])):
            raise ValueError('inconsistent funnel')
        services.append({
            'service': sid, 'label': LABELS[sid], 'visits': row.visits, 'page_views': row.page_views,
            'features': row.features if collected else None, 'feature_status': feature_status(sid),
            'feature_label': FEATURE_LABELS.get(sid, '핵심 기능'), 'used_sessions': used,
            'feature_rate': round(used / row.visits * 100, 1) if collected and row.visits else None,
            'external': row.external if sid == 'realestate' else None, 'errors': row.errors,
            'map_clicks': row.map_clicks if sid == 'realestate' else None,
            'project_clicks': row.project_clicks if sid == 'realestate' else None,
            'naver': row.naver if sid == 'realestate' else None,
            'session_funnel': flow if sid == 'realestate' else flow[:2] if sid == 'golf' else None,
        })
    daily = []
    by_day = {(row.day, row.service): row for row in summary.daily}
    for offset in range(PERIODS[period]):
        day = start + timedelta(days=offset)
        for sid in ('all', 'realestate', 'golf'):
            row = by_day.get((day, sid))
            daily.append({'day': day.isoformat(), 'service': sid,
                          **{name: getattr(row, name) if row else 0 for name in ('visits', 'page_views', 'features')}})
    recent = [{'at': row.created_at.isoformat(),
               'service_label': LABELS.get(row.service, safe_route(row.route)),
               'label': activity_label(row)} for row in summary.recent]
    return {'period': period, 'timezone': 'Asia/Seoul', 'start_at': summary.start_at.isoformat(),
            'end_at': summary.end_at.isoformat(), 'totals': summary.totals.model_dump(),
            'pages': sorted(pages.values(), key=lambda row: (-row['page_views'], row['route'])),
            'services': services, 'daily': daily, 'recent': recent}


class DashboardReader:
    def __init__(self):
        self.cache = {}  # Exactly three allowed periods.
        self.lock = asyncio.Lock()
        self.failed_until = 0.0
        self.failure = 'unavailable'

    async def get(self, period):
        if period not in PERIODS:
            raise ValueError('period')
        today = datetime.now(KST).date()
        hit = self.cache.get(period)
        if hit and time.monotonic() - hit[0] < 30 and hit[1] == today:
            return hit[2]
        if time.monotonic() < self.failed_until:
            raise DashboardUnavailable(self.failure)
        if self.lock.locked():
            raise DashboardUnavailable('busy')
        async with self.lock:
            try:
                dedicated = get_secret('ANALYTICS_SUPABASE_URL')
                url = dedicated or get_secret('SUPABASE_URL')
                key = get_secret('ANALYTICS_SUPABASE_SERVICE_ROLE_KEY' if dedicated else 'SUPABASE_SERVICE_ROLE_KEY')
                if not url or not key:
                    raise DashboardUnavailable('setup_required')
                raw = await asyncio.wait_for(read_json(url.rstrip('/') + '/rest/v1/rpc/usage_dashboard',
                                                       key, {'p_days': PERIODS[period]}), timeout=2.5)
                if isinstance(raw, dict) and raw.get('status') == 'too_many_events':
                    raise DashboardUnavailable('range_too_large')
                data = present_summary(raw, period)
                self.cache[period] = (time.monotonic(), today, data)
                return data
            except Exception as error:
                self.failure = error.code if isinstance(error, DashboardUnavailable) else 'unavailable'
                self.failed_until = time.monotonic() + 5
                raise DashboardUnavailable(self.failure) from None


reader = DashboardReader()

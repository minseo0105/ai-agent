"""Public write-only telemetry with finite payloads and no arbitrary metadata."""
import asyncio
import json
import re
import time
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from services.usage_events import collector

router = APIRouter()
ROUTES = {'/': 'home', '/realestate': 'realestate', '/golf': 'golf',
          '/golf/club': 'golf', '/dreamcar': 'dreamcar', '/report': 'report',
          '/saju': 'saju', '/car-selector': 'car-selector', '/gif': 'gif', '/other': 'other'}
DETAILS = {'page_view': set(), 'search': {'address_search', 'golf_search', 'trade_search', 'subscription_search'},
           'project_click': set(), 'map_click': set(),
           'external_link_click': {'naver_land_click', 'official_source_click'}}


class Event(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    session_id: str = Field(pattern=r'^[0-9a-f-]{36}$')
    service: str
    route: str
    event_type: Literal['page_view', 'search', 'project_click', 'map_click', 'external_link_click']
    metadata: dict[str, str] = Field(default_factory=dict, max_length=1)

    @model_validator(mode='after')
    def safe_values(self):
        identifier = UUID(self.session_id)
        if identifier.version != 4 or str(identifier) != self.session_id:
            raise ValueError('session')
        if ROUTES.get(self.route) != self.service:
            raise ValueError('route')
        if self.metadata and (set(self.metadata) != {'action'} or self.metadata['action'] not in DETAILS[self.event_type]):
            raise ValueError('metadata')
        return self


class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    events: list[Event] = Field(min_length=1, max_length=20)


class Budget:
    """Process-wide cap; no IP/session maps that can grow indefinitely."""
    def __init__(self):
        self.tokens = 120.0
        self.updated = time.monotonic()

    def take(self, count=1):
        now = time.monotonic()
        self.tokens = min(120, self.tokens + (now - self.updated) * 30)
        self.updated = now
        if self.tokens < count:
            return False
        self.tokens -= count
        return True


budget = Budget()


@router.post('/api/analytics/events', status_code=204)
async def events(request: Request):
    if not budget.take():
        return Response(status_code=204)
    try:
        async def read():
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16384:
                    raise ValueError('size')
            return body
        body = await asyncio.wait_for(read(), 1.0)
        batch = Batch.model_validate(json.loads(body))
    except (ValueError, ValidationError, asyncio.TimeoutError):
        return Response(status_code=400)
    except Exception:
        return Response(status_code=204)
    if budget.take(len(batch.events)):
        try:
            for event in batch.events:
                collector.offer(event.model_dump())
        except Exception:
            pass
    return Response(status_code=204)


class UsageErrorsMiddleware:
    """Observe completed service error responses, without reading body/headers/queries."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        parts = scope.get('path', '').split('/')
        service = parts[2] if len(parts) > 2 and parts[1] == 'api' else ''
        if service == 'chat' or service == 'agent':
            service = 'home'
        if service not in set(ROUTES.values()) - {'other'}:
            return await self.app(scope, receive, send)
        status, identifier, recorded = 200, None, False
        async def observed(message):
            nonlocal status, identifier, recorded
            if message['type'] == 'http.response.start':
                status = message['status']
                # Caller-supplied request ids may contain personal data; never store them.
                if not any(k.lower() == b'x-request-id' for k, _ in scope.get('headers', [])):
                    candidate = dict(message.get('headers', [])).get(b'x-request-id', b'').decode('ascii', errors='ignore')
                    if re.fullmatch(r'[0-9a-f]{16}', candidate):
                        identifier = candidate
            await send(message)
            if message['type'] == 'http.response.body' and not message.get('more_body') and not recorded and status >= 400:
                recorded = True
                try:
                    if not budget.take():
                        return
                    collector.offer({'session_id': None, 'service': service,
                                     'route': '/api/' + service, 'event_type': 'api_error',
                                     'metadata': {'status': status}, 'request_id': identifier})
                except Exception:
                    pass
        await self.app(scope, receive, observed)

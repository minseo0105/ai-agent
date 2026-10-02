"""Admin usage metrics: compatible admin tokens, read-only auth and aggregate-only output."""
import asyncio
import hashlib
import hmac
import json
import math
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from services import access
from services.config import get_secret
from services.usage_dashboard import HEADERS, DashboardUnavailable, read_json, reader

router = APIRouter()
_key = None
_key_at = 0.0
_key_lock = asyncio.Lock()


async def readonly_signing_key():
    """Do not call _secret_key(): it creates a DB/file secret if missing."""
    global _key, _key_at
    if os.environ.get('ACCESS_SECRET'):
        return os.environ['ACCESS_SECRET'].encode()
    if access._secret_cache['value']:
        return access._secret_cache['value']
    if _key and time.monotonic() - _key_at < 60:
        return _key
    if _key_lock.locked():
        raise DashboardUnavailable('busy')
    async with _key_lock:
        url, credential = get_secret('SUPABASE_URL'), get_secret('SUPABASE_SERVICE_ROLE_KEY')
        if url and credential:
            rows = await asyncio.wait_for(read_json(url.rstrip('/') + '/rest/v1/app_settings', credential,
                {'key': 'eq.access_secret', 'select': 'value', 'limit': 1}, limit=8192), timeout=2.5)
            value = rows[0]['value'] if isinstance(rows, list) and rows else None
            value = value.encode() if isinstance(value, str) else None
        else:
            value = access.SECRET_PATH.read_bytes().strip() if access.SECRET_PATH.is_file() else None
        if not value:
            raise DashboardUnavailable()
        _key, _key_at = value, time.monotonic()
        return value


async def require_usage_admin(request: Request):
    unauthorized = HTTPException(401, '관리자 로그인이 필요해요.', headers=HEADERS)
    auth = request.headers.get('authorization', '')
    if not auth.lower().startswith('bearer ') or len(auth) > 2048:
        raise unauthorized
    try:
        body, signature = auth[7:].strip().split('.', 1)
        payload = json.loads(access._unb64(body))
        expiry = payload.get('exp')
        if payload.get('r') != 'admin' or not isinstance(expiry, (int, float)) or not math.isfinite(expiry) or expiry <= time.time():
            raise ValueError('token')
    except Exception:
        raise unauthorized from None
    try:
        key = await readonly_signing_key()
        expected = access._b64(hmac.new(key, body.encode(), hashlib.sha256).digest())
        valid = hmac.compare_digest(signature.encode(), expected.encode())
    except Exception:
        raise HTTPException(503, '관리자 인증을 확인할 수 없어요. 잠시 후 다시 시도해 주세요.', headers=HEADERS) from None
    if not valid:
        raise unauthorized


@router.get('/api/admin/usage', dependencies=[Depends(require_usage_admin)])
async def usage(response: Response, period: Literal['today', '7d', '30d'] = 'today'):
    response.headers.update(HEADERS)
    try:
        return await reader.get(period)
    except DashboardUnavailable as error:
        messages = {'setup_required': '운영현황 집계가 아직 준비되지 않았어요.',
                    'range_too_large': '조회량이 많아요. 더 짧은 기간을 선택해 주세요.',
                    'busy': '다른 조회가 진행 중이에요. 잠시 후 다시 확인해 주세요.'}
        raise HTTPException(503, {'code': error.code,
                            'message': messages.get(error.code, '운영현황을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.')},
                            headers=HEADERS) from None

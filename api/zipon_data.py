"""Authenticated, read-only ZIP data operations dashboard."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response

from api.usage_dashboard import require_usage_admin
from services.config import get_secret
from services.usage_dashboard import read_json, HEADERS

router=APIRouter()


@router.get('/api/admin/zipon-data',dependencies=[Depends(require_usage_admin)])
async def zipon_data(response:Response):
    response.headers.update(HEADERS)
    url=get_secret('ZIPON_SUPABASE_URL',section='realestate').rstrip('/')
    key=get_secret('ZIPON_SUPABASE_SERVICE_ROLE_KEY',section='realestate')
    if not url or not key:
        raise HTTPException(503,{'code':'CONFIG_REQUIRED','message':'ZIP 데이터 연결 설정이 필요해요.'},headers=HEADERS)
    try:
        data=await asyncio.wait_for(read_json(url+'/rest/v1/rpc/zipon_refresh_dashboard',key,limit=1048576),timeout=5)
        # No arbitrary error messages or raw snapshots leave the server.
        if not isinstance(data,dict):
            raise ValueError()
        return data
    except Exception:
        raise HTTPException(503,{'code':'DB_MIGRATION_REQUIRED','message':'데이터 운영현황을 조회할 수 없어요. 연결과 SQL 설치 상태를 확인해 주세요.'},headers=HEADERS) from None

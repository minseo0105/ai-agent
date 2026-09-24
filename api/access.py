"""공개 범위 · 관리자 설정 API + 서비스 API 접근 제어 미들웨어."""

import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services import access as ac

router = APIRouter(tags=["access"])


def _token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else None


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _raise(e: ac.AccessError):
    raise HTTPException(e.status, {"code": e.code, "message": e.message})


def require_admin(request: Request):
    who = ac.identify(_token(request))
    if not who or who["role"] != "admin":
        raise HTTPException(401, {"code": "admin_required", "message": "관리자 로그인이 필요해요."})
    return who


# ---------------------------------------------------------
# 방문자
# ---------------------------------------------------------

@router.get("/api/access/status")
def status(request: Request):
    return ac.status(_token(request))


class CodeLogin(BaseModel):
    code: str = Field(min_length=4, max_length=20)


@router.post("/api/access/login")
def login(req: CodeLogin, request: Request):
    try:
        return ac.member_login(req.code, _client(request))
    except ac.AccessError as e:
        _raise(e)


# ---------------------------------------------------------
# 관리자
# ---------------------------------------------------------

class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.get("/api/admin/info")
def admin_info():
    return {"configured": ac.admin_configured()}


@router.post("/api/admin/login")
def admin_login(req: AdminLogin, request: Request):
    try:
        return ac.admin_login(req.password, _client(request))
    except ac.AccessError as e:
        _raise(e)


@router.get("/api/admin/settings", dependencies=[Depends(require_admin)])
def get_settings():
    return ac.admin_view()


class Notice(BaseModel):
    enabled: bool = False
    text: str = Field(default="", max_length=300)


class SettingsUpdate(BaseModel):
    site_mode: Literal["public", "members", "closed"]
    notice: Notice
    services: dict[str, Literal["inherit", "public", "members", "hidden"]]
    member_token_days: int = Field(ge=1, le=365)


@router.put("/api/admin/settings", dependencies=[Depends(require_admin)])
def put_settings(req: SettingsUpdate):
    try:
        return ac.update_settings(req.site_mode, req.notice.model_dump(), req.services, req.member_token_days)
    except ac.AccessError as e:
        _raise(e)


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=100)


class MemberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=40)
    note: Optional[str] = Field(default=None, max_length=100)
    active: Optional[bool] = None


@router.post("/api/admin/members", dependencies=[Depends(require_admin)])
def create_member(req: MemberCreate):
    try:
        return ac.add_member(req.name, req.note)
    except ac.AccessError as e:
        _raise(e)


@router.patch("/api/admin/members/{member_id}", dependencies=[Depends(require_admin)])
def patch_member(member_id: str, req: MemberUpdate):
    try:
        return ac.update_member(member_id, req.name, req.note, req.active)
    except ac.AccessError as e:
        _raise(e)


@router.post("/api/admin/members/{member_id}/reissue", dependencies=[Depends(require_admin)])
def reissue(member_id: str):
    try:
        return ac.reissue_code(member_id)
    except ac.AccessError as e:
        _raise(e)


@router.delete("/api/admin/members/{member_id}", dependencies=[Depends(require_admin)])
def remove_member(member_id: str):
    try:
        ac.delete_member(member_id)
        return {"ok": True}
    except ac.AccessError as e:
        _raise(e)


# ---------------------------------------------------------
# 서비스 API 접근 제어 (순수 ASGI: SSE 스트리밍을 버퍼링하지 않는다)
# ---------------------------------------------------------

class AccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        token = None
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                value = v.decode("latin-1")
                if value.lower().startswith("bearer "):
                    token = value[7:].strip()
        try:
            ac.check_api(scope["path"], token)
        except ac.AccessError as e:
            body = json.dumps({"detail": {"code": e.code, "message": e.message}}, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": e.status,
                        "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)

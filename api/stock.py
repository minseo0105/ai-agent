"""STOCK:ON API. 공개 범위는 AccessMiddleware(서비스 id 'stockon', 관리자 '서비스별 공개')가 적용한다.

- 방문자 API(overview · why)는 저장된 스냅샷만 읽는다. 외부 API·LLM을 부르지 않는다.
- 생활 속 종목 찾기(/api/stock/lifemap*)도 저장된 것만 읽는다. 단 새 단어 요청(POST .../word)만은
  대기열(동시 3·대기 12·1인 10분 3개·하루 150개)을 거쳐 AI를 부른다. 같은 단어는 한 번 그린 것을 모두 재사용.
- 관리 API(/api/stock/admin/*)는 공개 범위와 관계없이 관리자 토큰이 있어야 한다.
조회 전용이다. 개인 계좌·잔고·주문 API는 없다.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.access import require_admin
from services.stockon import lifemap, service

router = APIRouter(tags=["stock"])


def _enabled():
    if not service.enabled():
        raise HTTPException(404, "STOCK:ON은 오라클 서버에서 제공합니다.")


@router.get("/api/stock/overview")
def overview():
    return service.overview()


@router.get("/api/stock/why/{code}", dependencies=[Depends(_enabled)])
def why(code: str):
    if not code.isalnum() or len(code) > 12:
        raise HTTPException(400, "종목 코드가 올바르지 않아요.")
    try:
        return service.why(code)
    except KeyError:
        raise HTTPException(404, "기준일 시세에 없는 종목이에요.")


# ---------------------------------------------------------
# 생활 속 종목 찾기
# ---------------------------------------------------------

class LifeWord(BaseModel):
    word: str = Field(min_length=1, max_length=20)


def _session(request: Request) -> str:
    """1인 횟수 제한용. 브라우저가 만든 무작위 ID(X-Stockon-Session), 없으면 접속 IP.
    강의장 Wi-Fi는 여러 명이 같은 IP일 수 있어서 ID를 먼저 쓴다."""
    sid = (request.headers.get("x-stockon-session") or "").strip()
    if sid.replace("-", "").isalnum() and 8 <= len(sid) <= 64:
        return "s:" + sid
    return "ip:" + (request.client.host if request.client else "")


@router.get("/api/stock/lifemap", dependencies=[Depends(_enabled)])
def life_overview():
    return lifemap.overview()


@router.post("/api/stock/lifemap/word", dependencies=[Depends(_enabled)])
def life_word(req: LifeWord, request: Request):
    return lifemap.request_word(req.word, _session(request))


@router.get("/api/stock/lifemap/word", dependencies=[Depends(_enabled)])
def life_word_status(w: str = ""):
    return lifemap.word_status(w[:20])


# ---------------------------------------------------------
# 관리자
# ---------------------------------------------------------

class Watchlist(BaseModel):
    codes: list[str] = Field(max_length=30)


class Refresh(BaseModel):
    tasks: list[Literal["market", "fx", "news", "watch", "briefing", "why"]] = Field(min_length=1, max_length=6)


@router.get("/api/stock/admin/status", dependencies=[Depends(require_admin)])
def admin_status():
    return service.admin_status()


@router.get("/api/stock/admin/search", dependencies=[Depends(require_admin)])
def admin_search(q: str = ""):
    return {"items": service.search_stocks(q[:40])}


@router.put("/api/stock/admin/watchlist", dependencies=[Depends(require_admin), Depends(_enabled)])
def admin_watchlist(req: Watchlist):
    try:
        return service.save_watchlist([c.strip() for c in req.codes if c.strip()])
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/stock/admin/refresh", dependencies=[Depends(require_admin), Depends(_enabled)])
def admin_refresh(req: Refresh):
    started = service.refresh_in_background(list(req.tasks))
    return {"started": started, "refreshing": service.refreshing()}

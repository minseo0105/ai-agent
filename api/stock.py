"""STOCK:ON API. 공개 범위는 AccessMiddleware(서비스 id 'stockon', 관리자 '서비스별 공개')가 적용한다.

- 방문자 API(overview · why · live)는 저장된 스냅샷만 읽는다. 외부 API·LLM을 부르지 않는다.
  live = '오늘 시장' 실시간 장중 동향(수집기가 키움 웹소켓·REST로 쓴 파일만, 2초 캐시). 화면이 15초마다 부른다.
- 뉴스 속 숨은 종목(/api/stock/lifemap*)도 저장된 것만 읽는다(토픽·섹터 = 기사 + AI 해석 + 회사 지도 + 실제 등락).
  단 직접 입력(POST .../word)만은 대기열(동시 10·대기 30·1인 10분 3개·하루 평소 50개, 시연 주간 11/14~11/17 400개)을 거쳐 뉴스 검색 1회와 AI를 부른다.
  같은 단어는 한 번 만든 것을 모두 재사용. 응답의 item = {name, title, summary, sector, articles, map}.
- 관리 API(/api/stock/admin/*)는 공개 범위와 관계없이 관리자 토큰이 있어야 한다.
조회 전용이다. 개인 계좌·잔고·주문 API는 없다.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.access import require_admin
from services.stockon import lifemap, live, service

router = APIRouter(tags=["stock"])


def _enabled():
    if not service.enabled():
        raise HTTPException(404, "STOCK:ON은 오라클 서버에서 제공합니다.")


@router.get("/api/stock/overview")
def overview():
    return service.overview()


@router.get("/api/stock/live", dependencies=[Depends(_enabled)])
def live_view():
    return live.view()


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


# 뉴스 속 숨은 종목 시연 안전장치: 이슈 숨기기·순서·제외 키워드·금융 사고 이슈 첫 카드 제외
class LifeCuration(BaseModel):
    action: Literal["hide", "show", "order", "words", "fin_first"]
    key: str = Field("", max_length=600)
    keys: list[str] = Field(default_factory=list, max_length=10)
    words: list[str] = Field(default_factory=list, max_length=50)
    on: bool = True


@router.get("/api/stock/admin/lifemap", dependencies=[Depends(require_admin)])
def admin_lifemap():
    return lifemap.admin_curation()


@router.post("/api/stock/admin/lifemap", dependencies=[Depends(require_admin)])
def admin_lifemap_set(req: LifeCuration):
    try:
        if req.action in ("hide", "show"):
            return lifemap.set_hidden(req.key, req.action == "hide")
        if req.action == "order":
            return lifemap.set_order(req.keys)
        if req.action == "words":
            return lifemap.set_words([w[:20] for w in req.words])
        return lifemap.set_fin_first(req.on)
    except KeyError:
        raise HTTPException(404, "지금 후보에 없는 이슈예요. 새로고침해 주세요.")

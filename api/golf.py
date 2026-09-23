"""골프장 추천 API."""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from services import golf_service as gs

router = APIRouter(prefix="/api/golf", tags=["golf"])

Sort = Literal["추천순", "가까운순", "가격순"]


class ConditionParams(BaseModel):
    departure: str = Field("", max_length=80)
    day: Literal["주중", "주말"] = "주중"
    round_date: Optional[str] = None  # 구버전 호환용. 화면에서는 day를 사용한다.
    session: Optional[Literal["1부", "2부", "3부"]] = "2부"
    budget: str = "전체"
    caddie: Literal["전체", "캐디", "노캐디"] = "전체"
    areas: list[str] = Field(default_factory=list, max_length=3)
    subregions: list[str] = Field(default_factory=list, max_length=4)
    players: Literal["전체", "3인", "4인"] = "전체"
    night: bool = False
    avg_score_label: str = "미선택"
    challenge: Literal["편하게", "적당히", "도전"] = "적당히"


class ConditionSearch(BaseModel):
    params: ConditionParams
    sort: Sort = "추천순"


class TextSearch(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    sort: Sort = "추천순"


class DetailRequest(BaseModel):
    """직전 검색 조건. 요금·경로 계산에 사용한다. 둘 다 없으면 기본값."""
    params: Optional[ConditionParams] = None
    text: Optional[str] = Field(None, max_length=300)


@router.get("/options")
def options():
    return gs.search_options()


@router.get("/find")
def find(q: str):
    return {"items": gs.find_by_name(q.strip())} if q.strip() else {"items": []}


@router.post("/search")
async def search(req: ConditionSearch):
    return await run_in_threadpool(gs.condition_search, req.params.model_dump(), req.sort)


@router.post("/search/text")
async def search_text(req: TextSearch):
    return await run_in_threadpool(gs.ai_search, req.text, req.sort)


@router.post("/clubs/{club_id}")
async def club_detail(club_id: str, req: DetailRequest):
    search = {"text": req.text} if req.text else ({"params": req.params.model_dump()} if req.params else None)
    detail = await run_in_threadpool(gs.club_detail, club_id, search)
    if detail is None:
        raise HTTPException(404, "골프장을 찾을 수 없습니다.")
    return detail


@router.post("/clubs/{club_id}/reviews/refresh")
async def refresh_reviews(club_id: str):
    try:
        block = await run_in_threadpool(gs.refresh_reviews, club_id)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"후기 분석 중 오류: {e}")
    if block is None:
        raise HTTPException(404, "골프장을 찾을 수 없습니다.")
    return block

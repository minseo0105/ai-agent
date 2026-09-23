"""내 차에서 드림카까지 API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import dreamcar as dc

router = APIRouter(prefix="/api/dreamcar", tags=["dreamcar"])


@router.get("/config")
def config():
    return {"questions": dc.public_questions(), "apr": dc.DEMO_APR, "terms": dc.TERMS,
            "deposit_rates": dc.DEPOSIT_RATES}


class PlateRequest(BaseModel):
    plate: str = Field(max_length=20)


@router.post("/lookup")
def lookup(req: PlateRequest):
    car = dc.lookup_car(req.plate)
    if car is None:
        raise HTTPException(400, "차량 번호 형식을 확인해주세요. 예: 123가4567")
    return car


class RecommendRequest(BaseModel):
    answers: list[int] = Field(min_length=1, max_length=10)


@router.post("/recommend")
def recommend(req: RecommendRequest):
    try:
        return dc.recommend(req.answers)
    except ValueError as e:
        raise HTTPException(400, str(e))

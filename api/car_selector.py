"""차량 선택기 API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import car_selector as cs

router = APIRouter(prefix="/api/car-selector", tags=["car-selector"])


@router.get("/questions")
def questions():
    return {"questions": cs.public_questions()}


class RecommendRequest(BaseModel):
    answers: list[int] = Field(min_length=3, max_length=3)


@router.post("/recommend")
def recommend(req: RecommendRequest):
    try:
        return cs.recommend(req.answers)
    except ValueError as e:
        raise HTTPException(400, str(e))

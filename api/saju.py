"""AI 사주 · 대운 분석 API."""

import json
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import saju as sj

router = APIRouter(prefix="/api/saju", tags=["saju"])


class BirthInput(BaseModel):
    birth: str = Field(pattern=r"^\d{4}-\d{1,2}-\d{1,2}$")
    calendar_type: Literal["양력", "음력"] = "양력"
    time_text: str = Field(default="모름", max_length=5)
    gender: Literal["여성", "남성"] = "여성"
    lunar_leap: bool = False


class AiRequest(BirthInput):
    kind: Literal["full", "cycle", "year", "question"] = "full"
    cycle_index: Optional[int] = Field(default=None, ge=0, le=20)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    topic: Optional[str] = Field(default=None, max_length=20)
    question: Optional[str] = Field(default=None, max_length=1000)


@router.get("/options")
def options():
    return {"genders": sj.GENDERS, "calendars": sj.CALENDARS, "times": sj.make_time_options(),
            "topics": sj.AI_TOPICS, "available": sj.LUNAR_AVAILABLE}


@router.post("/analyze")
def analyze(req: BirthInput):
    try:
        return sj.analyze(req.birth, req.calendar_type, req.time_text, req.gender, req.lunar_leap)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.post("/ai")
def ai(req: AiRequest):
    """SSE: event delta(본문 조각)* → end{truncated} 또는 error → done"""
    try:
        prompt = sj.build_prompt(req.kind, req.birth, req.calendar_type, req.time_text, req.gender, req.lunar_leap,
                                 cycle_index=req.cycle_index, year=req.year, topic=req.topic, question=req.question)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    def stream():
        for event in sj.stream_ai(prompt):
            kind = event.pop("type")
            yield f"event: {kind}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

"""경영진 보고서 작성기 API."""

import json
from typing import Literal, Optional

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from services import report as rp

router = APIRouter(prefix="/api/report", tags=["report"])


@router.get("/options")
def options():
    return {"styles": rp.REPORT_STYLES, "depths": rp.REPORT_DEPTHS, "modes": rp.RESEARCH_MODES,
            "style_help": rp.STYLE_HELP, "depth_help": rp.DEPTH_HELP}


class ReportRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=6000)
    style: Literal["CEO/임원 보고", "전략 검토", "이슈·리스크 보고", "시장·경쟁 분석", "규제·법률 검토", "사업/투자 검토"] = "CEO/임원 보고"
    depth: Literal["핵심 중심", "표준", "상세"] = "표준"
    mode: Literal["빠른 작성", "최신자료 포함"] = "빠른 작성"


@router.post("/generate")
def generate(req: ReportRequest):
    """SSE: event tool(도구 호출 진행) → answer(보고서) 또는 error → done"""
    def stream():
        for event in rp.run_report(req.topic, req.style, req.depth, req.mode):
            kind = event.pop("type")
            yield f"event: {kind}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Chart(BaseModel):
    company: Optional[str] = None
    dates: list[str] = Field(default_factory=list, max_length=500)


class PdfRequest(BaseModel):
    text: str = Field(min_length=1, max_length=40000)
    chart: Optional[Chart] = None


@router.post("/pdf")
async def pdf(req: PdfRequest):
    data = await run_in_threadpool(rp.report_pdf, req.text, req.chart.model_dump() if req.chart else None)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="executive_report.pdf"'})

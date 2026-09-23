"""AI Lab 백엔드 (FastAPI).

실행:  venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000
문서:  http://localhost:8000/docs
"""

import json
import os
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.golf import router as golf_router
from api.realestate import router as realestate_router
from api.report import router as report_router
from services.agent import PROVIDERS, SEARCH_MODES, run_agent
from services.config import get_secret

app = FastAPI(title="AI Lab API", version="0.1.0")
app.include_router(golf_router)
app.include_router(realestate_router)
app.include_router(report_router)

# 프론트엔드 주소. 배포 시 FRONTEND_ORIGINS="https://my-site.vercel.app" 처럼 쉼표로 지정
_origins = os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    provider: Literal["claude", "gpt"] = "claude"
    search_mode: Literal["빠르게", "심층 검색"] = "빠르게"


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "providers": {
            "claude": bool(get_secret("ANTHROPIC_API_KEY")),
            "gpt": bool(get_secret("OPENAI_API_KEY")),
        },
    }


@app.get("/api/agent/options")
def agent_options():
    return {
        "providers": [{"id": k, "label": v} for k, v in PROVIDERS.items()],
        "search_modes": list(SEARCH_MODES),
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    """Server-Sent Events로 진행 상황과 최종 답변을 보낸다.

    event: tool    data: {"name", "label", "input"}
    event: answer  data: {"text", "provider", "search_mode"}
    event: done    data: {}
    """
    messages = [m.model_dump() for m in req.messages]

    def stream():
        for event in run_agent(messages, req.provider, req.search_mode):
            kind = event.pop("type")
            if kind == "answer":
                event.update(provider=req.provider, search_mode=req.search_mode)
            yield f"event: {kind}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

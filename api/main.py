"""AI Lab 백엔드 (FastAPI).

실행:  venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000
문서:  http://localhost:8000/docs
"""

import json
import mimetypes
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.access import AccessMiddleware
from api.access import router as access_router
from api.car_selector import router as car_selector_router
from api.dreamcar import router as dreamcar_router
from api.gif import router as gif_router
from api.golf import router as golf_router
from api.realestate import router as realestate_router
from api.report import router as report_router
from api.saju import router as saju_router
from services import car_selector
from services.agent import PROVIDERS, SEARCH_MODES, run_agent
from services.config import get_secret
from services.dreamcar import ASSET_DIR, IMAGE_DIR

app = FastAPI(title="AI Lab API", version="0.1.0")
app.include_router(golf_router)
app.include_router(realestate_router)
app.include_router(report_router)
app.include_router(dreamcar_router)
app.include_router(saju_router)
app.include_router(car_selector_router)
app.include_router(gif_router)
app.include_router(access_router)

# 드림카·차량 선택기 이미지 · 라이프스타일/페르소나 애니메이션 (base64 인라인 대신 파일로 서빙)
# Windows 레지스트리에는 webp 매핑이 없어 octet-stream으로 나가므로 직접 등록
mimetypes.init()  # 레지스트리를 먼저 읽어 둬야 아래 등록이 나중에 덮어써지지 않는다
mimetypes.add_type("image/webp", ".webp")
app.mount("/media/cars", StaticFiles(directory=IMAGE_DIR), name="car-images")
app.mount("/media/dreamcar", StaticFiles(directory=ASSET_DIR), name="dreamcar-assets")
app.mount(car_selector.CUTOUT_MEDIA, StaticFiles(directory=car_selector.IMAGE_DIR), name="car-cutout")
app.mount(car_selector.REAL_MEDIA, StaticFiles(directory=car_selector.FALLBACK_DIR), name="car-real")

# 프론트엔드 주소. 배포 시 FRONTEND_ORIGINS="https://my-site.vercel.app" 처럼 쉼표로 지정
_origins = os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
# 관리자 설정의 공개 범위를 서비스 API에 적용. CORS보다 먼저 추가해야(=안쪽) 차단 응답에도 CORS 헤더가 붙는다.
app.add_middleware(AccessMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Gif-Meta"],
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


# ==========================================
# 화면(Next.js 정적 빌드) 제공 - 배포용
# STATIC_EXPORT=1 로 빌드한 web/out 이 있으면 API와 같은 주소에서 화면도 제공한다.
# 반드시 파일 맨 끝(모든 API 라우트 뒤)에 둔다.
# ==========================================
WEB_DIST = Path(os.environ.get("WEB_DIST") or Path(__file__).resolve().parent.parent / "web" / "out").resolve()

if (WEB_DIST / "index.html").is_file():
    app.mount("/_next", StaticFiles(directory=WEB_DIST / "_next"), name="next-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def web_page(path: str):
        if path.startswith(("api/", "media/")):
            raise HTTPException(404)
        path = path.strip("/")
        candidates = [WEB_DIST / "index.html"] if not path else [WEB_DIST / f"{path}.html", WEB_DIST / path / "index.html", WEB_DIST / path]
        for c in candidates:
            c = c.resolve()
            if c.is_relative_to(WEB_DIST) and c.is_file():
                return FileResponse(c)
        return FileResponse(WEB_DIST / "404.html", status_code=404)

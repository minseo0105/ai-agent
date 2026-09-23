"""이미지 → GIF 변환기 API.

이미지 처리는 CPU를 많이 쓰므로 동시 작업 수를 제한한다.
def 엔드포인트라 FastAPI가 스레드풀에서 실행한다.
"""

import json
from threading import BoundedSemaphore
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from services import gif_maker as gm

router = APIRouter(prefix="/api/gif", tags=["gif"])
_slots = BoundedSemaphore(2)
HEX = r"^#[0-9A-Fa-f]{6}$"


def _read(upload: Optional[UploadFile]) -> Optional[bytes]:
    if upload is None:
        return None
    data = upload.file.read(gm.MAX_UPLOAD_BYTES + 1)
    if len(data) > gm.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "이미지는 15MB 이하만 올릴 수 있습니다.")
    return data or None


def _run(fn, *args):
    if not _slots.acquire(timeout=60):
        raise HTTPException(503, "지금 변환 작업이 많아요. 잠시 후 다시 시도해 주세요.")
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        _slots.release()


@router.post("/preview")
def preview(
    image: UploadFile = File(...),
    background: Optional[UploadFile] = File(None),
    remove_bg: bool = Form(False),
    use_background: bool = Form(False),
    canvas_color: str = Form("#F3F5F8", pattern=HEX),
):
    png = _run(gm.preview, _read(image), _read(background), remove_bg, use_background, canvas_color)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/generate")
def generate(
    image: UploadFile = File(...),
    background: Optional[UploadFile] = File(None),
    remove_bg: bool = Form(False),
    use_background: bool = Form(False),
    canvas_color: str = Form("#F3F5F8", pattern=HEX),
    use_drive: bool = Form(True),
    use_zoom: bool = Form(False),
    use_bounce: bool = Form(True),
    use_shake: bool = Form(False),
    use_tilt: bool = Form(False),
    use_pan: bool = Form(False),
    direction: Literal["왼쪽 → 오른쪽", "오른쪽 → 왼쪽"] = Form("왼쪽 → 오른쪽"),
    travel_strength: int = Form(20, ge=5, le=35),
    perspective_strength: int = Form(18, ge=0, le=30),
    speed: int = Form(3, ge=1, le=5),
    # 폼 값은 문자열이라 int Literal로는 검증되지 않으므로 int로 받고 아래에서 허용값을 확인
    frame_count: int = Form(20),
    max_width: int = Form(800),
    loop_style: Literal["일반 반복", "부메랑"] = Form("일반 반복"),
    brightness: int = Form(100, ge=80, le=120),
    contrast: int = Form(100, ge=80, le=120),
):
    if frame_count not in gm.FRAME_OPTIONS or max_width not in gm.WIDTH_OPTIONS:
        raise HTTPException(400, "프레임 수 또는 출력 폭 값이 올바르지 않습니다.")
    opts = gm.GifOptions(
        remove_bg=remove_bg, use_background=use_background, canvas_color=canvas_color,
        use_drive=use_drive, use_zoom=use_zoom, use_bounce=use_bounce, use_shake=use_shake, use_tilt=use_tilt, use_pan=use_pan,
        direction=direction, travel_strength=travel_strength, perspective_strength=perspective_strength,
        speed=speed, frame_count=frame_count, max_width=max_width, loop_style=loop_style,
        brightness=brightness, contrast=contrast,
    )
    data, meta = _run(gm.make_gif, _read(image), _read(background), opts)
    # 헤더는 latin-1만 허용되므로 JSON을 URL 인코딩해서 보낸다
    return Response(data, media_type="image/gif",
                    headers={"X-Gif-Meta": quote(json.dumps(meta, ensure_ascii=False)), "Cache-Control": "no-store"})

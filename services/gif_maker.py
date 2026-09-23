"""이미지 → 모션 GIF 변환기 (Streamlit 무관).

pages/5_GIF_변환기.py의 배경 제거 · 합성 · 모션 프레임 생성 로직을 그대로 옮긴 것.
"""

import hashlib
import io
import math
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from PIL import Image, ImageEnhance

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REMBG_CACHE_DIR = PROJECT_ROOT / ".rembg"
REMBG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("REMBG_HOME", str(REMBG_CACHE_DIR))

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000  # 약 8000×5000. 이보다 큰 이미지는 거부
SPEED_DURATION = {1: 120, 2: 90, 3: 70, 4: 55, 5: 42}  # speed 1~5 -> 느림~빠름 (ms)
FRAME_OPTIONS = [12, 16, 20, 24, 30]
WIDTH_OPTIONS = [480, 640, 800, 960, 1200]
DIRECTIONS = ["왼쪽 → 오른쪽", "오른쪽 → 왼쪽"]
LOOP_STYLES = ["일반 반복", "부메랑"]


# =========================================================
# 이미지 로드 · 배경 제거
# =========================================================

def open_image(data: bytes) -> Image.Image:
    """업로드 바이트를 RGBA 이미지로. 형식·크기 오류는 ValueError."""
    if not data:
        raise ValueError("이미지가 비어 있습니다.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("이미지는 15MB 이하만 올릴 수 있습니다.")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("이미지 해상도가 너무 큽니다. 8000px 이하로 줄여서 올려 주세요.")
        if img.format not in ("PNG", "JPEG", "WEBP"):
            raise ValueError("PNG · JPG · WEBP 이미지만 지원합니다.")
        return img.convert("RGBA")
    except ValueError:
        raise
    except Exception:
        raise ValueError("이미지를 읽을 수 없습니다. PNG · JPG · WEBP 파일인지 확인해 주세요.")


_session = None
_session_lock = Lock()
_bg_cache: "OrderedDict[str, bytes]" = OrderedDict()
_BG_CACHE_SIZE = 16


def _rembg_session():
    global _session
    with _session_lock:
        if _session is None:
            from rembg import new_session

            _session = new_session("u2net")
        return _session


def remove_background(image_bytes: bytes) -> Image.Image:
    """동일 이미지는 배경 제거를 다시 계산하지 않도록 캐시합니다."""
    key = hashlib.sha256(image_bytes).hexdigest()
    cached = _bg_cache.get(key)
    if cached is None:
        from rembg import remove

        img = open_image(image_bytes)
        out = io.BytesIO()
        remove(img, session=_rembg_session()).convert("RGBA").save(out, format="PNG")
        cached = out.getvalue()
        _bg_cache[key] = cached
        while len(_bg_cache) > _BG_CACHE_SIZE:
            _bg_cache.popitem(last=False)
    else:
        _bg_cache.move_to_end(key)
    return Image.open(io.BytesIO(cached)).convert("RGBA")


def resize_cover(img, target_size):
    """배경 이미지를 canvas에 꽉 차게 crop-resize."""
    tw, th = target_size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw = max(1, int(iw * scale))
    nh = max(1, int(ih * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return resized.crop((left, top, left + tw, top + th))


def fit_output_size(img, max_width):
    """GIF 파일 크기와 생성 속도를 줄이기 위해 출력 폭을 제한합니다."""
    w, h = img.size
    if w <= max_width:
        return img
    ratio = max_width / w
    return img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.Resampling.LANCZOS)


def paste_center(canvas, layer, x_shift=0, y_shift=0):
    x = (canvas.width - layer.width) // 2 + x_shift
    y = (canvas.height - layer.height) // 2 + y_shift
    canvas.alpha_composite(layer, (x, y))
    return canvas


# =========================================================
# 합성 미리보기
# =========================================================

def preview(original_bytes: bytes, bg_bytes: bytes | None, remove_bg: bool, use_background: bool, canvas_color: str) -> bytes:
    """원본 크기의 합성 미리보기 PNG (화면 표시용으로 최대 폭 900px)."""
    original = open_image(original_bytes)
    fg = remove_background(original_bytes) if remove_bg else original.copy()
    base = original.copy()

    if use_background and bg_bytes:
        bg_preview = resize_cover(open_image(bg_bytes), original.size)
        base = bg_preview.copy()
        if remove_bg:
            base = paste_center(base, fg)
        else:
            base = Image.blend(bg_preview, original, 0.68)
    elif remove_bg:
        base = paste_center(Image.new("RGBA", original.size, canvas_color), fg)

    out = io.BytesIO()
    fit_output_size(base, 900).save(out, format="PNG", optimize=True)
    return out.getvalue()


# =========================================================
# GIF 생성
# =========================================================

@dataclass
class GifOptions:
    remove_bg: bool = False
    use_background: bool = False
    canvas_color: str = "#F3F5F8"
    use_drive: bool = True
    use_zoom: bool = False
    use_bounce: bool = True
    use_shake: bool = False
    use_tilt: bool = False
    use_pan: bool = False
    direction: str = "왼쪽 → 오른쪽"
    travel_strength: int = 20
    perspective_strength: int = 18
    speed: int = 3
    frame_count: int = 20
    max_width: int = 800
    loop_style: str = "일반 반복"
    brightness: int = 100
    contrast: int = 100


def make_gif(original_bytes: bytes, bg_bytes: bytes | None, o: GifOptions):
    """(gif_bytes, meta) 반환. 효과를 하나도 고르지 않으면 ValueError."""
    if not (o.use_drive or o.use_zoom or o.use_bounce or o.use_shake or o.use_tilt or o.use_pan):
        raise ValueError("효과를 최소 1개 선택해주세요.")
    use_background = bool(o.use_background and bg_bytes)
    travel_strength = o.travel_strength if o.use_drive else 0
    perspective_strength = o.perspective_strength if o.use_drive else 0

    original = open_image(original_bytes)
    base_original = fit_output_size(original, o.max_width)
    W, H = base_original.size

    # Foreground도 output size에 맞춤
    fg_source = fit_output_size(remove_background(original_bytes), o.max_width) if o.remove_bg else base_original.copy()

    bg_raw = open_image(bg_bytes) if use_background else None
    bg_base = resize_cover(bg_raw, (W, H)) if use_background else Image.new("RGBA", (W, H), o.canvas_color)

    # 밝기·대비는 프레임마다 같으므로 한 번만 적용
    if o.brightness != 100:
        fg_source = ImageEnhance.Brightness(fg_source).enhance(o.brightness / 100)
    if o.contrast != 100:
        fg_source = ImageEnhance.Contrast(fg_source).enhance(o.contrast / 100)

    frames = []
    for i in range(o.frame_count):
        t = 0 if o.frame_count == 1 else i / (o.frame_count - 1)
        eased = 0.5 - 0.5 * math.cos(math.pi * t)  # 자연스러운 ease-in-out

        # 배경/전체 화면 패닝
        canvas = bg_base.copy()
        if o.use_pan and use_background:
            pan_px = int(W * 0.035 * math.sin(t * math.pi))
            larger_bg = resize_cover(bg_raw, (W + abs(pan_px) * 2 + 12, H))
            crop_left = max(0, (larger_bg.width - W) // 2 + pan_px)
            canvas = larger_bg.crop((crop_left, 0, crop_left + W, H))

        scale = 1.0
        if o.use_drive:
            scale += (perspective_strength / 100) * eased
        if o.use_zoom:
            scale *= 1.0 + 0.035 * math.sin(t * 2 * math.pi)

        layer = fg_source.resize((max(1, int(fg_source.width * scale)), max(1, int(fg_source.height * scale))), Image.Resampling.LANCZOS)

        if o.use_tilt:
            angle = 1.7 * math.sin(t * 2 * math.pi)
            layer = layer.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)

        x_shift = 0
        y_shift = 0
        if o.use_drive:
            distance = int(W * (travel_strength / 100))
            if o.direction == "왼쪽 → 오른쪽":
                x_shift += int(-distance / 2 + distance * eased)
            else:
                x_shift += int(distance / 2 - distance * eased)
        if o.use_shake:
            x_shift += int(5 * math.sin(t * 4 * math.pi * max(1, o.speed / 2)))
        if o.use_bounce:
            y_shift -= int(5 * abs(math.sin(t * 5 * math.pi)))

        # 배경 제거 없이 '완성 사진'에 효과를 주는 경우
        if not o.remove_bg and not use_background:
            canvas = Image.new("RGBA", (W, H), o.canvas_color)

        frame = paste_center(canvas, layer, x_shift=x_shift, y_shift=y_shift)

        # 화면 패닝인데 별도 배경이 없으면 전체 프레임 미세 이동
        if o.use_pan and not use_background:
            pan_x = int(5 * math.sin(t * 2 * math.pi))
            padded = Image.new("RGBA", (W + 20, H), o.canvas_color)
            padded.alpha_composite(frame, (10 + pan_x, 0))
            frame = padded.crop((10, 0, 10 + W, H))

        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE))

    if o.loop_style == "부메랑" and len(frames) > 2:
        frames = frames + frames[-2:0:-1]

    duration = SPEED_DURATION[o.speed]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=duration, loop=0, optimize=True, disposal=2)
    data = buf.getvalue()
    meta = {"frames": len(frames), "width": W, "height": H, "duration": duration, "loop_style": o.loop_style, "bytes": len(data)}
    return data, meta

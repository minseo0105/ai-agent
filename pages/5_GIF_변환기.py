import streamlit as st
from PIL import Image, ImageEnhance
from rembg import remove, new_session
import io
import math
from pathlib import Path

from auth import require_page_auth


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="이미지 → GIF 변환기",
    page_icon="🎞️",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_page_auth()


# =========================================================
# 한글 사이드바
# =========================================================
with st.sidebar:
    st.markdown("### ✦ AI WORKBENCH")
    st.caption("민서의 AI Lab")

    if st.button(
        "🏠 메인으로",
        key="sidebar_home",
        use_container_width=True,
    ):
        st.switch_page("app.py")

    st.divider()
    st.markdown("**빠른 이동**")

    if st.button(
        "🚙 내차에서 드림카까지",
        key="sidebar_dreamcar",
        use_container_width=True,
    ):
        st.switch_page("pages/1_내차에서_드림카까지.py")

    if st.button(
        "🏠 부동산 모니터",
        key="sidebar_realestate",
        use_container_width=True,
    ):
        st.switch_page("pages/2_부동산_모니터.py")

    if st.button(
        "📄 보고서 작성기",
        key="sidebar_report",
        use_container_width=True,
    ):
        st.switch_page("pages/3_보고서_작성기.py")

    if st.button(
        "🚗 차량 선택기",
        key="sidebar_car_selector",
        use_container_width=True,
    ):
        st.switch_page("pages/4_차량_선택기.py")

    st.button(
        "🎞️ GIF 변환기",
        key="sidebar_gif",
        use_container_width=True,
        disabled=True,
    )


# =========================================================
# STYLE
# =========================================================
st.markdown(
    """
<style>
:root{
    --ink:#172033;
    --muted:#697586;
    --line:#E7EAF0;
    --blue:#315EF5;
    --violet:#6D4FE8;
    --soft:#F6F8FC;
}

[data-testid="stSidebar"]{
    display:block !important;
}

.stApp{
    background:
        radial-gradient(circle at 95% 0%, rgba(49,94,245,.08), transparent 22%),
        linear-gradient(180deg,#FAFBFD 0%,#F5F7FA 100%);
}

.block-container{
    max-width:1120px;
    padding-top:1rem;
    padding-bottom:5rem;
}

header[data-testid="stHeader"]{
    background:rgba(249,250,252,.82);
    backdrop-filter:blur(12px);
}

#MainMenu,footer{
    visibility:hidden;
}

.hero{
    position:relative;
    overflow:hidden;
    padding:42px 44px;
    margin-bottom:18px;
    border-radius:30px;
    color:white;
    background:
        radial-gradient(circle at 84% 20%,rgba(124,151,255,.28),transparent 24%),
        linear-gradient(125deg,#07162C 0%,#123162 60%,#315AC8 100%);
    box-shadow:0 20px 52px rgba(15,31,70,.14);
}

.hero:after{
    content:"";
    position:absolute;
    right:-100px;
    top:-135px;
    width:285px;
    height:285px;
    border-radius:50%;
    border:1px solid rgba(255,255,255,.12);
}

.hero-kicker{
    position:relative;
    z-index:1;
    color:#ABC3FF;
    font-size:10px;
    font-weight:900;
    letter-spacing:.18em;
}

.hero-title{
    position:relative;
    z-index:1;
    margin-top:9px;
    max-width:760px;
    font-size:38px;
    line-height:1.18;
    font-weight:950;
    letter-spacing:-.045em;
}

.hero-title span{
    color:#C9D8FF;
}

.hero-desc{
    position:relative;
    z-index:1;
    margin-top:12px;
    max-width:760px;
    color:#D9E4F5;
    font-size:13px;
    line-height:1.7;
}

.hero-chips{
    position:relative;
    z-index:1;
    display:flex;
    flex-wrap:wrap;
    gap:7px;
    margin-top:16px;
}

.hero-chip{
    padding:6px 9px;
    border-radius:999px;
    border:1px solid rgba(255,255,255,.13);
    background:rgba(255,255,255,.08);
    color:#EDF3FF;
    font-size:9px;
    font-weight:800;
}

.section-card{
    margin:0 0 12px;
    padding:18px 20px;
    border:1px solid var(--line);
    border-radius:20px;
    background:#FFFFFF;
    box-shadow:0 8px 24px rgba(15,23,42,.035);
}

.section-kicker{
    color:var(--blue);
    font-size:9px;
    font-weight:900;
    letter-spacing:.12em;
}

.section-title{
    margin-top:4px;
    color:var(--ink);
    font-size:20px;
    font-weight:950;
    letter-spacing:-.03em;
}

.section-desc{
    margin-top:4px;
    color:#7B8798;
    font-size:11px;
    line-height:1.55;
}

.preview-note{
    margin-top:8px;
    padding:10px 12px;
    border-radius:13px;
    background:#F7F9FC;
    color:#7C8798;
    font-size:9px;
    line-height:1.5;
}

.effect-help{
    margin-top:3px;
    color:#8A95A6;
    font-size:9px;
}

.result-card{
    margin-top:14px;
    padding:20px;
    border:1px solid var(--line);
    border-radius:22px;
    background:#FFFFFF;
    box-shadow:0 10px 28px rgba(15,23,42,.04);
}

.metric-strip{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:7px;
    margin:10px 0 4px;
}

.metric-box{
    padding:10px 11px;
    border-radius:13px;
    background:#F7F9FC;
}

.metric-box span{
    display:block;
    color:#98A2B3;
    font-size:8px;
}

.metric-box strong{
    display:block;
    margin-top:2px;
    color:#344054;
    font-size:10px;
}

div[data-testid="stFileUploader"]{
    border-radius:16px;
}

div[data-testid="stButton"] button[kind="primary"]{
    min-height:49px;
    border:none;
    border-radius:13px;
    color:white;
    font-weight:900;
    background:linear-gradient(135deg,#315EF5,#674CE8);
    box-shadow:0 9px 22px rgba(49,94,245,.18);
}

div[data-testid="stDownloadButton"] button{
    min-height:46px;
    border-radius:12px;
    font-weight:850;
}

@media(max-width:768px){
    .block-container{
        padding-top:.55rem;
        padding-left:.8rem;
        padding-right:.8rem;
        padding-bottom:4.5rem;
    }

    .hero{
        padding:24px 20px;
        border-radius:22px;
        margin-bottom:13px;
    }

    .hero-title{
        font-size:27px;
        line-height:1.2;
    }

    .hero-desc{
        font-size:10px;
        line-height:1.5;
    }

    .hero-chip{
        font-size:8px;
        padding:5px 7px;
    }

    .section-card{
        padding:14px 14px;
        border-radius:16px;
    }

    .section-title{
        font-size:17px;
    }

    .metric-strip{
        grid-template-columns:repeat(2,1fr);
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# HERO
# =========================================================
st.markdown(
    """
<div class="hero">
    <div class="hero-kicker">MOTION MAKER · IMAGE TO GIF</div>
    <div class="hero-title">
        정적인 차량 이미지를,<br>
        <span>짧고 자연스러운 모션 콘텐츠로.</span>
    </div>
    <div class="hero-desc">
        배경 제거와 합성부터 달리기 · 줌 · 흔들림 · 바운스 · 틸트 · 패닝까지
        한 화면에서 조합해 GIF를 만들 수 있습니다.
    </div>
    <div class="hero-chips">
        <span class="hero-chip">Background Remove</span>
        <span class="hero-chip">Drive Motion</span>
        <span class="hero-chip">Zoom</span>
        <span class="hero-chip">Bounce</span>
        <span class="hero-chip">Tilt</span>
        <span class="hero-chip">Boomerang</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# =========================================================
# REMBG
# =========================================================
@st.cache_resource
def get_rembg_session():
    return new_session("u2net")


@st.cache_data(show_spinner=False)
def remove_background_cached(image_bytes):
    """
    동일 이미지는 배경 제거를 다시 계산하지 않도록 캐시합니다.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    session = get_rembg_session()
    result = remove(img, session=session)
    out = io.BytesIO()
    result.convert("RGBA").save(out, format="PNG")
    return out.getvalue()


def resize_cover(img, target_size):
    """
    배경 이미지를 canvas에 꽉 차게 crop-resize.
    """
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
    """
    GIF 파일 크기와 생성 속도를 줄이기 위해 출력 폭을 제한합니다.
    """
    w, h = img.size

    if w <= max_width:
        return img

    ratio = max_width / w
    new_size = (
        max(1, int(w * ratio)),
        max(1, int(h * ratio)),
    )

    return img.resize(
        new_size,
        Image.Resampling.LANCZOS,
    )


def paste_center(canvas, layer, x_shift=0, y_shift=0):
    x = (canvas.width - layer.width) // 2 + x_shift
    y = (canvas.height - layer.height) // 2 + y_shift

    canvas.alpha_composite(layer, (x, y))
    return canvas


# =========================================================
# INPUT
# =========================================================
st.markdown(
    """
<div class="section-card">
    <div class="section-kicker">STEP 01 · SOURCE</div>
    <div class="section-title">이미지를 준비해주세요</div>
    <div class="section-desc">
        차량 이미지만 올려도 되고, 별도 배경을 함께 올려 합성할 수도 있습니다.
    </div>
</div>
""",
    unsafe_allow_html=True,
)

upload_left, upload_right = st.columns(2, gap="medium")

with upload_left:
    uploaded_file = st.file_uploader(
        "차량(전경) 이미지",
        type=["png", "jpg", "jpeg", "webp"],
        key="fg",
        help="PNG/JPG/WEBP 지원",
    )

with upload_right:
    bg_file = st.file_uploader(
        "배경 이미지 · 선택",
        type=["png", "jpg", "jpeg", "webp"],
        key="bg",
        help="배경 합성을 원하는 경우에만 올리세요.",
    )


if uploaded_file:
    original_bytes = uploaded_file.getvalue()
    original = Image.open(io.BytesIO(original_bytes)).convert("RGBA")

    st.markdown(
        """
<div class="section-card">
    <div class="section-kicker">STEP 02 · COMPOSITE</div>
    <div class="section-title">전경과 배경을 정리합니다</div>
    <div class="section-desc">
        배경 제거는 처음 한 번만 시간이 걸리고, 같은 이미지는 캐시되어 이후 작업이 빨라집니다.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    opt1, opt2, opt3 = st.columns([1, 1, 1])

    with opt1:
        remove_bg = st.toggle(
            "차량 배경 제거",
            value=bool(bg_file),
            help="차량만 투명하게 분리합니다.",
        )

    with opt2:
        use_background = st.toggle(
            "배경 이미지 사용",
            value=bool(bg_file),
            disabled=not bool(bg_file),
        )

    with opt3:
        canvas_color = st.color_picker(
            "배경색",
            value="#F3F5F8",
            disabled=use_background,
        )

    if remove_bg:
        with st.spinner("차량 배경을 분리하고 있습니다..."):
            fg_bytes = remove_background_cached(original_bytes)
            fg_rgba = Image.open(io.BytesIO(fg_bytes)).convert("RGBA")
    else:
        fg_rgba = original.copy()

    # Preview base
    preview_base = original.copy()

    if use_background and bg_file:
        bg_original = Image.open(bg_file).convert("RGBA")
        bg_preview = resize_cover(bg_original, original.size)
        preview_base = bg_preview.copy()

        if remove_bg:
            preview_base = paste_center(
                preview_base,
                fg_rgba,
            )
        else:
            preview_base = Image.blend(
                bg_preview,
                original,
                0.68,
            )
    elif remove_bg:
        preview_base = Image.new(
            "RGBA",
            original.size,
            canvas_color,
        )
        preview_base = paste_center(
            preview_base,
            fg_rgba,
        )

    p1, p2 = st.columns(2, gap="medium")

    with p1:
        st.image(
            original,
            caption="원본",
            use_container_width=True,
        )

    with p2:
        st.image(
            preview_base,
            caption="합성 미리보기",
            use_container_width=True,
        )

    st.markdown(
        """
<div class="preview-note">
TIP · 차량이 화면 전체를 차지하는 사진이라면 배경 제거 후 '달려가기' 효과가 가장 자연스럽습니다.
이미 배경까지 완성된 사진이라면 배경 제거 없이 줌·패닝·바운스 조합을 추천합니다.
</div>
""",
        unsafe_allow_html=True,
    )


    # =====================================================
    # EFFECTS
    # =====================================================
    st.markdown(
        """
<div class="section-card" style="margin-top:14px;">
    <div class="section-kicker">STEP 03 · MOTION</div>
    <div class="section-title">움직임을 조합해주세요</div>
    <div class="section-desc">
        여러 효과를 동시에 적용할 수 있습니다. 기본값은 차량 콘텐츠에 가장 무난한 조합입니다.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    e1, e2, e3 = st.columns(3)

    with e1:
        use_drive = st.toggle(
            "🚗 달려가기",
            value=True,
            help="좌우 이동 + 원근감을 적용합니다.",
        )
        use_zoom = st.toggle(
            "🔎 줌 인/아웃",
            value=False,
        )

    with e2:
        use_bounce = st.toggle(
            "↕️ 바운스",
            value=True,
            help="주행 시 미세하게 위아래 움직입니다.",
        )
        use_shake = st.toggle(
            "↔️ 좌우 흔들림",
            value=False,
        )

    with e3:
        use_tilt = st.toggle(
            "↗️ 틸트",
            value=False,
            help="좌우로 아주 살짝 기울어집니다.",
        )
        use_pan = st.toggle(
            "🎥 화면 패닝",
            value=False,
            help="배경 또는 전체 화면이 서서히 이동합니다.",
        )

    st.caption(
        "추천 조합: 차량 이미지 → 달려가기 + 바운스 / 완성 사진 → 줌 + 패닝"
    )

    if use_drive:
        drive_c1, drive_c2, drive_c3 = st.columns(3)

        with drive_c1:
            direction = st.selectbox(
                "달리는 방향",
                ["왼쪽 → 오른쪽", "오른쪽 → 왼쪽"],
            )

        with drive_c2:
            travel_strength = st.slider(
                "이동 거리",
                min_value=5,
                max_value=35,
                value=20,
                step=5,
                help="화면 폭 대비 이동량입니다.",
            )

        with drive_c3:
            perspective_strength = st.slider(
                "원근감",
                min_value=0,
                max_value=30,
                value=18,
                step=3,
                help="끝으로 갈수록 차량이 커지는 정도입니다.",
            )
    else:
        direction = "왼쪽 → 오른쪽"
        travel_strength = 0
        perspective_strength = 0

    motion_c1, motion_c2, motion_c3, motion_c4 = st.columns(4)

    with motion_c1:
        speed = st.slider(
            "재생 속도",
            min_value=1,
            max_value=5,
            value=3,
        )

    with motion_c2:
        frame_count = st.select_slider(
            "프레임 수",
            options=[12, 16, 20, 24, 30],
            value=20,
            help="낮을수록 빠르게 생성됩니다.",
        )

    with motion_c3:
        max_width = st.select_slider(
            "출력 폭",
            options=[480, 640, 800, 960, 1200],
            value=800,
            help="작을수록 GIF 용량과 생성 시간이 줄어듭니다.",
        )

    with motion_c4:
        loop_style = st.selectbox(
            "반복 방식",
            ["일반 반복", "부메랑"],
            help="부메랑은 마지막 프레임에서 역방향으로 돌아옵니다.",
        )

    enhance_c1, enhance_c2 = st.columns(2)

    with enhance_c1:
        brightness = st.slider(
            "밝기",
            min_value=80,
            max_value=120,
            value=100,
            step=5,
        )

    with enhance_c2:
        contrast = st.slider(
            "대비",
            min_value=80,
            max_value=120,
            value=100,
            step=5,
        )


    # =====================================================
    # GENERATE
    # =====================================================
    if st.button(
        "✨ GIF 만들기",
        type="primary",
        use_container_width=True,
    ):
        if not (
            use_drive
            or use_zoom
            or use_bounce
            or use_shake
            or use_tilt
            or use_pan
        ):
            st.warning("효과를 최소 1개 선택해주세요.")

        else:
            with st.spinner("모션을 합성하고 GIF를 만들고 있습니다..."):
                base_original = fit_output_size(
                    original,
                    max_width,
                )

                W, H = base_original.size

                # Foreground도 output size에 맞춤
                if remove_bg:
                    fg_source = fit_output_size(
                        fg_rgba,
                        max_width,
                    )
                else:
                    fg_source = base_original.copy()

                # Background
                if use_background and bg_file:
                    bg_raw = Image.open(bg_file).convert("RGBA")
                    bg_base = resize_cover(
                        bg_raw,
                        (W, H),
                    )
                else:
                    bg_base = Image.new(
                        "RGBA",
                        (W, H),
                        canvas_color,
                    )

                frames = []

                for i in range(frame_count):
                    if frame_count == 1:
                        t = 0
                    else:
                        t = i / (frame_count - 1)

                    # 자연스러운 ease-in-out
                    eased = 0.5 - 0.5 * math.cos(math.pi * t)

                    # 배경/전체 화면 패닝
                    canvas = bg_base.copy()

                    if use_pan and use_background and bg_file:
                        pan_px = int(W * 0.035 * math.sin(t * math.pi))
                        larger_bg = resize_cover(
                            Image.open(bg_file).convert("RGBA"),
                            (W + abs(pan_px) * 2 + 12, H),
                        )
                        crop_left = max(
                            0,
                            (larger_bg.width - W) // 2 + pan_px,
                        )
                        canvas = larger_bg.crop(
                            (
                                crop_left,
                                0,
                                crop_left + W,
                                H,
                            )
                        )

                    # foreground scale
                    scale = 1.0

                    if use_drive:
                        scale += (
                            perspective_strength / 100
                        ) * eased

                    if use_zoom:
                        scale *= (
                            1.0
                            + 0.035
                            * math.sin(
                                t * 2 * math.pi
                            )
                        )

                    layer = fg_source.copy()

                    if brightness != 100:
                        layer = ImageEnhance.Brightness(
                            layer
                        ).enhance(
                            brightness / 100
                        )

                    if contrast != 100:
                        layer = ImageEnhance.Contrast(
                            layer
                        ).enhance(
                            contrast / 100
                        )

                    new_w = max(
                        1,
                        int(layer.width * scale),
                    )
                    new_h = max(
                        1,
                        int(layer.height * scale),
                    )

                    layer = layer.resize(
                        (new_w, new_h),
                        Image.Resampling.LANCZOS,
                    )

                    # tilt
                    if use_tilt:
                        angle = (
                            1.7
                            * math.sin(
                                t * 2 * math.pi
                            )
                        )
                        layer = layer.rotate(
                            angle,
                            resample=Image.Resampling.BICUBIC,
                            expand=True,
                        )

                    x_shift = 0
                    y_shift = 0

                    if use_drive:
                        distance = int(
                            W
                            * (
                                travel_strength
                                / 100
                            )
                        )

                        if direction == "왼쪽 → 오른쪽":
                            x_shift += int(
                                -distance / 2
                                + distance * eased
                            )
                        else:
                            x_shift += int(
                                distance / 2
                                - distance * eased
                            )

                    if use_shake:
                        x_shift += int(
                            5
                            * math.sin(
                                t
                                * 4
                                * math.pi
                                * max(1, speed / 2)
                            )
                        )

                    if use_bounce:
                        y_shift -= int(
                            5
                            * abs(
                                math.sin(
                                    t
                                    * 5
                                    * math.pi
                                )
                            )
                        )

                    # 배경 제거 없이 '완성 사진'에 효과를 주는 경우
                    if not remove_bg and not use_background:
                        canvas = Image.new(
                            "RGBA",
                            (W, H),
                            canvas_color,
                        )

                    # 중앙 합성
                    frame = paste_center(
                        canvas,
                        layer,
                        x_shift=x_shift,
                        y_shift=y_shift,
                    )

                    # 화면 패닝인데 별도 배경이 없으면 전체 프레임 미세 이동
                    if use_pan and not use_background:
                        pan_x = int(
                            5
                            * math.sin(
                                t * 2 * math.pi
                            )
                        )

                        padded = Image.new(
                            "RGBA",
                            (W + 20, H),
                            canvas_color,
                        )
                        padded.alpha_composite(
                            frame,
                            (10 + pan_x, 0),
                        )
                        frame = padded.crop(
                            (10, 0, 10 + W, H)
                        )

                    frames.append(
                        frame.convert("P", palette=Image.Palette.ADAPTIVE)
                    )

                if loop_style == "부메랑" and len(frames) > 2:
                    frames = (
                        frames
                        + frames[-2:0:-1]
                    )

                gif_buffer = io.BytesIO()

                # speed 1~5 -> 느림~빠름
                frame_duration = {
                    1: 120,
                    2: 90,
                    3: 70,
                    4: 55,
                    5: 42,
                }[speed]

                frames[0].save(
                    gif_buffer,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=frame_duration,
                    loop=0,
                    optimize=True,
                    disposal=2,
                )

                gif_buffer.seek(0)

                st.session_state["gif_result"] = gif_buffer.getvalue()
                st.session_state["gif_meta"] = {
                    "frames": len(frames),
                    "width": W,
                    "height": H,
                    "duration": frame_duration,
                    "loop_style": loop_style,
                }

            st.success("GIF 생성이 완료되었습니다.")


# =========================================================
# RESULT
# =========================================================
if st.session_state.get("gif_result"):
    gif_bytes = st.session_state["gif_result"]
    meta = st.session_state.get("gif_meta", {})

    st.markdown(
        """
<div class="result-card">
    <div class="section-kicker">RESULT</div>
    <div class="section-title">완성된 모션 GIF</div>
    <div class="section-desc">
        결과가 마음에 들지 않으면 위 효과를 조정하고 다시 생성해보세요.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.image(
        gif_bytes,
        caption="변환된 GIF",
        use_container_width=True,
    )

    st.markdown(
        f"""
<div class="metric-strip">
    <div class="metric-box"><span>출력 크기</span><strong>{meta.get('width','-')} × {meta.get('height','-')}</strong></div>
    <div class="metric-box"><span>총 프레임</span><strong>{meta.get('frames','-')} frame</strong></div>
    <div class="metric-box"><span>프레임 간격</span><strong>{meta.get('duration','-')} ms</strong></div>
    <div class="metric-box"><span>반복 방식</span><strong>{meta.get('loop_style','-')}</strong></div>
</div>
""",
        unsafe_allow_html=True,
    )

    d1, d2 = st.columns([2, 1])

    with d1:
        st.download_button(
            label="📥 GIF 다운로드",
            data=gif_bytes,
            file_name="animated_motion.gif",
            mime="image/gif",
            use_container_width=True,
        )

    with d2:
        if st.button(
            "결과 지우기",
            use_container_width=True,
        ):
            st.session_state.pop(
                "gif_result",
                None,
            )
            st.session_state.pop(
                "gif_meta",
                None,
            )
            st.rerun()

else:
    if not uploaded_file:
        st.info(
            "차량 이미지를 업로드하면 GIF 제작 옵션이 나타납니다."
        )

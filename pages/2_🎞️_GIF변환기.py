import streamlit as st
from PIL import Image
import io
import math

st.set_page_config(page_title="이미지 → GIF 변환기", page_icon="🎞️")

st.title("🎞️ 이미지를 움직이는 GIF로")
st.caption("사진을 올리고, 원하는 움직임 효과를 골라보세요")

def remove_white_background(img, sensitivity=30):
    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    threshold = 255 - sensitivity
    for item in datas:
        r, g, b = item[0], item[1], item[2]
        if r > threshold and g > threshold and b > threshold:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, 255))
    img.putdata(new_data)
    return img

st.subheader("1. 차량(전경) 이미지 업로드")
uploaded_file = st.file_uploader("배경이 흰색인 이미지를 올려주세요", type=["png", "jpg", "jpeg"], key="fg")

st.subheader("2. 배경 이미지 (선택사항)")
bg_file = st.file_uploader("합성할 배경 이미지를 올려주세요", type=["png", "jpg", "jpeg"], key="bg")

if uploaded_file:
    original = Image.open(uploaded_file).convert("RGB")

    use_bg_composite = False
    background_img = None
    sensitivity = 30

    if bg_file:
        use_bg_composite = st.checkbox("흰색 배경 제거하고 합성하기", value=True)
        if use_bg_composite:
            sensitivity = st.slider("배경 제거 민감도 (높을수록 더 많이 지워요)", 10, 100, 30)
            background_img = Image.open(bg_file).convert("RGB")

    if use_bg_composite and background_img:
        fg_transparent = remove_white_background(original, sensitivity)

        bg_resized = background_img.resize(original.size)
        preview = bg_resized.convert("RGBA")
        preview.paste(fg_transparent, (0, 0), fg_transparent)

        st.image(preview, caption="합성 미리보기", use_container_width=True)
        working_image = preview.convert("RGB")
        canvas_bg_color = None
        canvas_bg_image = bg_resized
    else:
        st.image(original, caption="원본 이미지", use_container_width=True)
        working_image = original
        canvas_bg_color = (255, 255, 255)
        canvas_bg_image = None

    st.write("적용할 효과를 선택하세요")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        use_zoom = st.checkbox("확대/축소", value=False)
    with col2:
        use_shake = st.checkbox("좌우 흔들림", value=False)
    with col3:
        use_bounce = st.checkbox("통통 튀기", value=False)
    with col4:
        use_drive = st.checkbox("달려가기(3D)", value=True)

    direction = "왼쪽 → 오른쪽"
    if use_drive:
        direction = st.radio("달려가는 방향", ["왼쪽 → 오른쪽", "오른쪽 → 왼쪽"], horizontal=True)

    speed = st.slider("애니메이션 속도", min_value=1, max_value=5, value=3)

    if st.button("GIF로 변환하기"):
        if not (use_zoom or use_shake or use_bounce or use_drive):
            st.warning("효과를 최소 1개는 선택해주세요.")
        else:
            with st.spinner("변환 중이에요..."):
                W, H = working_image.size
                num_frames = 20
                frames = []

                if use_bg_composite and background_img:
                    fg_transparent = remove_white_background(original, sensitivity)
                    bg_base = background_img.resize((W, H)).convert("RGBA")
                else:
                    fg_transparent = None
                    bg_base = None

                if use_drive:
                    for i in range(num_frames):
                        t = i / (num_frames - 1)

                        scale = 0.7 + 0.3 * t
                        if use_bg_composite and fg_transparent:
                            fg_resized = fg_transparent.resize((int(W * scale), int(H * scale)))
                        else:
                            fg_resized = original.resize((int(W * scale), int(H * scale)))
                        new_w, new_h = fg_resized.size

                        if use_bg_composite and bg_base:
                            canvas = bg_base.copy()
                        else:
                            canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))

                        if direction == "왼쪽 → 오른쪽":
                            x_shift = int(-W * 0.12 + W * 0.24 * t)
                        else:
                            x_shift = int(W * 0.12 - W * 0.24 * t)

                        bounce_offset = int(4 * abs(math.sin(t * 8 * 3.14159))) if use_bounce else 0

                        paste_x = (W - new_w) // 2 + x_shift
                        paste_y = (H - new_h) // 2 - bounce_offset

                        if use_bg_composite and fg_transparent:
                            canvas.paste(fg_resized, (paste_x, paste_y), fg_resized)
                        else:
                            canvas.paste(fg_resized, (paste_x, paste_y))

                        frames.append(canvas.convert("RGB"))
                else:
                    base_for_effects = working_image
                    for i in range(num_frames):
                        t = i / num_frames

                        zoom = 1.05
                        shift_x = 0
                        shift_y = 0

                        if use_zoom:
                            zoom = 1.0 + 0.04 * (1 + math.sin(t * 2 * 3.14159))

                        if use_shake:
                            shift_x = int(8 * math.sin(t * 4 * 3.14159 * speed / 3))

                        if use_bounce:
                            shift_y = int(6 * abs(math.sin(t * 6 * 3.14159 * speed / 3)))

                        new_w, new_h = int(W * zoom), int(H * zoom)
                        zoomed = base_for_effects.resize((new_w, new_h))

                        left = (new_w - W) // 2 + shift_x
                        top = (new_h - H) // 2 - shift_y
                        left = max(0, min(left, new_w - W))
                        top = max(0, min(top, new_h - H))

                        frame = zoomed.crop((left, top, left + W, top + H))
                        frames.append(frame.convert("RGB"))

                gif_buffer = io.BytesIO()
                frame_duration = int(100 / speed)
                frames[0].save(
                    gif_buffer,
                    format="GIF",
                    save_all=True,
                    append_images=frames[1:],
                    duration=frame_duration,
                    loop=0
                )
                gif_buffer.seek(0)

            st.success("변환 완료!")
            st.image(gif_buffer, caption="변환된 GIF", use_container_width=True)

            st.download_button(
                label="GIF 다운로드",
                data=gif_buffer,
                file_name="animated.gif",
                mime="image/gif"
            )
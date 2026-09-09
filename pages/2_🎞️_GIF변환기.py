import streamlit as st
from PIL import Image
import io
import math

st.set_page_config(page_title="이미지 → GIF 변환기", page_icon="🎞️")

st.title("🎞️ 이미지를 움직이는 GIF로")
st.caption("사진을 올리고, 원하는 움직임 효과를 골라보세요")

uploaded_file = st.file_uploader("이미지를 올려주세요", type=["png", "jpg", "jpeg"])

if uploaded_file:
    original = Image.open(uploaded_file).convert("RGB")
    st.image(original, caption="원본 이미지", use_container_width=True)

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

    speed = st.slider("애니메이션 속도", min_value=1, max_value=5, value=3)

    if st.button("GIF로 변환하기"):
        if not (use_zoom or use_shake or use_bounce or use_drive):
            st.warning("효과를 최소 1개는 선택해주세요.")
        else:
            with st.spinner("변환 중이에요..."):
                W, H = original.size
                num_frames = 20
                frames = []

                if use_drive:
                    # 뒤에서 앞으로 다가오며 달려오는 느낌
                    # : 작게(멀리) 시작해서 점점 크게(가까이) 변하며, 살짝 좌->우로 이동
                    for i in range(num_frames):
                        t = i / (num_frames - 1)

                        # 크기: 0.7배(멀리) -> 1.0배(가까이)
                        scale = 0.7 + 0.3 * t
                        new_w, new_h = int(W * scale), int(H * scale)
                        resized = original.resize((new_w, new_h))

                        canvas = Image.new("RGB", (W, H), (255, 255, 255))

                        # 좌우 이동 (전체 폭의 20% 정도만 살짝 이동)
                        x_shift = int(-W * 0.12 + W * 0.24 * t)

                        # 통통 튀기 옵션이 켜져 있으면 위아래도 살짝
                        bounce_offset = int(4 * abs(math.sin(t * 8 * 3.14159))) if use_bounce else 0

                        paste_x = (W - new_w) // 2 + x_shift
                        paste_y = (H - new_h) // 2 - bounce_offset

                        canvas.paste(resized, (paste_x, paste_y))
                        frames.append(canvas)
                else:
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
                        zoomed = original.resize((new_w, new_h))

                        left = (new_w - W) // 2 + shift_x
                        top = (new_h - H) // 2 - shift_y
                        left = max(0, min(left, new_w - W))
                        top = max(0, min(top, new_h - H))

                        frame = zoomed.crop((left, top, left + W, top + H))
                        frames.append(frame)

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
import streamlit as st
from PIL import Image
import io

st.set_page_config(page_title="이미지 → GIF 변환기", page_icon="🎞️")

st.title("🎞️ 이미지를 움직이는 GIF로")
st.caption("사진을 올리면 통통 튀고, 살짝 확대되고, 좌우로 흔들리는 GIF로 만들어드려요")

uploaded_file = st.file_uploader("이미지를 올려주세요", type=["png", "jpg", "jpeg"])

if uploaded_file:
    original = Image.open(uploaded_file).convert("RGB")
    st.image(original, caption="원본 이미지", use_container_width=True)

    if st.button("GIF로 변환하기"):
        with st.spinner("변환 중이에요..."):
            W, H = original.size
            num_frames = 16
            frames = []

            for i in range(num_frames):
                t = i / num_frames

                # 1. 줌 효과 (1.0배 ~ 1.08배 사이를 왔다갔다)
                zoom = 1.0 + 0.04 * (1 + __import__("math").sin(t * 2 * 3.14159))
                new_w, new_h = int(W * zoom), int(H * zoom)
                zoomed = original.resize((new_w, new_h))

                # 2. 좌우 흔들림
                shift_x = int(6 * __import__("math").sin(t * 4 * 3.14159))
                # 3. 상하 통통 튀기
                shift_y = int(5 * abs(__import__("math").sin(t * 6 * 3.14159)))

                # 중앙 기준으로 크롭해서 원본 크기로 되돌리며 흔들림 반영
                left = (new_w - W) // 2 + shift_x
                top = (new_h - H) // 2 - shift_y
                left = max(0, min(left, new_w - W))
                top = max(0, min(top, new_h - H))

                frame = zoomed.crop((left, top, left + W, top + H))
                frames.append(frame)

            gif_buffer = io.BytesIO()
            frames[0].save(
                gif_buffer,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=80,
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
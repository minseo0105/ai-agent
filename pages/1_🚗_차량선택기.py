import streamlit as st
import pandas as pd

st.set_page_config(page_title="차량 선택기", page_icon="🚗", layout="centered")

st.markdown("""
<style>
    .block-container {
        padding-top: 2rem;
        max-width: 700px;
    }

    h1 {
        text-align: center;
        font-size: 2rem !important;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        text-align: center;
        color: #888;
        margin-bottom: 2rem;
    }

    /* 이미지 카드 느낌 */
    [data-testid="stImage"] {
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }

    /* 모델 선택 드롭다운 */
    [data-testid="stSelectbox"] {
        margin-bottom: 1.5rem;
    }

    /* 색상 버튼을 동그랗게 */
    .stButton > button {
        border-radius: 50px !important;
        padding: 0.5rem 1.5rem !important;
        border: 2px solid #e0e0e0 !important;
        font-weight: 600 !important;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        border-color: #4472C4 !important;
        color: #4472C4 !important;
        transform: translateY(-2px);
    }

    /* 가격 정보 카드 */
    .price-card {
        background: linear-gradient(135deg, #f8f9ff 0%, #eef2ff 100%);
        border-radius: 16px;
        padding: 1.5rem;
        margin-top: 1.5rem;
        text-align: center;
    }

    .price-card .model-name {
        font-size: 1.4rem;
        font-weight: 700;
        color: #333;
        margin-bottom: 0.3rem;
    }

    .price-card .color-name {
        color: #4472C4;
        font-weight: 600;
        margin-bottom: 1rem;
    }

    .price-card .price-row {
        display: flex;
        justify-content: space-around;
        margin-top: 1rem;
    }

    .price-card .price-item {
        text-align: center;
    }

    .price-card .price-label {
        font-size: 0.85rem;
        color: #888;
    }

    .price-card .price-value {
        font-size: 1.3rem;
        font-weight: 700;
        color: #333;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚗 차량 선택기")
st.markdown('<p class="subtitle">원하는 모델과 색상을 골라보세요</p>', unsafe_allow_html=True)

df = pd.read_excel("sample_cars.xlsx", sheet_name="차량목록")

model_list = df["모델"].unique()
selected_model = st.selectbox("모델 선택", model_list, label_visibility="collapsed")

filtered = df[df["모델"] == selected_model]

if "selected_color" not in st.session_state:
    st.session_state.selected_color = filtered.iloc[0]["색상"]

colors = filtered["색상"].tolist()
if st.session_state.selected_color not in colors:
    st.session_state.selected_color = colors[0]

selected_row = filtered[filtered["색상"] == st.session_state.selected_color].iloc[0]

st.image(f"car_images/{selected_row['이미지파일명']}", use_container_width=True)

st.write("")
cols = st.columns(len(colors))
for i, color in enumerate(colors):
    with cols[i]:
        if st.button(color, use_container_width=True, key=f"color_{color}"):
            st.session_state.selected_color = color

st.markdown(f"""
<div class="price-card">
    <div class="model-name">{selected_row['모델']}</div>
    <div class="color-name">{selected_row['색상']}</div>
    <div class="price-row">
        <div class="price-item">
            <div class="price-label">차량 가격</div>
            <div class="price-value">{selected_row['가격(만원)']:,}만원</div>
        </div>
        <div class="price-item">
            <div class="price-label">월 리스료</div>
            <div class="price-value">{selected_row['월리스료(만원)']:,}만원</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
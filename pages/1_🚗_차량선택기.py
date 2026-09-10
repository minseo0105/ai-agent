import streamlit as st
import pandas as pd

st.set_page_config(page_title="차량 견적기", page_icon="🚘", layout="wide")

st.markdown("""
<style>
    .block-container {
        max-width: 750px;
        padding-top: 2rem;
    }
    h1 {
        text-align: center;
        font-size: 1.9rem !important;
    }
    .subtitle {
        text-align: center;
        color: #7B8794;
        margin-bottom: 2rem;
    }
    [data-testid="stImage"] {
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 6px 24px rgba(30, 41, 59, 0.08);
    }
    .stButton > button {
        border-radius: 16px !important;
        font-weight: 600 !important;
        border: 2px solid #E2E8F0 !important;
        padding: 1.2rem 0.5rem !important;
        height: auto !important;
    }
    .stButton > button:hover {
        border-color: #2563EB !important;
        color: #2563EB !important;
        background-color: #F5F8FF !important;
    }
    .persona-emoji {
        font-size: 3rem;
        text-align: center;
    }
    .persona-desc {
        text-align: center;
        color: #64748B;
        font-size: 0.85rem;
    }
    .quote-card {
        background: linear-gradient(135deg, #EEF2FF 0%, #E0E9FF 100%);
        border-radius: 20px;
        padding: 2rem;
        margin-top: 1.5rem;
        text-align: center;
        border: 1px solid #D6E0FA;
    }
    .quote-card .model-name {
        font-size: 1.5rem;
        font-weight: 800;
        color: #1E293B;
    }
    .quote-card .color-badge {
        display: inline-block;
        background: #2563EB;
        color: white;
        border-radius: 20px;
        padding: 0.2rem 0.9rem;
        font-size: 0.85rem;
        margin-top: 0.4rem;
        font-weight: 600;
    }
    .quote-card .divider-line {
        height: 1px;
        background: #C7D2FE;
        margin: 1.2rem 0;
    }
    .quote-row {
        display: flex;
        justify-content: space-between;
        padding: 0.4rem 0;
        font-size: 1rem;
        color: #334155;
    }
    .quote-row .highlight {
        color: #2563EB;
        font-weight: 800;
        font-size: 1.4rem;
    }
    .step-badge {
        display: inline-block;
        background: #2563EB;
        color: white;
        border-radius: 20px;
        padding: 0.15rem 0.8rem;
        font-size: 0.8rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ---- 퀴즈 데이터 ----
questions = [
    {
        "question": "주로 어떤 상황에서 운전하시나요?",
        "options": [
            {"emoji": "🏙️", "label": "출퇴근/도심 위주", "desc": "복잡한 도심에서 편하게", "type": "세단"},
            {"emoji": "🏞️", "label": "레저/캠핑 위주", "desc": "가끔은 자연 속으로", "type": "SUV"},
        ]
    },
    {
        "question": "주로 몇 명이 함께 타시나요?",
        "options": [
            {"emoji": "🧑", "label": "1~2명", "desc": "가볍고 날렵하게", "type": "세단"},
            {"emoji": "👨‍👩‍👧‍👦", "label": "3명 이상", "desc": "넉넉한 공간이 필요해요", "type": "SUV"},
        ]
    },
    {
        "question": "선호하는 이미지는 어떤 쪽인가요?",
        "options": [
            {"emoji": "✨", "label": "세련되고 날렵한", "desc": "낮고 매끈한 라인", "type": "세단"},
            {"emoji": "🛡️", "label": "든든하고 넉넉한", "desc": "높고 안정감 있는 차체", "type": "SUV"},
        ]
    },
]

# ---- 상태 초기화 ----
if "quiz_step" not in st.session_state:
    st.session_state.quiz_step = 0
if "quiz_answers" not in st.session_state:
    st.session_state.quiz_answers = []

st.title("🚘 나에게 맞는 차량 찾기")

# ---- 퀴즈 진행 화면 ----
if st.session_state.quiz_step < len(questions):
    step = st.session_state.quiz_step
    q = questions[step]

    st.markdown(f'<div class="step-badge">STEP {step + 1} / {len(questions)}</div>', unsafe_allow_html=True)
    st.subheader(q["question"])

    cols = st.columns(len(q["options"]))
    for i, opt in enumerate(q["options"]):
        with cols[i]:
            st.markdown(f'<div class="persona-emoji">{opt["emoji"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="persona-desc">{opt["desc"]}</div>', unsafe_allow_html=True)
            if st.button(opt["label"], use_container_width=True, key=f"q{step}_{i}"):
                st.session_state.quiz_answers.append(opt["type"])
                st.session_state.quiz_step += 1
                st.rerun()

    if step > 0:
        if st.button("← 이전으로"):
            st.session_state.quiz_step -= 1
            st.session_state.quiz_answers.pop()
            st.rerun()

else:
    # ---- 퀴즈 결과 계산 ----
    sedan_count = st.session_state.quiz_answers.count("세단")
    suv_count = st.session_state.quiz_answers.count("SUV")
    recommended_type = "세단" if sedan_count >= suv_count else "SUV"

    st.success(f"당신에게 어울리는 차종은 **{recommended_type}**이에요!")

    if st.button("🔄 처음부터 다시 하기"):
        st.session_state.quiz_step = 0
        st.session_state.quiz_answers = []
        if "selected_color" in st.session_state:
            del st.session_state["selected_color"]
        st.rerun()

    st.divider()

    df = pd.read_excel("sample_cars_v2.xlsx", sheet_name="차량목록")
    filtered_type = df[df["차종"] == recommended_type]

    model_list = filtered_type["모델"].unique()
    selected_model = st.selectbox("모델을 선택하세요", model_list)

    filtered = filtered_type[filtered_type["모델"] == selected_model]

    if "selected_color" not in st.session_state:
        st.session_state.selected_color = filtered.iloc[0]["색상"]

    colors = filtered["색상"].tolist()
    if st.session_state.selected_color not in colors:
        st.session_state.selected_color = colors[0]

    selected_row = filtered[filtered["색상"] == st.session_state.selected_color].iloc[0]

    st.image(f"car_images_real/{selected_row['이미지파일명']}", use_container_width=True)

    st.write("색상을 선택하세요")
    cols = st.columns(len(colors))
    for i, color in enumerate(colors):
        with cols[i]:
            if st.button(color, use_container_width=True, key=f"color_{color}"):
                st.session_state.selected_color = color

    selected_row = filtered[filtered["색상"] == st.session_state.selected_color].iloc[0]

    st.write("렌트 기간을 선택하세요")
    months = st.select_slider("개월수", options=[12, 24, 36, 48, 60], value=36)

    price_manwon = int(selected_row["차량가격(만원)"])
    residual_rate = max(0.35, 0.75 - (months / 100))
    monthly_fee = round((price_manwon * (1 - residual_rate)) / months + (price_manwon * 0.012), 1)

    st.markdown(f"""
    <div class="quote-card">
        <div class="model-name">{selected_row['모델']}</div>
        <div class="color-badge">{selected_row['색상']}</div>
        <div class="divider-line"></div>
        <div class="quote-row">
            <span>차량 가격</span>
            <span>{price_manwon:,}만원</span>
        </div>
        <div class="quote-row">
            <span>렌트 기간</span>
            <span>{months}개월</span>
        </div>
        <div class="divider-line"></div>
        <div class="quote-row">
            <span>예상 월 렌트료</span>
            <span class="highlight">{monthly_fee:,}만원</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.caption("※ 위 견적은 참고용 예상치이며, 실제 견적과 다를 수 있어요.")
import streamlit as st
import pandas as pd
from pathlib import Path
import base64
import re
import hashlib

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="내 차에서 드림카까지",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="collapsed"
)

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = BASE_DIR / "sample_cars_v2.xlsx"
IMAGE_DIR = BASE_DIR / "car_images_cutout"
GIF_DIR = BASE_DIR / "dreamcar_gifs"

# 시연용 고정 금리
DEMO_APR = 5.9


# =========================================================
# 공통 함수
# =========================================================
def html(content):
    clean = "\n".join(line.strip() for line in content.splitlines())
    st.markdown(clean, unsafe_allow_html=True)


def image_data_uri(path):
    if not path.exists():
        return ""

    suffix = path.suffix.lower()

    if suffix == ".png":
        mime = "image/png"
    elif suffix == ".gif":
        mime = "image/gif"
    else:
        mime = "image/jpeg"

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


@st.cache_data
def load_car_data():
    return pd.read_excel(EXCEL_PATH, sheet_name="차량목록")


def reset_all():
    keys = [
        "flow_step", "has_car", "plate_no", "owned_car",
        "persona_step", "persona_answers", "color", "months"
    ]
    for key in keys:
        st.session_state.pop(key, None)
    st.rerun()


def normalize_plate(value):
    return re.sub(r"\s+", "", value.strip())


def valid_plate(value):
    """
    프로토타입용 간단한 번호판 형식 검증.
    실제 서비스에서는 차량등록정보 조회 API의 응답으로 검증해야 합니다.
    """
    value = normalize_plate(value)
    patterns = [
        r"^\d{2,3}[가-힣]\d{4}$",
        r"^[가-힣]{1,2}\d{2}[가-힣]\d{4}$",
    ]
    return any(re.match(p, value) for p in patterns)


def demo_used_car_lookup(plate):
    """
    시연용 중고차 조회 함수.
    번호판을 기반으로 항상 동일한 차량/시세가 반환되도록 구성했습니다.

    실제 서비스 적용 시 이 함수만
    - 차량등록정보 API
    - 중고차 시세 API
    로 교체하면 됩니다.
    """
    demo_cars = [
        {
            "model": "2020 그랜저",
            "year": 2020,
            "mileage": 52000,
            "market": 2350,
            "range_low": 2200,
            "range_high": 2490,
            "grade": "양호"
        },
        {
            "model": "2021 쏘나타",
            "year": 2021,
            "mileage": 41000,
            "market": 1840,
            "range_low": 1710,
            "range_high": 1970,
            "grade": "양호"
        },
        {
            "model": "2020 팰리세이드",
            "year": 2020,
            "mileage": 63000,
            "market": 3080,
            "range_low": 2920,
            "range_high": 3260,
            "grade": "보통"
        },
        {
            "model": "2021 카니발",
            "year": 2021,
            "mileage": 57000,
            "market": 2980,
            "range_low": 2810,
            "range_high": 3150,
            "grade": "양호"
        },
        {
            "model": "2019 싼타페",
            "year": 2019,
            "mileage": 76000,
            "market": 2060,
            "range_low": 1910,
            "range_high": 2180,
            "grade": "보통"
        },
        {
            "model": "2022 아반떼",
            "year": 2022,
            "mileage": 29000,
            "market": 1870,
            "range_low": 1760,
            "range_high": 1990,
            "grade": "우수"
        },
    ]

    digest = hashlib.sha256(plate.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(demo_cars)
    car = demo_cars[index].copy()
    car["plate"] = plate
    return car


def monthly_installment(principal_manwon, months, annual_rate=DEMO_APR):
    """
    원리금균등 방식 월 납입금.
    principal_manwon: 만원 단위
    return: 월 납입금(만원), 총 이자(만원)
    """
    if principal_manwon <= 0:
        return 0.0, 0.0

    principal = principal_manwon * 10000
    monthly_rate = annual_rate / 100 / 12

    if monthly_rate == 0:
        monthly = principal / months
    else:
        monthly = (
            principal
            * monthly_rate
            * (1 + monthly_rate) ** months
            / ((1 + monthly_rate) ** months - 1)
        )

    total_payment = monthly * months
    total_interest = total_payment - principal

    return monthly / 10000, total_interest / 10000


# =========================================================
# 추천 질문용 GIF 비주얼
# dreamcar_gifs 폴더의 실제 GIF 파일을 사용합니다.
# =========================================================
CITY = "city_drive.gif"
TRIP = "road_trip.gif"
DUO = "duo_drive.gif"
FAMILY = "family_trip.gif"
STYLE = "design_motion.gif"
SPACE = "cargo_space.gif"


def gif_uri(filename):
    return image_data_uri(GIF_DIR / filename)


# =========================================================
# 페르소나 질문
# =========================================================
questions = [
    {
        "title": "당신의 주말은 어느 장면에 더 가깝나요?",
        "desc": "평소 가장 자연스럽게 반복되는 이동 장면을 골라주세요.",
        "options": [
            {"art": CITY, "label": "도심을 가볍게 누비는 편", "desc": "맛집 · 카페 · 쇼핑 · 근거리 이동"},
            {"art": TRIP, "label": "주말이면 멀리 떠나는 편", "desc": "여행 · 캠핑 · 레저 · 장거리 이동"},
        ]
    },
    {
        "title": "차 안에서 가장 자주 함께하는 사람은?",
        "desc": "누구와 이동하는지가 공간과 편안함의 기준을 바꿉니다.",
        "options": [
            {"art": DUO, "label": "혼자 또는 둘이", "desc": "나의 감도와 이동 편의가 중요해요"},
            {"art": FAMILY, "label": "가족과 함께", "desc": "사람과 짐, 일정까지 함께 담아야 해요"},
        ]
    },
    {
        "title": "차를 고를 때 마지막까지 포기하기 어려운 것은?",
        "desc": "마지막 선택으로 드림카 추천의 방향을 완성합니다.",
        "options": [
            {"art": STYLE, "label": "볼 때마다 마음에 드는 디자인", "desc": "스타일 · 주행감 · 소유 만족감"},
            {"art": SPACE, "label": "필요할 때 든든한 공간", "desc": "수납 · 안정감 · 다양한 상황 대응력"},
        ]
    },
]


# =========================================================
# 8개 조합 추천
# =========================================================
recommendation_map = {
    (0,0,0): {
        "name":"CITY CURATOR",
        "sub":"도시의 장면을 고르는 사람",
        "copy":"도심에서의 편안함과 세련된 감도를 함께 중요하게 생각합니다.",
        "quote":"\u201c내 일상의 템포와 가장 자연스럽게 맞는 차.\u201d",
        "model":"디 올 뉴 그랜저",
        "reasons":["도심 활용성","정제된 승차감","디자인 만족도"],
        "art":CITY,
        "match":96
    },
    (0,0,1): {
        "name":"SMART MINIMALIST",
        "sub":"필요한 만큼 정확하게 고르는 사람",
        "copy":"과한 크기보다 일상에서 자주 쓰는 편의와 효율을 중요하게 봅니다.",
        "quote":"\u201c좋은 선택은 더 많이 갖는 것이 아니라 딱 맞게 갖는 것.\u201d",
        "model":"쏘나타",
        "reasons":["운전 편의성","합리적 이용","데일리 실용성"],
        "art":SPACE,
        "match":93
    },
    (0,1,0): {
        "name":"URBAN HOST",
        "sub":"함께 타는 순간까지 세련되게 만드는 사람",
        "copy":"동승자의 편안함과 도심에서의 세련된 주행감을 함께 중요하게 봅니다.",
        "quote":"\u201c함께 타는 사람도, 나도 만족하는 균형.\u201d",
        "model":"디 올 뉴 그랜저",
        "reasons":["동승자 편안함","도심 주행감","프리미엄 감성"],
        "art":FAMILY,
        "match":94
    },
    (0,1,1): {
        "name":"FAMILY NAVIGATOR",
        "sub":"가족의 매일을 더 여유롭게 설계하는 사람",
        "copy":"도심에서도 다루기 편하면서 가족을 위한 공간과 안정감도 충분해야 합니다.",
        "quote":"\u201c가족의 하루가 편해지면, 내 하루도 편해진다.\u201d",
        "model":"디 올 뉴 팰리세이드",
        "reasons":["가족 이동 최적화","넉넉한 실내","도심·주말 균형"],
        "art":FAMILY,
        "match":97
    },
    (1,0,0): {
        "name":"ROAD VOYAGER",
        "sub":"가는 길의 감도를 즐기는 사람",
        "copy":"목적지뿐 아니라 이동하는 시간 자체의 편안함과 감성을 중요하게 생각합니다.",
        "quote":"\u201c목적지보다 가는 길이 기억에 남는 차.\u201d",
        "model":"디 올 뉴 그랜저",
        "reasons":["장거리 승차감","주행 감성","디자인 완성도"],
        "art":TRIP,
        "match":92
    },
    (1,0,1): {
        "name":"FREEDOM EXPLORER",
        "sub":"주말의 반경을 자유롭게 넓히는 사람",
        "copy":"여행과 레저를 위해 SUV의 공간과 안정감을 적극적으로 활용하는 타입입니다.",
        "quote":"\u201c차가 커지는 것이 아니라, 갈 수 있는 곳이 많아진다.\u201d",
        "model":"디 올 뉴 팰리세이드",
        "reasons":["여행 활용성","적재 공간","장거리 안정감"],
        "art":TRIP,
        "match":95
    },
    (1,1,0): {
        "name":"WEEKEND DIRECTOR",
        "sub":"가족의 특별한 주말을 만드는 사람",
        "copy":"가족 여행의 편안함과 차량의 존재감, 디자인 모두를 중요하게 생각합니다.",
        "quote":"\u201c함께하는 시간도, 그 장면도 특별하게.\u201d",
        "model":"디 올 뉴 팰리세이드",
        "reasons":["패밀리 여행","프리미엄 디자인","편안한 주행"],
        "art":STYLE,
        "match":96
    },
    (1,1,1): {
        "name":"LIFE ORCHESTRATOR",
        "sub":"가족의 모든 장면을 담아내는 사람",
        "copy":"사람과 짐, 여행과 일상까지 한 대의 차가 여러 역할을 해내길 원합니다.",
        "quote":"\u201c차 한 대가 가족의 가능성을 더 크게 만든다.\u201d",
        "model":"더 뉴 카니발",
        "reasons":["최대 공간 활용","다인승 편의성","여행·레저 확장성"],
        "art":SPACE,
        "match":98
    },
}


# =========================================================
# 세션 상태
# =========================================================
if "flow_step" not in st.session_state:
    st.session_state.flow_step = "tradein"
if "has_car" not in st.session_state:
    st.session_state.has_car = True
if "plate_no" not in st.session_state:
    st.session_state.plate_no = ""
if "owned_car" not in st.session_state:
    st.session_state.owned_car = None
if "persona_step" not in st.session_state:
    st.session_state.persona_step = 0
if "persona_answers" not in st.session_state:
    st.session_state.persona_answers = []
if "color" not in st.session_state:
    st.session_state.color = None
if "months" not in st.session_state:
    st.session_state.months = 48


# =========================================================
# 프리미엄 UI
# =========================================================
html("""
<style>
:root{
    --ink:#111827;
    --muted:#748094;
    --line:#E6EAF0;
    --blue:#315EF5;
    --violet:#7056E8;
    --navy:#07172D;
    --navy2:#173B70;
    --soft:#F6F8FB;
    --white:#FFFFFF;
}

html,body,[class*="css"]{
    font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}

.stApp{
    background:
      radial-gradient(circle at 92% 2%,rgba(66,98,255,.10),transparent 22%),
      radial-gradient(circle at 5% 46%,rgba(112,86,232,.05),transparent 18%),
      linear-gradient(180deg,#FAFBFD 0%,#F5F7FA 100%);
}

.block-container{
    max-width:1080px;
    padding-top:1rem;
    padding-bottom:3.2rem;
}

header[data-testid="stHeader"]{
    background:rgba(249,250,252,.78);
    backdrop-filter:blur(14px);
}

#MainMenu,footer{
    visibility:hidden;
}

/* =======================================================
   HERO
======================================================= */
.hero{
    position:relative;
    overflow:hidden;
    min-height:280px;
    border-radius:32px;
    padding:48px 50px;
    margin-bottom:16px;
    color:#fff;
    background:
      radial-gradient(circle at 82% 18%,rgba(115,148,255,.24),transparent 24%),
      linear-gradient(125deg,#061426 0%,#0D284F 60%,#244B9C 100%);
    box-shadow:0 25px 62px rgba(15,29,55,.16);
}

.hero:before,
.hero:after{
    content:"";
    position:absolute;
    border-radius:50%;
    border:1px solid rgba(255,255,255,.12);
}

.hero:before{
    width:300px;
    height:300px;
    right:-85px;
    top:-150px;
    animation:heroOrbit 8s ease-in-out infinite;
}

.hero:after{
    width:150px;
    height:150px;
    right:145px;
    bottom:-95px;
    background:rgba(101,136,255,.09);
    animation:heroFloat 6s ease-in-out infinite;
}

@keyframes heroOrbit{
    50%{transform:translate(-13px,13px) scale(1.04)}
}

@keyframes heroFloat{
    50%{transform:translateY(-13px)}
}

.hero-kicker{
    position:relative;
    z-index:2;
    color:#AAC3FF;
    font-size:10px;
    font-weight:900;
    letter-spacing:.18em;
}

.hero-title{
    position:relative;
    z-index:2;
    margin-top:11px;
    max-width:730px;
    font-size:41px;
    font-weight:900;
    line-height:1.17;
    letter-spacing:-.05em;
}

.hero-title span{
    background:linear-gradient(90deg,#FFFFFF,#BFD1FF);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}

.hero-desc{
    position:relative;
    z-index:2;
    margin-top:14px;
    max-width:690px;
    color:#D7E1F0;
    font-size:13px;
    line-height:1.72;
}

/* =======================================================
   FLOW
======================================================= */
.flowbar{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:8px;
    margin-bottom:14px;
}

.flow{
    position:relative;
    overflow:hidden;
    min-height:59px;
    padding:11px 13px;
    border:1px solid #E5E9F0;
    border-radius:16px;
    background:rgba(255,255,255,.86);
    box-shadow:0 5px 18px rgba(15,23,42,.025);
    color:#99A3B2;
    font-size:9px;
    font-weight:800;
}

.flow b{
    display:block;
    margin-bottom:3px;
    font-size:8px;
    letter-spacing:.07em;
}

.flow.active{
    color:#2856D9;
    border-color:#BFCCF8;
    background:linear-gradient(135deg,#F7F9FF,#EEF3FF);
}

.flow.active:after{
    content:"";
    position:absolute;
    left:0;right:0;bottom:0;
    height:3px;
    background:linear-gradient(90deg,#315EF5,#765AE8);
}

/* =======================================================
   LOOKUP
======================================================= */
.lookup{
    position:relative;
    overflow:hidden;
    padding:31px 32px 28px;
    border:1px solid var(--line);
    border-radius:27px;
    background:#FFFFFF;
    box-shadow:0 12px 34px rgba(15,23,42,.045);
}

.lookup:after{
    content:"12가 3456";
    position:absolute;
    right:30px;
    top:30px;
    padding:10px 18px;
    border-radius:10px;
    border:2px solid #25395B;
    background:#F8FAFD;
    color:#172B4D;
    font-size:19px;
    font-weight:900;
    letter-spacing:.08em;
    opacity:.18;
    transform:rotate(-4deg);
}

.lookup-kicker{
    color:#315EF5;
    font-size:9px;
    font-weight:900;
    letter-spacing:.12em;
}

.lookup-title{
    margin-top:6px;
    font-size:28px;
    font-weight:900;
    letter-spacing:-.04em;
    color:var(--ink);
}

.lookup-desc{
    margin-top:7px;
    max-width:670px;
    color:#7B8798;
    font-size:12px;
    line-height:1.66;
}

.lookup-notice{
    margin-top:14px;
    padding:11px 13px;
    border:1px solid #EEF1F5;
    border-radius:13px;
    background:#F8FAFC;
    color:#8D98A8;
    font-size:10px;
    line-height:1.55;
}

/* Streamlit radio + input */
div[role="radiogroup"]{
    gap:8px!important;
}

div[role="radiogroup"] label{
    padding:8px 12px!important;
    border:1px solid #E2E7EF!important;
    border-radius:12px!important;
    background:#FFFFFF!important;
}

div[data-baseweb="input"]{
    border-radius:13px!important;
}

/* =======================================================
   USED CAR VALUE
======================================================= */
.usedcar-card{
    display:grid;
    grid-template-columns:1.08fr .92fr;
    gap:10px;
    margin-top:14px;
}

.used-main{
    position:relative;
    overflow:hidden;
    min-height:215px;
    padding:25px 26px;
    border-radius:24px;
    color:#fff;
    background:
      radial-gradient(circle at 90% 10%,rgba(101,139,255,.21),transparent 23%),
      linear-gradient(128deg,#07172D,#17396E);
}

.used-main:after{
    content:"";
    position:absolute;
    width:145px;
    height:145px;
    right:-55px;
    bottom:-65px;
    border-radius:50%;
    background:rgba(111,150,255,.11);
}

.used-label{
    color:#AAC4FF;
    font-size:9px;
    font-weight:900;
    letter-spacing:.11em;
}

.used-model{
    margin-top:7px;
    font-size:26px;
    font-weight:900;
    letter-spacing:-.035em;
}

.used-sub{
    margin-top:4px;
    color:#C7D3E5;
    font-size:11px;
}

.used-value{
    margin-top:20px;
    color:#AFC6F7;
    font-size:10px;
}

.used-price{
    margin-top:1px;
    font-size:36px;
    font-weight:900;
    letter-spacing:-.045em;
}

.used-price span{
    margin-left:3px;
    color:#C6D6FA;
    font-size:14px;
}

.used-detail{
    padding:20px;
    border:1px solid var(--line);
    border-radius:24px;
    background:#FFFFFF;
}

.used-detail-row{
    display:flex;
    justify-content:space-between;
    padding:8px 0;
    border-bottom:1px solid #EFF2F6;
    color:#7D8999;
    font-size:11px;
}

.used-detail-row:last-child{
    border-bottom:none;
}

.used-detail-row strong{
    color:#28374E;
}

/* =======================================================
   PERSONA QUESTION
======================================================= */
.qbox{
    padding:23px 26px 21px;
    margin-bottom:13px;
    border:1px solid var(--line);
    border-radius:23px;
    background:#FFFFFF;
    box-shadow:0 8px 22px rgba(15,23,42,.035);
}

.qtop{
    display:flex;
    justify-content:space-between;
    color:#98A2B3;
    font-size:10px;
    font-weight:800;
}

.qtop b{
    color:#315EF5;
    letter-spacing:.1em;
}

.progress{
    height:4px;
    margin:10px 0 17px;
    border-radius:999px;
    background:#EAEDF3;
    overflow:hidden;
}

.progress div{
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#315EF5,#7257E7);
}

.qtitle{
    color:#101828;
    font-size:23px;
    font-weight:900;
    letter-spacing:-.035em;
}

.qdesc{
    margin-top:5px;
    color:#758195;
    font-size:12px;
}

/* GIF CHOICE CARD */
.choice{
    overflow:hidden;
    margin-bottom:7px;
    border:1px solid #E5E9F0;
    border-radius:23px;
    background:#FFFFFF;
    box-shadow:0 8px 23px rgba(15,23,42,.032);
    transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease;
}

.choice:hover{
    transform:translateY(-4px);
    border-color:#B7C5F8;
    box-shadow:0 17px 34px rgba(49,94,245,.085);
}

.choice-visual{
    height:190px;
    margin:9px;
    border-radius:18px;
    overflow:hidden;
    background:#EEF2F8;
}

.choice-visual img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
}

.choice-copy{
    padding:8px 19px 18px;
}

.choice-title{
    color:#182236;
    font-size:15px;
    font-weight:900;
}

.choice-desc{
    margin-top:4px;
    color:#8995A6;
    font-size:11px;
}

/* =======================================================
   BUTTONS
======================================================= */
.stButton>button{
    min-height:42px;
    border:1px solid #DFE4EC!important;
    border-radius:12px!important;
    background:#FFFFFF!important;
    color:#26354B!important;
    box-shadow:none!important;
    font-size:12px!important;
    font-weight:800!important;
    transition:.16s ease!important;
}

.stButton>button:hover{
    transform:translateY(-1px);
    border-color:#A7B9F7!important;
    color:#315EF5!important;
    box-shadow:0 7px 17px rgba(49,94,245,.07)!important;
}

button[kind="primary"]{
    min-height:48px!important;
    border:none!important;
    color:#FFFFFF!important;
    background:linear-gradient(135deg,#315EF5,#654FE1)!important;
    box-shadow:0 11px 24px rgba(49,94,245,.19)!important;
}

/* =======================================================
   RESULT PERSONA
======================================================= */
.result-title{
    margin-bottom:3px;
    color:#101828;
    font-size:31px;
    font-weight:900;
    letter-spacing:-.045em;
}

.result-desc{
    margin-bottom:13px;
    color:#7B8798;
    font-size:11px;
}

.persona{
    display:grid;
    grid-template-columns:220px 1fr;
    gap:26px;
    align-items:center;
    padding:25px 28px;
    border-radius:27px;
    color:#FFFFFF;
    background:
      radial-gradient(circle at 88% 12%,rgba(109,146,255,.22),transparent 21%),
      linear-gradient(124deg,#07162B,#102E5A 67%,#29498D);
    box-shadow:0 17px 39px rgba(15,23,42,.11);
}

.persona-visual{
    height:150px;
    overflow:hidden;
    border:1px solid rgba(255,255,255,.10);
    border-radius:20px;
    background:rgba(255,255,255,.06);
}

.persona-visual img{
    width:100%;
    height:100%;
    object-fit:cover;
    display:block;
    opacity:.94;
}

.persona-label{
    color:#AFC6FF;
    font-size:9px;
    font-weight:900;
    letter-spacing:.16em;
}

.persona-name{
    margin-top:5px;
    font-size:29px;
    font-weight:900;
    letter-spacing:-.035em;
}

.persona-sub{
    margin-top:2px;
    color:#D3DEF0;
    font-size:13px;
    font-weight:700;
}

.persona-copy{
    margin-top:8px;
    color:#E0E8F3;
    font-size:11px;
    line-height:1.64;
}

.persona-quote{
    display:inline-block;
    margin-top:9px;
    padding:7px 10px;
    border:1px solid rgba(255,255,255,.09);
    border-radius:999px;
    background:rgba(255,255,255,.07);
    font-size:10px;
}

/* =======================================================
   DREAM CAR
======================================================= */
.dream{
    position:relative;
    overflow:hidden;
    margin-top:13px;
    border:1px solid var(--line);
    border-radius:29px;
    background:#FFFFFF;
    box-shadow:0 14px 36px rgba(15,23,42,.05);
}

.dream-head{
    display:flex;
    justify-content:space-between;
    padding:27px 30px 0;
}

.dream-badge{
    display:inline-block;
    padding:5px 9px;
    border-radius:999px;
    background:#EEF3FF;
    color:#315EF5;
    font-size:9px;
    font-weight:900;
}

.dream-name{
    margin-top:8px;
    color:#101828;
    font-size:31px;
    font-weight:900;
    letter-spacing:-.045em;
}

.dream-copy{
    margin-top:4px;
    color:#7D8999;
    font-size:11px;
}

.match-score{
    text-align:right;
}

.match-score span{
    display:block;
    color:#98A2B3;
    font-size:9px;
    font-weight:900;
}

.match-score strong{
    color:#315EF5;
    font-size:31px;
    letter-spacing:-.04em;
}

.car-stage{
    position:relative;
    height:385px;
    display:flex;
    align-items:center;
    justify-content:center;
    overflow:hidden;
    background:
      radial-gradient(ellipse at 50% 62%,rgba(212,220,233,.68),transparent 35%),
      linear-gradient(180deg,#FFFFFF,#F3F5F8);
}

.car-stage:after{
    content:"";
    position:absolute;
    width:49%;
    height:15px;
    bottom:52px;
    border-radius:50%;
    background:rgba(20,31,48,.13);
    filter:blur(13px);
}

.car-stage img{
    position:relative;
    z-index:2;
    width:83%;
    height:86%;
    object-fit:contain;
    filter:drop-shadow(0 18px 14px rgba(20,31,47,.10));
    animation:carfloat 4.8s ease-in-out infinite;
}

@keyframes carfloat{
    50%{transform:translateY(-5px)}
}

.reason-row{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:7px;
    padding:0 21px 21px;
}

.reason{
    padding:11px 6px 4px;
    border-top:1px solid #E7EAF0;
}

.reason b{
    display:block;
    color:#315EF5;
    font-size:8px;
}

.reason span{
    display:block;
    margin-top:3px;
    color:#2C3A50;
    font-size:10px;
    font-weight:850;
}

/* =======================================================
   QUOTE - PREMIUM FINANCE CARD
======================================================= */
.quote{
    margin-top:14px;
    padding:28px 30px;
    border:1px solid #E3E7EE;
    border-radius:28px;
    background:#FFFFFF;
    box-shadow:0 14px 36px rgba(15,23,42,.045);
}

.quote-top{
    display:grid;
    grid-template-columns:1fr auto;
    gap:24px;
    align-items:start;
    padding-bottom:19px;
    border-bottom:1px solid #E9EDF2;
}

.quote-kicker{
    color:#315EF5;
    font-size:9px;
    font-weight:900;
    letter-spacing:.11em;
}

.quote-label{
    margin-top:5px;
    color:#667085;
    font-size:11px;
}

.quote-fee{
    margin-top:1px;
    color:#101828;
    font-size:41px;
    font-weight:900;
    letter-spacing:-.055em;
}

.quote-fee em{
    color:#315EF5;
    font-style:normal;
}

.quote-chip{
    padding:9px 12px;
    border-radius:999px;
    background:#F0F4FF;
    color:#315EF5;
    font-size:10px;
    font-weight:850;
}

.money-flow{
    display:grid;
    grid-template-columns:1fr 32px 1fr 32px 1fr;
    gap:7px;
    align-items:center;
    margin-top:18px;
}

.money-box{
    min-height:72px;
    padding:14px;
    border-radius:15px;
    background:#F7F9FC;
}

.money-box span{
    display:block;
    color:#8C97A8;
    font-size:9px;
}

.money-box strong{
    display:block;
    margin-top:4px;
    color:#26354B;
    font-size:13px;
}

.money-box.highlight{
    background:linear-gradient(135deg,#EEF3FF,#F3F0FF);
}

.money-box.highlight strong{
    color:#315EF5;
}

.operator{
    color:#A0A9B7;
    font-size:20px;
    font-weight:700;
    text-align:center;
}

.quote-details{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:7px;
    margin-top:9px;
}

.qdetail{
    padding:11px 12px;
    border:1px solid #F0F2F5;
    border-radius:13px;
    background:#FAFBFD;
}

.qdetail span{
    display:block;
    color:#929DAC;
    font-size:9px;
}

.qdetail strong{
    display:block;
    margin-top:3px;
    color:#314057;
    font-size:10px;
}

.quote-note{
    margin-top:11px;
    color:#A0A9B7;
    font-size:9px;
}

/* =======================================================
   MOBILE
======================================================= */
@media(max-width:760px){
    .hero{
        padding:34px 24px;
        min-height:auto;
    }

    .hero-title{
        font-size:31px;
    }

    .flowbar{
        grid-template-columns:1fr 1fr;
    }

    .usedcar-card,
    .persona{
        grid-template-columns:1fr;
    }

    .dream-head,
    .quote-top{
        display:block;
    }

    .match-score{
        margin-top:10px;
        text-align:left;
    }

    .car-stage{
        height:300px;
    }

    .reason-row,
    .quote-details{
        grid-template-columns:1fr;
    }

    .money-flow{
        grid-template-columns:1fr;
    }
}
</style>
""")


# =========================================================
# HERO + 진행 단계
# =========================================================
html("""
<div class="hero">
<div class="hero-kicker">MY CAR CHANGE JOURNEY</div>
<div class="hero-title">지금 타는 차의 가치에서,<br><span>다음 드림카까지 연결합니다.</span></div>
<div class="hero-desc">
내 차의 현재 가치를 확인하고, 라이프스타일을 바탕으로 새 차를 추천한 뒤
내 차 시세를 반영한 실제 교체 필요금액과 월 할부금을 한 번에 확인해보세요.
</div>
</div>
""")

step_labels = {
    "tradein": 1,
    "persona": 2,
    "result": 3,
}

current_no = step_labels.get(st.session_state.flow_step, 1)

html(f"""
<div class="flowbar">
<div class="flow {'active' if current_no >= 1 else ''}"><b>STEP 01</b>내 차 가치 확인</div>
<div class="flow {'active' if current_no >= 2 else ''}"><b>STEP 02</b>라이프스타일 분석</div>
<div class="flow {'active' if current_no >= 3 else ''}"><b>STEP 03</b>드림카 추천</div>
<div class="flow {'active' if current_no >= 3 else ''}"><b>STEP 04</b>교체 견적</div>
</div>
""")


# =========================================================
# STEP 1. 내 차 조회
# =========================================================
if st.session_state.flow_step == "tradein":

    html("""
    <div class="lookup">
    <div class="lookup-kicker">MY CURRENT CAR</div>
    <div class="lookup-title">지금 타고 있는 차가 있으신가요?</div>
    <div class="lookup-desc">
    차량이 있다면 번호판을 입력해 현재 차량과 예상 중고차 시세를 확인합니다.
    차량이 없다면 바로 드림카 찾기로 넘어갈 수 있습니다.
    </div>
    </div>
    """)

    st.write("")

    has_car = st.radio(
        "현재 차량 보유 여부",
        ["내 차가 있어요", "현재 차량이 없어요"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.session_state.has_car = has_car == "내 차가 있어요"

    if st.session_state.has_car:
        plate = st.text_input(
            "차량 번호",
            placeholder="예: 123가4567",
            value=st.session_state.plate_no
        )

        st.session_state.plate_no = plate

        c1, c2 = st.columns([2, 1])

        with c1:
            if st.button(
                "내 차 시세 조회하기 →",
                type="primary",
                use_container_width=True
            ):
                clean_plate = normalize_plate(plate)

                if not clean_plate:
                    st.warning("차량 번호를 입력해주세요.")
                elif not valid_plate(clean_plate):
                    st.warning("차량 번호 형식을 확인해주세요. 예: 123가4567")
                else:
                    st.session_state.owned_car = demo_used_car_lookup(clean_plate)
                    st.rerun()

        with c2:
            if st.button(
                "조회 없이 추천 시작",
                use_container_width=True
            ):
                st.session_state.owned_car = None
                st.session_state.flow_step = "persona"
                st.rerun()

        if st.session_state.owned_car:
            car = st.session_state.owned_car

            html(f"""
            <div class="usedcar-card">

            <div class="used-main">
            <div class="used-label">MY CAR ESTIMATED VALUE</div>
            <div class="used-model">{car["model"]}</div>
            <div class="used-sub">{car["plate"]} · {car["year"]}년식</div>
            <div class="used-value">예상 중고차 시세</div>
            <div class="used-price">{car["market"]:,}<span>만원</span></div>
            </div>

            <div class="used-detail">
            <div class="used-detail-row"><span>연식</span><strong>{car["year"]}년</strong></div>
            <div class="used-detail-row"><span>주행거리</span><strong>{car["mileage"]:,} km</strong></div>
            <div class="used-detail-row"><span>예상 시세범위</span><strong>{car["range_low"]:,} ~ {car["range_high"]:,}만원</strong></div>
            <div class="used-detail-row"><span>차량 상태</span><strong>{car["grade"]}</strong></div>
            </div>

            </div>
            """)

            html("""
            <div class="lookup-notice">
            현재 차량 조회와 시세는 프로토타입 시연용 데이터입니다.
            실제 서비스에서는 차량등록정보 및 중고차 시세 API를 연동하여 이 조회 영역을 교체할 수 있습니다.
            </div>
            """)

            st.write("")

            if st.button(
                "내 드림카 찾기 시작 →",
                type="primary",
                use_container_width=True
            ):
                st.session_state.flow_step = "persona"
                st.rerun()

    else:
        html("""
        <div class="lookup-notice">
        현재 차량이 없으므로 보상판매 금액 없이 신차 전체 가격을 기준으로 견적을 계산합니다.
        </div>
        """)

        if st.button(
            "내 드림카 찾기 시작 →",
            type="primary",
            use_container_width=True
        ):
            st.session_state.owned_car = None
            st.session_state.flow_step = "persona"
            st.rerun()


# =========================================================
# STEP 2. 페르소나
# =========================================================
elif st.session_state.flow_step == "persona":

    step = st.session_state.persona_step
    q = questions[step]
    progress = int(((step + 1) / len(questions)) * 100)

    html(f"""
    <div class="qbox">
    <div class="qtop">
    <b>MY DREAM CAR SIGNAL {step + 1}</b>
    <span>{step + 1} / {len(questions)}</span>
    </div>
    <div class="progress"><div style="width:{progress}%"></div></div>
    <div class="qtitle">{q["title"]}</div>
    <div class="qdesc">{q["desc"]}</div>
    </div>
    """)

    cols = st.columns(2, gap="large")

    for i, opt in enumerate(q["options"]):
        with cols[i]:
            art_uri = gif_uri(opt["art"])

            html(f"""
            <div class="choice">
            <div class="choice-visual">
            <img src="{art_uri}" alt="{opt["label"]}">
            </div>
            <div class="choice-copy">
            <div class="choice-title">{opt["label"]}</div>
            <div class="choice-desc">{opt["desc"]}</div>
            </div>
            </div>
            """)

            if st.button(
                "이 선택이 나와 가까워요",
                key=f"persona_{step}_{i}",
                use_container_width=True
            ):
                st.session_state.persona_answers.append(i)

                if step < len(questions) - 1:
                    st.session_state.persona_step += 1
                else:
                    st.session_state.flow_step = "result"

                st.rerun()

    if step > 0:
        back, _ = st.columns([1, 3])
        with back:
            if st.button("← 이전 선택", use_container_width=True):
                st.session_state.persona_answers.pop()
                st.session_state.persona_step -= 1
                st.rerun()


# =========================================================
# STEP 3/4. 추천 + 교체 견적
# =========================================================
else:
    if not GIF_DIR.exists():
        st.error(f"GIF 폴더가 없습니다: {GIF_DIR}")
        st.stop()

    df = load_car_data()

    key = tuple(st.session_state.persona_answers)
    recommendation = recommendation_map.get(
        key,
        recommendation_map[(0, 1, 1)]
    )

    model = recommendation["model"]

    models = df["모델"].dropna().astype(str).unique().tolist()
    if model not in models:
        model = models[0]

    filtered = df[
        df["모델"].astype(str) == model
    ].copy()

    colors = (
        filtered["색상"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    if st.session_state.color not in colors:
        st.session_state.color = colors[0]

    selected = filtered[
        filtered["색상"].astype(str) == st.session_state.color
    ].iloc[0]

    html("""
    <div class="result-title">당신의 드림카를 찾았습니다.</div>
    <div class="result-desc">
    기존 차량의 가치와 새로운 라이프스타일 추천을 연결해 실제 교체 견적까지 계산합니다.
    </div>
    """)

    persona_gif = gif_uri(recommendation["art"])

    html(f"""
    <div class="persona">
    <div class="persona-visual">
    <img src="{persona_gif}" alt="{recommendation["name"]}">
    </div>
    <div>
    <div class="persona-label">YOUR MOBILITY PERSONA</div>
    <div class="persona-name">{recommendation["name"]}</div>
    <div class="persona-sub">{recommendation["sub"]}</div>
    <div class="persona-copy">{recommendation["copy"]}</div>
    <div class="persona-quote">{recommendation["quote"]}</div>
    </div>
    </div>
    """)

    original_image = Path(str(selected["이미지파일명"]))
    png_name = original_image.with_suffix(".png").name
    image_path = IMAGE_DIR / png_name
    uri = image_data_uri(image_path)

    r1, r2, r3 = recommendation["reasons"]

    html(f"""
    <div class="dream">
    <div class="dream-head">

    <div>
    <span class="dream-badge">YOUR DREAM CAR</span>
    <div class="dream-name">{model}</div>
    <div class="dream-copy">
    선택한 라이프스타일에 가장 자연스럽게 어울리는 차량입니다.
    </div>
    </div>

    <div class="match-score">
    <span>LIFESTYLE MATCH</span>
    <strong>{recommendation["match"]}%</strong>
    </div>

    </div>

    <div class="car-stage">
    <img src="{uri}" alt="{model}">
    </div>

    <div class="reason-row">
    <div class="reason"><b>MATCH 01</b><span>{r1}</span></div>
    <div class="reason"><b>MATCH 02</b><span>{r2}</span></div>
    <div class="reason"><b>MATCH 03</b><span>{r3}</span></div>
    </div>

    </div>
    """)

    c1, c2 = st.columns(2, gap="medium")

    with c1:
        st.caption("COLOR")
        color_cols = st.columns(len(colors))
        for i, color in enumerate(colors):
            with color_cols[i]:
                label = (
                    f"✓ {color}"
                    if color == st.session_state.color
                    else color
                )
                if st.button(
                    label,
                    key=f"color_{i}",
                    use_container_width=True
                ):
                    st.session_state.color = color
                    st.rerun()

    with c2:
        st.caption("할부기간")
        terms = [24, 36, 48, 60]
        term_cols = st.columns(4)

        for i, term in enumerate(terms):
            with term_cols[i]:
                label = (
                    f"✓ {term}"
                    if term == st.session_state.months
                    else str(term)
                )
                if st.button(
                    label,
                    key=f"term_{term}",
                    use_container_width=True
                ):
                    st.session_state.months = term
                    st.rerun()

    selected = filtered[
        filtered["색상"].astype(str) == st.session_state.color
    ].iloc[0]

    new_price = int(float(selected["차량가격(만원)"]))

    tradein_value = (
        int(st.session_state.owned_car["market"])
        if st.session_state.owned_car
        else 0
    )

    finance_principal = max(
        new_price - tradein_value,
        0
    )

    monthly_payment, total_interest = monthly_installment(
        finance_principal,
        st.session_state.months,
        DEMO_APR
    )

    owned_name = (
        st.session_state.owned_car["model"]
        if st.session_state.owned_car
        else "보유차량 없음"
    )

    html(f"""
    <div class="quote">

    <div class="quote-top">
    <div>
    <div class="quote-kicker">DREAM CAR CHANGE QUOTE</div>
    <div class="quote-label">보상판매 반영 예상 월 할부금</div>
    <div class="quote-fee">월 <em>{monthly_payment:,.1f}만원</em></div>
    </div>
    <div class="quote-chip">
    {st.session_state.months}개월 · 연 {DEMO_APR:.1f}%
    </div>
    </div>

    <div class="money-flow">

    <div class="money-box">
    <span>추천 신차가격</span>
    <strong>{new_price:,}만원</strong>
    </div>

    <div class="operator">−</div>

    <div class="money-box">
    <span>내 차 예상 시세</span>
    <strong>{tradein_value:,}만원</strong>
    </div>

    <div class="operator">=</div>

    <div class="money-box highlight">
    <span>예상 할부원금</span>
    <strong>{finance_principal:,}만원</strong>
    </div>

    </div>

    <div class="quote-details">
    <div class="qdetail">
    <span>추천 차량</span>
    <strong>{model}</strong>
    </div>
    <div class="qdetail">
    <span>현재 차량</span>
    <strong>{owned_name}</strong>
    </div>
    <div class="qdetail">
    <span>선택 색상</span>
    <strong>{st.session_state.color}</strong>
    </div>
    <div class="qdetail">
    <span>예상 총 이자</span>
    <strong>{total_interest:,.0f}만원</strong>
    </div>
    </div>

    <div class="quote-note">
    ※ 프로토타입 기준 연 {DEMO_APR:.1f}% 원리금균등 상환 방식입니다.
    실제 시세, 금리, 취급수수료, 신용도, 차량 옵션 및 금융상품 조건에 따라 달라질 수 있습니다.
    </div>

    </div>
    """)

    st.write("")

    a, b, c = st.columns([2, 1, 1])

    with a:
        if st.button(
            "이 조건으로 상세 견적 보기 →",
            type="primary",
            use_container_width=True
        ):
            st.success(
                f"{model} / 할부원금 {finance_principal:,}만원 / "
                f"{st.session_state.months}개월 / "
                f"월 약 {monthly_payment:,.1f}만원"
            )

    with b:
        if st.button(
            "추천 다시 받기",
            use_container_width=True
        ):
            st.session_state.persona_step = 0
            st.session_state.persona_answers = []
            st.session_state.color = None
            st.session_state.flow_step = "persona"
            st.rerun()

    with c:
        if st.button(
            "처음부터",
            use_container_width=True
        ):
            reset_all()
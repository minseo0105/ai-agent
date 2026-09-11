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
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
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
# 추천 질문용 이미지형 SVG
# =========================================================
CITY = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="c1" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#DDE8FF"/><stop offset="1" stop-color="#F8FAFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#c1)"/>
<g class="bgmove" opacity=".76">
<rect x="40" y="60" width="47" height="105" rx="5" fill="#9DB0D1"/>
<rect x="101" y="30" width="61" height="135" rx="5" fill="#7693C3"/>
<rect x="176" y="76" width="48" height="89" rx="5" fill="#C0CBDD"/>
<rect x="241" y="45" width="72" height="120" rx="5" fill="#9FB1D0"/>
</g>
<path d="M0 165H420V210H0Z" fill="#DCE3ED"/>
<g class="carmove">
<path d="M123 164L146 142H217L245 164L269 170V185H104V171Z" fill="#17305B"/>
<path d="M152 146H211L229 163H136Z" fill="#86A4D3"/>
<circle cx="138" cy="184" r="12" fill="#101827"/>
<circle cx="239" cy="184" r="12" fill="#101827"/>
</g>
</svg>
"""

TRIP = """
<svg viewBox="0 0 420 210">
<rect width="420" height="210" fill="#EAF2FF"/>
<circle class="glow" cx="330" cy="45" r="24" fill="#FFD986"/>
<g class="bgmove">
<path d="M0 164L90 84L153 147L231 62L345 164Z" fill="#A5B8DA"/>
<path d="M81 164L161 104L219 152L291 91L420 164Z" fill="#6F8FC7"/>
</g>
<path d="M0 164H420V210H0Z" fill="#DEE7DF"/>
<g class="carmove">
<path d="M126 163L149 142H217L245 163L269 169V185H106V171Z" fill="#243C63"/>
<path d="M155 146H211L230 162H139Z" fill="#98ADD1"/>
<circle cx="140" cy="184" r="12" fill="#172233"/>
<circle cx="239" cy="184" r="12" fill="#172233"/>
</g>
</svg>
"""

DUO = """
<svg viewBox="0 0 420 210">
<rect width="420" height="210" fill="#EEF3FF"/>
<circle cx="210" cy="106" r="81" fill="#FFFFFF" opacity=".72"/>
<g class="float">
<rect x="112" y="66" width="81" height="98" rx="30" fill="#2E529C"/>
<circle cx="152" cy="72" r="22" fill="#CCD9F4"/>
</g>
<g class="float delay">
<rect x="228" y="66" width="81" height="98" rx="30" fill="#615AA8"/>
<circle cx="268" cy="72" r="22" fill="#DBD5F7"/>
</g>
</svg>
"""

FAMILY = """
<svg viewBox="0 0 420 210">
<rect width="420" height="210" fill="#EEF3FF"/>
<circle cx="210" cy="106" r="82" fill="#FFFFFF" opacity=".72"/>
<g class="float">
<rect x="88" y="67" width="72" height="96" rx="28" fill="#2C519A"/>
<circle cx="124" cy="72" r="21" fill="#CBD9F5"/>
</g>
<g class="float delay">
<rect x="260" y="67" width="72" height="96" rx="28" fill="#5D57A3"/>
<circle cx="296" cy="72" r="21" fill="#D9D3F5"/>
</g>
<g class="float delay2">
<rect x="177" y="103" width="66" height="62" rx="24" fill="#4971C0"/>
<circle cx="210" cy="107" r="18" fill="#DAE4F9"/>
</g>
</svg>
"""

STYLE = """
<svg viewBox="0 0 420 210">
<rect width="420" height="210" fill="#EFF3FB"/>
<ellipse cx="210" cy="171" rx="124" ry="13" fill="#CDD5E1" opacity=".58"/>
<g class="carmove">
<path d="M91 149L127 119H244L289 149L327 157V176H73V159Z" fill="#142A51"/>
<path d="M140 123H236L271 148H112Z" fill="#819CC8"/>
<circle cx="125" cy="175" r="16" fill="#101827"/>
<circle cx="278" cy="175" r="16" fill="#101827"/>
<path class="glow" d="M77 157H105M292 154H320" stroke="#86A8FF" stroke-width="6" stroke-linecap="round"/>
</g>
</svg>
"""

SPACE = """
<svg viewBox="0 0 420 210">
<rect width="420" height="210" fill="#EDF3FC"/>
<path d="M80 167V83C80 59 100 40 124 40H296C320 40 340 59 340 83V167" fill="#E8EDF5" stroke="#AABBD3" stroke-width="4"/>
<path d="M110 69H310V160H110Z" fill="#FFFFFF"/>
<g class="float">
<rect x="129" y="100" width="67" height="58" rx="10" fill="#345FAC"/>
<path d="M143 100V86H182V100" fill="none" stroke="#345FAC" stroke-width="7"/>
</g>
<g class="float delay">
<rect x="210" y="84" width="78" height="74" rx="11" fill="#7067B2"/>
<path d="M226 84V68H272V84" fill="none" stroke="#7067B2" stroke-width="7"/>
</g>
</svg>
"""


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
    --ink:#101828;
    --muted:#667085;
    --blue:#2A5CF4;
    --line:#E7EBF2;
    --soft:#F7F9FC;
}
html,body,[class*="css"]{
    font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
.stApp{
    background:
      radial-gradient(circle at 92% 0%,rgba(56,99,246,.09),transparent 22%),
      #F6F8FB;
}
.block-container{
    max-width:1060px;
    padding-top:1rem;
    padding-bottom:3rem;
}
header[data-testid="stHeader"]{
    background:rgba(246,248,251,.82);
    backdrop-filter:blur(10px);
}
#MainMenu,footer{visibility:hidden}

.hero{
    position:relative;
    overflow:hidden;
    border-radius:30px;
    padding:45px 49px;
    margin-bottom:17px;
    color:#fff;
    background:
      linear-gradient(122deg,#071426 0%,#102A51 60%,#244EA6 100%);
    box-shadow:0 22px 55px rgba(16,32,60,.13);
}
.hero:after{
    content:"";
    position:absolute;
    width:300px;height:300px;
    border-radius:50%;
    right:-105px;top:-160px;
    border:1px solid rgba(255,255,255,.12);
    animation:orb 8s ease-in-out infinite;
}
@keyframes orb{
    50%{transform:translate(-14px,14px)}
}
.hero-kicker{
    position:relative;z-index:2;
    color:#AAC4FF;
    font-size:10px;
    font-weight:900;
    letter-spacing:.18em;
}
.hero-title{
    position:relative;z-index:2;
    margin-top:10px;
    font-size:40px;
    font-weight:900;
    line-height:1.18;
    letter-spacing:-.05em;
}
.hero-title span{color:#C4D5FF}
.hero-desc{
    position:relative;z-index:2;
    margin-top:14px;
    max-width:680px;
    color:#D7E1F1;
    font-size:13px;
    line-height:1.72;
}

.flowbar{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:7px;
    margin-bottom:14px;
}
.flow{
    background:#fff;
    border:1px solid var(--line);
    border-radius:15px;
    padding:11px 13px;
    color:#98A2B3;
    font-size:9px;
    font-weight:800;
}
.flow.active{
    border-color:#AFC0F8;
    background:#F2F5FF;
    color:#2A5CF4;
}
.flow b{
    display:block;
    font-size:8px;
    margin-bottom:2px;
}

.lookup{
    background:#fff;
    border:1px solid var(--line);
    border-radius:27px;
    padding:29px 31px;
    box-shadow:0 11px 31px rgba(15,23,42,.045);
}
.lookup-kicker{
    font-size:9px;
    font-weight:900;
    color:#2A5CF4;
    letter-spacing:.12em;
}
.lookup-title{
    margin-top:6px;
    font-size:27px;
    font-weight:900;
    letter-spacing:-.04em;
    color:var(--ink);
}
.lookup-desc{
    margin-top:7px;
    max-width:670px;
    color:#7D8898;
    font-size:12px;
    line-height:1.65;
}
.lookup-notice{
    margin-top:16px;
    padding:11px 13px;
    background:#F7F9FC;
    border-radius:13px;
    color:#8A95A5;
    font-size:10px;
    line-height:1.55;
}

.usedcar-card{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:10px;
    margin-top:14px;
}
.used-main{
    background:
      radial-gradient(circle at 92% 10%,rgba(98,136,255,.18),transparent 22%),
      linear-gradient(125deg,#08172D,#17386B);
    color:#fff;
    border-radius:24px;
    padding:24px 25px;
}
.used-label{
    color:#AFC7FF;
    font-size:9px;
    font-weight:900;
    letter-spacing:.11em;
}
.used-model{
    margin-top:7px;
    font-size:25px;
    font-weight:900;
}
.used-sub{
    margin-top:5px;
    color:#C8D5E8;
    font-size:11px;
}
.used-value{
    margin-top:18px;
    color:#AFC7FF;
    font-size:10px;
}
.used-price{
    margin-top:2px;
    font-size:34px;
    font-weight:900;
}
.used-price span{
    color:#BFD2FF;
    font-size:15px;
}
.used-detail{
    background:#fff;
    border:1px solid var(--line);
    border-radius:24px;
    padding:20px;
}
.used-detail-row{
    display:flex;
    justify-content:space-between;
    padding:7px 0;
    border-bottom:1px solid #EEF1F5;
    font-size:11px;
    color:#7B8797;
}
.used-detail-row:last-child{border-bottom:none}
.used-detail-row strong{color:#26354B}

.qbox{
    background:#fff;
    border:1px solid var(--line);
    border-radius:23px;
    padding:23px 26px 21px;
    margin-bottom:13px;
    box-shadow:0 8px 22px rgba(15,23,42,.035);
}
.qtop{
    display:flex;
    justify-content:space-between;
    font-size:10px;
    color:#98A2B3;
    font-weight:800;
}
.qtop b{
    color:#2A5CF4;
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
    background:linear-gradient(90deg,#2A5CF4,#7257E7);
}
.qtitle{
    font-size:23px;
    font-weight:900;
    letter-spacing:-.035em;
    color:#101828;
}
.qdesc{
    margin-top:5px;
    font-size:12px;
    color:#758195;
}

.choice{
    overflow:hidden;
    background:#fff;
    border:1px solid var(--line);
    border-radius:22px;
    margin-bottom:7px;
    box-shadow:0 7px 20px rgba(15,23,42,.03);
    transition:.2s ease;
}
.choice:hover{
    transform:translateY(-3px);
    border-color:#B7C5F8;
    box-shadow:0 15px 31px rgba(42,92,244,.08);
}
.choice-visual{
    height:172px;
    margin:9px;
    border-radius:17px;
    overflow:hidden;
    background:#F1F4FA;
}
.choice-visual svg{
    width:100%;
    height:100%;
}
.choice-copy{
    padding:8px 19px 18px;
}
.choice-title{
    font-size:15px;
    font-weight:900;
    color:#182236;
}
.choice-desc{
    margin-top:4px;
    font-size:11px;
    color:#8995A6;
}

.bgmove{animation:bgmove 7s ease-in-out infinite}
.carmove{animation:carmove 5s ease-in-out infinite}
.float{animation:float 4s ease-in-out infinite}
.delay{animation-delay:.6s}
.delay2{animation-delay:1.1s}
.glow{animation:glow 2.8s ease-in-out infinite}
@keyframes bgmove{50%{transform:translateX(-5px)}}
@keyframes carmove{0%,100%{transform:translateX(-7px)}50%{transform:translateX(11px)}}
@keyframes float{50%{transform:translateY(-6px)}}
@keyframes glow{0%,100%{opacity:.48}50%{opacity:1}}

.stButton>button{
    min-height:42px;
    border-radius:12px!important;
    border:1px solid #DFE4EC!important;
    background:#fff!important;
    color:#26354B!important;
    font-size:12px!important;
    font-weight:800!important;
    box-shadow:none!important;
}
.stButton>button:hover{
    border-color:#A7B9F7!important;
    color:#2A5CF4!important;
    box-shadow:0 6px 16px rgba(42,92,244,.07)!important;
}
button[kind="primary"]{
    min-height:48px!important;
    border:none!important;
    color:#fff!important;
    background:linear-gradient(135deg,#2A5CF4,#624FE2)!important;
    box-shadow:0 10px 22px rgba(42,92,244,.18)!important;
}

.result-title{
    font-size:30px;
    color:#101828;
    font-weight:900;
    letter-spacing:-.045em;
    margin-bottom:3px;
}
.result-desc{
    color:#7B8798;
    font-size:11px;
    margin-bottom:13px;
}
.persona{
    display:grid;
    grid-template-columns:175px 1fr;
    gap:25px;
    align-items:center;
    padding:25px 28px;
    border-radius:26px;
    color:#fff;
    background:linear-gradient(122deg,#07162B,#112E58 68%,#294A8E);
    box-shadow:0 16px 37px rgba(15,23,42,.11);
}
.persona-visual{
    height:138px;
    border-radius:19px;
    overflow:hidden;
    background:rgba(255,255,255,.06);
    border:1px solid rgba(255,255,255,.1);
}
.persona-visual svg{width:100%;height:100%}
.persona-label{
    color:#AFC6FF;
    font-size:9px;
    font-weight:900;
    letter-spacing:.16em;
}
.persona-name{
    margin-top:5px;
    font-size:28px;
    font-weight:900;
}
.persona-sub{
    margin-top:2px;
    color:#D2DDF0;
    font-size:13px;
    font-weight:700;
}
.persona-copy{
    margin-top:8px;
    color:#E1E8F3;
    font-size:11px;
    line-height:1.62;
}
.persona-quote{
    display:inline-block;
    margin-top:9px;
    padding:7px 10px;
    border-radius:999px;
    background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.09);
    font-size:10px;
}

.dream{
    margin-top:13px;
    overflow:hidden;
    background:#fff;
    border:1px solid var(--line);
    border-radius:28px;
    box-shadow:0 13px 34px rgba(15,23,42,.05);
}
.dream-head{
    display:flex;
    justify-content:space-between;
    padding:26px 29px 0;
}
.dream-badge{
    display:inline-block;
    padding:5px 9px;
    border-radius:999px;
    background:#EEF3FF;
    color:#2A5CF4;
    font-size:9px;
    font-weight:900;
}
.dream-name{
    margin-top:8px;
    font-size:30px;
    font-weight:900;
    letter-spacing:-.045em;
    color:#101828;
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
    font-size:9px;
    color:#98A2B3;
    font-weight:900;
}
.match-score strong{
    font-size:30px;
    color:#2A5CF4;
}
.car-stage{
    position:relative;
    height:370px;
    display:flex;
    align-items:center;
    justify-content:center;
    overflow:hidden;
    background:linear-gradient(180deg,#fff,#F4F6F9);
}
.car-stage:before{
    content:"";
    position:absolute;
    width:68%;height:52%;
    border-radius:50%;
    background:radial-gradient(circle,rgba(219,225,235,.8),transparent 70%);
}
.car-stage:after{
    content:"";
    position:absolute;
    width:48%;height:15px;
    bottom:48px;
    border-radius:50%;
    background:rgba(20,31,48,.13);
    filter:blur(13px);
}
.car-stage img{
    position:relative;
    z-index:2;
    width:84%;
    height:86%;
    object-fit:contain;
    filter:drop-shadow(0 18px 14px rgba(20,31,47,.10));
    animation:carfloat 4.8s ease-in-out infinite;
}
@keyframes carfloat{50%{transform:translateY(-5px)}}
.reason-row{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:7px;
    padding:0 20px 20px;
}
.reason{
    padding:11px 5px 4px;
    border-top:1px solid #E7EAF0;
}
.reason b{
    display:block;
    font-size:8px;
    color:#2A5CF4;
}
.reason span{
    display:block;
    margin-top:3px;
    font-size:10px;
    color:#2C3A50;
    font-weight:850;
}

.quote{
    margin-top:13px;
    background:#fff;
    border:1px solid var(--line);
    border-radius:27px;
    padding:27px 29px;
    box-shadow:0 13px 34px rgba(15,23,42,.045);
}
.quote-top{
    display:flex;
    justify-content:space-between;
    gap:25px;
    align-items:flex-start;
    padding-bottom:18px;
    border-bottom:1px solid #E9EDF2;
}
.quote-kicker{
    color:#2A5CF4;
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
    font-size:39px;
    font-weight:900;
    letter-spacing:-.055em;
}
.quote-fee em{
    color:#2A5CF4;
    font-style:normal;
}
.quote-chip{
    padding:9px 12px;
    border-radius:999px;
    background:#F1F5FF;
    color:#2A5CF4;
    font-size:10px;
    font-weight:850;
}
.money-flow{
    display:grid;
    grid-template-columns:1fr auto 1fr auto 1fr;
    gap:8px;
    align-items:center;
    margin-top:18px;
}
.money-box{
    padding:14px;
    border-radius:15px;
    background:#F7F9FC;
}
.money-box span{
    display:block;
    font-size:9px;
    color:#8C97A8;
}
.money-box strong{
    display:block;
    margin-top:4px;
    font-size:13px;
    color:#26354B;
}
.money-box.highlight{
    background:#EEF3FF;
}
.money-box.highlight strong{
    color:#2A5CF4;
}
.operator{
    font-size:20px;
    color:#A0A9B7;
    font-weight:700;
}
.quote-details{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:7px;
    margin-top:9px;
}
.qdetail{
    padding:11px 12px;
    background:#FAFBFD;
    border-radius:13px;
}
.qdetail span{
    display:block;
    font-size:9px;
    color:#929DAC;
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

@media(max-width:760px){
    .hero{padding:34px 24px}
    .hero-title{font-size:31px}
    .flowbar{grid-template-columns:1fr 1fr}
    .usedcar-card,.persona{grid-template-columns:1fr}
    .dream-head,.quote-top{display:block}
    .match-score{text-align:left;margin-top:10px}
    .car-stage{height:295px}
    .reason-row,.quote-details{grid-template-columns:1fr}
    .money-flow{grid-template-columns:1fr}
    .operator{text-align:center}
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
            html(f"""
            <div class="choice">
            <div class="choice-visual">{opt["art"]}</div>
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

    html(f"""
    <div class="persona">
    <div class="persona-visual">{recommendation["art"]}</div>
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
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
EXCEL_PATH = BASE_DIR / "sample_cars_v3.xlsx"
IMAGE_DIR = BASE_DIR / "car_images_photoreal_39"
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
    if path is None:
        return ""

    path = Path(path)

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


@st.cache_data(show_spinner=False)
def load_car_data(excel_path):
    """
    엑셀 경로를 cache key에 포함시켜
    v2 -> v3 파일 변경 시 이전 차량 데이터가 남지 않도록 합니다.
    """
    return pd.read_excel(excel_path, sheet_name="차량목록")


def reset_all():
    keys = [
        "flow_step", "has_car", "plate_no", "owned_car",
        "persona_step", "persona_answers", "color", "months", "selected_model",
        "color_selector", "term_selector"
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



def resolve_car_image(filename):
    """
    차량 이미지 위치를 자동으로 찾습니다.

    지원 예:
    ai-agent/car_images_photoreal_39/gv80_white.jpg
    ai-agent/car_images_photoreal_39/car_images_photoreal_39/gv80_white.jpg
    ai-agent/어떤폴더/gv80_white.jpg

    엑셀에 .png가 적혀 있어도 같은 stem의 .jpg/.jpeg/.png를 찾습니다.
    """
    raw = Path(str(filename))
    stem = raw.stem.lower()

    # 1. 정상 위치 우선
    direct_candidates = [
        IMAGE_DIR / raw.name,
        IMAGE_DIR / f"{raw.stem}.jpg",
        IMAGE_DIR / f"{raw.stem}.jpeg",
        IMAGE_DIR / f"{raw.stem}.png",
        IMAGE_DIR / "car_images_photoreal_39" / f"{raw.stem}.jpg",
        IMAGE_DIR / "car_images_photoreal_39" / f"{raw.stem}.jpeg",
        IMAGE_DIR / "car_images_photoreal_39" / f"{raw.stem}.png",
    ]

    for candidate in direct_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    # 2. 이미지 폴더 내부 재귀 검색
    if IMAGE_DIR.exists():
        for candidate in IMAGE_DIR.rglob("*"):
            if (
                candidate.is_file()
                and candidate.suffix.lower() in [".jpg", ".jpeg", ".png"]
                and candidate.stem.lower() == stem
            ):
                return candidate

    # 3. 마지막 안전장치: ai-agent 루트 전체에서 검색
    for candidate in BASE_DIR.rglob("*"):
        if (
            candidate.is_file()
            and candidate.suffix.lower() in [".jpg", ".jpeg", ".png"]
            and candidate.stem.lower() == stem
        ):
            return candidate

    return None

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
# 페르소나 질문 - 4문항 × 3선택
# =========================================================
questions = [
    {
        "title": "평소 차량을 가장 많이 쓰는 장면은?",
        "desc": "일상에서 가장 자주 반복되는 이동 장면을 골라주세요.",
        "options": [
            {"art": "q1_city.gif", "label": "출퇴근 · 도심 이동", "desc": "주차와 기동성, 일상 편의가 중요해요", "scores": {"city": 3, "comfort": 1}},
            {"art": "q1_trip.gif", "label": "주말 여행 · 장거리", "desc": "장거리 안정감과 승차감을 중요하게 봐요", "scores": {"trip": 3, "comfort": 2}},
            {"art": "q1_mix.gif", "label": "도심과 여행을 반반", "desc": "평일과 주말을 모두 만족시키고 싶어요", "scores": {"city": 2, "trip": 2, "versatility": 2}},
        ]
    },
    {
        "title": "차 안에서 가장 자주 함께하는 사람은?",
        "desc": "동승 인원이 차량 크기와 공간의 기준을 크게 바꿉니다.",
        "options": [
            {"art": "q2_duo.gif", "label": "혼자 또는 둘이", "desc": "운전자 중심의 편안함과 감도가 중요해요", "scores": {"solo": 3, "style": 1}},
            {"art": "q2_family.gif", "label": "3~4인 가족", "desc": "가족이 편하면서도 너무 크지 않았으면 해요", "scores": {"family": 3, "space": 2}},
            {"art": "q2_large.gif", "label": "5인 이상 · 다인승", "desc": "사람과 짐을 넉넉하게 태울 공간이 필요해요", "scores": {"large_family": 4, "space": 4}},
        ]
    },
    {
        "title": "차를 고를 때 가장 중요하게 보는 것은?",
        "desc": "한 가지를 가장 우선한다면 무엇인가요?",
        "options": [
            {"art": "q3_style.gif", "label": "디자인 · 고급감", "desc": "볼 때마다 만족스럽고 품격 있는 차", "scores": {"style": 4, "premium": 3}},
            {"art": "q3_space.gif", "label": "공간 · 실용성", "desc": "짐과 사람을 편하게 담는 활용성", "scores": {"space": 4, "versatility": 3}},
            {"art": "q3_efficiency.gif", "label": "편안함 · 효율", "desc": "매일 타기 편하고 부담이 적은 차", "scores": {"comfort": 3, "value": 3}},
        ]
    },
    {
        "title": "새 차를 고를 때 가장 가까운 생각은?",
        "desc": "차급과 가격에 대한 선호를 반영해 추천을 정교하게 만듭니다.",
        "options": [
            {"art": "q4_value.gif", "label": "합리적인 가격이 우선", "desc": "필요한 기능은 충분하되 부담은 낮게", "scores": {"value": 5}},
            {"art": "q4_balance.gif", "label": "가격과 만족의 균형", "desc": "예산 안에서 한 단계 좋은 차를 원해요", "scores": {"balanced": 4, "premium": 1}},
            {"art": "q4_premium.gif", "label": "마음에 들면 차급을 올려도 좋아요", "desc": "가격보다 만족도와 완성도가 중요해요", "scores": {"premium": 5, "style": 2}},
        ]
    },
]

vehicle_profiles = {
    "아반떼": {
        "scores": {"city":6,"trip":1,"comfort":3,"solo":6,"family":1,"large_family":0,"space":1,"style":3,"premium":0,"value":6,"balanced":3,"versatility":2},
        "tagline":"가볍고 합리적인 도심형 준중형 세단",
        "reason_pool":["도심 주행 편의","합리적인 차량가격","초기 교체 부담 절감","데일리 효율성"],
    },
    "쏘나타": {
        "scores": {"city":5,"trip":3,"comfort":5,"solo":5,"family":3,"large_family":0,"space":2,"style":3,"premium":1,"value":5,"balanced":5,"versatility":3},
        "tagline":"편안함과 실용성을 고르게 갖춘 중형 세단",
        "reason_pool":["데일리 편안함","도심·장거리 균형","합리적인 가격","안정적인 승차감"],
    },
    "K5": {
        "scores": {"city":5,"trip":3,"comfort":4,"solo":5,"family":2,"large_family":0,"space":2,"style":5,"premium":2,"value":4,"balanced":4,"versatility":3},
        "tagline":"스타일을 중시하는 감각적인 중형 세단",
        "reason_pool":["스포티한 디자인","도심 주행 감도","가격·스타일 균형","운전자 중심 만족감"],
    },
    "디 올 뉴 그랜저": {
        "scores": {"city":4,"trip":4,"comfort":6,"solo":4,"family":3,"large_family":0,"space":2,"style":5,"premium":6,"value":2,"balanced":6,"versatility":3},
        "tagline":"편안함과 고급감을 함께 잡는 프리미엄 세단",
        "reason_pool":["프리미엄 감성","정숙한 승차감","도심·장거리 균형","높은 소유 만족감"],
    },
    "K8": {
        "scores": {"city":4,"trip":4,"comfort":5,"solo":4,"family":3,"large_family":0,"space":2,"style":5,"premium":5,"value":3,"balanced":6,"versatility":3},
        "tagline":"품격과 합리성의 균형을 갖춘 준대형 세단",
        "reason_pool":["준대형 세단의 여유","세련된 디자인","가격·차급 균형","편안한 장거리 주행"],
    },
    "투싼": {
        "scores": {"city":5,"trip":4,"comfort":4,"solo":4,"family":4,"large_family":1,"space":4,"style":3,"premium":1,"value":5,"balanced":5,"versatility":5},
        "tagline":"도심과 주말을 연결하는 실용적인 SUV",
        "reason_pool":["도심 친화적 크기","주말 활용성","SUV 실용 공간","균형 잡힌 차량가격"],
    },
    "스포티지": {
        "scores": {"city":5,"trip":4,"comfort":4,"solo":4,"family":4,"large_family":1,"space":4,"style":4,"premium":1,"value":5,"balanced":5,"versatility":5},
        "tagline":"스타일과 실용성을 함께 갖춘 준중형 SUV",
        "reason_pool":["감각적인 SUV 디자인","도심 활용성","가족 일상 적합","가격 대비 공간"],
    },
    "싼타페": {
        "scores": {"city":3,"trip":6,"comfort":5,"solo":2,"family":6,"large_family":3,"space":6,"style":4,"premium":3,"value":4,"balanced":5,"versatility":6},
        "tagline":"가족의 일상과 여행에 강한 중형 SUV",
        "reason_pool":["가족 이동 최적화","넉넉한 적재공간","여행·캠핑 활용성","편안한 장거리 주행"],
    },
    "쏘렌토": {
        "scores": {"city":3,"trip":6,"comfort":5,"solo":2,"family":6,"large_family":3,"space":6,"style":4,"premium":3,"value":4,"balanced":6,"versatility":6},
        "tagline":"패밀리와 장거리 활용의 균형형 SUV",
        "reason_pool":["패밀리 SUV 균형","도심·여행 대응력","넉넉한 공간","높은 활용 범위"],
    },
    "디 올 뉴 팰리세이드": {
        "scores": {"city":2,"trip":6,"comfort":6,"solo":1,"family":6,"large_family":5,"space":7,"style":5,"premium":5,"value":2,"balanced":4,"versatility":6},
        "tagline":"가족과 여행의 반경을 넓히는 대형 SUV",
        "reason_pool":["넉넉한 실내공간","가족 이동 최적화","장거리 안정감","대형 SUV의 존재감"],
    },
    "더 뉴 카니발": {
        "scores": {"city":1,"trip":6,"comfort":5,"solo":0,"family":6,"large_family":8,"space":8,"style":2,"premium":2,"value":3,"balanced":3,"versatility":8},
        "tagline":"사람과 짐을 모두 담는 패밀리 모빌리티",
        "reason_pool":["최대 공간 활용","다인승 편의성","가족·레저 활용성","다양한 좌석 활용"],
    },
    "GV70": {
        "scores": {"city":4,"trip":5,"comfort":5,"solo":5,"family":3,"large_family":0,"space":3,"style":7,"premium":7,"value":1,"balanced":4,"versatility":4},
        "tagline":"운전 감성과 고급감을 강조한 프리미엄 SUV",
        "reason_pool":["프리미엄 디자인","도심 주행 감성","고급 실내 만족감","SUV의 활용성"],
    },
    "GV80": {
        "scores": {"city":2,"trip":6,"comfort":7,"solo":2,"family":5,"large_family":3,"space":6,"style":7,"premium":8,"value":0,"balanced":4,"versatility":5},
        "tagline":"공간과 품격을 모두 원하는 프리미엄 대형 SUV",
        "reason_pool":["프리미엄 대형 SUV","최상급 승차감","가족과 비즈니스 활용","높은 소유 만족감"],
    },
}

def calculate_user_scores(answers):
    user_scores = {}
    for q_idx, option_idx in enumerate(answers):
        option = questions[q_idx]["options"][option_idx]
        for key, value in option["scores"].items():
            user_scores[key] = user_scores.get(key, 0) + value
    return user_scores

def rank_vehicles(answers, available_models):
    user_scores = calculate_user_scores(answers)
    ranked = []
    for model in available_models:
        if model not in vehicle_profiles:
            continue
        profile = vehicle_profiles[model]
        score = sum(v * profile["scores"].get(k, 0) for k, v in user_scores.items())
        ranked.append({"model": model, "score": score, "profile": profile})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    if not ranked:
        return []
    max_score = ranked[0]["score"] or 1
    for idx, item in enumerate(ranked):
        relative = item["score"] / max_score
        item["match"] = max(82, min(98, round(82 + relative * 16 - idx * 2)))
    return ranked

def build_persona(answers, ranked):
    s = calculate_user_scores(answers)
    family = s.get("family",0)+s.get("large_family",0)+s.get("space",0)
    premium = s.get("premium",0)+s.get("style",0)
    value = s.get("value",0)
    trip = s.get("trip",0)+s.get("versatility",0)

    if family >= 10:
        return {"name":"LIFE EXPANDER","sub":"가족의 모든 이동을 넓게 설계하는 사람","copy":"사람과 짐, 평일과 주말을 모두 고려하며 차량 한 대의 활용 범위를 크게 보는 타입입니다.","quote":"“차 한 대가 가족의 활동 반경을 넓혀준다.”","art":"persona_life.gif"}
    if premium >= 9:
        return {"name":"PREMIUM CURATOR","sub":"이동의 감도까지 고르는 사람","copy":"편안함과 디자인, 소유 만족도를 중요하게 보며 한 단계 높은 완성도를 선호합니다.","quote":"“매일 타는 차일수록 만족감이 중요하다.”","art":"persona_premium.gif"}
    if value >= 6:
        return {"name":"SMART SELECTOR","sub":"필요한 만큼 정확하게 고르는 사람","copy":"차량가격과 실용성을 함께 보며 매일 쓰는 기능에 집중해 효율적인 선택을 하는 타입입니다.","quote":"“좋은 차는 내 생활에 정확히 맞는 차.”","art":"persona_smart.gif"}
    if trip >= 7:
        return {"name":"WEEKEND VOYAGER","sub":"주말의 반경을 넓히는 사람","copy":"평일의 이동뿐 아니라 여행과 장거리 주행까지 고려해 활용성과 편안함을 함께 봅니다.","quote":"“차가 바뀌면 갈 수 있는 곳도 달라진다.”","art":"persona_weekend.gif"}
    return {"name":"BALANCE DRIVER","sub":"평일과 주말의 균형을 고르는 사람","copy":"편안함, 가격, 공간, 디자인 어느 하나에 치우치기보다 전체 균형을 중요하게 생각합니다.","quote":"“매일 타도 좋고, 주말에는 더 좋은 차.”","art":"persona_balance.gif"}


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
if "selected_model" not in st.session_state:
    st.session_state.selected_model = None


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

.top3-title{margin-top:15px;margin-bottom:5px;color:#101828;font-size:14px;font-weight:900}
.top3-sub{margin-bottom:10px;color:#8B96A6;font-size:10px}
.reco-card{min-height:154px;padding:17px;border:1px solid #E4E9F0;border-radius:19px;background:#fff;box-shadow:0 8px 21px rgba(15,23,42,.035)}
.reco-card.top{border-color:#B9C8FA;background:linear-gradient(145deg,#fff,#F3F6FF)}
.reco-rank{color:#315EF5;font-size:9px;font-weight:900;letter-spacing:.08em}
.reco-model{margin-top:6px;color:#172237;font-size:18px;font-weight:900;letter-spacing:-.035em}
.reco-tag{margin-top:4px;min-height:30px;color:#7D8999;font-size:9px;line-height:1.45}
.reco-match{margin-top:11px;color:#8A95A6;font-size:9px}
.reco-match strong{display:block;color:#315EF5;font-size:22px}


/* =======================================================
   TOP 3 - MOBILE FIRST
======================================================= */
.reco-photo{
    height:150px;
    margin:2px 0 7px;
    border-radius:18px;
    overflow:hidden;
    background:
      radial-gradient(circle at 50% 58%,rgba(221,228,239,.8),transparent 38%),
      linear-gradient(180deg,#FFFFFF,#F4F6F9);
    border:1px solid #EDF0F4;
}
.reco-photo img{
    width:100%;
    height:100%;
    object-fit:contain;
    padding:6px;
}
.reco-price{
    margin-top:7px;
    color:#7A8698;
    font-size:10px;
}
.reco-price b{
    color:#2C3B52;
}
.top3-guide{
    margin:12px 0 3px;
    padding:11px 13px;
    border-radius:14px;
    background:linear-gradient(135deg,#F0F5FF,#F5F1FF);
    color:#52627A;
    font-size:10px;
    line-height:1.55;
}


@media(max-width:760px){

    .block-container{
        max-width:100%!important;
        padding-top:.35rem!important;
        padding-left:.72rem!important;
        padding-right:.72rem!important;
        padding-bottom:2rem!important;
    }

    .hero{
        padding:24px 19px!important;
        margin-bottom:10px!important;
        border-radius:22px!important;
        min-height:auto!important;
    }

    .hero-kicker{
        font-size:8px!important;
    }

    .hero-title{
        margin-top:7px!important;
        font-size:27px!important;
        line-height:1.18!important;
    }

    .hero-desc{
        margin-top:9px!important;
        font-size:11px!important;
        line-height:1.55!important;
    }

    .flowbar{
        grid-template-columns:1fr 1fr!important;
        gap:6px!important;
        margin-bottom:10px!important;
    }

    .flow{
        min-height:50px!important;
        padding:9px 10px!important;
        border-radius:13px!important;
        font-size:8px!important;
    }

    .lookup,
    .qbox,
    .quote{
        padding:20px 17px!important;
        border-radius:20px!important;
    }

    .lookup-title{
        font-size:23px!important;
    }

    .lookup:after{
        display:none!important;
    }

    .qbox{
        margin-bottom:10px!important;
    }

    .qtitle{
        font-size:21px!important;
        line-height:1.27!important;
    }

    .qdesc{
        font-size:11px!important;
        line-height:1.5!important;
    }

    .choice{
        margin-bottom:1px!important;
        border-radius:19px!important;
    }

    .choice-visual{
        height:155px!important;
        margin:7px!important;
        border-radius:15px!important;
    }

    .choice-copy{
        padding:7px 15px 14px!important;
    }

    .choice-title{
        font-size:15px!important;
    }

    .choice-desc{
        font-size:10px!important;
    }

    .stButton>button{
        min-height:48px!important;
        border-radius:13px!important;
        font-size:13px!important;
    }

    .result-title{
        font-size:26px!important;
        line-height:1.22!important;
    }

    .result-desc{
        font-size:10px!important;
        line-height:1.5!important;
    }

    .persona{
        grid-template-columns:1fr!important;
        gap:14px!important;
        padding:18px!important;
        border-radius:21px!important;
    }

    .persona-visual{
        height:135px!important;
    }

    .persona-name{
        font-size:24px!important;
    }

    .persona-sub{
        font-size:12px!important;
    }

    .persona-copy{
        font-size:10px!important;
    }

    .top3-title{
        margin-top:14px!important;
        font-size:16px!important;
    }

    .top3-sub{
        font-size:10px!important;
        line-height:1.5!important;
    }

    .reco-photo{
        height:170px!important;
        margin-top:5px!important;
    }

    .reco-card{
        min-height:auto!important;
        padding:15px!important;
        border-radius:18px!important;
    }

    .reco-model{
        font-size:19px!important;
    }

    .reco-tag{
        min-height:auto!important;
        font-size:10px!important;
    }

    .reco-match strong{
        font-size:24px!important;
    }

    .dream{
        margin-top:12px!important;
        border-radius:21px!important;
    }

    .dream-head{
        padding:20px 18px 0!important;
    }

    .dream-name{
        font-size:25px!important;
    }

    .car-stage{
        height:245px!important;
    }

    .car-stage img{
        width:94%!important;
        height:92%!important;
    }

    .reason-row{
        grid-template-columns:1fr!important;
        padding:0 15px 15px!important;
    }

    .reason{
        padding:9px 4px!important;
    }

    .quote{
        margin-top:10px!important;
    }

    .quote-fee{
        font-size:34px!important;
    }

    .quote-details{
        grid-template-columns:1fr 1fr!important;
    }

    .money-flow{
        grid-template-columns:1fr!important;
    }

    .operator{
        font-size:16px!important;
        line-height:1!important;
    }

    .usedcar-card{
        grid-template-columns:1fr!important;
    }

    .used-main{
        min-height:auto!important;
        padding:20px!important;
    }

    .used-price{
        font-size:31px!important;
    }
}


/* =========================================================
   MOBILE UX REFINEMENT v2
   - 질문/TOP3만 1열
   - 색상/기간 버튼은 가로 유지
   - 결과 화면 세로 길이 대폭 축소
========================================================= */
.reco-mobile-card{
    display:grid;
    grid-template-columns:42% 58%;
    align-items:center;
    min-height:150px;
    overflow:hidden;
    border:1px solid #E8EDF5;
    border-radius:20px;
    background:#FFFFFF;
    box-shadow:0 8px 24px rgba(31,49,83,.07);
    margin:3px 0 8px;
}
.reco-mobile-card.top{
    border:1.5px solid #7C8CFF;
    box-shadow:0 10px 26px rgba(89,101,225,.13);
}
.reco-mobile-img{
    height:100%;
    min-height:150px;
    display:flex;
    align-items:center;
    justify-content:center;
    background:linear-gradient(145deg,#F8FAFD,#EEF2F7);
}
.reco-mobile-img img{
    width:100%;
    height:145px;
    object-fit:contain;
    padding:7px;
}
.reco-mobile-copy{
    padding:14px 14px 13px;
    min-width:0;
}
.reco-bottom{
    display:flex;
    justify-content:space-between;
    align-items:flex-end;
    gap:8px;
    margin-top:10px;
    color:#78869B;
    font-size:10px;
}
.reco-bottom b{color:#263750;}
.reco-bottom strong{
    color:#4968F2;
    font-size:24px;
    line-height:1;
    letter-spacing:-1px;
}

/* 모바일 결과 화면에서 불필요한 장식/여백 축소 */
@media(max-width:760px){
    /* 질문 선택지와 TOP3만 세로 1열 */
    div[data-testid="stHorizontalBlock"]:has(.choice),
    div[data-testid="stHorizontalBlock"]:has(.reco-mobile-card){
        flex-wrap:wrap!important;
        gap:.45rem!important;
    }
    div[data-testid="stHorizontalBlock"]:has(.choice) > div[data-testid="column"],
    div[data-testid="stHorizontalBlock"]:has(.reco-mobile-card) > div[data-testid="column"]{
        flex:1 1 100%!important;
        width:100%!important;
        min-width:100%!important;
    }

    /* 일반 선택 버튼(색상/기간)은 가로 배열 유지 */
    div[data-testid="stHorizontalBlock"]:not(:has(.choice)):not(:has(.reco-mobile-card)){
        flex-wrap:nowrap!important;
        gap:.35rem!important;
    }
    div[data-testid="stHorizontalBlock"]:not(:has(.choice)):not(:has(.reco-mobile-card))
      > div[data-testid="column"]{
        min-width:0!important;
        width:auto!important;
        flex:1 1 0!important;
    }

    .persona{
        padding:13px!important;
        gap:10px!important;
    }
    .persona-visual{
        height:92px!important;
    }
    .persona-visual img{
        object-fit:cover!important;
    }
    .persona-name{
        font-size:21px!important;
        margin-top:3px!important;
    }
    .persona-sub{
        font-size:11px!important;
        margin-top:2px!important;
    }
    .persona-copy{
        font-size:9px!important;
        line-height:1.45!important;
        margin-top:5px!important;
    }

    .top3-title{
        margin:13px 0 2px!important;
        font-size:17px!important;
    }
    .top3-sub{
        margin-bottom:7px!important;
    }

    .reco-mobile-card{
        grid-template-columns:43% 57%!important;
        min-height:128px!important;
        border-radius:17px!important;
        margin-bottom:2px!important;
    }
    .reco-mobile-img{
        min-height:128px!important;
    }
    .reco-mobile-img img{
        height:122px!important;
        padding:5px!important;
    }
    .reco-mobile-copy{
        padding:10px 11px!important;
    }
    .reco-rank{
        font-size:8px!important;
        margin-bottom:3px!important;
    }
    .reco-model{
        font-size:17px!important;
        line-height:1.18!important;
        margin-bottom:4px!important;
    }
    .reco-tag{
        font-size:9px!important;
        line-height:1.35!important;
        min-height:auto!important;
        display:-webkit-box;
        -webkit-line-clamp:2;
        -webkit-box-orient:vertical;
        overflow:hidden;
    }
    .reco-bottom{
        margin-top:7px!important;
        font-size:8px!important;
    }
    .reco-bottom strong{
        font-size:20px!important;
    }

    /* TOP3 버튼을 카드와 붙여서 작게 */
    div[data-testid="stHorizontalBlock"]:has(.reco-mobile-card) .stButton>button{
        min-height:38px!important;
        height:38px!important;
        font-size:10px!important;
        margin:0 0 5px!important;
        border-radius:11px!important;
    }

    .top3-guide{
        margin:7px 0 4px!important;
        padding:9px 11px!important;
        font-size:9px!important;
    }

    /* 선택 차량 상세도 지나치게 크게 보이지 않게 */
    .dream{
        margin-top:8px!important;
    }
    .dream-head{
        padding:15px 14px 0!important;
    }
    .dream-name{
        font-size:22px!important;
    }
    .car-stage{
        height:190px!important;
    }
    .car-stage img{
        width:92%!important;
        height:96%!important;
        object-fit:contain!important;
    }
    .reason-row{
        padding:0 11px 10px!important;
        gap:4px!important;
    }

    /* 일반 버튼은 모바일에서 너무 높지 않게 */
    .stButton>button{
        min-height:42px!important;
        height:auto!important;
        padding:.45rem .45rem!important;
        font-size:11px!important;
        border-radius:11px!important;
    }

    /* 색상/할부기간 버튼의 텍스트 줄바꿈 억제 */
    div[data-testid="stHorizontalBlock"]:not(:has(.choice)):not(:has(.reco-mobile-card))
      .stButton>button{
        white-space:nowrap!important;
        font-size:10px!important;
        padding:.38rem .2rem!important;
    }

    /* 견적은 핵심 금액을 먼저, 상세는 컴팩트하게 */
    .quote{
        padding:15px 14px!important;
        border-radius:18px!important;
    }
    .quote-fee{
        font-size:31px!important;
        margin-top:2px!important;
    }
    .quote-details{
        gap:5px!important;
        margin-top:9px!important;
    }
    .detail{
        padding:9px!important;
        min-height:58px!important;
    }
    .money-flow{
        gap:5px!important;
        margin-top:8px!important;
    }
    .money-box{
        padding:9px!important;
    }
}

/* 아주 작은 휴대폰 */
@media(max-width:390px){
    .hero-title{font-size:24px!important;}
    .result-title{font-size:23px!important;}
    .reco-mobile-card{grid-template-columns:41% 59%!important;}
    .reco-mobile-img img{height:112px!important;}
    .reco-model{font-size:16px!important;}
    .reco-bottom strong{font-size:18px!important;}
}


.image-missing{
    width:100%;
    min-height:180px;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#7C899C;
    font-size:11px;
    background:linear-gradient(145deg,#F7F9FC,#EEF2F7);
    border-radius:16px;
}
@media(max-width:760px){
    .image-missing{min-height:145px!important;}
}


/* =========================================================
   MOBILE FINAL POLISH
========================================================= */
html, body, .stApp{
    overflow-x:hidden!important;
    max-width:100vw!important;
}
.block-container{
    overflow-x:hidden!important;
}

/* 추천 TOP3 - 선택 카드 강조 */
.reco-mobile-card.selected{
    border:2px solid #4D6BFF!important;
    background:linear-gradient(145deg,#F8FAFF,#EEF2FF)!important;
    box-shadow:0 12px 30px rgba(77,107,255,.16)!important;
    position:relative;
}
.reco-mobile-card.selected:after{
    content:"SELECTED";
    position:absolute;
    top:9px;
    right:9px;
    padding:4px 7px;
    border-radius:999px;
    background:#4D6BFF;
    color:#fff;
    font-size:7px;
    font-weight:900;
    letter-spacing:.08em;
}

/* 견적 조건 섹션 - 추천영역과 명확히 분리 */
.config-section{
    margin-top:14px;
    padding:14px 15px 11px;
    border:1px solid #E6E9FF;
    border-radius:18px 18px 0 0;
    background:linear-gradient(135deg,#F8F9FF,#F1F4FF);
}
.config-title{
    color:#1B2940;
    font-size:14px;
    font-weight:900;
    letter-spacing:-.02em;
}
.config-sub{
    margin-top:3px;
    color:#8590A3;
    font-size:9px;
    line-height:1.45;
}
.control-label{
    margin:10px 0 5px;
    color:#667085;
    font-size:10px;
    font-weight:900;
    letter-spacing:.06em;
}
.term-label{margin-top:13px;}

/* Streamlit radio를 선택칩처럼 */
div[role="radiogroup"]{
    display:flex!important;
    flex-wrap:nowrap!important;
    gap:6px!important;
    width:100%!important;
    overflow:visible!important;
}
div[role="radiogroup"] > label{
    flex:1 1 0!important;
    min-width:0!important;
    max-width:none!important;
    margin:0!important;
    padding:0!important;
    border:1px solid #DDE3EC!important;
    border-radius:12px!important;
    background:#FFFFFF!important;
    transition:.15s ease!important;
    box-shadow:none!important;
}
div[role="radiogroup"] > label:hover{
    border-color:#AEBBFF!important;
}
div[role="radiogroup"] > label:has(input:checked){
    border:2px solid #4D6BFF!important;
    background:#EEF2FF!important;
    box-shadow:0 5px 14px rgba(77,107,255,.12)!important;
}
div[role="radiogroup"] > label > div:first-child{
    display:none!important;
}
div[role="radiogroup"] > label > div:last-child{
    width:100%!important;
    justify-content:center!important;
    padding:9px 5px!important;
    text-align:center!important;
}
div[role="radiogroup"] p{
    margin:0!important;
    color:#344054!important;
    font-size:10px!important;
    font-weight:800!important;
    white-space:nowrap!important;
}
div[role="radiogroup"] > label:has(input:checked) p{
    color:#315EF5!important;
}

/* 견적 결과 섹션 */
.quote-section-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin-top:15px;
    padding:14px 15px;
    border-radius:18px;
    background:linear-gradient(125deg,#0A1B34,#163B73);
    color:#fff;
}
.quote-section-kicker{
    color:#9FBCFF;
    font-size:8px;
    font-weight:900;
    letter-spacing:.12em;
}
.quote-section-title{
    margin-top:3px;
    font-size:17px;
    font-weight:900;
}
.quote-section-chip{
    padding:6px 9px;
    border-radius:999px;
    background:rgba(255,255,255,.10);
    border:1px solid rgba(255,255,255,.13);
    color:#DCE7FF;
    font-size:8px;
    font-weight:850;
}

@media(max-width:760px){
    .block-container{
        width:100%!important;
        max-width:100%!important;
        padding-left:.65rem!important;
        padding-right:.65rem!important;
    }

    /* 사이드 스크롤 유발 요소 제거 */
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    section.main{
        overflow-x:hidden!important;
        max-width:100vw!important;
    }

    div[role="radiogroup"]{
        gap:5px!important;
    }
    div[role="radiogroup"] > label > div:last-child{
        padding:9px 2px!important;
    }
    div[role="radiogroup"] p{
        font-size:9px!important;
    }

    .quote-section-head{
        margin-top:12px!important;
        padding:12px 13px!important;
        border-radius:15px!important;
    }
    .quote-section-title{
        font-size:15px!important;
    }

    .config-section{
        margin-top:10px!important;
        padding:12px 13px 9px!important;
        border-radius:15px 15px 0 0!important;
    }

    /* 선택차량 상세 카드는 추천영역보다 다른 톤 */
    .dream{
        border:1px solid #E1E6F5!important;
        background:linear-gradient(180deg,#FFFFFF,#FAFBFF)!important;
    }
    .dream-badge{
        background:#EDEBFF!important;
        color:#6941C6!important;
    }
}


/* =========================================================
   COMPACT MOBILE QUOTE v4
========================================================= */
.compact-quote{
    padding:18px 18px 15px!important;
    border-radius:22px!important;
}
.quote-summary{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:12px;
    padding-bottom:13px;
    border-bottom:1px solid #EEF1F5;
}
.quote-summary .quote-fee{
    margin-top:2px;
}
.money-strip{
    display:grid;
    grid-template-columns:1fr 18px 1fr 18px 1fr;
    align-items:center;
    gap:4px;
    margin-top:13px;
}
.money-mini{
    min-width:0;
    padding:10px 7px;
    border-radius:13px;
    background:#F7F9FC;
    text-align:center;
}
.money-mini span{
    display:block;
    color:#8B96A7;
    font-size:8px;
    white-space:nowrap;
}
.money-mini strong{
    display:block;
    margin-top:3px;
    color:#26364D;
    font-size:11px;
    font-weight:900;
    white-space:nowrap;
}
.money-mini.highlight{
    background:linear-gradient(135deg,#EEF3FF,#F2EEFF);
}
.money-mini.highlight strong{
    color:#315EF5;
}
.money-sign{
    text-align:center;
    color:#A3ADBA;
    font-size:17px;
    font-weight:800;
}
.quote-mini-grid{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:6px;
    margin-top:8px;
}
.qmini{
    min-height:52px;
    padding:9px 10px;
    border-radius:12px;
    border:1px solid #EEF1F5;
    background:#FBFCFD;
}
.qmini span{
    display:block;
    color:#98A2B3;
    font-size:8px;
}
.qmini strong{
    display:block;
    margin-top:3px;
    color:#344054;
    font-size:10px;
    font-weight:850;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
}
.compact-note{
    margin-top:8px!important;
    font-size:8px!important;
    line-height:1.4!important;
}

@media(max-width:760px){
    /* 추천차량 상세 자체도 더 짧게 */
    .dream-head{
        padding:13px 13px 0!important;
    }
    .dream-name{
        font-size:20px!important;
        margin-top:5px!important;
    }
    .dream-copy{
        font-size:9px!important;
        line-height:1.4!important;
    }
    .match-score strong{
        font-size:25px!important;
    }
    .car-stage{
        height:150px!important;
    }
    .car-stage img{
        width:94%!important;
        height:96%!important;
        object-fit:contain!important;
    }
    .reason-row{
        grid-template-columns:repeat(3,1fr)!important;
        padding:0 10px 10px!important;
        gap:5px!important;
    }
    .reason{
        padding:8px 3px 2px!important;
    }
    .reason span{
        font-size:8px!important;
        line-height:1.3!important;
    }

    /* 견적 조건 섹션도 더 압축 */
    .config-section{
        margin-top:8px!important;
        padding:10px 11px 7px!important;
    }
    .config-title{
        font-size:13px!important;
    }
    .config-sub{
        font-size:8px!important;
    }
    .control-label{
        margin:8px 0 4px!important;
        font-size:9px!important;
    }

    /* 견적 헤더 */
    .quote-section-head{
        margin-top:10px!important;
        padding:10px 12px!important;
    }
    .quote-section-title{
        font-size:14px!important;
    }

    .compact-quote{
        padding:14px 12px 12px!important;
        border-radius:18px!important;
    }
    .quote-summary{
        gap:8px!important;
        padding-bottom:10px!important;
    }
    .quote-kicker{
        font-size:7px!important;
    }
    .quote-label{
        font-size:9px!important;
        margin-top:3px!important;
    }
    .quote-fee{
        font-size:29px!important;
        line-height:1.05!important;
    }
    .quote-chip{
        padding:6px 8px!important;
        font-size:8px!important;
        white-space:nowrap!important;
    }

    .money-strip{
        grid-template-columns:1fr 12px 1fr 12px 1fr!important;
        gap:2px!important;
        margin-top:10px!important;
    }
    .money-mini{
        padding:8px 3px!important;
        border-radius:10px!important;
    }
    .money-mini span{
        font-size:7px!important;
    }
    .money-mini strong{
        font-size:9px!important;
    }
    .money-sign{
        font-size:14px!important;
    }

    .quote-mini-grid{
        gap:5px!important;
        margin-top:6px!important;
    }
    .qmini{
        min-height:46px!important;
        padding:7px 8px!important;
    }
    .qmini span{
        font-size:7px!important;
    }
    .qmini strong{
        font-size:9px!important;
    }
    .compact-note{
        font-size:7px!important;
        margin-top:6px!important;
    }

    /* CTA를 견적 바로 아래 붙게 */
    .compact-quote + div{
        margin-top:5px!important;
    }

    /* 마지막 액션 버튼도 높이 축소 */
    button[kind="primary"]{
        min-height:44px!important;
        height:44px!important;
        font-size:11px!important;
    }
}

@media(max-width:390px){
    .quote-fee{font-size:27px!important;}
    .money-mini strong{font-size:8px!important;}
    .money-mini span{font-size:6px!important;}
}

</style>
""")


# =========================================================
# HERO + 진행 단계
# =========================================================
html("""
<div class="hero">
<div class="hero-kicker">MY CAR CHANGE JOURNEY · MOBILE UI v3</div>
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

    cols = st.columns(len(q["options"]), gap="medium")

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
    if not EXCEL_PATH.exists():
        st.error(f"엑셀 파일이 없습니다: {EXCEL_PATH}")
        st.stop()

    if not IMAGE_DIR.exists():
        st.error(f"차량 이미지 폴더가 없습니다: {IMAGE_DIR}")
        st.stop()

    if not GIF_DIR.exists():
        st.error(f"GIF 폴더가 없습니다: {GIF_DIR}")
        st.stop()

    df = load_car_data(str(EXCEL_PATH)).copy()

    # 문자열 공백 때문에 동일 모델이 다르게 인식되는 문제 방지
    df["모델"] = df["모델"].astype(str).str.strip()
    df["색상"] = df["색상"].astype(str).str.strip()

    loaded_models = df["모델"].dropna().unique().tolist()

    if len(loaded_models) != 13:
        st.warning(
            f"현재 엑셀에서 {len(loaded_models)}개 차종만 읽혔습니다. "
            f"사용 중인 파일: {EXCEL_PATH.name}"
        )

    models = df["모델"].dropna().astype(str).unique().tolist()
    ranked = rank_vehicles(st.session_state.persona_answers, models)

    if not ranked:
        st.error("추천 가능한 차량 데이터가 없습니다.")
        st.stop()

    # 엑셀 모델과 추천 프로파일의 모델명이 정확히 맞는지 확인
    missing_profiles = [m for m in models if m not in vehicle_profiles]
    if missing_profiles:
        st.warning(
            "추천 프로파일이 없는 모델: " + ", ".join(missing_profiles)
        )

    recommendation = build_persona(st.session_state.persona_answers, ranked)
    ranked_models = [item["model"] for item in ranked]

    if st.session_state.selected_model not in ranked_models:
        st.session_state.selected_model = ranked_models[0]

    model = st.session_state.selected_model

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

    selected_rank = next((item for item in ranked if item["model"] == model), ranked[0])
    recommendation["match"] = selected_rank["match"]
    recommendation["reasons"] = selected_rank["profile"]["reason_pool"][:3]

    html(f"""
    <div class="result-title">당신에게 가장 잘 맞는 드림카 TOP 3</div>
    <div class="result-desc">
    총 <b>{len(loaded_models)}개 차종</b>을 내부적으로 비교하고,
    선택을 어렵게 하지 않도록 가장 적합한 3대만 추천합니다.
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

    html("""
    <div class="top3-title">AI 추천 차량 TOP 3</div>
    <div class="top3-sub">한 대로 단정하지 않고, 라이프스타일 점수가 높은 차량을 비교해보세요.</div>
    """)

    top_items = ranked[:3]
    top_cols = st.columns(len(top_items), gap="medium")

    for idx, item in enumerate(top_items):
        with top_cols[idx]:
            is_selected = item["model"] == model
            top_class = " top" if idx == 0 else ""
            selected_class = " selected" if is_selected else ""
            selected_mark = " · 선택됨" if is_selected else ""

            top_row = df[
                df["모델"].astype(str) == item["model"]
            ].iloc[0]

            top_file = Path(str(top_row["이미지파일명"]))
            top_image_path = resolve_car_image(top_file.name)
            top_uri = image_data_uri(top_image_path)
            top_price = int(float(top_row["차량가격(만원)"]))

            image_html = (
                f'<img src="{top_uri}" alt="{item["model"]}">'
                if top_uri else ""
            )

            html(f"""
            <div class="reco-mobile-card{top_class}{selected_class}">
                <div class="reco-mobile-img">{image_html}</div>
                <div class="reco-mobile-copy">
                    <div class="reco-rank">TOP {idx + 1}{selected_mark}</div>
                    <div class="reco-model">{item["model"]}</div>
                    <div class="reco-tag">{item["profile"]["tagline"]}</div>
                    <div class="reco-bottom">
                        <span>신차가 약 <b>{top_price:,}만원</b></span>
                        <strong>{item["match"]}%</strong>
                    </div>
                </div>
            </div>
            """)

            button_label = "✓ 선택된 차량" if is_selected else "이 차량으로 견적 보기"

            if st.button(
                button_label,
                key=f"select_model_{idx}",
                use_container_width=True,
                disabled=is_selected
            ):
                st.session_state.selected_model = item["model"]
                st.session_state.color = None
                st.session_state.pop("color_selector", None)
                st.rerun()

    html("""
    <div class="top3-guide">
    💡 마음에 드는 차량 1대를 선택하면 아래에서 색상과 할부기간을 바로 조정할 수 있습니다.
    </div>
    """)

    original_image = Path(str(selected["이미지파일명"]))
    image_path = resolve_car_image(original_image.name)
    uri = image_data_uri(image_path)

    # 이미지가 없을 때만 사용자에게 정확한 원인을 보여줍니다.
    if not uri:
        st.warning(
            f"'{model}' 이미지를 찾지 못했습니다. "
            f"찾는 파일 기준: {original_image.stem}.jpg / .jpeg / .png"
        )
        with st.expander("이미지 폴더 위치 확인"):
            st.code(
                f"BASE_DIR = {BASE_DIR}\n"
                f"IMAGE_DIR = {IMAGE_DIR}\n"
                f"IMAGE_DIR exists = {IMAGE_DIR.exists()}"
            )

    r1, r2, r3 = recommendation["reasons"]

    detail_image_html = (
        f'<img src="{uri}" alt="{model}">'
        if uri else
        '<div class="image-missing">차량 이미지를 찾는 중입니다.</div>'
    )

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
    {detail_image_html}
    </div>

    <div class="reason-row">
    <div class="reason"><b>MATCH 01</b><span>{r1}</span></div>
    <div class="reason"><b>MATCH 02</b><span>{r2}</span></div>
    <div class="reason"><b>MATCH 03</b><span>{r3}</span></div>
    </div>

    </div>
    """)

    html("""
    <div class="config-section">
        <div class="config-title">내 견적 조건 선택</div>
        <div class="config-sub">추천 차량을 기준으로 색상과 할부기간을 선택해주세요.</div>
    </div>
    """)

    # COLOR - 모바일에서 깨지지 않는 pill형 radio
    st.markdown('<div class="control-label">COLOR</div>', unsafe_allow_html=True)
    color_index = colors.index(st.session_state.color) if st.session_state.color in colors else 0

    selected_color = st.radio(
        "COLOR",
        colors,
        index=color_index,
        horizontal=True,
        label_visibility="collapsed",
        key="color_selector"
    )

    if selected_color != st.session_state.color:
        st.session_state.color = selected_color
        st.rerun()

    # TERM
    terms = [24, 36, 48, 60]
    st.markdown('<div class="control-label term-label">할부기간</div>', unsafe_allow_html=True)

    term_index = terms.index(st.session_state.months) if st.session_state.months in terms else 2
    selected_term = st.radio(
        "할부기간",
        terms,
        index=term_index,
        horizontal=True,
        format_func=lambda x: f"{x}개월",
        label_visibility="collapsed",
        key="term_selector"
    )

    if selected_term != st.session_state.months:
        st.session_state.months = selected_term
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

    html("""
    <div class="quote-section-head">
        <div>
            <div class="quote-section-kicker">SELECTED CAR QUOTE</div>
            <div class="quote-section-title">선택 차량 견적</div>
        </div>
        <div class="quote-section-chip">MY QUOTE</div>
    </div>
    """)

    html(f"""
    <div class="quote compact-quote">

        <div class="quote-summary">
            <div>
                <div class="quote-kicker">DREAM CAR CHANGE QUOTE</div>
                <div class="quote-label">보상판매 반영 예상 월 할부금</div>
                <div class="quote-fee">월 <em>{monthly_payment:,.1f}만원</em></div>
            </div>
            <div class="quote-chip">
                {st.session_state.months}개월 · 연 {DEMO_APR:.1f}%
            </div>
        </div>

        <div class="money-strip">
            <div class="money-mini">
                <span>신차가격</span>
                <strong>{new_price:,}만원</strong>
            </div>
            <div class="money-sign">−</div>
            <div class="money-mini">
                <span>내 차 시세</span>
                <strong>{tradein_value:,}만원</strong>
            </div>
            <div class="money-sign">=</div>
            <div class="money-mini highlight">
                <span>할부원금</span>
                <strong>{finance_principal:,}만원</strong>
            </div>
        </div>

        <div class="quote-mini-grid">
            <div class="qmini">
                <span>추천 차량</span>
                <strong>{model}</strong>
            </div>
            <div class="qmini">
                <span>현재 차량</span>
                <strong>{owned_name}</strong>
            </div>
            <div class="qmini">
                <span>선택 색상</span>
                <strong>{st.session_state.color}</strong>
            </div>
            <div class="qmini">
                <span>예상 총 이자</span>
                <strong>{total_interest:,.0f}만원</strong>
            </div>
        </div>

        <div class="quote-note compact-note">
        ※ 프로토타입 기준 · 실제 시세/금리/수수료/신용도/옵션에 따라 달라질 수 있습니다.
        </div>

    </div>
    """)
    st.write("")

    a, b, c = st.columns([2, 1, 1])

    with a:
        if st.button(
            "상세 견적 보기 →",
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
            st.session_state.selected_model = None
            st.session_state.flow_step = "persona"
            st.rerun()

    with c:
        if st.button(
            "처음부터",
            use_container_width=True
        ):
            reset_all()
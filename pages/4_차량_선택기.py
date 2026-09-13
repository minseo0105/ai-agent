import streamlit as st
import pandas as pd
from pathlib import Path
import base64
from auth import require_page_auth

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(
    page_title="내차만들기",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# 로그인 세션 확인 + 한글 사이드바
# =========================================================
require_page_auth()

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

    st.button(
        "🚗 차량 선택기",
        key="sidebar_car_selector",
        use_container_width=True,
        disabled=True,
    )

    if st.button(
        "🎞️ GIF 변환기",
        key="sidebar_gif",
        use_container_width=True,
    ):
        st.switch_page("pages/5_GIF_변환기.py")

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = BASE_DIR / "sample_cars_v2.xlsx"
IMAGE_DIR = BASE_DIR / "car_images_cutout"


def html(content):
    clean = "\n".join(line.strip() for line in content.splitlines())
    st.markdown(clean, unsafe_allow_html=True)


def image_data_uri(path):
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


# =========================================================
# PREMIUM LIGHT UI
# =========================================================
html("""
<style>
[data-testid="stSidebar"]{
    display:block !important;
}
[data-testid="stSidebarContent"]{
    display:block !important;
}
:root{
 --ink:#101828; --muted:#667085; --line:#E8ECF2;
 --blue:#2858F5; --navy:#07152B; --soft:#F7F8FA;
}
html,body,[class*="css"]{font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.stApp{background:#F6F8FB}
.block-container{max-width:1060px;padding-top:1rem;padding-bottom:3rem}
header[data-testid="stHeader"]{background:rgba(246,248,251,.84);backdrop-filter:blur(12px)}
#MainMenu,footer{visibility:hidden}

/* HERO */
.hero{position:relative;overflow:hidden;border-radius:30px;padding:48px 50px;margin-bottom:18px;color:#fff;
background:linear-gradient(122deg,#071426 0%,#102A51 60%,#244DA4 100%);
box-shadow:0 22px 55px rgba(16,32,60,.13)}
.hero:before{content:"";position:absolute;width:320px;height:320px;right:-120px;top:-170px;border-radius:50%;
border:1px solid rgba(255,255,255,.12);animation:drift 8s ease-in-out infinite}
.hero-kicker{font-size:10px;font-weight:900;letter-spacing:.18em;color:#ABC5FF}
.hero-title{position:relative;z-index:2;margin-top:10px;font-size:41px;line-height:1.16;font-weight:900;letter-spacing:-.05em}
.hero-title span{color:#C3D4FF}
.hero-desc{position:relative;z-index:2;margin-top:14px;max-width:650px;font-size:13px;line-height:1.72;color:#D9E3F2}
@keyframes drift{50%{transform:translate(-15px,15px)}}

/* QUESTION */
.step-card{background:#fff;border:1px solid var(--line);border-radius:22px;padding:23px 26px 21px;
box-shadow:0 8px 22px rgba(15,23,42,.035);margin-bottom:14px}
.step-top{display:flex;justify-content:space-between;font-size:10px;font-weight:850;color:#98A2B3}
.step-top b{color:var(--blue);letter-spacing:.1em}
.progress{height:4px;background:#EAEDF3;border-radius:999px;margin:10px 0 17px;overflow:hidden}
.progress>div{height:100%;background:linear-gradient(90deg,#2858F5,#7257E7)}
.step-title{font-size:23px;font-weight:900;letter-spacing:-.035em;color:var(--ink)}
.step-desc{margin-top:5px;font-size:12px;color:var(--muted)}

.choice{overflow:hidden;background:#fff;border:1px solid var(--line);border-radius:22px;margin-bottom:7px;
box-shadow:0 7px 20px rgba(15,23,42,.03);transition:.22s ease}
.choice:hover{transform:translateY(-3px);border-color:#B7C5F8;box-shadow:0 15px 32px rgba(40,88,245,.08)}
.choice-visual{height:174px;margin:9px;border-radius:17px;overflow:hidden;background:#F1F4F9}
.choice-visual svg{width:100%;height:100%}
.choice-copy{padding:8px 19px 18px}
.choice-title{font-size:15px;font-weight:900;color:#172033}
.choice-desc{margin-top:4px;font-size:11px;color:#8A95A6}

/* elegant animated scene */
.scene-bg{animation:scene 7s ease-in-out infinite}
.scene-car{animation:drive 5s ease-in-out infinite}
.scene-float{animation:float 4s ease-in-out infinite}
.scene-glow{animation:glow 2.8s ease-in-out infinite}
@keyframes scene{50%{transform:translateX(-5px)}}
@keyframes drive{0%,100%{transform:translateX(-8px)}50%{transform:translateX(12px)}}
@keyframes float{50%{transform:translateY(-7px)}}
@keyframes glow{0%,100%{opacity:.45}50%{opacity:1}}

/* STREAMLIT BUTTON */
.stButton>button{min-height:42px;border-radius:12px!important;border:1px solid #DFE4EC!important;background:#fff!important;
color:#26354B!important;font-size:12px!important;font-weight:800!important;box-shadow:none!important}
.stButton>button:hover{border-color:#A7B9F7!important;color:#2858F5!important;box-shadow:0 6px 16px rgba(40,88,245,.07)!important}
button[kind="primary"]{min-height:49px!important;color:#fff!important;border:none!important;
background:linear-gradient(135deg,#2858F5,#624FE2)!important;box-shadow:0 10px 22px rgba(40,88,245,.18)!important}

/* RESULT INTRO */
.result-intro{padding:9px 3px 18px}
.result-kicker{font-size:10px;font-weight:900;letter-spacing:.14em;color:#2858F5}
.result-title{margin-top:5px;font-size:32px;font-weight:900;letter-spacing:-.045em;color:#101828}
.result-desc{margin-top:5px;font-size:12px;color:#7B8798}

/* PERSONA - no cartoon icon */
.persona-card{position:relative;overflow:hidden;display:grid;grid-template-columns:190px 1fr;gap:27px;align-items:center;
border-radius:27px;padding:26px 29px;margin-bottom:14px;color:#fff;
background:linear-gradient(122deg,#07162B 0%,#102C55 68%,#29498D 100%);
box-shadow:0 17px 38px rgba(15,23,42,.11)}
.persona-visual{height:150px;border-radius:20px;overflow:hidden;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1)}
.persona-visual svg{width:100%;height:100%}
.persona-label{color:#AFC6FF;font-size:9px;font-weight:900;letter-spacing:.17em}
.persona-name{margin-top:5px;font-size:29px;font-weight:900;letter-spacing:-.04em}
.persona-sub{margin-top:2px;font-size:13px;color:#D5DFF0;font-weight:750}
.persona-copy{margin-top:9px;max-width:630px;font-size:12px;color:#E1E8F3;line-height:1.65}
.persona-quote{display:inline-block;margin-top:10px;padding:7px 11px;border-radius:999px;background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.09);font-size:10px;color:#fff}

/* VEHICLE CONFIGURATOR */
.configurator{overflow:hidden;border-radius:29px;background:#fff;border:1px solid var(--line);
box-shadow:0 14px 38px rgba(15,23,42,.05);margin-bottom:12px}
.config-top{display:flex;justify-content:space-between;align-items:flex-start;padding:27px 29px 0}
.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:#EEF3FF;color:#2858F5;font-size:9px;font-weight:900;letter-spacing:.08em}
.vehicle-name{margin-top:8px;font-size:31px;font-weight:900;color:#101828;letter-spacing:-.045em}
.vehicle-copy{margin-top:3px;color:#7C899A;font-size:11px}
.match-score{text-align:right}
.match-score small{display:block;font-size:9px;font-weight:900;color:#98A2B3;letter-spacing:.08em}
.match-score strong{font-size:30px;color:#2858F5;letter-spacing:-.04em}

.vehicle-stage{position:relative;height:385px;display:flex;align-items:center;justify-content:center;overflow:hidden;
background:linear-gradient(180deg,#fff 0%,#F4F6F9 100%)}
.vehicle-stage:before{content:"";position:absolute;width:70%;height:55%;border-radius:50%;
background:radial-gradient(circle,rgba(222,228,238,.78),rgba(255,255,255,0) 70%)}
.vehicle-stage:after{content:"";position:absolute;width:51%;height:15px;bottom:54px;border-radius:50%;background:rgba(21,32,49,.13);filter:blur(13px)}
.vehicle-stage img{position:relative;z-index:2;width:84%;height:86%;object-fit:contain;
filter:drop-shadow(0 18px 14px rgba(20,31,47,.10));animation:carfloat 4.8s ease-in-out infinite}
@keyframes carfloat{50%{transform:translateY(-5px)}}

.match-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:0 20px 20px}
.match-item{border-top:1px solid #E7EAF0;padding:12px 4px 4px}
.match-item b{display:block;font-size:8px;color:#2858F5;letter-spacing:.08em}
.match-item span{display:block;margin-top:3px;color:#2C3A50;font-size:10px;font-weight:850}

/* compact controls */
.control-label{margin-top:10px;font-size:9px;font-weight:900;color:#66758A;letter-spacing:.11em}
.control-sub{margin-top:2px;margin-bottom:4px;font-size:10px;color:#9AA5B4}

/* QUOTE: light premium card, not another giant navy block */
.quote-shell{margin-top:14px;padding:28px 30px;border-radius:27px;background:#fff;border:1px solid #E4E8EF;
box-shadow:0 13px 34px rgba(15,23,42,.045)}
.quote-head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;padding-bottom:20px;border-bottom:1px solid #E8ECF2}
.quote-kicker{font-size:9px;font-weight:900;letter-spacing:.11em;color:#2858F5}
.quote-label{margin-top:6px;font-size:12px;color:#667085}
.quote-fee{margin-top:1px;font-size:40px;font-weight:900;letter-spacing:-.055em;color:#101828}
.quote-fee em{font-style:normal;color:#2858F5}
.quote-chip{padding:9px 12px;border-radius:999px;background:#F1F5FF;color:#2858F5;font-size:10px;font-weight:850}
.quote-details{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding-top:17px}
.quote-detail{padding:12px 13px;border-radius:14px;background:#F7F9FC}
.quote-detail span{display:block;font-size:9px;color:#8B96A7}
.quote-detail strong{display:block;margin-top:3px;font-size:11px;color:#26354B}
.quote-note{margin-top:13px;font-size:9px;color:#A0A9B7}

@media(max-width:760px){
 .hero{padding:35px 25px}.hero-title{font-size:31px}
 .persona-card{grid-template-columns:1fr}.persona-visual{height:135px}
 .config-top{display:block}.match-score{text-align:left;margin-top:12px}
 .vehicle-stage{height:300px}.match-row,.quote-details{grid-template-columns:1fr}
 .quote-head{display:block}.quote-chip{display:inline-block;margin-top:12px}
}
</style>
""")


# =========================================================
# QUESTION VISUALS - 라이프스타일 모션 이미지
# =========================================================
CITY = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="csky" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#DDE8FF"/><stop offset="1" stop-color="#F6F8FC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#csky)"/>
<g class="scene-bg" opacity=".75">
<rect x="38" y="54" width="48" height="110" rx="5" fill="#8EA7CE"/><rect x="98" y="28" width="61" height="136" rx="5" fill="#6E8FC4"/>
<rect x="174" y="72" width="47" height="92" rx="5" fill="#B7C5DA"/><rect x="236" y="43" width="70" height="121" rx="5" fill="#91A8CB"/>
<rect x="319" y="81" width="50" height="83" rx="5" fill="#C2CCDA"/>
</g>
<path d="M0 164H420V210H0Z" fill="#D9E0EA"/><path d="M0 187H420" stroke="#FFF" stroke-width="3" stroke-dasharray="26 20"/>
<g class="scene-car"><path d="M120 163L143 143H211L238 163L262 168V184H101V170Z" fill="#162C55"/>
<path d="M150 146H205L224 162H132Z" fill="#8CA8D9"/><circle cx="135" cy="184" r="12" fill="#101827"/><circle cx="229" cy="184" r="12" fill="#101827"/>
<path class="scene-glow" d="M260 172H300" stroke="#88A9FF" stroke-width="5" stroke-linecap="round"/></g>
</svg>
"""

TRIP = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="tsky" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#DCE9FF"/><stop offset="1" stop-color="#F8FAFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#tsky)"/><circle class="scene-glow" cx="330" cy="44" r="22" fill="#FFD98A"/>
<g class="scene-bg"><path d="M0 163L87 81L148 145L224 59L336 163Z" fill="#A9BBDC"/><path d="M78 163L157 103L215 151L288 91L420 163Z" fill="#6F8FC7"/></g>
<path d="M0 163H420V210H0Z" fill="#D9E3DC"/><path d="M0 187H420" stroke="#FFF" stroke-width="3" stroke-dasharray="27 20"/>
<g class="scene-car"><path d="M124 162L146 141H213L241 162L265 168V184H104V170Z" fill="#203758"/>
<path d="M152 145H207L226 161H135Z" fill="#9AB0D1"/><circle cx="138" cy="184" r="12" fill="#182334"/><circle cx="232" cy="184" r="12" fill="#182334"/></g>
</svg>
"""

DUO = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="d" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E4EBFF"/><stop offset="1" stop-color="#F9FAFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#d)"/>
<path d="M64 178C92 113 140 79 210 77C281 75 333 111 356 178" fill="none" stroke="#CAD6EE" stroke-width="24" stroke-linecap="round"/>
<g class="scene-float"><rect x="116" y="69" width="78" height="91" rx="28" fill="#284F9A"/><circle cx="155" cy="74" r="22" fill="#C6D5F5"/></g>
<g class="scene-float" style="animation-delay:.6s"><rect x="226" y="69" width="78" height="91" rx="28" fill="#5D57A8"/><circle cx="265" cy="74" r="22" fill="#D7D0F7"/></g>
<path d="M195 158L210 142L225 158" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"/>
</svg>
"""

FAMILY = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="f" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E1EAFF"/><stop offset="1" stop-color="#FAFBFD"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#f)"/>
<path d="M68 177C99 112 146 82 210 82C277 82 326 114 352 177" fill="none" stroke="#CDD8EE" stroke-width="25" stroke-linecap="round"/>
<g class="scene-float"><rect x="91" y="67" width="70" height="94" rx="27" fill="#284F98"/><circle cx="126" cy="71" r="21" fill="#C7D7F6"/></g>
<g class="scene-float" style="animation-delay:.5s"><rect x="259" y="67" width="70" height="94" rx="27" fill="#58549E"/><circle cx="294" cy="71" r="21" fill="#D7D1F7"/></g>
<g class="scene-float" style="animation-delay:1s"><rect x="176" y="101" width="68" height="64" rx="25" fill="#4771C4"/><circle cx="210" cy="105" r="18" fill="#D5E1FA"/></g>
</svg>
"""

STYLE = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="s" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E4EBFF"/><stop offset="1" stop-color="#F8F7FF"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#s)"/>
<ellipse cx="210" cy="172" rx="124" ry="13" fill="#CAD2DF" opacity=".55"/>
<g class="scene-car"><path d="M92 148L126 119H242L286 148L325 156V174H73V158Z" fill="#142A51"/>
<path d="M137 123H234L268 147H109Z" fill="#7F9CCB"/><circle cx="124" cy="174" r="16" fill="#101827"/><circle cx="275" cy="174" r="16" fill="#101827"/>
<path class="scene-glow" d="M77 157H104M289 153H319" stroke="#87A9FF" stroke-width="6" stroke-linecap="round"/></g>
<path class="scene-glow" d="M95 68C164 40 258 40 326 70" fill="none" stroke="#718FF1" stroke-width="3" opacity=".55"/>
</svg>
"""

SPACE = """
<svg viewBox="0 0 420 210">
<defs><linearGradient id="sp" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#E5ECFA"/><stop offset="1" stop-color="#FAFBFC"/></linearGradient></defs>
<rect width="420" height="210" fill="url(#sp)"/>
<path d="M80 166V83C80 59 99 40 123 40H297C321 40 340 59 340 83V166" fill="#E8EDF5" stroke="#AEBED6" stroke-width="4"/>
<path d="M111 68H309V161H111Z" fill="#F8FAFD"/>
<g class="scene-float"><rect x="130" y="100" width="65" height="57" rx="10" fill="#345FAE"/><path d="M143 100V87H182V100" fill="none" stroke="#345FAE" stroke-width="7"/></g>
<g class="scene-float" style="animation-delay:.6s"><rect x="209" y="84" width="78" height="73" rx="11" fill="#7167B6"/><path d="M225 84V68H271V84" fill="none" stroke="#7167B6" stroke-width="7"/></g>
<path class="scene-glow" d="M103 167H317" stroke="#7294DF" stroke-width="5" stroke-linecap="round"/>
</svg>
"""

# =========================================================
# QUESTIONS
# =========================================================
questions = [
    {
        "title":"당신의 주말은 어느 장면에 더 가깝나요?",
        "desc":"가장 자연스럽게 반복되는 이동 장면부터 읽어볼게요.",
        "options":[
            {"art":CITY,"label":"도심을 가볍게 누비는 편","desc":"맛집 · 카페 · 쇼핑 · 근거리 이동"},
            {"art":TRIP,"label":"주말이면 멀리 떠나는 편","desc":"여행 · 캠핑 · 레저 · 장거리 이동"},
        ]
    },
    {
        "title":"차 안에서 가장 자주 함께하는 사람은?",
        "desc":"누구와 이동하는지가 공간과 편안함의 기준을 바꿉니다.",
        "options":[
            {"art":DUO,"label":"혼자 또는 둘이","desc":"나의 감도와 이동 편의가 중요해요"},
            {"art":FAMILY,"label":"가족과 함께","desc":"사람과 짐, 일정까지 함께 담아야 해요"},
        ]
    },
    {
        "title":"차를 고를 때 마지막까지 포기하기 어려운 것은?",
        "desc":"마지막 선택으로 추천 방향을 완성합니다.",
        "options":[
            {"art":STYLE,"label":"볼 때마다 마음에 드는 디자인","desc":"스타일 · 주행감 · 소유 만족감"},
            {"art":SPACE,"label":"필요할 때 든든한 공간","desc":"수납 · 안정감 · 다양한 상황 대응력"},
        ]
    },
]


# =========================================================
# PERSONAS + 추천 차량 로직
# 3개 질문의 8개 조합마다 별도 페르소나와 추천 차량을 지정합니다.
# =========================================================
recommendation_map = {
    # 도심 / 혼자·둘 / 디자인
    (0, 0, 0): {
        "name": "CITY CURATOR",
        "sub": "도시의 장면을 고르는 사람",
        "copy": "복잡한 도심에서도 편하고 세련된 이동을 중요하게 생각합니다. "
                "차를 단순한 이동수단보다 나의 하루와 분위기를 완성하는 오브제로 보는 타입입니다.",
        "quote": "“내 일상의 템포와 가장 자연스럽게 맞는 차.”",
        "model": "디 올 뉴 그랜저",
        "reasons": ["도심 활용성", "정제된 승차감", "디자인 만족도"],
        "art": CITY,
        "match": 96
    },

    # 도심 / 혼자·둘 / 공간·실용
    (0, 0, 1): {
        "name": "SMART MINIMALIST",
        "sub": "필요한 만큼 정확하게 고르는 사람",
        "copy": "과한 크기나 기능보다 실제 일상에서 자주 쓰는 편의와 효율을 중요하게 봅니다. "
                "부담 없이 운전하고 합리적으로 이용할 수 있는 균형 잡힌 선택을 선호합니다.",
        "quote": "“좋은 선택은 더 많이 갖는 것이 아니라, 딱 맞게 갖는 것.”",
        "model": "쏘나타",
        "reasons": ["운전 편의성", "합리적 이용", "데일리 실용성"],
        "art": SPACE,
        "match": 93
    },

    # 도심 / 가족 / 디자인
    (0, 1, 0): {
        "name": "URBAN HOST",
        "sub": "함께 타는 순간까지 세련되게 만드는 사람",
        "copy": "가족이나 동승자와 함께 이동하지만, 큰 차만을 답으로 생각하지 않습니다. "
                "편안함과 디자인, 도심에서의 세련된 주행감을 함께 중요하게 봅니다.",
        "quote": "“함께 타는 사람도, 나도 만족하는 균형.”",
        "model": "디 올 뉴 그랜저",
        "reasons": ["동승자 편안함", "도심 주행감", "프리미엄 감성"],
        "art": FAMILY,
        "match": 94
    },

    # 도심 / 가족 / 공간
    (0, 1, 1): {
        "name": "FAMILY NAVIGATOR",
        "sub": "가족의 매일을 더 여유롭게 설계하는 사람",
        "copy": "등하원, 장보기, 주말 외출처럼 가족의 일상이 차 안에서 연결됩니다. "
                "도심에서도 다루기 편하면서 공간과 안정감까지 충분한 차량을 선호합니다.",
        "quote": "“가족의 하루가 편해지면, 내 하루도 편해진다.”",
        "model": "디 올 뉴 팰리세이드",
        "reasons": ["가족 이동 최적화", "넉넉한 실내", "도심·주말 균형"],
        "art": FAMILY,
        "match": 97
    },

    # 여행 / 혼자·둘 / 디자인
    (1, 0, 0): {
        "name": "ROAD VOYAGER",
        "sub": "가는 길의 감도를 즐기는 사람",
        "copy": "목적지뿐 아니라 이동하는 시간 자체를 중요하게 생각합니다. "
                "장거리에서도 편안하고, 도착했을 때까지 운전의 감성과 만족감이 이어지는 차를 선호합니다.",
        "quote": "“목적지보다 가는 길이 기억에 남는 차.”",
        "model": "디 올 뉴 그랜저",
        "reasons": ["장거리 승차감", "주행 감성", "디자인 완성도"],
        "art": TRIP,
        "match": 92
    },

    # 여행 / 혼자·둘 / 공간
    (1, 0, 1): {
        "name": "FREEDOM EXPLORER",
        "sub": "주말의 반경을 자유롭게 넓히는 사람",
        "copy": "평소에는 여유 있게, 필요할 때는 짐과 활동 범위를 크게 확장하고 싶어합니다. "
                "여행과 레저를 위해 SUV의 공간과 안정감을 적극적으로 활용하는 타입입니다.",
        "quote": "“차가 커지는 것이 아니라, 갈 수 있는 곳이 많아진다.”",
        "model": "디 올 뉴 팰리세이드",
        "reasons": ["여행 활용성", "적재 공간", "장거리 안정감"],
        "art": TRIP,
        "match": 95
    },

    # 여행 / 가족 / 디자인
    (1, 1, 0): {
        "name": "WEEKEND DIRECTOR",
        "sub": "가족의 특별한 주말을 만드는 사람",
        "copy": "가족 여행의 편안함도 중요하지만 차량의 존재감과 스타일도 포기하지 않습니다. "
                "일상과 여행 모두에서 만족감을 주는 프리미엄 패밀리 SUV가 잘 맞습니다.",
        "quote": "“함께하는 시간도, 그 장면도 특별하게.”",
        "model": "디 올 뉴 팰리세이드",
        "reasons": ["패밀리 여행", "프리미엄 디자인", "편안한 주행"],
        "art": STYLE,
        "match": 96
    },

    # 여행 / 가족 / 공간
    (1, 1, 1): {
        "name": "LIFE ORCHESTRATOR",
        "sub": "가족의 모든 장면을 담아내는 사람",
        "copy": "사람도 많고, 짐도 많고, 하고 싶은 일도 많습니다. "
                "여행·레저·일상까지 한 대의 차가 여러 역할을 해내는 압도적인 공간 활용성을 가장 중요하게 봅니다.",
        "quote": "“차 한 대가 가족의 가능성을 더 크게 만든다.”",
        "model": "더 뉴 카니발",
        "reasons": ["최대 공간 활용", "다인승 편의성", "여행·레저 확장성"],
        "art": SPACE,
        "match": 98
    },
}


def get_recommendation(answers):
    """
    3개 질문의 선택값을 기반으로 추천 페르소나와 차량을 반환합니다.
    answers 예시: [0, 1, 1]
    """
    key = tuple(answers)

    if key in recommendation_map:
        return recommendation_map[key]

    # 예외 상황에서는 가족/공간 활용성이 높은 기본 추천
    return recommendation_map[(0, 1, 1)]


# =========================================================
# DATA / STATE
# =========================================================
@st.cache_data
def load_data():
    return pd.read_excel(EXCEL_PATH, sheet_name="차량목록")

if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = []
if "color" not in st.session_state:
    st.session_state.color = None
if "months" not in st.session_state:
    st.session_state.months = 60


# =========================================================
# HERO
# =========================================================
html("""
<div class="hero">
<div class="hero-kicker">MY CAR MAKER · PERSONALIZED MOBILITY</div>
<div class="hero-title">나의 일상을 읽고,<br><span>지금 가장 어울리는 차를 만납니다.</span></div>
<div class="hero-desc">세 번의 선택만으로 이동 습관과 취향을 분석해, 나에게 자연스럽게 어울리는 차량과 이용 조건을 제안합니다.</div>
</div>
""")


# =========================================================
# QUESTION VIEW
# =========================================================
if st.session_state.step < len(questions):
    step = st.session_state.step
    q = questions[step]
    progress = int(((step+1)/len(questions))*100)

    html(f"""
    <div class="step-card">
    <div class="step-top">
    <b>LIFESTYLE SIGNAL {step+1}</b>
    <span>{step+1} / {len(questions)}</span>
    </div>
    <div class="progress"><div style="width:{progress}%"></div></div>
    <div class="step-title">{q["title"]}</div>
    <div class="step-desc">{q["desc"]}</div>
    </div>
    """)

    cols = st.columns(2, gap="large")

    for i,opt in enumerate(q["options"]):
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
                key=f"q_{step}_{i}",
                use_container_width=True
            ):
                st.session_state.answers.append(i)
                st.session_state.step += 1
                st.rerun()

    if step > 0:
        b1,_ = st.columns([1,3])
        with b1:
            if st.button("← 이전", use_container_width=True):
                st.session_state.answers.pop()
                st.session_state.step -= 1
                st.rerun()


# =========================================================
# RESULT VIEW
# =========================================================
else:
    if not EXCEL_PATH.exists():
        st.error(f"엑셀 파일이 없습니다: {EXCEL_PATH}")
        st.stop()

    if not IMAGE_DIR.exists():
        st.error(f"배경 제거 차량 이미지 폴더가 없습니다: {IMAGE_DIR}")
        st.stop()

    df = load_data()

    recommendation = get_recommendation(st.session_state.answers)

    persona = recommendation
    model = recommendation["model"]

    models = df["모델"].dropna().astype(str).unique().tolist()

    # 엑셀에 추천 모델이 없을 경우 첫 번째 모델로 안전하게 대체
    if model not in models:
        model = models[0]

    filtered = df[df["모델"].astype(str)==model].copy()
    colors = filtered["색상"].dropna().astype(str).unique().tolist()

    if st.session_state.color not in colors:
        st.session_state.color = colors[0]

    selected = filtered[
        filtered["색상"].astype(str)==st.session_state.color
    ].iloc[0]

    # Result headline
    html("""
    <div class="result-intro">
    <div class="result-kicker">PERSONALIZED MATCH COMPLETE</div>
    <div class="result-title">당신의 이동 취향을 찾았습니다.</div>
    <div class="result-desc">선택한 라이프스타일 신호를 바탕으로 가장 자연스럽게 어울리는 차량을 제안합니다.</div>
    </div>
    """)

    # Persona
    html(f"""
    <div class="persona-card">
    <div class="persona-visual">{persona["art"]}</div>
    <div>
    <div class="persona-label">YOUR MOBILITY PERSONA</div>
    <div class="persona-name">{persona["name"]}</div>
    <div class="persona-sub">{persona["sub"]}</div>
    <div class="persona-copy">{persona["copy"]}</div>
    <div class="persona-quote">{persona["quote"]}</div>
    </div>
    </div>
    """)

    # 배경 제거 PNG 차량 이미지
    original_name = Path(str(selected["이미지파일명"]))
    png_name = original_name.with_suffix(".png").name
    image_path = IMAGE_DIR / png_name

    # PNG가 아직 없을 경우 기존 실사 JPG를 자동 fallback
    if image_path.exists():
        uri = image_data_uri(image_path)
    else:
        fallback_path = BASE_DIR / "car_images_real" / original_name.name
        uri = image_data_uri(fallback_path)

    r1,r2,r3 = persona["reasons"]
    match_pct = recommendation["match"]

    html(f"""
    <div class="configurator">
    <div class="config-top">
      <div>
        <span class="badge">RECOMMENDED FOR YOU</span>
        <div class="vehicle-name">{model}</div>
        <div class="vehicle-copy">당신의 선택 패턴과 가장 자연스럽게 이어지는 차량입니다.</div>
      </div>
      <div class="match-score"><small>LIFESTYLE MATCH</small><strong>{match_pct}%</strong></div>
    </div>
    <div class="vehicle-stage"><img src="{uri}" alt="{model}"></div>
    <div class="match-row">
      <div class="match-item"><b>MATCH 01</b><span>{r1}</span></div>
      <div class="match-item"><b>MATCH 02</b><span>{r2}</span></div>
      <div class="match-item"><b>MATCH 03</b><span>{r3}</span></div>
    </div>
    </div>
    """)

    # Controls
    left,right = st.columns(2, gap="medium")

    with left:
        html("""
        <div class="control-label">COLOR</div>
        <div class="control-sub">원하는 컬러를 선택하세요.</div>
        """)

        color_cols = st.columns(len(colors))

        for i,color in enumerate(colors):
            with color_cols[i]:
                label = f"✓ {color}" if color == st.session_state.color else color

                if st.button(
                    label,
                    key=f"color_{i}",
                    use_container_width=True
                ):
                    st.session_state.color = color
                    st.rerun()

    with right:
        html("""
        <div class="control-label">TERM</div>
        <div class="control-sub">이용기간을 선택하세요.</div>
        """)

        term_cols = st.columns(3)

        for term in [36,48,60]:
            with term_cols[[36,48,60].index(term)]:
                label = f"✓ {term}개월" if term == st.session_state.months else f"{term}개월"

                if st.button(
                    label,
                    key=f"term_{term}",
                    use_container_width=True
                ):
                    st.session_state.months = term
                    st.rerun()

    # Re-select after color change
    selected = filtered[
        filtered["색상"].astype(str)==st.session_state.color
    ].iloc[0]

    months = st.session_state.months
    column = f"{months}개월"

    monthly = float(selected[column]) if (
        column in selected.index and pd.notna(selected[column])
    ) else 0

    price = int(float(selected["차량가격(만원)"]))

    # Quote
    html(f"""
    <div class="quote-shell">
      <div class="quote-head">
        <div>
          <div class="quote-kicker">PERSONALIZED SMART QUOTE</div>
          <div class="quote-label">나에게 맞춘 예상 이용금액</div>
          <div class="quote-fee">월 <em>{monthly:,.0f}만원</em>부터</div>
        </div>
        <div class="quote-chip">{months}개월 · {st.session_state.color}</div>
      </div>
      <div class="quote-details">
        <div class="quote-detail"><span>추천 차량</span><strong>{model}</strong></div>
        <div class="quote-detail"><span>선택 색상</span><strong>{st.session_state.color}</strong></div>
        <div class="quote-detail"><span>이용기간</span><strong>{months}개월</strong></div>
        <div class="quote-detail"><span>차량가격</span><strong>{price:,}만원</strong></div>
      </div>
      <div class="quote-note">시연용 예상 금액이며 실제 계약 조건에 따라 달라질 수 있습니다.</div>
    </div>
    """)

    st.write("")

    a,b = st.columns([2,1])

    with a:
        if st.button(
            "이 차량으로 내 견적 완성하기 →",
            type="primary",
            use_container_width=True
        ):
            st.success(
                f"{model} / {st.session_state.color} / "
                f"{months}개월 조건이 선택되었습니다."
            )

    with b:
        if st.button(
            "처음부터 다시",
            use_container_width=True
        ):
            st.session_state.step = 0
            st.session_state.answers = []
            st.session_state.color = None
            st.session_state.months = 60
            st.rerun()

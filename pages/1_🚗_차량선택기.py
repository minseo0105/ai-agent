import streamlit as st
import pandas as pd
from pathlib import Path

# =========================================================
# 1. 기본 설정
# =========================================================
st.set_page_config(
    page_title="내차만들기",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 현재 프로젝트 구조:
# ai-agent/
# ├─ app.py
# ├─ sample_cars_v2.xlsx
# ├─ car_images_real/
# └─ pages/
#    └─ 1_🚗_차량선택기.py
BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = BASE_DIR / "sample_cars_v2.xlsx"
IMAGE_DIR = BASE_DIR / "car_images_real"


# =========================================================
# 2. HTML 렌더링 헬퍼
# =========================================================
def html(content):
    clean = "\n".join(line.strip() for line in content.splitlines())
    st.markdown(clean, unsafe_allow_html=True)


# =========================================================
# 3. 디자인
# =========================================================
html("""
<style>
:root{
    --navy:#071426;
    --navy2:#102A52;
    --blue:#2F67F6;
    --violet:#6C55F5;
    --ink:#111827;
    --muted:#748195;
    --line:#E6EBF3;
    --panel:#FFFFFF;
    --soft:#F5F7FB;
}

html, body, [class*="css"]{
    font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}

.stApp{
    background:
        radial-gradient(circle at 85% 5%, rgba(47,103,246,.10), transparent 23%),
        radial-gradient(circle at 8% 32%, rgba(108,85,245,.07), transparent 20%),
        linear-gradient(180deg,#F9FAFC 0%,#F4F6FA 100%);
}

.block-container{
    max-width:1040px;
    padding-top:1.2rem;
    padding-bottom:4rem;
}

header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer{visibility:hidden;}

/* HERO */
.hero{
    position:relative;
    overflow:hidden;
    border-radius:34px;
    min-height:292px;
    padding:54px 55px;
    margin-bottom:24px;
    color:white;
    background:
        radial-gradient(circle at 82% 20%,rgba(116,163,255,.20),transparent 22%),
        linear-gradient(130deg,#061426 0%,#102A55 55%,#214BB5 100%);
    box-shadow:0 28px 70px rgba(10,24,48,.20);
}
.hero:before{
    content:"";
    position:absolute;
    width:250px;height:250px;
    right:-45px;top:-95px;
    border:1px solid rgba(255,255,255,.16);
    border-radius:50%;
    animation:heroOrbit 8s ease-in-out infinite;
}
.hero:after{
    content:"";
    position:absolute;
    width:155px;height:155px;
    right:95px;bottom:-95px;
    border-radius:50%;
    background:rgba(80,132,255,.15);
    filter:blur(2px);
    animation:heroFloat 6s ease-in-out infinite;
}
@keyframes heroOrbit{
    0%,100%{transform:translate(0,0) rotate(0deg)}
    50%{transform:translate(-12px,12px) rotate(7deg)}
}
@keyframes heroFloat{
    0%,100%{transform:translateY(0) scale(1)}
    50%{transform:translateY(-14px) scale(1.07)}
}

.eyebrow{
    position:relative;z-index:2;
    font-size:11px;font-weight:900;
    letter-spacing:.20em;color:#BED5FF;
    margin-bottom:13px;
}
.hero-title{
    position:relative;z-index:2;
    max-width:700px;
    font-size:43px;font-weight:900;
    line-height:1.19;letter-spacing:-.045em;
}
.hero-title b{
    background:linear-gradient(90deg,#FFFFFF,#AFCBFF);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}
.hero-desc{
    position:relative;z-index:2;
    max-width:665px;
    margin-top:17px;
    color:#D8E5F8;font-size:15px;line-height:1.75;
}
.hero-meta{
    position:relative;z-index:2;
    display:flex;gap:8px;flex-wrap:wrap;
    margin-top:23px;
}
.hero-chip{
    padding:7px 12px;
    border-radius:999px;
    border:1px solid rgba(255,255,255,.16);
    background:rgba(255,255,255,.07);
    color:#EDF4FF;font-size:10px;font-weight:800;
}

/* QUESTION */
.q-head{
    background:rgba(255,255,255,.94);
    border:1px solid var(--line);
    border-radius:26px;
    padding:29px 31px 25px;
    margin-bottom:15px;
    box-shadow:0 12px 34px rgba(15,23,42,.05);
}
.step-row{
    display:flex;justify-content:space-between;align-items:center;
    margin-bottom:10px;
}
.step-label{font-size:11px;font-weight:900;color:var(--blue);letter-spacing:.09em}
.step-count{font-size:11px;font-weight:800;color:#9AA6B7}
.progress{
    height:6px;border-radius:999px;background:#E9EDF5;overflow:hidden;margin-bottom:23px;
}
.progress > div{
    height:100%;border-radius:999px;
    background:linear-gradient(90deg,var(--blue),var(--violet));
    transition:width .35s ease;
}
.question-title{
    font-size:26px;font-weight:900;color:var(--ink);letter-spacing:-.035em;
}
.question-desc{
    margin-top:7px;color:var(--muted);font-size:13px;line-height:1.6;
}

/* VISUAL OPTION */
.visual-card{
    height:290px;
    border:1px solid #E4E9F1;
    border-radius:26px;
    background:linear-gradient(180deg,#FFFFFF 0%,#FBFCFE 100%);
    overflow:hidden;
    box-shadow:0 10px 28px rgba(15,23,42,.045);
    transition:.22s ease;
    margin-bottom:8px;
}
.visual-card:hover{
    transform:translateY(-4px);
    border-color:#B8CBF8;
    box-shadow:0 18px 38px rgba(47,103,246,.09);
}
.visual-scene{
    position:relative;
    height:190px;
    margin:14px;
    border-radius:20px;
    overflow:hidden;
    background:
        radial-gradient(circle at 73% 25%,rgba(255,255,255,.85),transparent 18%),
        linear-gradient(145deg,#EEF4FF,#F4F0FF);
}
.visual-copy{
    padding:4px 20px 18px;text-align:left;
}
.visual-title{
    font-size:16px;font-weight:900;color:#182236;letter-spacing:-.02em;
}
.visual-desc{
    margin-top:5px;font-size:12px;line-height:1.5;color:#8591A2;
}

/* SVG motion */
.scene-svg{
    width:100%;height:100%;
}
.float-a{animation:floatA 3.8s ease-in-out infinite}
.float-b{animation:floatB 4.6s ease-in-out infinite}
.drive{animation:drive 4.8s ease-in-out infinite}
.pulse{animation:pulse 3s ease-in-out infinite;transform-origin:center}
.rotate{animation:slowRotate 10s linear infinite;transform-origin:center}
@keyframes floatA{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes floatB{0%,100%{transform:translateY(0)}50%{transform:translateY(5px)}}
@keyframes drive{0%,100%{transform:translateX(-4px)}50%{transform:translateX(8px)}}
@keyframes pulse{0%,100%{transform:scale(.96);opacity:.80}50%{transform:scale(1.05);opacity:1}}
@keyframes slowRotate{from{transform:rotate(0)}to{transform:rotate(360deg)}}

/* BUTTON */
.stButton > button{
    width:100%;
    min-height:48px;
    border-radius:14px !important;
    border:1px solid #DBE2EC !important;
    background:#FFFFFF !important;
    color:#223047 !important;
    font-weight:800 !important;
    transition:.18s ease;
}
.stButton > button:hover{
    transform:translateY(-1px);
    color:var(--blue) !important;
    border-color:#98B6FF !important;
    box-shadow:0 8px 20px rgba(47,103,246,.08);
}
button[kind="primary"]{
    background:linear-gradient(135deg,#2457D7,#6647E8) !important;
    color:white !important;border:none !important;
}

/* PERSONA */
.persona-card{
    position:relative;
    overflow:hidden;
    border-radius:30px;
    padding:34px;
    margin-bottom:18px;
    color:white;
    background:
        radial-gradient(circle at 83% 21%,rgba(136,174,255,.19),transparent 20%),
        linear-gradient(132deg,#071426 0%,#102958 60%,#2E317E 100%);
    box-shadow:0 22px 52px rgba(15,23,42,.16);
}
.persona-card:after{
    content:"";
    position:absolute;
    width:150px;height:150px;border-radius:50%;
    right:-55px;bottom:-70px;
    background:rgba(92,128,255,.15);
    animation:heroFloat 5.5s ease-in-out infinite;
}
.persona-layout{
    position:relative;z-index:2;
    display:grid;
    grid-template-columns:165px 1fr;
    gap:28px;
    align-items:center;
}
.persona-art{
    height:165px;border-radius:25px;
    display:flex;align-items:center;justify-content:center;
    background:linear-gradient(145deg,rgba(255,255,255,.12),rgba(255,255,255,.04));
    border:1px solid rgba(255,255,255,.13);
    backdrop-filter:blur(9px);
}
.persona-art svg{width:135px;height:135px}
.persona-label{
    color:#AFC9FF;font-size:10px;font-weight:900;letter-spacing:.18em;
}
.persona-name{
    margin-top:7px;font-size:33px;font-weight:900;letter-spacing:-.04em;
}
.persona-sub{
    margin-top:5px;color:#D0DDF4;font-size:14px;font-weight:700;
}
.persona-copy{
    margin-top:15px;color:#E3EAF6;font-size:13px;line-height:1.72;
}
.persona-quote{
    margin-top:15px;padding:12px 15px;border-radius:14px;
    background:rgba(255,255,255,.07);
    border:1px solid rgba(255,255,255,.10);
    color:#FFFFFF;font-size:12px;font-weight:700;
}
.tags{margin-top:14px}
.tag{
    display:inline-block;margin-right:5px;margin-bottom:5px;
    padding:5px 10px;border-radius:999px;
    background:rgba(255,255,255,.09);
    border:1px solid rgba(255,255,255,.11);
    color:#EAF1FF;font-size:10px;font-weight:700;
}

/* CAR SHOWCASE */
.car-stage{
    position:relative;
    border-radius:30px;
    overflow:hidden;
    background:
        radial-gradient(circle at 50% 45%,rgba(217,227,245,.95),transparent 31%),
        linear-gradient(180deg,#F8FAFD 0%,#EEF2F7 100%);
    border:1px solid #E1E7F0;
    box-shadow:0 18px 44px rgba(15,23,42,.075);
    padding:24px 28px 26px;
    margin-bottom:18px;
}
.car-stage:before{
    content:"";
    position:absolute;
    width:64%;height:22px;
    left:18%;bottom:38px;
    border-radius:50%;
    background:rgba(21,35,58,.15);
    filter:blur(15px);
}
.car-top{
    position:relative;z-index:2;
    display:flex;justify-content:space-between;align-items:flex-start;
}
.smart-badge{
    display:inline-block;
    padding:6px 10px;border-radius:999px;
    background:#E8EFFF;color:#355ED5;
    font-size:10px;font-weight:900;letter-spacing:.07em;
}
.car-name{
    margin-top:9px;font-size:30px;font-weight:900;color:#111827;letter-spacing:-.035em;
}
.car-sub{
    margin-top:5px;color:#738094;font-size:12px;
}
.car-image-shell{
    position:relative;z-index:2;
    height:390px;
    display:flex;
    justify-content:center;
    align-items:center;
    overflow:hidden;
}
.car-image-shell img{
    width:88% !important;
    max-height:345px !important;
    object-fit:contain !important;
    border-radius:0 !important;
    box-shadow:none !important;
    animation:carFloat 4.2s ease-in-out infinite;
}
@keyframes carFloat{
    0%,100%{transform:translateY(3px)}
    50%{transform:translateY(-5px)}
}

/* MATCH */
.match-grid{
    position:relative;z-index:2;
    display:grid;grid-template-columns:repeat(3,1fr);gap:10px;
}
.match-item{
    padding:13px 14px;border-radius:14px;
    background:rgba(255,255,255,.76);
    border:1px solid rgba(222,228,237,.95);
    backdrop-filter:blur(5px);
}
.match-num{font-size:9px;font-weight:900;color:#3A66E2}
.match-text{margin-top:3px;font-size:11px;font-weight:800;color:#26364E}

/* COLOR + TERM */
.control-card{
    background:#FFFFFF;
    border:1px solid #E4E9F1;
    border-radius:24px;
    padding:23px 24px;
    margin-top:14px;
    box-shadow:0 10px 28px rgba(15,23,42,.045);
}
.control-label{
    font-size:11px;font-weight:900;color:#718096;letter-spacing:.10em;
    margin-bottom:12px;
}
.term-grid{
    display:grid;grid-template-columns:repeat(3,1fr);gap:9px;
}
.term-pill{
    border-radius:16px;
    padding:13px 8px;
    text-align:center;
    border:1px solid #DCE3ED;
    background:#FAFBFD;
    color:#354258;
    font-size:12px;font-weight:900;
}
.term-pill.active{
    border-color:#4C75E8;
    background:linear-gradient(135deg,#EDF3FF,#F2EEFF);
    color:#2857D4;
}

/* QUOTE */
.quote-card{
    position:relative;overflow:hidden;
    margin-top:16px;
    border-radius:27px;padding:27px 29px;
    color:white;
    background:
        radial-gradient(circle at 88% 18%,rgba(104,149,255,.19),transparent 20%),
        linear-gradient(135deg,#071525,#122955 65%,#1E3A8A);
    box-shadow:0 18px 42px rgba(15,23,42,.18);
}
.quote-row{
    display:flex;justify-content:space-between;
    padding:5px 0;color:#C7D4E7;font-size:12px;
}
.quote-divider{height:1px;background:rgba(255,255,255,.12);margin:14px 0}
.monthly-label{color:#9FC0FF;font-size:10px;font-weight:900;letter-spacing:.08em}
.monthly-fee{margin-top:4px;font-size:34px;font-weight:900;letter-spacing:-.04em}
.monthly-note{margin-top:6px;color:#99A8BC;font-size:10px}

@media(max-width:720px){
    .hero{padding:38px 26px;min-height:auto;border-radius:26px}
    .hero-title{font-size:31px}
    .persona-layout{grid-template-columns:1fr}
    .persona-art{height:140px}
    .car-image-shell{height:300px}
    .match-grid{grid-template-columns:1fr}
}
</style>
""")


# =========================================================
# 4. 질문용 동적 SVG 일러스트
# =========================================================
CITY_SCENE = """
<svg class="scene-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="sky1" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#EAF1FF"/>
<stop offset="100%" stop-color="#F5EEFF"/>
</linearGradient>
<linearGradient id="car1" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#2F67F6"/>
<stop offset="100%" stop-color="#654BE5"/>
</linearGradient>
</defs>
<rect width="420" height="220" rx="24" fill="url(#sky1)"/>
<circle class="pulse" cx="337" cy="47" r="24" fill="#FFFFFF" opacity=".9"/>
<rect x="38" y="55" width="52" height="108" rx="8" fill="#B7C7E8"/>
<rect x="102" y="29" width="66" height="134" rx="9" fill="#9FB4DF"/>
<rect x="181" y="72" width="48" height="91" rx="7" fill="#C3CDE5"/>
<rect x="243" y="45" width="75" height="118" rx="9" fill="#AABAE0"/>
<g opacity=".85">
<rect x="53" y="71" width="11" height="11" rx="2" fill="#F7FAFF"/>
<rect x="70" y="71" width="11" height="11" rx="2" fill="#F7FAFF"/>
<rect x="119" y="48" width="12" height="12" rx="2" fill="#F7FAFF"/>
<rect x="139" y="48" width="12" height="12" rx="2" fill="#F7FAFF"/>
<rect x="262" y="64" width="13" height="13" rx="2" fill="#F7FAFF"/>
<rect x="285" y="64" width="13" height="13" rx="2" fill="#F7FAFF"/>
</g>
<rect x="0" y="163" width="420" height="57" fill="#DCE4F2"/>
<rect x="0" y="188" width="420" height="3" fill="#F8FAFC" opacity=".9"/>
<g class="drive">
<rect x="135" y="149" width="128" height="35" rx="15" fill="url(#car1)"/>
<path d="M160 149L181 128H231L250 149Z" fill="#446FD8"/>
<path d="M185 132H205V148H168Z" fill="#DCE9FF" opacity=".9"/>
<path d="M209 132H228L243 148H209Z" fill="#DCE9FF" opacity=".9"/>
<circle cx="165" cy="184" r="12" fill="#273249"/>
<circle cx="237" cy="184" r="12" fill="#273249"/>
<circle cx="165" cy="184" r="5" fill="#A9B5C9"/>
<circle cx="237" cy="184" r="5" fill="#A9B5C9"/>
</g>
</svg>
"""

TRIP_SCENE = """
<svg class="scene-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="sky2" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#EAF4FF"/>
<stop offset="100%" stop-color="#EFEAFF"/>
</linearGradient>
</defs>
<rect width="420" height="220" rx="24" fill="url(#sky2)"/>
<circle class="pulse" cx="328" cy="53" r="27" fill="#FFD778"/>
<path class="float-b" d="M0 171L95 87L164 151L234 60L345 171Z" fill="#9EB3DF"/>
<path class="float-a" d="M90 171L170 100L229 154L295 93L420 171Z" fill="#718FD1"/>
<path d="M0 171H420V220H0Z" fill="#D9E4DE"/>
<path d="M0 220C89 180 161 183 234 195C304 206 350 196 420 173V220H0Z" fill="#E8EDF5"/>
<g class="drive">
<rect x="151" y="155" width="122" height="35" rx="14" fill="#263B67"/>
<path d="M174 155L193 134H237L257 155Z" fill="#36517E"/>
<rect x="193" y="137" width="39" height="15" rx="3" fill="#DCE9FF" opacity=".9"/>
<circle cx="178" cy="190" r="12" fill="#243044"/>
<circle cx="248" cy="190" r="12" fill="#243044"/>
<path d="M206 130L215 116L224 130Z" fill="#7A5AF8"/>
</g>
</svg>
"""

DUO_SCENE = """
<svg class="scene-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="sky3" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#EFF4FF"/>
<stop offset="100%" stop-color="#F6F1FF"/>
</linearGradient>
</defs>
<rect width="420" height="220" rx="24" fill="url(#sky3)"/>
<circle cx="210" cy="108" r="76" fill="#FFFFFF" opacity=".72"/>
<g class="float-a">
<circle cx="167" cy="87" r="29" fill="#385FDB"/>
<path d="M121 166C124 127 141 111 167 111C193 111 210 127 213 166Z" fill="#6F8DE0"/>
</g>
<g class="float-b">
<circle cx="251" cy="87" r="29" fill="#7056E8"/>
<path d="M205 166C208 127 225 111 251 111C277 111 294 127 297 166Z" fill="#9C8BEA"/>
</g>
<path d="M190 111C199 119 219 119 228 111" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round" opacity=".9"/>
<circle class="pulse" cx="210" cy="45" r="8" fill="#89A8F0"/>
</svg>
"""

FAMILY_SCENE = """
<svg class="scene-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="sky4" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#EDF4FF"/>
<stop offset="100%" stop-color="#F2EDFF"/>
</linearGradient>
</defs>
<rect width="420" height="220" rx="24" fill="url(#sky4)"/>
<circle cx="210" cy="108" r="82" fill="#FFFFFF" opacity=".72"/>
<g class="float-a">
<circle cx="157" cy="84" r="26" fill="#355FD8"/>
<path d="M116 162C119 125 134 111 157 111C180 111 195 125 198 162Z" fill="#7692E0"/>
</g>
<g class="float-b">
<circle cx="263" cy="84" r="26" fill="#6A55E4"/>
<path d="M222 162C225 125 240 111 263 111C286 111 301 125 304 162Z" fill="#9D8DEA"/>
</g>
<g class="pulse">
<circle cx="210" cy="116" r="20" fill="#486CD7"/>
<path d="M177 172C180 143 190 132 210 132C230 132 240 143 243 172Z" fill="#95A8E8"/>
</g>
<path d="M190 54C197 45 223 45 230 54" stroke="#88A5EC" stroke-width="5" stroke-linecap="round"/>
</svg>
"""

STYLE_SCENE = """
<svg class="scene-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg">
<defs>
<linearGradient id="gem" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#2E67F4"/>
<stop offset="100%" stop-color="#8057F0"/>
</linearGradient>
</defs>
<rect width="420" height="220" rx="24" fill="#F1F4FF"/>
<circle cx="210" cy="110" r="80" fill="#FFFFFF" opacity=".68"/>
<circle class="rotate" cx="210" cy="110" r="65" fill="none" stroke="#B4C7F7" stroke-width="2" stroke-dasharray="8 10"/>
<g class="pulse">
<path d="M210 45L273 89L249 163H171L147 89Z" fill="url(#gem)"/>
<path d="M210 45L210 163M147 89H273M171 163L210 89L249 163M147 89L210 89L273 89" stroke="#FFFFFF" stroke-width="2.5" opacity=".75"/>
</g>
<circle cx="292" cy="62" r="8" fill="#8DAAF3" class="float-a"/>
<circle cx="126" cy="152" r="6" fill="#B299F7" class="float-b"/>
</svg>
"""

SPACE_SCENE = """
<svg class="scene-svg" viewBox="0 0 420 220" xmlns="http://www.w3.org/2000/svg">
<rect width="420" height="220" rx="24" fill="#EFF4FF"/>
<rect x="78" y="43" width="264" height="134" rx="26" fill="#FFFFFF" opacity=".76"/>
<g class="pulse">
<rect x="112" y="72" width="84" height="76" rx="16" fill="#4B70DB"/>
<rect x="207" y="72" width="101" height="76" rx="16" fill="#8D82E9"/>
</g>
<g class="float-a">
<rect x="132" y="91" width="44" height="38" rx="9" fill="#D8E4FF"/>
<path d="M221 91H294M221 110H283M221 129H272" stroke="#E7E4FF" stroke-width="8" stroke-linecap="round"/>
</g>
<path d="M100 168H320" stroke="#A8B9DF" stroke-width="5" stroke-linecap="round"/>
</svg>
"""


# =========================================================
# 5. 질문
# =========================================================
questions = [
    {
        "question": "당신의 주말은 어느 장면에 더 가깝나요?",
        "desc": "일상에서 가장 자주 마주하는 이동 장면부터 읽어볼게요.",
        "options": [
            {"visual": CITY_SCENE, "label": "도심을 가볍게 누비는 편", "desc": "맛집 · 카페 · 쇼핑 · 근거리 이동"},
            {"visual": TRIP_SCENE, "label": "주말이면 멀리 떠나는 편", "desc": "여행 · 캠핑 · 레저 · 장거리 이동"},
        ],
    },
    {
        "question": "차 안에서 가장 자주 함께하는 사람은 누구인가요?",
        "desc": "누구와 이동하는지가 공간과 편안함의 기준을 바꿉니다.",
        "options": [
            {"visual": DUO_SCENE, "label": "혼자 또는 둘이", "desc": "나의 감도와 이동 편의가 더 중요해요"},
            {"visual": FAMILY_SCENE, "label": "가족과 함께", "desc": "사람과 짐, 일정까지 함께 담아야 해요"},
        ],
    },
    {
        "question": "차를 고를 때 마지막까지 포기하기 어려운 한 가지는?",
        "desc": "당신의 선택 기준을 하나만 남기면 추천이 더 선명해집니다.",
        "options": [
            {"visual": STYLE_SCENE, "label": "볼 때마다 마음에 드는 디자인", "desc": "스타일 · 정제된 주행감 · 소유 만족감"},
            {"visual": SPACE_SCENE, "label": "필요할 때 든든한 공간", "desc": "수납 · 안정감 · 다양한 상황 대응력"},
        ],
    },
]


# =========================================================
# 6. 8개 선택 조합 → 6개 페르소나
# =========================================================
personas = {
    "CITY_CURATOR": {
        "name": "CITY CURATOR",
        "sub": "도시의 장면을 고르는 사람",
        "copy": "차를 단순한 이동수단보다 하루의 분위기를 완성하는 오브제에 가깝게 봅니다. "
                "복잡한 도심에서 다루기 편하면서도, 주차한 뒤 다시 한 번 돌아보게 되는 차를 선호합니다.",
        "quote": "“큰 차보다, 내 일상의 템포와 잘 맞는 차.”",
        "tags": ["도심 감도", "스타일", "데일리", "정제된 주행"],
        "models": ["디 올 뉴 그랜저", "쏘나타"],
        "reasons": ["도심 활용성", "정제된 승차감", "스타일 만족도"],
        "art": "CITY"
    },
    "QUIET_LUXE": {
        "name": "QUIET LUXE",
        "sub": "조용한 만족을 고르는 사람",
        "copy": "화려한 기능보다 매일 타도 질리지 않는 감도와 편안함을 중요하게 봅니다. "
                "차 안에서 보내는 시간이 스트레스 없이 부드럽게 이어지는가가 선택의 기준입니다.",
        "quote": "“좋은 차는 과시보다, 매일의 기분을 조용히 높여준다.”",
        "tags": ["편안함", "정숙성", "세련된 감도", "데일리 프리미엄"],
        "models": ["디 올 뉴 그랜저", "쏘나타"],
        "reasons": ["일상 편안함", "정숙한 이동", "균형 잡힌 감성"],
        "art": "STYLE"
    },
    "FAMILY_DIRECTOR": {
        "name": "FAMILY DIRECTOR",
        "sub": "가족의 하루를 설계하는 사람",
        "copy": "등하원, 장보기, 주말 일정, 여행까지 차량 하나에 가족의 하루가 연결됩니다. "
                "그래서 나만 편한 차보다 모두의 이동이 편해지는 차를 더 좋은 선택으로 봅니다.",
        "quote": "“내가 편한 차보다, 모두가 편해지는 차.”",
        "tags": ["패밀리 허브", "공간", "승하차", "일상 확장"],
        "models": ["디 올 뉴 팰리세이드", "더 뉴 카니발"],
        "reasons": ["가족 이동 최적화", "공간 활용성", "안정적인 주행"],
        "art": "FAMILY"
    },
    "WEEKEND_ESCAPER": {
        "name": "WEEKEND ESCAPER",
        "sub": "주말의 반경을 넓히는 사람",
        "copy": "평일의 이동보다 주말의 가능성을 더 크게 봅니다. "
                "갑자기 떠나는 여행과 캠핑 장비, 긴 이동거리까지 받아주는 여유가 차량 선택의 핵심입니다.",
        "quote": "“차가 커지는 게 아니라, 내 주말의 반경이 넓어진다.”",
        "tags": ["여행", "캠핑", "장거리", "공간 확장"],
        "models": ["더 뉴 카니발", "디 올 뉴 팰리세이드"],
        "reasons": ["장거리 편안함", "짐 적재 능력", "여행 활용성"],
        "art": "TRIP"
    },
    "FLEX_CAPTAIN": {
        "name": "FLEX CAPTAIN",
        "sub": "평일과 주말을 모두 잡는 사람",
        "copy": "도심의 편리함도 놓치고 싶지 않고, 주말에는 공간과 활용성도 필요합니다. "
                "한쪽으로 치우친 차보다 상황에 따라 역할을 바꿀 수 있는 균형감 있는 선택을 선호합니다.",
        "quote": "“월요일에도 좋고, 토요일에는 더 좋은 차.”",
        "tags": ["밸런스", "멀티유즈", "도심+여행", "실용성"],
        "models": ["디 올 뉴 팰리세이드", "디 올 뉴 그랜저"],
        "reasons": ["다목적 활용", "도심 적응력", "주말 확장성"],
        "art": "SPACE"
    },
    "DESIGN_VOYAGER": {
        "name": "DESIGN VOYAGER",
        "sub": "감도와 여행을 함께 고르는 사람",
        "copy": "떠나는 즐거움만큼 타고 있는 순간의 분위기도 중요하게 생각합니다. "
                "공간만 큰 차보다, 이동의 장면 자체를 멋지게 만들어주는 차에 더 끌립니다.",
        "quote": "“목적지보다 가는 길이 기억에 남는 차.”",
        "tags": ["스타일", "여행 감성", "주행 경험", "취향"],
        "models": ["디 올 뉴 그랜저", "디 올 뉴 팰리세이드"],
        "reasons": ["디자인 만족도", "장거리 승차감", "라이프스타일 감성"],
        "art": "STYLE"
    },
}

combo_map = {
    (0, 0, 0): "CITY_CURATOR",
    (0, 0, 1): "QUIET_LUXE",
    (0, 1, 0): "QUIET_LUXE",
    (0, 1, 1): "FAMILY_DIRECTOR",
    (1, 0, 0): "DESIGN_VOYAGER",
    (1, 0, 1): "WEEKEND_ESCAPER",
    (1, 1, 0): "DESIGN_VOYAGER",
    (1, 1, 1): "WEEKEND_ESCAPER",
}


# =========================================================
# 7. 페르소나용 동적 이미지형 SVG
# =========================================================
PERSONA_ART = {
"CITY": """
<svg viewBox="0 0 160 160">
<defs><linearGradient id="pc1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#64A1FF"/><stop offset="1" stop-color="#876AF7"/></linearGradient></defs>
<circle cx="80" cy="80" r="61" fill="none" stroke="rgba(255,255,255,.16)" stroke-width="1.5" class="rotate" stroke-dasharray="7 9"/>
<g class="float-a">
<rect x="35" y="65" width="22" height="47" rx="5" fill="#9DB9F3"/>
<rect x="63" y="42" width="29" height="70" rx="5" fill="url(#pc1)"/>
<rect x="98" y="57" width="27" height="55" rx="5" fill="#B4A7F4"/>
</g>
<path d="M25 119H135" stroke="#DCE7FF" stroke-width="4" stroke-linecap="round"/>
<g class="drive"><rect x="54" y="104" width="58" height="17" rx="8" fill="#FFFFFF"/><circle cx="67" cy="121" r="6" fill="#4265C9"/><circle cx="99" cy="121" r="6" fill="#4265C9"/></g>
</svg>
""",
"STYLE": """
<svg viewBox="0 0 160 160">
<defs><linearGradient id="pc2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#73B1FF"/><stop offset="1" stop-color="#8B65F5"/></linearGradient></defs>
<circle cx="80" cy="80" r="58" fill="none" stroke="rgba(255,255,255,.16)" class="rotate" stroke-dasharray="7 10"/>
<g class="pulse"><path d="M80 28L127 62L109 119H51L33 62Z" fill="url(#pc2)"/><path d="M80 28L80 119M33 62H127M51 119L80 62L109 119" stroke="#FFFFFF" stroke-width="2" opacity=".7"/></g>
</svg>
""",
"FAMILY": """
<svg viewBox="0 0 160 160">
<circle cx="80" cy="80" r="60" fill="rgba(255,255,255,.06)"/>
<g class="float-a"><circle cx="53" cy="62" r="18" fill="#78A8FF"/><path d="M27 118C30 91 39 80 53 80C67 80 76 91 79 118Z" fill="#7192E3"/></g>
<g class="float-b"><circle cx="108" cy="62" r="18" fill="#A687F4"/><path d="M82 118C85 91 94 80 108 80C122 80 131 91 134 118Z" fill="#9A82E7"/></g>
<g class="pulse"><circle cx="80" cy="89" r="14" fill="#FFFFFF"/><path d="M59 128C61 107 68 100 80 100C92 100 99 107 101 128Z" fill="#BFD3FF"/></g>
</svg>
""",
"TRIP": """
<svg viewBox="0 0 160 160">
<circle cx="118" cy="39" r="16" fill="#FFD987" class="pulse"/>
<path d="M18 112L53 61L81 99L103 50L143 112Z" fill="#7799DB" class="float-a"/>
<path d="M17 112H144V128H17Z" fill="rgba(255,255,255,.18)"/>
<g class="drive"><rect x="51" y="100" width="63" height="19" rx="8" fill="#FFFFFF"/><circle cx="65" cy="119" r="7" fill="#405D9E"/><circle cx="101" cy="119" r="7" fill="#405D9E"/></g>
</svg>
""",
"SPACE": """
<svg viewBox="0 0 160 160">
<rect x="24" y="29" width="112" height="102" rx="24" fill="rgba(255,255,255,.07)" stroke="rgba(255,255,255,.13)"/>
<g class="pulse"><rect x="40" y="48" width="34" height="64" rx="9" fill="#75A5FB"/><rect x="83" y="48" width="37" height="28" rx="9" fill="#9A7DEF"/><rect x="83" y="84" width="37" height="28" rx="9" fill="#C4B7FA"/></g>
</svg>
"""
}


# =========================================================
# 8. 데이터
# =========================================================
@st.cache_data
def load_data():
    return pd.read_excel(EXCEL_PATH, sheet_name="차량목록")


# =========================================================
# 9. 상태
# =========================================================
if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = []
if "color" not in st.session_state:
    st.session_state.color = None
if "months" not in st.session_state:
    st.session_state.months = 60


# =========================================================
# 10. HERO
# =========================================================
html("""
<div class="hero">
<div class="eyebrow">MY CAR MAKER · PERSONALIZED MOBILITY</div>
<div class="hero-title">세 번의 선택으로,<br><b>나를 닮은 차를 발견하세요.</b></div>
<div class="hero-desc">차종을 고르는 대신 당신의 하루를 먼저 묻습니다. 이동 장면, 함께 타는 사람, 포기할 수 없는 취향을 읽어 지금의 라이프스타일과 가장 자연스럽게 맞는 차량을 제안합니다.</div>
<div class="hero-meta">
<span class="hero-chip">3 LIFESTYLE SIGNALS</span>
<span class="hero-chip">PERSONA MATCHING</span>
<span class="hero-chip">SMART QUOTE</span>
</div>
</div>
""")


# =========================================================
# 11. 질문 화면
# =========================================================
if st.session_state.step < len(questions):
    step = st.session_state.step
    q = questions[step]
    progress = int(((step + 1) / len(questions)) * 100)

    html(f"""
    <div class="q-head">
    <div class="step-row">
    <div class="step-label">LIFESTYLE SIGNAL {step + 1}</div>
    <div class="step-count">{step + 1} / {len(questions)}</div>
    </div>
    <div class="progress"><div style="width:{progress}%"></div></div>
    <div class="question-title">{q["question"]}</div>
    <div class="question-desc">{q["desc"]}</div>
    </div>
    """)

    cols = st.columns(2, gap="large")
    for i, opt in enumerate(q["options"]):
        with cols[i]:
            html(f"""
            <div class="visual-card">
            <div class="visual-scene">{opt["visual"]}</div>
            <div class="visual-copy">
            <div class="visual-title">{opt["label"]}</div>
            <div class="visual-desc">{opt["desc"]}</div>
            </div>
            </div>
            """)
            if st.button(
                "이 장면이 나와 가까워요",
                key=f"q_{step}_{i}",
                use_container_width=True
            ):
                st.session_state.answers.append(i)
                st.session_state.step += 1
                st.rerun()

    if step > 0:
        back_col, _ = st.columns([1, 3])
        with back_col:
            if st.button("← 이전 선택", use_container_width=True):
                st.session_state.answers.pop()
                st.session_state.step -= 1
                st.rerun()


# =========================================================
# 12. 결과 화면
# =========================================================
else:
    if not EXCEL_PATH.exists():
        st.error(f"엑셀 파일을 찾지 못했습니다: {EXCEL_PATH}")
        st.stop()

    if not IMAGE_DIR.exists():
        st.error(f"이미지 폴더를 찾지 못했습니다: {IMAGE_DIR}")
        st.stop()

    try:
        df = load_data()
    except Exception as e:
        st.error("sample_cars_v2.xlsx의 '차량목록' 시트를 확인해주세요.")
        st.code(str(e))
        st.stop()

    combo = tuple(st.session_state.answers)
    persona_key = combo_map.get(combo, "FLEX_CAPTAIN")
    persona = personas[persona_key]

    models = df["모델"].dropna().astype(str).unique().tolist()
    recommended_model = next(
        (m for m in persona["models"] if m in models),
        models[0]
    )

    filtered = df[df["모델"].astype(str) == recommended_model].copy()
    colors = filtered["색상"].dropna().astype(str).unique().tolist()

    if not colors:
        st.error("선택 가능한 색상 데이터가 없습니다.")
        st.stop()

    if st.session_state.color not in colors:
        st.session_state.color = colors[0]

    selected = filtered[
        filtered["색상"].astype(str) == st.session_state.color
    ].iloc[0]

    # Persona
    tags = "".join(f'<span class="tag">#{x}</span>' for x in persona["tags"])
    persona_art = PERSONA_ART[persona["art"]]

    html(f"""
    <div class="persona-card">
    <div class="persona-layout">
    <div class="persona-art">{persona_art}</div>
    <div>
    <div class="persona-label">YOUR MOBILITY PERSONA</div>
    <div class="persona-name">{persona["name"]}</div>
    <div class="persona-sub">{persona["sub"]}</div>
    <div class="persona-copy">{persona["copy"]}</div>
    <div class="persona-quote">{persona["quote"]}</div>
    <div class="tags">{tags}</div>
    </div>
    </div>
    </div>
    """)

    # Car stage header
    r1, r2, r3 = persona["reasons"]
    html(f"""
    <div class="car-stage">
    <div class="car-top">
    <div>
    <span class="smart-badge">SMART MATCH · 01</span>
    <div class="car-name">{recommended_model}</div>
    <div class="car-sub">당신의 선택 장면과 가장 자연스럽게 이어지는 차량입니다.</div>
    </div>
    </div>
    """)

    # Vehicle image, rendered inside same visual stage via Streamlit image container
    image_path = IMAGE_DIR / str(selected["이미지파일명"])
    if image_path.exists():
        html('<div class="car-image-shell">')
        st.image(str(image_path), use_container_width=True)
        html('</div>')
    else:
        st.warning(f"이미지를 찾지 못했습니다: {image_path.name}")

    html(f"""
    <div class="match-grid">
    <div class="match-item"><div class="match-num">MATCH 01</div><div class="match-text">{r1}</div></div>
    <div class="match-item"><div class="match-num">MATCH 02</div><div class="match-text">{r2}</div></div>
    <div class="match-item"><div class="match-num">MATCH 03</div><div class="match-text">{r3}</div></div>
    </div>
    </div>
    """)

    # Color selector
    html("""
    <div class="control-card">
    <div class="control-label">COLOR</div>
    </div>
    """)
    color_cols = st.columns(len(colors))
    for i, color in enumerate(colors):
        with color_cols[i]:
            label = f"✓ {color}" if color == st.session_state.color else color
            if st.button(label, key=f"color_{i}", use_container_width=True):
                st.session_state.color = color
                st.rerun()

    selected = filtered[
        filtered["색상"].astype(str) == st.session_state.color
    ].iloc[0]

    # Period - no radio
    html("""
    <div class="control-card">
    <div class="control-label">이용기간</div>
    <div style="color:#8A95A5;font-size:12px;margin-bottom:12px;">원하는 기간을 선택하세요.</div>
    </div>
    """)

    term_cols = st.columns(3)
    for idx, term in enumerate([36, 48, 60]):
        with term_cols[idx]:
            label = f"✓ {term}개월" if st.session_state.months == term else f"{term}개월"
            if st.button(label, key=f"term_{term}", use_container_width=True):
                st.session_state.months = term
                st.rerun()

    months = st.session_state.months

    # Quote
    column = f"{months}개월"
    if column in selected.index and pd.notna(selected[column]):
        monthly_fee = float(selected[column])
    else:
        price_temp = float(selected["차량가격(만원)"])
        residual = max(0.35, 0.75 - months / 100)
        monthly_fee = round(
            (price_temp * (1 - residual)) / months + price_temp * 0.012,
            1
        )

    price = int(float(selected["차량가격(만원)"]))

    html(f"""
    <div class="quote-card">
    <div class="quote-row"><span>추천 차량</span><span>{recommended_model}</span></div>
    <div class="quote-row"><span>선택 색상</span><span>{st.session_state.color}</span></div>
    <div class="quote-row"><span>차량 가격</span><span>{price:,}만원</span></div>
    <div class="quote-row"><span>이용기간</span><span>{months}개월</span></div>
    <div class="quote-divider"></div>
    <div class="monthly-label">ESTIMATED MONTHLY PAYMENT</div>
    <div class="monthly-fee">월 {monthly_fee:,.0f}만원부터</div>
    <div class="monthly-note">시연용 예상 금액이며 실제 계약 조건에 따라 달라질 수 있습니다.</div>
    </div>
    """)

    st.write("")
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("이 차량으로 내 견적 완성하기 →", type="primary", use_container_width=True):
            st.success(
                f"{recommended_model} / {st.session_state.color} / "
                f"{months}개월 조건이 선택되었습니다."
            )
    with c2:
        if st.button("처음부터 다시", use_container_width=True):
            st.session_state.step = 0
            st.session_state.answers = []
            st.session_state.color = None
            st.session_state.months = 60
            st.rerun()

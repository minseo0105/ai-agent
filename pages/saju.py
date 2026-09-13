import streamlit as st
from datetime import date, datetime
from collections import Counter
import json
import textwrap
from services.navigation import render_sidebar

# =========================================================
# AI 명리 인사이트
# pages/saju.py
#
# 필요 패키지:
#   pip install lunar_python openai
#
# requirements.txt 에 추가:
#   lunar_python
#   openai
# =========================================================


# =========================================================
# 0. 라이브러리 로딩
# =========================================================

try:
    from lunar_python import Solar, Lunar
    LUNAR_AVAILABLE = True
except Exception:
    LUNAR_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False


# =========================================================
# 1. CSS
# - 전체를 밝은 배경으로 변경
# - 라벨/라디오 가독성 강화
# - 모바일 세로 길이 축소
# =========================================================

st.markdown(
    """
    <style>
    :root {
        --navy: #2F241C;
        --navy2: #4B3525;
        --blue: #B8873B;
        --indigo: #A8742A;
        --text: #2F241C;
        --muted: #7C6A5B;
        --line: #E8DDCC;
        --soft: #FCF8F1;
        --soft-blue: #FBF2DF;
        --white: #FFFDF8;
    }

    /* 전체 */
    .stApp {
        background: #FBF7EF !important;
        color: var(--text) !important;
    }

    .block-container {
        max-width: 1080px !important;
        padding-top: 1.1rem !important;
        padding-bottom: 3rem !important;
    }

    /* Streamlit 기본 텍스트 대비 강제 */
    label,
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] p,
    .stRadio label,
    .stCheckbox label,
    .stSelectbox label,
    .stDateInput label,
    .stTextInput label {
        color: #4A3C31 !important;
        opacity: 1 !important;
        font-weight: 700 !important;
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: #4A3C31;
    }

    /* 상단 네비 */
    .topline {
        display:flex;
        justify-content:space-between;
        align-items:center;
        margin-bottom:.7rem;
    }

    .brand-mini {
        font-size:.78rem;
        font-weight:850;
        letter-spacing:.12em;
        color:#6D5B4D;
    }

    /* HERO */
    .saju-hero {
        position: relative;
        overflow: hidden;
        padding: 1.8rem 2rem;
        border-radius: 26px;
        background:
            radial-gradient(circle at 84% 18%, rgba(214,170,86,.24), transparent 28%),
            linear-gradient(135deg, #2B2118 0%, #4A3423 56%, #8C622A 100%);
        color:white;
        box-shadow: 0 18px 45px rgba(15,23,42,.14);
        margin-bottom: 1rem;
    }

    .saju-kicker {
        font-size:.72rem;
        font-weight:850;
        letter-spacing:.16em;
        color:#F3D9A3;
        margin-bottom:.45rem;
    }

    .saju-title {
        color:white !important;
        font-size:2rem;
        line-height:1.18;
        font-weight:900;
        letter-spacing:-.045em;
        margin-bottom:.55rem;
    }

    .saju-desc {
        max-width:760px;
        font-size:.92rem;
        line-height:1.65;
        color:#F8EBCF;
    }

    /* 입력 카드 */
    .input-head {
        margin-top:.25rem;
        margin-bottom:.4rem;
        font-size:1.08rem;
        font-weight:850;
        color:#2F241C;
    }

    div[data-testid="stForm"] {
        background:#FFFDF8;
        border:1px solid #E8DDCC;
        border-radius:22px;
        padding:1.05rem 1.1rem .9rem 1.1rem;
        box-shadow:0 8px 28px rgba(15,23,42,.045);
    }

    /* 입력 컴포넌트 */
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    input {
        background:#FFFDF8 !important;
        color:#2F241C !important;
    }

    .stButton > button,
    .stFormSubmitButton > button {
        border-radius:13px !important;
        min-height:46px !important;
        font-weight:850 !important;
    }

    /* 결과 제목 */
    .result-title {
        margin-top:.4rem;
        font-size:1.45rem;
        font-weight:900;
        letter-spacing:-.03em;
        color:#2F241C;
    }

    .result-sub {
        color:#7C6A5B;
        font-size:.88rem;
        margin-top:.2rem;
        margin-bottom:.9rem;
    }

    /* 명식 */
    .pillar-grid {
        display:grid;
        grid-template-columns:repeat(4, minmax(0,1fr));
        gap:.65rem;
        margin:.65rem 0 1rem 0;
    }

    .pillar {
        background:#FFFDF8;
        border:1px solid #E8DDCC;
        border-radius:18px;
        padding:1rem .8rem;
        text-align:center;
        box-shadow:0 6px 18px rgba(15,23,42,.035);
    }

    .pillar-label {
        font-size:.73rem;
        color:#7C6A5B;
        font-weight:800;
        margin-bottom:.28rem;
    }

    .pillar-gz {
        color:#2F241C;
        font-size:1.65rem;
        font-weight:900;
        line-height:1.2;
    }

    .pillar-meta {
        font-size:.72rem;
        color:#7C6A5B;
        margin-top:.35rem;
        line-height:1.45;
    }

    /* 핵심 인사이트 카드 */
    .insight-grid {
        display:grid;
        grid-template-columns:repeat(3, minmax(0,1fr));
        gap:.7rem;
        margin:.7rem 0;
    }

    .insight-card {
        background:#FFFDF8;
        border:1px solid #E8DDCC;
        border-radius:18px;
        padding:1rem;
    }

    .insight-label {
        font-size:.72rem;
        font-weight:850;
        letter-spacing:.06em;
        color:#A8742A;
        margin-bottom:.38rem;
    }

    .insight-title {
        font-size:1rem;
        font-weight:850;
        color:#2F241C;
        margin-bottom:.32rem;
    }

    .insight-text {
        font-size:.82rem;
        line-height:1.58;
        color:#7C6A5B;
    }

    /* 오행 바 */
    .element-row {
        display:grid;
        grid-template-columns:46px 1fr 34px;
        gap:.55rem;
        align-items:center;
        margin:.55rem 0;
    }

    .element-name {
        font-weight:850;
        color:#4A3C31;
        font-size:.86rem;
    }

    .element-track {
        height:10px;
        border-radius:999px;
        background:#E8DDCC;
        overflow:hidden;
    }

    .element-fill {
        height:100%;
        border-radius:999px;
        background:linear-gradient(90deg,#A8742A,#D0A65A);
    }

    .element-count {
        font-size:.78rem;
        font-weight:800;
        color:#7C6A5B;
        text-align:right;
    }

    /* 대운 */
    .current-cycle {
        background:linear-gradient(135deg,#F7E8C8,#FBF2DF);
        border:1px solid #E4C584;
        border-radius:20px;
        padding:1.15rem 1.2rem;
        margin:.5rem 0 .9rem 0;
    }

    .current-cycle-label {
        color:#A8742A;
        font-size:.72rem;
        font-weight:900;
        letter-spacing:.09em;
    }

    .current-cycle-title {
        color:#2F241C;
        font-size:1.45rem;
        font-weight:900;
        margin:.25rem 0;
    }

    .current-cycle-text {
        color:#6D5B4D;
        font-size:.86rem;
        line-height:1.55;
    }

    .cycle-row {
        display:grid;
        grid-template-columns:90px 76px 1fr;
        gap:.6rem;
        align-items:center;
        padding:.72rem .85rem;
        border-radius:14px;
        background:#FFFDF8;
        border:1px solid #E8DDCC;
        margin-bottom:.42rem;
        font-size:.82rem;
    }

    .cycle-row.current {
        background:#FFF8E8;
        border:2px solid #A8742A;
    }

    .cycle-year { color:#7C6A5B; font-weight:750; }
    .cycle-gz { color:#2F241C; font-size:1rem; font-weight:900; }
    .cycle-age { color:#6D5B4D; }

    /* 상세 해석 */
    .detail-box {
        background:#FFFDF8;
        border:1px solid #E8DDCC;
        border-radius:18px;
        padding:1rem 1.05rem;
        margin-bottom:.65rem;
    }

    .detail-head {
        font-weight:900;
        color:#2F241C;
        font-size:.96rem;
        margin-bottom:.42rem;
    }

    .detail-body {
        font-size:.84rem;
        color:#6D5B4D;
        line-height:1.72;
    }

    /* 안내 */
    .caution {
        margin-top:1rem;
        padding:.85rem 1rem;
        border-radius:14px;
        background:#FCF8F1;
        border:1px solid #E8DDCC;
        color:#7C6A5B;
        font-size:.75rem;
        line-height:1.55;
    }

    /* 탭 */
    div[data-testid="stTabs"] button {
        font-weight:800 !important;
        padding-left:.75rem !important;
        padding-right:.75rem !important;
    }

    /* 모바일 */
    @media (max-width: 768px) {
        .block-container {
            padding-top:.45rem !important;
            padding-left:.7rem !important;
            padding-right:.7rem !important;
            padding-bottom:2.2rem !important;
        }

        .saju-hero {
            padding:1rem 1rem .95rem 1rem;
            border-radius:18px;
            margin-bottom:.7rem;
        }

        .saju-kicker {
            font-size:.59rem;
            margin-bottom:.26rem;
        }

        .saju-title {
            font-size:1.38rem;
            line-height:1.2;
            margin-bottom:.32rem;
        }

        .saju-desc {
            font-size:.75rem;
            line-height:1.45;
        }

        .desktop-extra {
            display:none;
        }

        div[data-testid="stForm"] {
            padding:.75rem .8rem .6rem .8rem;
            border-radius:16px;
        }

        /* 위젯 간 세로 간격 축소 */
        div[data-testid="stVerticalBlock"] {
            gap:.48rem;
        }

        [data-testid="stWidgetLabel"] p {
            font-size:.78rem !important;
        }

        .stButton > button,
        .stFormSubmitButton > button {
            min-height:40px !important;
            font-size:.86rem !important;
        }

        .result-title {
            font-size:1.18rem;
        }

        .result-sub {
            font-size:.75rem;
            margin-bottom:.5rem;
        }

        .pillar-grid {
            grid-template-columns:repeat(4, minmax(0,1fr));
            gap:.32rem;
        }

        .pillar {
            border-radius:12px;
            padding:.7rem .3rem;
        }

        .pillar-label { font-size:.62rem; }
        .pillar-gz { font-size:1.05rem; }
        .pillar-meta { font-size:.58rem; }

        .insight-grid {
            grid-template-columns:1fr;
            gap:.42rem;
        }

        .insight-card {
            padding:.75rem .8rem;
            border-radius:14px;
        }

        .insight-label { font-size:.62rem; }
        .insight-title { font-size:.88rem; }
        .insight-text { font-size:.74rem; line-height:1.48; }

        .cycle-row {
            grid-template-columns:72px 58px 1fr;
            padding:.58rem .6rem;
            gap:.35rem;
            font-size:.7rem;
        }

        .cycle-gz { font-size:.85rem; }

        .current-cycle {
            padding:.85rem;
            border-radius:15px;
        }

        .current-cycle-title { font-size:1.08rem; }
        .current-cycle-text { font-size:.75rem; }

        .detail-box {
            padding:.8rem;
            border-radius:14px;
        }

        .detail-head { font-size:.86rem; }
        .detail-body { font-size:.75rem; line-height:1.58; }

        /* 모바일 탭 한 줄 스크롤 */
        div[data-testid="stTabs"] [role="tablist"] {
            overflow-x:auto;
            flex-wrap:nowrap;
        }

        div[data-testid="stTabs"] button {
            white-space:nowrap;
            font-size:.76rem !important;
            padding:.45rem .55rem !important;
        }
    }
    
    /* 사이드바 - 골드 톤 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #FBF4E6 0%, #F7EBD6 100%) !important;
        border-right: 1px solid #E8D7B4;
    }

    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p {
        color: #4A3525 !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background: #FFFDF8 !important;
        color: #4A3525 !important;
        border: 1px solid #E6D2A7 !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        background: #FFF4DB !important;
        border-color: #C99B48 !important;
        color: #7A5320 !important;
    }


    /* 풍부한 오행/십성 카드 */
    .five-grid {
        display:grid;
        grid-template-columns:repeat(5,minmax(0,1fr));
        gap:.55rem;
        margin:.65rem 0 1rem 0;
    }

    .five-card {
        background:#FFFDF8;
        border:1px solid #E8D7B4;
        border-radius:16px;
        padding:.85rem .75rem;
        min-height:155px;
    }

    .five-symbol { font-size:1.25rem; margin-bottom:.2rem; }
    .five-title { font-size:.92rem; font-weight:900; color:#4A3525; }
    .five-count { font-size:1.4rem; font-weight:950; color:#A8742A; margin:.12rem 0; }
    .five-role { font-size:.73rem; font-weight:850; color:#7A5320; margin-bottom:.3rem; }
    .five-desc { font-size:.71rem; line-height:1.48; color:#786655; }

    .god-grid {
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:.55rem;
        margin:.5rem 0 .9rem 0;
    }

    .god-card {
        background:#FFFDF8;
        border:1px solid #E8D7B4;
        border-radius:15px;
        padding:.8rem .9rem;
    }

    .god-name { font-weight:900; color:#4A3525; font-size:.9rem; }
    .god-key { color:#A8742A; font-size:.73rem; font-weight:850; margin:.18rem 0; }
    .god-desc { color:#786655; font-size:.74rem; line-height:1.5; }

    .cycle-detail-wrap {
        margin-top:.85rem;
        padding:1rem;
        border-radius:18px;
        background:linear-gradient(135deg,#FFF9ED 0%,#FBF1DD 100%);
        border:1px solid #DFC18A;
    }

    .cycle-detail-kicker {
        color:#A8742A;
        font-weight:900;
        font-size:.7rem;
        letter-spacing:.08em;
    }

    .cycle-detail-title {
        color:#3F2E20;
        font-weight:950;
        font-size:1.25rem;
        margin:.2rem 0 .55rem 0;
    }

    .cycle-detail-meta {
        color:#725C49;
        font-size:.78rem;
        line-height:1.55;
    }

    .mini-analysis-grid {
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:.55rem;
        margin-top:.7rem;
    }

    .mini-analysis {
        background:#FFFDF8;
        border:1px solid #E8D7B4;
        border-radius:14px;
        padding:.8rem;
    }

    .mini-analysis h4 {
        margin:0 0 .3rem 0;
        font-size:.84rem;
        color:#5B4027;
    }

    .mini-analysis p {
        margin:0;
        font-size:.74rem;
        line-height:1.55;
        color:#786655;
    }

    @media (max-width:768px) {
        .five-grid {
            grid-template-columns:repeat(5,minmax(76px,1fr));
            overflow-x:auto;
            padding-bottom:.2rem;
        }
        .five-card { min-height:130px; padding:.65rem .55rem; }
        .five-title { font-size:.8rem; }
        .five-count { font-size:1.12rem; }
        .five-role,.five-desc { font-size:.64rem; }

        .god-grid, .mini-analysis-grid {
            grid-template-columns:1fr;
        }
    }


    .life-map-note {
        background:#FFF9EE;
        border:1px solid #E3C98F;
        border-radius:16px;
        padding:.9rem 1rem;
        color:#6D5231;
        font-size:.78rem;
        line-height:1.55;
        margin:.5rem 0 .9rem 0;
    }

</style>
    """,
    unsafe_allow_html=True
)



def html(markup):
    """들여쓰기 때문에 HTML이 코드블록으로 보이는 문제 방지."""
    st.markdown(textwrap.dedent(markup).strip(), unsafe_allow_html=True)


# =========================================================
# 2. 명리학 기본 매핑
# =========================================================

STEM_ELEMENT = {
    "甲":"목", "乙":"목",
    "丙":"화", "丁":"화",
    "戊":"토", "己":"토",
    "庚":"금", "辛":"금",
    "壬":"수", "癸":"수",
}

BRANCH_ELEMENT = {
    "寅":"목", "卯":"목",
    "巳":"화", "午":"화",
    "辰":"토", "戌":"토", "丑":"토", "未":"토",
    "申":"금", "酉":"금",
    "亥":"수", "子":"수",
}

ELEMENT_DESC = {
    "목": "성장·기획·확장·관계 형성",
    "화": "표현·실행·성과 노출·속도",
    "토": "안정·관리·축적·현실화",
    "금": "판단·원칙·결단·정리",
    "수": "정보·사고·유연성·통찰",
}

DAY_MASTER_DESC = {
    "甲": ("갑목", "큰 나무처럼 방향성과 성장 욕구가 강한 유형", "장기 비전과 개척"),
    "乙": ("을목", "덩굴과 화초처럼 섬세하게 환경을 읽고 연결하는 유형", "기획·조정·관계 감각"),
    "丙": ("병화", "태양처럼 밖으로 에너지를 드러내고 분위기를 만드는 유형", "표현·리더십·확산"),
    "丁": ("정화", "등불처럼 집중된 빛으로 세밀하게 파고드는 유형", "집중·감각·전문성"),
    "戊": ("무토", "큰 산처럼 중심을 잡고 쉽게 흔들리지 않는 유형", "관리·신뢰·책임"),
    "己": ("기토", "밭과 흙처럼 사람과 자원을 실용적으로 키우는 유형", "운영·육성·조율"),
    "庚": ("경금", "단단한 쇠처럼 빠르게 판단하고 구조를 정리하는 유형", "결단·개혁·실행"),
    "辛": ("신금", "보석처럼 기준이 세밀하고 완성도를 중시하는 유형", "정교함·브랜드·품질"),
    "壬": ("임수", "큰 물처럼 범위를 넓게 보고 흐름을 읽는 유형", "전략·네트워크·확장"),
    "癸": ("계수", "비와 이슬처럼 미세한 신호를 포착하고 스며드는 유형", "분석·관찰·정보"),
}

TEN_GOD_KO = {
    "比肩": "비견",
    "劫财": "겁재",
    "食神": "식신",
    "伤官": "상관",
    "傷官": "상관",
    "偏财": "편재",
    "偏財": "편재",
    "正财": "정재",
    "正財": "정재",
    "七杀": "편관",
    "七殺": "편관",
    "偏官": "편관",
    "正官": "정관",
    "偏印": "편인",
    "正印": "정인",
    "日主": "일주",
    "日元": "일주",
}

def normalize_ten_god(value):
    """lunar_python의 한자 십성명을 한국 명리 용어로 통일."""
    if not value:
        return value
    return TEN_GOD_KO.get(value, value)


TEN_GOD_DESC = {
    "비견": "자기주도·동료·독립성",
    "겁재": "경쟁·추진·관계 속 주도권",
    "식신": "생산·표현·실무 성과",
    "상관": "창의·문제제기·기존 방식의 개선",
    "편재": "기회 포착·외부 자원·유동적 재물",
    "정재": "안정적 자산·관리·책임 있는 재무",
    "편관": "압박·도전·권한·빠른 책임",
    "정관": "조직·원칙·직책·공식적 책임",
    "편인": "직관·전문지식·비정형 학습",
    "정인": "학습·보호·문서·체계적 지식",
    "日主": "나 자신",
    "일주": "나 자신",
    "日元": "나 자신",
}



STEM_POLARITY = {
    "甲":"양", "乙":"음", "丙":"양", "丁":"음", "戊":"양",
    "己":"음", "庚":"양", "辛":"음", "壬":"양", "癸":"음"
}

BRANCH_POLARITY = {
    "子":"양","丑":"음","寅":"양","卯":"음","辰":"양","巳":"음",
    "午":"양","未":"음","申":"양","酉":"음","戌":"양","亥":"음"
}

GENERATES = {"목":"화","화":"토","토":"금","금":"수","수":"목"}
CONTROLS = {"목":"토","토":"수","수":"화","화":"금","금":"목"}

ROLE_GROUP_DESC = {
    "비겁": {
        "title": "자기주도 · 동료 · 경쟁",
        "work": "내 기준과 주도권이 강해지고, 동료·경쟁자와의 관계가 중요해집니다.",
        "money": "독립적인 의사결정이 늘지만 공동 자원이나 지출 경쟁은 점검할 필요가 있습니다.",
        "relation": "관계에서 대등함과 자율성을 중시하는 경향이 커질 수 있습니다.",
        "action": "혼자 밀어붙이기보다 역할과 책임의 경계를 분명히 하는 것이 좋습니다.",
    },
    "식상": {
        "title": "표현 · 생산 · 성과",
        "work": "아이디어를 결과물로 만들고 발표·기획·실행하는 힘이 커지는 흐름입니다.",
        "money": "직접 만든 성과와 전문성이 수익 기회로 연결되기 쉽습니다.",
        "relation": "말과 표현이 활발해지므로 설득력은 커지지만 직설성은 조절할 필요가 있습니다.",
        "action": "결과물을 눈에 보이게 만들고 기록·발표·콘텐츠화하는 것이 유리합니다.",
    },
    "재성": {
        "title": "재물 · 현실 · 관리",
        "work": "성과를 숫자와 실익으로 연결하고 자원·예산·사업성을 관리하는 역할이 커집니다.",
        "money": "자산, 계약, 현금흐름처럼 현실적인 재무 의사결정에 관심이 커질 수 있습니다.",
        "relation": "책임을 실제 행동과 지원으로 표현하는 성향이 강해질 수 있습니다.",
        "action": "기회 확대와 함께 현금흐름·리스크·계약조건을 숫자로 관리하는 것이 중요합니다.",
    },
    "관성": {
        "title": "조직 · 책임 · 직책",
        "work": "조직의 기준, 직책, 평가, 책임과 관련된 이슈가 전면에 나올 수 있습니다.",
        "money": "안정성과 규칙을 중시하므로 무리한 확장보다 제도권 안의 관리가 중요합니다.",
        "relation": "원칙과 역할을 강조하면서 관계가 다소 경직될 수 있습니다.",
        "action": "공식적인 책임을 피하기보다 권한과 책임의 범위를 명확히 하는 것이 좋습니다.",
    },
    "인성": {
        "title": "학습 · 문서 · 보호",
        "work": "전문지식, 자격, 문서, 기획, 연구, 지원체계가 힘을 발휘하는 흐름입니다.",
        "money": "즉각적 수익보다 기반 구축과 전문성 투자에 무게가 실릴 수 있습니다.",
        "relation": "생각이 많아지거나 보호받고 싶어지는 경향이 생길 수 있습니다.",
        "action": "배우고 정리하고 체계화하는 일을 실제 성과와 연결하는 것이 핵심입니다.",
    },
}

ELEMENT_SYMBOL = {
    "목":"🌱", "화":"🔥", "토":"⛰️", "금":"⚙️", "수":"💧"
}

GAN_HANGUL = {
    "甲":"갑", "乙":"을", "丙":"병", "丁":"정", "戊":"무",
    "己":"기", "庚":"경", "辛":"신", "壬":"임", "癸":"계",
}
ZHI_HANGUL = {
    "子":"자", "丑":"축", "寅":"인", "卯":"묘", "辰":"진", "巳":"사",
    "午":"오", "未":"미", "申":"신", "酉":"유", "戌":"술", "亥":"해",
}

def ganji_to_hangul(gz):
    """갑자(甲子) 형식의 간지를 갑자처럼 한글로 표시."""
    if not gz:
        return ""
    return "".join(GAN_HANGUL.get(ch, ZHI_HANGUL.get(ch, ch)) for ch in gz)

def gan_to_hangul(gan):
    return GAN_HANGUL.get(gan, gan)

def zhi_to_hangul(zhi):
    return ZHI_HANGUL.get(zhi, zhi)

ELEMENT_LONG_DESC = {
    "목": "성장·기획·확장·관계 형성의 기운",
    "화": "표현·실행·주목·성과 노출의 기운",
    "토": "현실화·안정·관리·축적의 기운",
    "금": "기준·판단·결단·정리의 기운",
    "수": "정보·사고·유연성·통찰의 기운",
}


def relation_group(day_element, other_element):
    """일간 오행 기준으로 상대 오행이 어떤 십성 그룹인지 반환."""
    if not day_element or not other_element:
        return ""
    if other_element == day_element:
        return "비겁"
    if GENERATES.get(day_element) == other_element:
        return "식상"
    if CONTROLS.get(day_element) == other_element:
        return "재성"
    if CONTROLS.get(other_element) == day_element:
        return "관성"
    if GENERATES.get(other_element) == day_element:
        return "인성"
    return ""


def ten_god_for_stem(day_gan, other_gan):
    """일간과 다른 천간의 오행+음양 관계로 십성을 계산."""
    if day_gan not in STEM_ELEMENT or other_gan not in STEM_ELEMENT:
        return ""

    day_el = STEM_ELEMENT[day_gan]
    other_el = STEM_ELEMENT[other_gan]
    same_polarity = STEM_POLARITY[day_gan] == STEM_POLARITY[other_gan]

    group = relation_group(day_el, other_el)

    if group == "비겁":
        return "비견" if same_polarity else "겁재"
    if group == "식상":
        return "식신" if same_polarity else "상관"
    if group == "재성":
        return "편재" if same_polarity else "정재"
    if group == "관성":
        return "편관" if same_polarity else "정관"
    if group == "인성":
        return "편인" if same_polarity else "정인"
    return ""


def element_role_cards(chart):
    day_el = STEM_ELEMENT.get(chart["day_gan"], "")
    result = []
    for el in ["목","화","토","금","수"]:
        group = relation_group(day_el, el)
        count = chart["elements"].get(el, 0)
        result.append({
            "element": el,
            "count": count,
            "group": group,
            "desc": ELEMENT_LONG_DESC[el],
            "role": ROLE_GROUP_DESC.get(group, {}).get("title", ""),
        })
    return result


def cycle_detail(chart, cycle):
    gz = cycle.get("ganji", "")
    if len(gz) < 2:
        return {}

    gan, zhi = gz[0], gz[1]
    day_gan = chart["day_gan"]
    day_el = STEM_ELEMENT.get(day_gan, "")
    gan_el = STEM_ELEMENT.get(gan, "")
    zhi_el = BRANCH_ELEMENT.get(zhi, "")

    gan_god = ten_god_for_stem(day_gan, gan)
    gan_group = relation_group(day_el, gan_el)
    zhi_group = relation_group(day_el, zhi_el)

    primary = ROLE_GROUP_DESC.get(gan_group, {})
    secondary = ROLE_GROUP_DESC.get(zhi_group, {})

    headline = (
        f"{gan_god or gan_group}의 외부 과제와 "
        f"{zhi_group}의 생활 기반이 함께 작동하는 10년"
    )

    work = primary.get("work", "") + " " + secondary.get("work", "")
    money = primary.get("money", "") + " " + secondary.get("money", "")
    relation = primary.get("relation", "") + " " + secondary.get("relation", "")
    action = primary.get("action", "") + " " + secondary.get("action", "")

    return {
        "gan": gan,
        "zhi": zhi,
        "gan_el": gan_el,
        "zhi_el": zhi_el,
        "gan_god": gan_god,
        "gan_group": gan_group,
        "zhi_group": zhi_group,
        "headline": headline,
        "work": work.strip(),
        "money": money.strip(),
        "relation": relation.strip(),
        "action": action.strip(),
    }


def build_cycle_ai_prompt(chart, cycle):
    detail = cycle_detail(chart, cycle)
    return f"""
당신은 전통 명리학의 구조를 현대적으로 설명하는 해석가다.
아래 원국과 선택된 대운만 집중적으로 분석하라.

[원국]
연주: {chart['year']}
월주: {chart['month']}
일주: {chart['day']}
시주: {chart['hour'] or '미상'}
일간: {chart['day_gan']}
오행 표면분포: {chart['elements']}
천간십성: {chart['shishen_gan']}
지지십성: {chart['shishen_zhi']}

[선택 대운]
간지: {cycle['ganji']}
기간: {cycle['start_year']}~{cycle['end_year']}
나이: {cycle['start_age']}~{cycle['end_age']}
대운 천간 십성: {detail.get('gan_god')}
대운 천간 오행: {detail.get('gan_el')}
대운 지지 오행: {detail.get('zhi_el')}

다음 순서로 한국어로 자세히 설명하라.
1. 이 대운의 핵심 의미
2. 원국과 대운이 만날 때 강화되는 기운
3. 직장·직책·커리어
4. 재물·사업·자산관리
5. 인간관계·가족
6. 이 시기에 생기기 쉬운 부담이나 과잉
7. 이 10년을 잘 쓰는 행동전략 5가지

단정적 예언은 하지 말고 구조와 경향 중심으로 설명한다.
"""



# =========================================================
# 3. 입력/계산 함수
# =========================================================

def make_time_options():
    options = ["모름"]
    for hour in range(24):
        for minute in (0, 30):
            options.append(f"{hour:02d}:{minute:02d}")
    return options


def visible_element_counts(pillars):
    """
    천간 4 + 지지 4의 '표면 오행'을 단순 집계합니다.
    지장간/월령 가중치는 포함하지 않으므로 정밀 신강·신약 판단용이 아닙니다.
    """
    counts = Counter({"목":0, "화":0, "토":0, "금":0, "수":0})
    for gz in pillars:
        if not gz or len(gz) < 2:
            continue
        counts[STEM_ELEMENT.get(gz[0], "")] += 1
        counts[BRANCH_ELEMENT.get(gz[1], "")] += 1
    counts.pop("", None)
    return dict(counts)


def safe_call(obj, method, default=""):
    try:
        return getattr(obj, method)()
    except Exception:
        return default


def normalize_ten_god_list(values):
    if not isinstance(values, list):
        return values
    return [normalize_ten_god(v) for v in values if v]


def make_solar_from_input(birth_date, calendar_type, time_text, lunar_leap=False):
    """
    time_text가 '모름'이면 명식의 연·월·일 계산을 위해 12:00을 임시 사용합니다.
    시주는 결과에서 제외하고, 대운 시작시점은 '근사'라고 표시합니다.
    """
    unknown_time = time_text == "모름"

    if unknown_time:
        hour, minute = 12, 0
    else:
        hour, minute = map(int, time_text.split(":"))

    if calendar_type == "양력":
        solar = Solar.fromYmdHms(
            birth_date.year, birth_date.month, birth_date.day,
            hour, minute, 0
        )
    else:
        lunar_month = -birth_date.month if lunar_leap else birth_date.month
        lunar = Lunar.fromYmd(birth_date.year, lunar_month, birth_date.day)
        converted = lunar.getSolar()
        solar = Solar.fromYmdHms(
            converted.getYear(), converted.getMonth(), converted.getDay(),
            hour, minute, 0
        )

    return solar, unknown_time


def build_chart(birth_date, calendar_type, time_text, gender, lunar_leap=False):
    if not LUNAR_AVAILABLE:
        raise RuntimeError(
            "lunar_python 패키지가 설치되어 있지 않습니다. "
            "PowerShell에서 python -m pip install lunar_python 를 실행해주세요."
        )

    solar, unknown_time = make_solar_from_input(
        birth_date, calendar_type, time_text, lunar_leap
    )
    lunar = solar.getLunar()
    eight = lunar.getEightChar()

    # 일부 명리 계파에서 야자시(23시) 일주 기준이 다를 수 있음.
    # 라이브러리 기본값을 사용.
    year = safe_call(eight, "getYear")
    month = safe_call(eight, "getMonth")
    day = safe_call(eight, "getDay")
    hour = "" if unknown_time else safe_call(eight, "getTime")

    pillars_for_count = [year, month, day] + ([] if unknown_time else [hour])
    elem_counts = visible_element_counts(pillars_for_count)

    shishen_gan = {
        "연간": normalize_ten_god(safe_call(eight, "getYearShiShenGan")),
        "월간": normalize_ten_god(safe_call(eight, "getMonthShiShenGan")),
        "일간": "일주",
        "시간": "" if unknown_time else normalize_ten_god(safe_call(eight, "getTimeShiShenGan")),
    }

    shishen_zhi = {
        "연지": normalize_ten_god_list(safe_call(eight, "getYearShiShenZhi", [])),
        "월지": normalize_ten_god_list(safe_call(eight, "getMonthShiShenZhi", [])),
        "일지": normalize_ten_god_list(safe_call(eight, "getDayShiShenZhi", [])),
        "시지": [] if unknown_time else normalize_ten_god_list(safe_call(eight, "getTimeShiShenZhi", [])),
    }

    wuxing = {
        "연주": safe_call(eight, "getYearWuXing"),
        "월주": safe_call(eight, "getMonthWuXing"),
        "일주": safe_call(eight, "getDayWuXing"),
        "시주": "" if unknown_time else safe_call(eight, "getTimeWuXing"),
    }

    nayin = {
        "연주": safe_call(eight, "getYearNaYin"),
        "월주": safe_call(eight, "getMonthNaYin"),
        "일주": safe_call(eight, "getDayNaYin"),
        "시주": "" if unknown_time else safe_call(eight, "getTimeNaYin"),
    }

    return {
        "solar": solar,
        "lunar": lunar,
        "eight": eight,
        "year": year,
        "month": month,
        "day": day,
        "hour": hour,
        "unknown_time": unknown_time,
        "day_gan": day[0] if day else "",
        "day_zhi": day[1] if len(day) > 1 else "",
        "elements": elem_counts,
        "wuxing": wuxing,
        "nayin": nayin,
        "shishen_gan": shishen_gan,
        "shishen_zhi": shishen_zhi,
    }


def build_daewoon(chart, gender):
    eight = chart["eight"]
    gender_num = 1 if gender == "남성" else 0

    yun = eight.getYun(gender_num)

    raw = yun.getDaYun()
    cycles = []

    valid = []
    for d in raw:
        gz = safe_call(d, "getGanZhi")
        if gz:
            valid.append(d)

    for i, d in enumerate(valid[:9]):
        start_year = safe_call(d, "getStartYear", 0)
        start_age = safe_call(d, "getStartAge", 0)
        gz = safe_call(d, "getGanZhi")

        if i + 1 < len(valid):
            next_year = safe_call(valid[i + 1], "getStartYear", start_year + 10)
            next_age = safe_call(valid[i + 1], "getStartAge", start_age + 10)
            end_year = next_year - 1
            end_age = next_age - 1
        else:
            end_year = start_year + 9
            end_age = start_age + 9

        cycles.append({
            "ganji": gz,
            "start_year": start_year,
            "end_year": end_year,
            "start_age": start_age,
            "end_age": end_age,
        })

    now_year = datetime.now().year
    current = None
    for c in cycles:
        c["current"] = c["start_year"] <= now_year <= c["end_year"]
        if c["current"]:
            current = c

    return {
        "yun": yun,
        "cycles": cycles,
        "current": current,
        "start_years": safe_call(yun, "getStartYear", ""),
        "start_months": safe_call(yun, "getStartMonth", ""),
        "start_days": safe_call(yun, "getStartDay", ""),
        "start_solar": (
            safe_call(safe_call(yun, "getStartSolar", None), "toYmd", "")
            if safe_call(yun, "getStartSolar", None) else ""
        ),
        "forward": safe_call(yun, "isForward", None),
    }


def collect_ten_gods(chart):
    result = []
    for _, v in chart["shishen_gan"].items():
        if v and v not in ("일주", "日主", "日元"):
            result.append(v)
    for _, arr in chart["shishen_zhi"].items():
        if isinstance(arr, list):
            result.extend([x for x in arr if x])
    return Counter(result)


def daewoon_simple_theme(gz):
    if not gz or len(gz) < 2:
        return "환경 변화"
    stem_el = STEM_ELEMENT.get(gz[0], "")
    branch_el = BRANCH_ELEMENT.get(gz[1], "")
    if stem_el == branch_el:
        return f"{ELEMENT_DESC.get(stem_el, '변화')}의 성격이 강해지는 시기"
    return (
        f"{ELEMENT_DESC.get(stem_el, stem_el)}와 "
        f"{ELEMENT_DESC.get(branch_el, branch_el)}가 함께 작동하는 시기"
    )


def current_year_ganji():
    """
    간단한 연도 간지 표시.
    입춘 이전/이후의 정확한 명리 연도는 lunar_python 결과를 우선 사용합니다.
    """
    try:
        solar = Solar.fromYmd(datetime.now().year, datetime.now().month, datetime.now().day)
        return solar.getLunar().getYearInGanZhiExact()
    except Exception:
        return ""


# =========================================================
# 4. 정적 명리 해석
# =========================================================

def base_interpretation(chart):
    day_gan = chart["day_gan"]
    dm_name, dm_desc, dm_focus = DAY_MASTER_DESC.get(
        day_gan,
        ("일간", "자기 중심 기운을 살펴보는 기준", "균형")
    )

    counts = chart["elements"]
    max_el = max(counts, key=counts.get) if counts else ""
    min_el = min(counts, key=counts.get) if counts else ""

    gods = collect_ten_gods(chart)
    top_gods = gods.most_common(3)

    god_text = []
    for god, cnt in top_gods:
        god_text.append(
            f"{god}({TEN_GOD_DESC.get(god, '명식 내 역할')})"
        )

    return {
        "dm_name": dm_name,
        "dm_desc": dm_desc,
        "dm_focus": dm_focus,
        "max_element": max_el,
        "min_element": min_el,
        "top_gods": god_text,
    }



# =========================================================
# 4-1. 전문 명리 상담용 해석 레이어
# =========================================================

DAY_MASTER_RICH = {
    "甲": {
        "title": "곧게 뻗는 큰 나무형",
        "core": "방향을 정하면 꾸준히 밀고 가는 힘이 강합니다. 기준과 원칙이 분명하고, 성장과 확장을 중요하게 보는 편입니다.",
        "strength": "장기적인 그림을 보고 사람과 일을 키우는 힘, 책임을 맡았을 때 중심을 잡는 힘이 장점입니다.",
        "shadow": "내가 옳다고 생각한 방향을 너무 오래 고수하면 유연성이 떨어질 수 있습니다.",
        "relation": "관계에서도 신뢰와 일관성을 중요하게 보며, 한번 마음을 주면 오래 가는 편입니다.",
    },
    "乙": {
        "title": "유연하게 뻗는 풀과 꽃형",
        "core": "상황을 세밀하게 읽고 관계 속에서 방향을 조정하는 힘이 좋습니다. 부드럽지만 끈기가 있습니다.",
        "strength": "협상, 조율, 감각적인 기획, 사람 사이의 연결에서 강점을 보이기 쉽습니다.",
        "shadow": "주변 상황을 너무 많이 고려하다 보면 결정이 늦어지거나 감정 소모가 커질 수 있습니다.",
        "relation": "상대의 분위기와 감정을 잘 읽지만, 혼자 속으로 삭이는 경향이 생길 수 있습니다.",
    },
    "丙": {
        "title": "크게 비추는 태양형",
        "core": "존재감과 추진력이 분명하고, 사람과 분위기를 움직이는 힘이 있습니다. 결과를 눈에 보이게 만드는 것을 중요하게 봅니다.",
        "strength": "리더십, 발표, 확장, 외부 커뮤니케이션, 빠른 실행에서 강점을 보입니다.",
        "shadow": "성과와 인정에 몰입하면 피로가 누적되거나 감정이 즉각적으로 드러날 수 있습니다.",
        "relation": "관계에서는 솔직하고 따뜻하지만, 상대의 반응이 기대에 못 미치면 실망도 빠를 수 있습니다.",
    },
    "丁": {
        "title": "섬세하게 밝히는 촛불형",
        "core": "집중력과 감각이 세밀하며, 작지만 분명한 영향력을 만들어내는 유형입니다.",
        "strength": "디테일, 콘텐츠, 설득, 상담, 기획처럼 세심한 관찰이 필요한 일에 강합니다.",
        "shadow": "생각이 깊어질수록 걱정과 예민함이 함께 커질 수 있습니다.",
        "relation": "친밀한 관계에서는 깊이 연결되지만, 상처를 오래 기억하는 면이 있을 수 있습니다.",
    },
    "戊": {
        "title": "중심을 잡는 큰 산형",
        "core": "쉽게 흔들리지 않고 전체 구조를 안정시키는 힘이 있습니다. 신뢰와 책임을 중시합니다.",
        "strength": "조직 안정, 관리, 장기 계획, 자원 배분, 책임 있는 의사결정에 강합니다.",
        "shadow": "변화를 늦게 받아들이거나, 혼자 책임을 너무 많이 짊어질 수 있습니다.",
        "relation": "말보다 행동으로 책임을 보여주는 편이고, 믿음이 깨지는 상황을 특히 힘들어할 수 있습니다.",
    },
    "己": {
        "title": "기르는 힘이 강한 밭과 흙형",
        "core": "사람과 자원을 실제 성과로 키우는 힘이 강합니다. 눈앞의 현실을 정리하고 운영하는 능력이 좋습니다.",
        "strength": "조율, 운영, 육성, 실무형 기획, 여러 이해관계를 맞추는 능력이 강점입니다.",
        "shadow": "모든 것을 내가 챙겨야 한다는 책임감이 커지면 과로와 생각의 과잉으로 이어질 수 있습니다.",
        "relation": "관계에서는 챙기고 책임지는 쪽이 되기 쉽지만, 내 노력이 당연하게 받아들여지면 서운함이 쌓일 수 있습니다.",
    },
    "庚": {
        "title": "결단력 있는 단단한 쇠형",
        "core": "판단이 빠르고 불필요한 것을 잘라내는 힘이 있습니다. 문제 해결과 결단을 중요하게 봅니다.",
        "strength": "위기 대응, 구조조정, 협상, 기준 수립, 성과 중심의 실행에 강합니다.",
        "shadow": "효율을 중시하다 보면 관계의 섬세한 감정을 놓칠 수 있습니다.",
        "relation": "신뢰와 약속을 중요하게 보고, 애매한 태도를 오래 견디기 어려운 편입니다.",
    },
    "辛": {
        "title": "정교하게 다듬는 보석형",
        "core": "정확성과 완성도를 중시하며, 섬세한 기준을 갖고 있습니다.",
        "strength": "품질, 전략, 분석, 브랜딩, 전문성처럼 정교함이 필요한 분야에서 강점을 보입니다.",
        "shadow": "기준이 높아 자신과 타인을 지나치게 평가할 수 있습니다.",
        "relation": "관계에서 예의와 신뢰를 중요하게 보고, 무례함이나 가벼운 태도에 민감할 수 있습니다.",
    },
    "壬": {
        "title": "크게 흐르는 바다형",
        "core": "정보와 사람을 넓게 연결하고 변화에 적응하는 힘이 좋습니다. 큰 그림을 보며 움직이는 편입니다.",
        "strength": "전략, 네트워크, 이동, 정보 해석, 새로운 영역 확장에 강합니다.",
        "shadow": "가능성을 너무 많이 열어두면 집중력이 분산될 수 있습니다.",
        "relation": "관계에서는 자유와 신뢰를 중요하게 여기며, 지나친 통제를 답답해할 수 있습니다.",
    },
    "癸": {
        "title": "스며드는 비와 샘물형",
        "core": "관찰력과 감수성이 섬세하고, 겉으로 드러나지 않는 흐름을 읽는 힘이 좋습니다.",
        "strength": "분석, 연구, 상담, 데이터, 기획처럼 작은 신호를 읽어내는 일에 강합니다.",
        "shadow": "생각이 많아지면 결정을 미루거나 혼자 불안을 키울 수 있습니다.",
        "relation": "상대의 감정을 잘 읽지만, 내 감정을 직접적으로 표현하는 데 시간이 걸릴 수 있습니다.",
    },
}


def build_personal_summary(chart, daewoon):
    dm = chart["day_gan"]
    dm_info = DAY_MASTER_RICH.get(dm, {})
    gods = collect_ten_gods(chart)
    top_gods = gods.most_common(3)

    top_phrase = ""
    if top_gods:
        names = " · ".join([f"{g} {c}회" for g, c in top_gods])
        top_phrase = f"현재 명식에서 반복해서 보이는 십성은 {names}입니다."

    current = daewoon.get("current")
    current_text = ""
    if current:
        detail = cycle_detail(chart, current)
        current_text = (
            f"현재는 {ganji_to_hangul(current['ganji'])} 대운({current['start_year']}~{current['end_year']})에 있고, "
            f"{detail.get('gan_group')}의 외부 과제와 {detail.get('zhi_group')}의 생활 주제가 함께 강조됩니다."
        )

    return {
        "title": dm_info.get("title", f"{dm} 일간"),
        "core": dm_info.get("core", ""),
        "strength": dm_info.get("strength", ""),
        "shadow": dm_info.get("shadow", ""),
        "relation": dm_info.get("relation", ""),
        "top_phrase": top_phrase,
        "current_text": current_text,
    }



DOMAIN_GUIDE = {
    "career": {
        "title": "직업 · 성취",
        "icon": "💼",
        "groups": ["관성", "식상", "인성"],
        "summary": "조직 안에서 어떤 방식으로 성과를 만들고, 책임과 전문성을 어떻게 다루는지 봅니다.",
    },
    "wealth": {
        "title": "재물 · 자산",
        "icon": "💰",
        "groups": ["재성", "식상", "비겁"],
        "summary": "돈을 버는 방식보다 자원을 관리하고 확장하는 방식, 지출·경쟁·현실 감각을 함께 봅니다.",
    },
    "relationship": {
        "title": "관계 · 가족",
        "icon": "🤝",
        "groups": ["비겁", "관성", "재성"],
        "summary": "관계에서의 거리감, 책임감, 주도권, 현실적 배려가 어떤 식으로 드러나는지 봅니다.",
    },
    "learning": {
        "title": "학습 · 내면",
        "icon": "📚",
        "groups": ["인성", "식상"],
        "summary": "배우고 정리하고 표현하는 방식, 생각이 과해질 때의 패턴까지 함께 봅니다.",
    },
}


def ten_god_group(god):
    if god in ("비견", "겁재"):
        return "비겁"
    if god in ("식신", "상관"):
        return "식상"
    if god in ("편재", "정재"):
        return "재성"
    if god in ("편관", "정관"):
        return "관성"
    if god in ("편인", "정인"):
        return "인성"
    return ""


def domain_score(chart, groups):
    """객관적 확률이 아니라 명식에서 해당 주제가 얼마나 자주 등장하는지 보여주는 참고 지표."""
    gods = collect_ten_gods(chart)
    total = sum(gods.values()) or 1
    hit = sum(cnt for god, cnt in gods.items() if ten_god_group(god) in groups)
    return min(5, max(1, round(1 + (hit / total) * 4)))


def _dominant_gods(chart, groups, limit=3):
    gods = collect_ten_gods(chart)
    result = []
    for god, cnt in gods.most_common():
        grp = ten_god_group(god)
        if grp in groups:
            result.append((god, cnt, grp))
            if len(result) >= limit:
                break
    return result


def _current_cycle_groups(chart, daewoon):
    current = daewoon.get("current")
    if not current:
        return "", "", ""
    detail = cycle_detail(chart, current)
    return (
        detail.get("gan_group", ""),
        detail.get("zhi_group", ""),
        current.get("ganji", ""),
    )



def _god_sentence(god, cnt):
    mapping = {
        "비견": "내 기준으로 판단하고 직접 끌고 가려는 힘",
        "겁재": "경쟁 속에서 주도권을 잡고 밀어붙이는 힘",
        "식신": "꾸준히 결과물을 만들고 실무 성과로 연결하는 힘",
        "상관": "기존 방식의 문제를 발견하고 더 나은 방식으로 바꾸려는 힘",
        "편재": "외부 기회와 사람·자원을 빠르게 연결하는 힘",
        "정재": "숫자와 현실을 안정적으로 관리하는 힘",
        "편관": "압박이 있어도 책임지고 돌파하려는 힘",
        "정관": "조직의 기준과 역할, 공식적인 책임을 받아들이는 힘",
        "편인": "남들이 놓치는 맥락을 직관적으로 읽고 새롭게 해석하는 힘",
        "정인": "배우고 정리하고 체계화해 신뢰를 만드는 힘",
    }
    base = mapping.get(god, TEN_GOD_DESC.get(god, "반복되는 성향"))
    return f"{god}이 {cnt}회 반복되어, {base}이 삶에서 자주 드러나는 편입니다."


def build_personalized_profile(chart, daewoon):
    dm = chart["day_gan"]
    dm_info = DAY_MASTER_RICH.get(dm, {})
    month = chart.get("month", "")
    gods = collect_ten_gods(chart)
    top = gods.most_common(3)

    main_god = top[0] if top else ("", 0)
    second_god = top[1] if len(top) > 1 else ("", 0)

    current = daewoon.get("current")
    cycle_text = ""
    if current:
        detail = cycle_detail(chart, current)
        cycle_text = (
            f"현재는 {ganji_to_hangul(current['ganji'])} 대운({current['start_year']}~{current['end_year']})으로, "
            f"{detail.get('gan_group') or '외부 역할'}과 "
            f"{detail.get('zhi_group') or '생활 기반'}의 주제가 동시에 커지는 시기입니다."
        )

    one_line = dm_info.get("core", "")
    if main_god[0]:
        one_line += f" 특히 {main_god[0]}이 반복되어 {TEN_GOD_DESC.get(main_god[0], '')}의 방식이 자주 나타납니다."

    work = ""
    if main_god[0]:
        grp = ten_god_group(main_god[0])
        work = ROLE_GROUP_DESC.get(grp, {}).get("work", "")
    if second_god[0]:
        grp2 = ten_god_group(second_god[0])
        extra = ROLE_GROUP_DESC.get(grp2, {}).get("work", "")
        if extra and extra not in work:
            work = (work + " " + extra).strip()

    money = personalized_domain_interpretation(chart, daewoon, "wealth")
    relation = personalized_domain_interpretation(chart, daewoon, "relationship")

    return {
        "title": dm_info.get("title", f"{dm} 일간"),
        "one_line": one_line,
        "month": month,
        "main_god": main_god,
        "second_god": second_god,
        "god_sentences": [_god_sentence(g, c) for g, c in top],
        "top_gods": top,
        "strength": dm_info.get("strength", ""),
        "shadow": dm_info.get("shadow", ""),
        "work": work or "직업에서는 한 가지 역할보다 상황에 맞춰 책임과 성과를 조정하는 방식이 중요합니다.",
        "money": money.get("strength", ""),
        "relation": relation.get("strength", ""),
        "cycle": cycle_text,
    }


def personalized_domain_compact(chart, daewoon, domain_key):
    result = personalized_domain_interpretation(chart, daewoon, domain_key)
    guide = DOMAIN_GUIDE[domain_key]
    related = _dominant_gods(chart, guide["groups"], limit=2)

    basis = ""
    if related:
        basis = " · ".join([f"{god} {cnt}회" for god, cnt, _ in related])

    return {
        "title": guide["title"],
        "icon": guide["icon"],
        "headline": result["headline"],
        "main": result["lead"],
        "strength": result["strength"],
        "risk": result["risk"],
        "cycle": result["cycle"],
        "basis": basis,
    }


def personalized_domain_interpretation(chart, daewoon, domain_key):
    """
    단순 카테고리 설명이 아니라 현재 명식 자체를 근거로 한 개인화 해석.
    """
    dm = chart["day_gan"]
    dm_info = DAY_MASTER_RICH.get(dm, {})
    guide = DOMAIN_GUIDE[domain_key]
    dominant = _dominant_gods(chart, guide["groups"], limit=3)
    gan_group, zhi_group, current_gz = _current_cycle_groups(chart, daewoon)

    god_names = [x[0] for x in dominant]
    first_god = god_names[0] if god_names else ""
    second_god = god_names[1] if len(god_names) > 1 else ""

    if domain_key == "career":
        if first_god:
            lead = (
                f"이 명식의 직업 영역에서는 **{first_god}**의 성격이 먼저 눈에 들어옵니다. "
                f"{TEN_GOD_DESC.get(first_god, '')}의 방식으로 성과를 만드는 경향이 반복됩니다."
            )
        else:
            lead = (
                f"{dm} 일간의 기본 성향상, 한 가지 직업 성향보다 상황에 맞춰 역할을 조정하는 방식이 더 중요합니다."
            )

        strength = dm_info.get("strength", "")
        risk = dm_info.get("shadow", "")

        cycle = ""
        if current_gz:
            cycle = (
                f"현재 **{current_gz} 대운**에서는 {gan_group or '외부 역할'}과 "
                f"{zhi_group or '생활 기반'}의 주제가 함께 작동하므로, "
                "기존의 실무 역량에 역할 확대나 책임 변화가 붙는지 살펴볼 필요가 있습니다."
            )

        return {
            "headline": "내가 일에서 힘을 쓰는 방식",
            "lead": lead,
            "strength": f"강점은 {strength}",
            "risk": f"주의할 점은 {risk}",
            "cycle": cycle,
        }

    if domain_key == "wealth":
        if first_god:
            lead = (
                f"재물 영역에서는 **{first_god}**이 주요하게 보입니다. "
                "이것은 단순히 돈복의 많고 적음보다, 돈과 자원을 어떤 방식으로 다루는지가 중요하다는 뜻입니다."
            )
        else:
            lead = (
                "재물은 특정 십성이 한쪽으로 강하게 반복되기보다 여러 기운을 함께 보아야 하는 구조입니다."
            )

        if "재성" in [x[2] for x in dominant]:
            trait = "현실적인 숫자, 성과, 자원 배분, 자산 관리가 중요한 판단 기준이 되기 쉽습니다."
        elif "식상" in [x[2] for x in dominant]:
            trait = "직접 만든 결과물이나 전문성을 수익으로 연결하는 방식이 중요해지기 쉽습니다."
        elif "비겁" in [x[2] for x in dominant]:
            trait = "내 판단으로 돈을 움직이는 힘은 있지만, 경쟁·공동자원·지출 통제도 함께 봐야 합니다."
        else:
            trait = "재물은 독립된 주제라기보다 직업·책임·성과와 연결해서 보는 편이 더 맞습니다."

        cycle = ""
        if current_gz:
            cycle = (
                f"현재 {current_gz} 대운의 {gan_group}/{zhi_group} 성격은 "
                "재물 자체보다 돈을 만드는 역할과 책임, 현실적인 선택 방식에 영향을 줍니다."
            )

        return {
            "headline": "돈을 벌고 지키는 방식",
            "lead": lead,
            "strength": trait,
            "risk": "수입의 크기보다 '무엇을 위해 돈을 쓰고, 어디에 자원을 집중하는가'가 더 중요한 명식으로 읽는 것이 좋습니다.",
            "cycle": cycle,
        }

    if domain_key == "relationship":
        if first_god:
            lead = (
                f"관계 영역에서는 **{first_god}**의 성격이 먼저 드러납니다. "
                f"{TEN_GOD_DESC.get(first_god, '')}의 관계 방식이 반복되기 쉽습니다."
            )
        else:
            lead = "관계에서는 한 가지 패턴보다 일간의 기본 성향과 상대 상황에 따라 반응 차이가 큰 편입니다."

        relation_base = dm_info.get("relation", "")
        risk = dm_info.get("shadow", "")
        cycle = ""
        if current_gz:
            cycle = (
                f"현재 {current_gz} 대운에서는 {gan_group}/{zhi_group}의 주제가 함께 작동해 "
                "관계에서도 역할·책임·거리 조절 문제가 평소보다 중요하게 느껴질 수 있습니다."
            )

        return {
            "headline": "사람과 관계를 맺는 방식",
            "lead": lead,
            "strength": relation_base,
            "risk": f"관계가 부담스러워질 때는 {risk}",
            "cycle": cycle,
        }

    # learning
    if first_god:
        lead = (
            f"생각과 성장 영역에서는 **{first_god}**의 성격이 반복됩니다. "
            "배우는 것 자체보다 배운 것을 정리하고 실제 판단과 결과물로 연결하는 방식이 중요합니다."
        )
    else:
        lead = "학습과 내면은 특정 십성보다 일간의 사고 방식과 전체 원국의 균형을 함께 보는 편이 좋습니다."

    return {
        "headline": "생각하고 성장하는 방식",
        "lead": lead,
        "strength": dm_info.get("core", ""),
        "risk": dm_info.get("shadow", ""),
        "cycle": (
            f"현재 {current_gz} 대운에서는 {gan_group}/{zhi_group}의 변화가 "
            "기존의 사고방식과 학습 방향을 다시 정리하게 만들 수 있습니다."
            if current_gz else ""
        ),
    }

def year_ganji(year):
    """연도 간지는 입춘 경계 논쟁을 피하기 위해 해당 연도의 한가운데 날짜를 사용해 연운 간지를 구합니다."""
    try:
        s = Solar.fromYmd(year, 7, 1)
        return s.getLunar().getYearInGanZhiExact()
    except Exception:
        return ""


def year_detail(chart, year):
    gz = year_ganji(year)
    if len(gz) < 2:
        return {}

    gan, zhi = gz[0], gz[1]
    day_gan = chart["day_gan"]
    day_el = STEM_ELEMENT.get(day_gan, "")
    gan_el = STEM_ELEMENT.get(gan, "")
    zhi_el = BRANCH_ELEMENT.get(zhi, "")
    gan_god = ten_god_for_stem(day_gan, gan)
    gan_group = relation_group(day_el, gan_el)
    zhi_group = relation_group(day_el, zhi_el)

    primary = ROLE_GROUP_DESC.get(gan_group, {})
    secondary = ROLE_GROUP_DESC.get(zhi_group, {})

    keywords = {
        "비겁": "주도권·동료·경쟁",
        "식상": "표현·실행·성과",
        "재성": "재물·현실·관리",
        "관성": "조직·책임·직책",
        "인성": "학습·문서·보호",
    }

    return {
        "year": year,
        "ganji": gz,
        "gan": gan,
        "zhi": zhi,
        "gan_el": gan_el,
        "zhi_el": zhi_el,
        "gan_god": gan_god,
        "gan_group": gan_group,
        "zhi_group": zhi_group,
        "headline": f"{keywords.get(gan_group, '변화')}가 전면에 나오고, {keywords.get(zhi_group, '생활 변화')}가 배경에서 작동하는 해",
        "work": primary.get("work", "") + " " + secondary.get("work", ""),
        "money": primary.get("money", "") + " " + secondary.get("money", ""),
        "relation": primary.get("relation", "") + " " + secondary.get("relation", ""),
        "action": primary.get("action", "") + " " + secondary.get("action", ""),
    }


def build_year_ai_prompt(chart, daewoon, year):
    yd = year_detail(chart, year)
    current_cycle = None
    for c in daewoon.get("cycles", []):
        if c["start_year"] <= year <= c["end_year"]:
            current_cycle = c
            break

    return f"""
아래는 사주 원국과 특정 연도 세운의 계산 데이터다.

[원국]
연주 {chart['year']}
월주 {chart['month']}
일주 {chart['day']}
시주 {chart['hour'] or '미상'}
일간 {chart['day_gan']}

[해당 연도]
{year}년 {ganji_to_hangul(yd.get('ganji'))}
천간 십성 {yd.get('gan_god')}
천간 오행 {yd.get('gan_el')}
지지 오행 {yd.get('zhi_el')}
천간 주제 {yd.get('gan_group')}
지지 주제 {yd.get('zhi_group')}

[해당 연도가 속한 대운]
{json.dumps(current_cycle, ensure_ascii=False, default=str)}

숙련된 명리 해석가의 방식으로 다음 순서로 설명하라.
1. 이 해의 제목을 한 문장으로
2. 원국에서 무엇을 건드리는 해인지
3. 직장·직책·성과
4. 재물·자산·현실 판단
5. 인간관계·가족
6. 과해지기 쉬운 부분
7. 잘 활용하는 행동전략 4가지

계산 데이터에 없는 합·충·형·파·해, 용신, 격국을 임의로 만들어내지 않는다.
단정적 예언 대신 경향과 선택 포인트를 설명한다.
"""


def expert_system_prompt():
    return (
        "당신은 사주명리학을 오랫동안 연구하고 상담해 온 숙련된 명리 해석가의 관점으로 분석합니다. "
        "말투만 권위적으로 흉내 내는 것이 아니라, 반드시 일간→월주/계절→오행→십성→원국 구조→대운→세운 순으로 읽습니다. "
        "초보적인 '오행이 많다/적다' 식 해석으로 끝내지 않습니다. "
        "전문용어를 사용하면 즉시 쉬운 말로 풀어 설명합니다. "
        "좋은 말만 나열하지 않고 강점과 과잉, 기회와 부담을 함께 설명합니다. "
        "계산 데이터에 없는 합·충·형·파·해, 격국, 용신, 신강·신약을 임의로 지어내지 않습니다. "
        "사용자의 실제 과거를 알고 있는 것처럼 꾸미지 않습니다. "
        "미래는 확정적으로 예언하지 않고 전통 명리학의 구조적·상징적 해석으로 설명합니다."
    )


# =========================================================
# 5. AI 상세 해석
# =========================================================

def build_ai_prompt(chart, daewoon, gender, calendar_type, birth_date, time_text):
    current = daewoon.get("current")
    gods = collect_ten_gods(chart)

    domain_summary = {
        key: {
            "score": domain_score(chart, guide["groups"]),
            "comment": personalized_domain_interpretation(chart, daewoon, key),
        }
        for key, guide in DOMAIN_GUIDE.items()
    }

    next_years = []
    now_y = datetime.now().year
    for y in range(now_y, now_y + 5):
        next_years.append(year_detail(chart, y))

    payload = {
        "성별": gender,
        "달력": calendar_type,
        "생년월일": birth_date.isoformat(),
        "출생시간": time_text,
        "사주": {
            "연주": chart["year"],
            "월주": chart["month"],
            "일주": chart["day"],
            "시주": chart["hour"] if chart["hour"] else "미상",
            "일간": chart["day_gan"],
            "표면오행": chart["elements"],
            "천간십성": chart["shishen_gan"],
            "지지십성": chart["shishen_zhi"],
            "납음": chart["nayin"],
        },
        "대운": {
            "기산": {
                "년": daewoon.get("start_years"),
                "개월": daewoon.get("start_months"),
                "일": daewoon.get("start_days"),
                "시작일": daewoon.get("start_solar"),
                "순행": daewoon.get("forward"),
            },
            "현재": current,
            "전체": daewoon.get("cycles"),
        },
        "주요십성빈도": dict(gods),
        "영역별참고지표": domain_summary,
        "향후5년세운": next_years,
    }

    return f"""
아래 데이터는 만세력/절기 계산을 거쳐 얻은 명식 데이터다.

[계산 데이터]
{json.dumps(payload, ensure_ascii=False, default=str, indent=2)}

이 명식을 자동 사주 사이트처럼 설명하지 말고, 반드시 '이 사람에게만 해당되는 문장'으로 풀어라.
일반적인 명리학 설명은 최소화하고, 각 문단마다 최소 하나 이상의 실제 계산값
(일간, 월주, 반복 십성, 현재 대운, 세운)을 근거로 연결하라.
'보통 이런 사람은', '일반적으로', '대체로' 같은 교과서식 문장을 반복하지 말고
'이 명식에서는', '당신에게는', '현재 대운에서는'처럼 개인화해 설명하라.

[풀이 순서]
1. 첫인상과 핵심 구조
   - 이 명식에서 가장 먼저 눈에 들어오는 포인트 3가지
   - 서로 상충하거나 동시에 작동하는 성향이 있다면 함께 설명
2. 일간
   - 기본 성향, 판단 방식, 힘을 쓸 때의 장점, 과할 때의 단점
3. 월주와 사회적 얼굴
   - 조직 안에서 어떤 역할을 맡을 때 힘이 나는지
   - 책임·성과·전문성·관계 중 무엇이 중요한 축인지
4. 오행과 십성
   - 표면 개수는 참고로만 사용
   - 십성이 실제 생활에서 어떤 방식으로 나타나는지 연결
5. 직업·커리어
   - 리더십
   - 조직생활
   - 승진/역할확대
   - 변화가 필요할 때의 신호
6. 재물·자산
   - 돈을 대하는 방식
   - 안정과 확장 사이의 성향
   - 자산관리에서 과해지기 쉬운 부분
7. 관계·가족
   - 친밀감, 책임감, 갈등 시 패턴
   - 관계에서 지켜야 할 균형
8. 현재 대운
   - 이전 대운과 무엇이 달라졌는지
   - 현재 10년의 제목을 한 문장으로
   - 초반/중반/후반으로 나눠 읽을 수 있다면 구조적으로 설명
9. 향후 5년 세운
   - 각 연도를 한 줄 제목 + 직장/재물/관계/행동 포인트로
10. 지금의 선택 기준
   - 지금 키워야 할 것 3가지
   - 줄여야 할 것 3가지
   - 한 문장 조언

[금지]
- '무조건 승진', '큰돈을 번다', '질병이 생긴다' 같은 확정 예언
- 데이터에 없는 합충형파해/용신/격국을 임의 생성
- 과거 사건을 맞힌 척하는 표현

전문용어는 쓰되 바로 쉬운 설명을 붙이고, 문장은 상담하듯 자연스럽고 구체적으로 작성하라.
분량은 충분히 자세하게 작성하라.
"""



def ask_openai(prompt):
    """
    OpenAI Responses API를 사용해 명리 해석을 생성합니다.
    API Key는 .streamlit/secrets.toml 의 OPENAI_API_KEY에서 읽습니다.
    """

    if not OPENAI_AVAILABLE:
        return None, (
            "openai 패키지가 설치되어 있지 않습니다. "
            "PowerShell에서 `python -m pip install openai` 를 실행해주세요."
        )

    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception:
        return None, (
            "OPENAI_API_KEY가 설정되어 있지 않습니다. "
            ".streamlit/secrets.toml 파일에 "
            '`OPENAI_API_KEY = "sk-..."` 형식으로 추가해주세요.'
        )

    try:
        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model="gpt-5.6-terra",
            input=[
                {
                    "role": "system",
                    "content": expert_system_prompt(),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            reasoning={
                "effort": "medium"
            },
            max_output_tokens=3500,
        )

        result = response.output_text

        if not result:
            return None, "OpenAI 응답은 수신했지만 해석 텍스트가 비어 있습니다."

        return result, None

    except Exception as e:
        return None, str(e)


# =========================================================
# 5-1. 공통 사이드바
# =========================================================
render_sidebar(current_page="saju.py")


# =========================================================
# 6. 상단
# =========================================================

top1, top2 = st.columns([1, 4])
with top1:
    if st.button("← AI Lab", use_container_width=True, key="back_ai_lab"):
        st.switch_page("app.py")

st.markdown(
    """
    <div class="saju-hero">
        <div class="saju-kicker">AI MYEONGRI INSIGHT</div>
        <div class="saju-title">나에게 반복되는 패턴과<br>지금의 흐름을 읽습니다.</div>
        <div class="saju-desc">
            일간 · 반복 십성 · 현재 대운을 연결해, ‘나는 어떤 방식으로 일하고 관계 맺는가’를 중심으로 봅니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# =========================================================
# 7. 입력 UI
# =========================================================

if not LUNAR_AVAILABLE:
    st.error(
        "먼저 **lunar_python** 설치가 필요합니다.\n\n"
        "PowerShell에서 아래 명령을 한 번 실행하세요:\n\n"
        "`python -m pip install lunar_python`"
    )
    st.stop()

st.markdown('<div class="input-head">출생 정보</div>', unsafe_allow_html=True)

time_options = make_time_options()

with st.form("saju_form"):
    # 1행: 성별 / 양음력
    row1a, row1b = st.columns(2)

    with row1a:
        gender = st.radio(
            "성별",
            ["여성", "남성"],
            horizontal=True,
            key="saju_gender"
        )

    with row1b:
        calendar_type = st.radio(
            "달력",
            ["양력", "음력"],
            horizontal=True,
            key="saju_calendar"
        )

    # 2행: 날짜 / 시간
    row2a, row2b = st.columns([1.15, 1])

    with row2a:
        birth_date = st.date_input(
            "생년월일",
            value=date(1985, 1, 1),
            min_value=date(1930, 1, 1),
            max_value=date.today(),
            key="saju_birth_date"
        )

    with row2b:
        time_text = st.selectbox(
            "출생시간",
            time_options,
            index=1 + (17 * 2),  # 17:00
            key="saju_birth_time",
            help="30분 단위로 선택할 수 있습니다. 정확히 모르면 '모름'을 선택하세요."
        )

    lunar_leap = st.checkbox(
        "음력 생일이 윤달인 경우 체크",
        value=False,
        key="saju_leap"
    )

    submitted = st.form_submit_button(
        "명리 분석 시작하기",
        type="primary",
        use_container_width=True
    )


# =========================================================
# 8. 계산
# =========================================================

if submitted:
    try:
        chart = build_chart(
            birth_date=birth_date,
            calendar_type=calendar_type,
            time_text=time_text,
            gender=gender,
            lunar_leap=(lunar_leap and calendar_type == "음력")
        )

        daewoon = build_daewoon(chart, gender)
        basic = base_interpretation(chart)

        st.session_state["saju_data"] = {
            "gender": gender,
            "calendar_type": calendar_type,
            "birth_date": birth_date,
            "time_text": time_text,
            "lunar_leap": lunar_leap,
            "chart": chart,
            "daewoon": daewoon,
            "basic": basic,
        }

    except Exception as e:
        st.error(f"명식 계산 중 오류가 발생했습니다: {e}")


# =========================================================
# 9. 결과
# =========================================================

if "saju_data" in st.session_state:
    data = st.session_state["saju_data"]
    chart = data["chart"]
    daewoon = data["daewoon"]
    basic = data["basic"]

    st.markdown('<div style="height:.4rem"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="result-title">나의 명리 구조</div>',
        unsafe_allow_html=True
    )

    converted_solar = chart["solar"].toYmd()
    time_note = "출생시간 미상 · 시주 제외" if chart["unknown_time"] else f"{data['time_text']} 출생"

    st.markdown(
        f'<div class="result-sub">양력 환산 {converted_solar} · {time_note}</div>',
        unsafe_allow_html=True
    )

    tabs = st.tabs([
        "핵심 해석",
        "직업·재물·관계",
        "인생 대운",
        "AI 명리상담"
    ])

    # -----------------------------------------------------
    # TAB 1 핵심 해석
    # -----------------------------------------------------
    with tabs[0]:

        profile = build_personalized_profile(chart, daewoon)

        st.markdown("## 나를 가장 잘 설명하는 핵심")
        with st.container(border=True):
            st.markdown(f"### {profile['title']}")
            st.write(profile["one_line"])

            if profile["god_sentences"]:
                st.markdown("**내 사주에서 실제로 반복되는 십성**")
                for god, cnt in profile.get("top_gods", []):
                    group = ten_god_group(god)
                    group_info = ROLE_GROUP_DESC.get(group, {})
                    st.markdown(f"#### {god} · {cnt}회")
                    st.write(_god_sentence(god, cnt))
                    if group_info:
                        st.caption(
                            f"쉽게 말하면 · {group_info.get('title', '')} | "
                            f"일에서는 {group_info.get('work', '')}"
                        )

        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                st.markdown("### 💼 일할 때의 나")
                st.write(profile["work"])
                st.caption(f"월주 {profile['month']} · 사회생활과 직업환경을 읽는 자리")

        with c2:
            with st.container(border=True):
                st.markdown("### ⚠️ 내가 과해질 때")
                st.write(profile["shadow"])

        c3, c4 = st.columns(2)
        with c3:
            with st.container(border=True):
                st.markdown("### 💰 돈을 다루는 방식")
                st.write(profile["money"])
        with c4:
            with st.container(border=True):
                st.markdown("### 🤝 관계에서의 나")
                st.write(profile["relation"])

        if profile["cycle"]:
            with st.container(border=True):
                st.markdown("### 🧭 지금의 10년")
                st.write(profile["cycle"])

        # 오행 분포를 핵심해석 화면에 다시 표시
        st.markdown("### 🌿 내 오행 분포")
        st.caption("천간·지지의 표면 오행을 기준으로 본 참고 분포입니다.")

        element_order = ["목", "화", "토", "금", "수"]
        element_cols = st.columns(5)

        for idx, el in enumerate(element_order):
            count = chart["elements"].get(el, 0)
            with element_cols[idx]:
                st.metric(
                    label=f"{ELEMENT_SYMBOL.get(el, '')} {el}",
                    value=f"{count}개",
                )

        if chart["elements"]:
            max_count = max(chart["elements"].values())
            min_count = min(chart["elements"].values())
            strong_elements = [
                el for el, cnt in chart["elements"].items()
                if cnt == max_count
            ]
            weak_elements = [
                el for el, cnt in chart["elements"].items()
                if cnt == min_count
            ]

            strong_text = " · ".join(strong_elements)
            weak_text = " · ".join(weak_elements)

            with st.container(border=True):
                st.markdown(
                    f"**가장 많이 드러나는 오행** · {strong_text} {max_count}개"
                )
                st.markdown(
                    f"**상대적으로 적게 드러나는 오행** · {weak_text} {min_count}개"
                )
                st.caption(
                    "오행 개수는 성향을 이해하는 참고값입니다. "
                    "많고 적음만으로 좋고 나쁨이나 용신을 단정하지 않습니다."
                )

        with st.expander("내 명식 근거만 간단히 보기"):
            cols = st.columns(4)
            pillar_data = [
                ("연주", chart["year"]),
                ("월주", chart["month"]),
                ("일주", chart["day"]),
                ("시주", chart["hour"] or "미상"),
            ]
            for idx, (title, value) in enumerate(pillar_data):
                with cols[idx]:
                    st.caption(title)
                    st.markdown(f"### {ganji_to_hangul(value)}")

            gods = collect_ten_gods(chart).most_common(5)
            if gods:
                st.caption(
                    "반복 십성 · "
                    + " / ".join([
                        f"{g} {c}회 ({TEN_GOD_DESC.get(g, '')})"
                        for g, c in gods
                    ])
                )

        if chart["unknown_time"]:
            st.info(
                "출생시간을 모름으로 선택해 시주는 제외했습니다. "
                "연·월·일 중심 해석은 가능하지만 세부 시점 해석은 정밀도가 낮아질 수 있습니다."
            )

    # -----------------------------------------------------
    # TAB 2 직업·재물·관계
    # -----------------------------------------------------
    with tabs[1]:

        st.markdown("## 내 삶의 영역별 패턴")

        domain_order = ["career", "wealth", "relationship", "learning"]

        for key in domain_order:
            result = personalized_domain_compact(chart, daewoon, key)

            with st.container(border=True):
                st.markdown(f"### {result['icon']} {result['title']}")
                st.markdown(f"**{result['headline']}**")
                st.write(result["main"])

                if result["strength"]:
                    st.markdown(f"**강하게 쓰이는 부분** · {result['strength']}")
                if result["risk"]:
                    st.markdown(f"**과해질 때** · {result['risk']}")
                if result["cycle"]:
                    st.markdown(f"**현재 대운에서는** · {result['cycle']}")
                if result["basis"]:
                    st.caption("근거 십성 · " + result["basis"])

    # -----------------------------------------------------
    # TAB 4 인생 대운
    # -----------------------------------------------------
    with tabs[2]:

        current = daewoon.get("current")
        direction = "순행" if daewoon.get("forward") else "역행"
        start_phrase = (
            f"출생 후 약 {daewoon.get('start_years')}년 "
            f"{daewoon.get('start_months')}개월 {daewoon.get('start_days')}일"
        )

        if current:
            current_detail = cycle_detail(chart, current)
            html(f"""
            <div class="current-cycle">
                <div class="current-cycle-label">CURRENT 10-YEAR CYCLE</div>
                <div class="current-cycle-title">
                    {ganji_to_hangul(current['ganji'])} 대운 · {current['start_year']}~{current['end_year']}
                </div>
                <div class="current-cycle-text">
                    {current['start_age']}~{current['end_age']}세 ·
                    천간은 <b>{current_detail.get('gan_god') or current_detail.get('gan_group')}</b>,
                    지지는 <b>{current_detail.get('zhi_group')}</b>의 성격으로 작동합니다.
                </div>
            </div>
            """)

        with st.expander("대운 계산 기준 보기"):
            st.write(f"대운 방향: **{direction}**")
            st.write(f"기산점: **{start_phrase} 후**")
            st.write(f"계산된 대운 시작일: **{daewoon.get('start_solar') or '시간 미상으로 근사'}**")
            st.caption(
                "대운은 10년 단위 환경 변화의 축입니다. 실제 해석은 원국의 일간·월주와 "
                "대운 천간·지지가 어떤 십성/오행 관계를 만드는지를 함께 봅니다."
            )

        st.markdown("#### 보고 싶은 대운을 눌러보세요")
        st.caption("누르면 바로 아래에 해당 10년의 직장·재물·관계·행동 포인트가 펼쳐집니다.")

        cycles = daewoon["cycles"]

        if "selected_daewoon_index" not in st.session_state:
            current_idx = 0
            for i, c in enumerate(cycles):
                if c.get("current"):
                    current_idx = i
                    break
            st.session_state["selected_daewoon_index"] = current_idx

        # 3개씩 버튼 배치
        for row_start in range(0, len(cycles), 3):
            cols = st.columns(3)
            for j in range(3):
                idx = row_start + j
                if idx >= len(cycles):
                    break
                c = cycles[idx]
                active = idx == st.session_state["selected_daewoon_index"]
                label = (
                    f"{'● ' if active else ''}{ganji_to_hangul(c['ganji'])} 대운\n"
                    f"{c['start_year']}~{c['end_year']} · {c['start_age']}~{c['end_age']}세"
                )
                with cols[j]:
                    if st.button(
                        label,
                        key=f"select_dw_{idx}",
                        use_container_width=True,
                        type="primary" if active else "secondary"
                    ):
                        st.session_state["selected_daewoon_index"] = idx
                        # 선택이 바뀌면 이전 대운 AI 답변은 제거
                        st.session_state.pop("cycle_ai_result", None)
                        st.session_state.pop("cycle_ai_index", None)
                        st.rerun()

        selected_idx = st.session_state["selected_daewoon_index"]
        selected = cycles[selected_idx]
        detail = cycle_detail(chart, selected)

        html(f"""
        <div class="cycle-detail-wrap">
            <div class="cycle-detail-kicker">SELECTED DAEWOON</div>
            <div class="cycle-detail-title">
                {ganji_to_hangul(selected['ganji'])} 대운 · {selected['start_year']}~{selected['end_year']}
            </div>
            <div class="cycle-detail-meta">
                <b>천간 {gan_to_hangul(detail.get('gan'))}</b> · {detail.get('gan_el')} ·
                {detail.get('gan_god') or detail.get('gan_group')}
                &nbsp;&nbsp;|&nbsp;&nbsp;
                <b>지지 {zhi_to_hangul(detail.get('zhi'))}</b> · {detail.get('zhi_el')} ·
                {detail.get('zhi_group')}
                <br>
                {detail.get('headline')}
            </div>
        </div>

        <div class="mini-analysis-grid">
            <div class="mini-analysis">
                <h4>💼 직장 · 커리어</h4>
                <p>{detail.get('work')}</p>
            </div>
            <div class="mini-analysis">
                <h4>💰 재물 · 현실</h4>
                <p>{detail.get('money')}</p>
            </div>
            <div class="mini-analysis">
                <h4>🤝 관계 · 가족</h4>
                <p>{detail.get('relation')}</p>
            </div>
            <div class="mini-analysis">
                <h4>🎯 이 대운을 쓰는 법</h4>
                <p>{detail.get('action')}</p>
            </div>
        </div>
        """)

        # 선택 대운만 OpenAI로 더 깊게 분석
        if st.button(
            "선택한 대운을 GPT로 더 자세히 분석",
            use_container_width=True,
            key="deep_cycle_ai"
        ):
            prompt = build_cycle_ai_prompt(chart, selected)
            with st.spinner(f"{ganji_to_hangul(selected['ganji'])} 대운을 원국과 함께 정밀 해석하고 있습니다..."):
                result, error = ask_openai(prompt)
            if result:
                st.session_state["cycle_ai_result"] = result
                st.session_state["cycle_ai_index"] = selected_idx
            else:
                st.error(f"대운 상세 해석을 불러오지 못했습니다: {error}")

        if (
            st.session_state.get("cycle_ai_result")
            and st.session_state.get("cycle_ai_index") == selected_idx
        ):
            with st.container(border=True):
                st.markdown(f"### {ganji_to_hangul(selected['ganji'])} 대운 심층 해석")
                st.markdown(st.session_state["cycle_ai_result"])


        st.divider()
        st.markdown("#### 선택한 대운 안에서 연도별 흐름 보기")
        st.caption("해당 대운에 속한 연도를 눌러 원국 × 대운 × 세운의 흐름을 단계적으로 살펴봅니다.")

        years = list(range(selected["start_year"], selected["end_year"] + 1))
        visible_years = [y for y in years if 1900 <= y <= 2100]

        if "selected_year" not in st.session_state or st.session_state["selected_year"] not in visible_years:
            now_y = datetime.now().year
            st.session_state["selected_year"] = now_y if now_y in visible_years else visible_years[0]

        for row_start in range(0, len(visible_years), 5):
            cols = st.columns(5)
            for j in range(5):
                idx = row_start + j
                if idx >= len(visible_years):
                    break
                y = visible_years[idx]
                yd = year_detail(chart, y)
                active = y == st.session_state["selected_year"]
                with cols[j]:
                    if st.button(
                        f"{'● ' if active else ''}{y}\n{ganji_to_hangul(yd.get('ganji',''))}",
                        key=f"select_year_{selected_idx}_{y}",
                        use_container_width=True,
                        type="primary" if active else "secondary"
                    ):
                        st.session_state["selected_year"] = y
                        st.session_state.pop("year_ai_result", None)
                        st.session_state.pop("year_ai_key", None)
                        st.rerun()

        sy = st.session_state["selected_year"]
        yd = year_detail(chart, sy)

        html(f"""
        <div class="cycle-detail-wrap">
            <div class="cycle-detail-kicker">YEAR FLOW</div>
            <div class="cycle-detail-title">{sy}년 · {ganji_to_hangul(yd.get('ganji'))}</div>
            <div class="cycle-detail-meta">
                천간 <b>{gan_to_hangul(yd.get('gan'))}</b> · {yd.get('gan_god') or yd.get('gan_group')}
                &nbsp;&nbsp;|&nbsp;&nbsp;
                지지 <b>{zhi_to_hangul(yd.get('zhi'))}</b> · {yd.get('zhi_group')}
                <br>{yd.get('headline')}
            </div>
        </div>

        <div class="mini-analysis-grid">
            <div class="mini-analysis">
                <h4>💼 직장·성과</h4>
                <p>{yd.get('work')}</p>
            </div>
            <div class="mini-analysis">
                <h4>💰 재물·현실</h4>
                <p>{yd.get('money')}</p>
            </div>
            <div class="mini-analysis">
                <h4>🤝 관계</h4>
                <p>{yd.get('relation')}</p>
            </div>
            <div class="mini-analysis">
                <h4>🎯 행동 포인트</h4>
                <p>{yd.get('action')}</p>
            </div>
        </div>
        """)

        if st.button(
            f"{sy}년을 GPT로 깊게 보기",
            use_container_width=True,
            key="deep_year_ai"
        ):
            with st.spinner(f"{sy}년 세운을 원국과 대운에 연결해 해석하고 있습니다..."):
                result, error = ask_openai(build_year_ai_prompt(chart, daewoon, sy))
            if result:
                st.session_state["year_ai_result"] = result
                st.session_state["year_ai_key"] = (selected_idx, sy)
            else:
                st.error(f"연도 해석을 불러오지 못했습니다: {error}")

        if (
            st.session_state.get("year_ai_result")
            and st.session_state.get("year_ai_key") == (selected_idx, sy)
        ):
            with st.container(border=True):
                st.markdown(f"### {sy}년 심층 세운 해석")
                st.markdown(st.session_state["year_ai_result"])


        if chart["unknown_time"]:
            st.warning(
                "출생시간 미상인 경우 시주가 빠지므로 대운 기산점의 일·월 단위 정밀도와 "
                "세부 사건 시점 해석은 제한될 수 있습니다."
            )

    # -----------------------------------------------------
    # TAB 5 AI 명리상담
    # -----------------------------------------------------
    with tabs[3]:

        st.markdown(
            """
            <div class="detail-box">
                <div class="detail-head">AI 개인화 명리상담</div>
                <div class="detail-body">
                    내 명식의 실제 계산값과 현재 대운을 기준으로, 일반론보다 ‘왜 나에게 이런 패턴이 반복되는지’를 중심으로 해석합니다.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if "saju_ai_result" not in st.session_state:
            if st.button(
                "전문 명리상담 시작하기",
                type="primary",
                use_container_width=True,
                key="run_ai_saju"
            ):
                prompt = build_ai_prompt(
                    chart=chart,
                    daewoon=daewoon,
                    gender=data["gender"],
                    calendar_type=data["calendar_type"],
                    birth_date=data["birth_date"],
                    time_text=data["time_text"]
                )

                with st.spinner("명식과 대운을 함께 해석하고 있습니다..."):
                    result, error = ask_openai(prompt)

                if result:
                    st.session_state["saju_ai_result"] = result
                    st.rerun()
                else:
                    st.error(f"AI 해석을 불러오지 못했습니다: {error}")

        if "saju_ai_result" in st.session_state:
            st.markdown(st.session_state["saju_ai_result"])

            if st.button(
                "AI 해석 다시 생성",
                use_container_width=True,
                key="reset_ai_saju"
            ):
                del st.session_state["saju_ai_result"]
                st.rerun()

        st.divider()

        st.markdown("#### 추가로 궁금한 질문")
        topic = st.selectbox(
            "주제",
            [
                "직장·승진",
                "커리어 변화",
                "재물·자산",
                "부동산",
                "인간관계",
                "배우자·가족",
                "자녀",
                "현재 대운",
                "향후 3년",
            ],
            key="saju_topic"
        )

        question = st.text_area(
            "질문",
            placeholder="예: 현재 대운에서 직장 내 역할 변화는 어떤 의미인가요?",
            height=90,
            key="saju_question"
        )

        if st.button(
            "이 질문 분석하기",
            use_container_width=True,
            key="ask_saju_question"
        ):
            if not question.strip():
                st.warning("질문을 입력해주세요.")
            else:
                base_prompt = build_ai_prompt(
                    chart=chart,
                    daewoon=daewoon,
                    gender=data["gender"],
                    calendar_type=data["calendar_type"],
                    birth_date=data["birth_date"],
                    time_text=data["time_text"]
                )

                q_prompt = (
                    base_prompt
                    + f"\n\n[추가 질문 분야] {topic}"
                    + f"\n[사용자 질문] {question}"
                    + "\n위 질문에 집중해서, 명식과 현재 대운의 근거를 밝혀 구체적으로 답하라."
                )

                with st.spinner("질문을 명식과 대운에 연결해 분석하고 있습니다..."):
                    answer, error = ask_openai(q_prompt)

                if answer:
                    st.markdown(answer)
                else:
                    st.error(f"답변을 생성하지 못했습니다: {error}")


# =========================================================
# 10. 하단 안내
# =========================================================

st.markdown(
    """
    <div class="caution">
        ※ 본 서비스는 전통 명리학의 계산 체계와 해석 논리를 활용한 자기이해·참고용 콘텐츠입니다.
        명리학은 과학적으로 미래를 확정하는 예측 도구가 아니며,
        의료·투자·법률 등 중요한 의사결정을 대체하지 않습니다.
        특히 출생시간이 정확하지 않은 경우 시주 및 세부 시점 해석에는 한계가 있습니다.
    </div>
    """,
    unsafe_allow_html=True
)

import streamlit as st
import anthropic
import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import Counter
from pathlib import Path
import io
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader

from auth import require_page_auth


# ============================================================
# PAGE
# ============================================================
st.set_page_config(
    page_title="AI 보고서 작성기",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_page_auth()


# ============================================================
# 한글 사이드바
# ============================================================
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

    st.button(
        "📄 보고서 작성기",
        key="sidebar_report",
        use_container_width=True,
        disabled=True,
    )

    if st.button(
        "🚗 차량 선택기",
        key="sidebar_car_selector",
        use_container_width=True,
    ):
        st.switch_page("pages/4_차량_선택기.py")

    if st.button(
        "🎞️ GIF 변환기",
        key="sidebar_gif",
        use_container_width=True,
    ):
        st.switch_page("pages/5_GIF_변환기.py")


# ============================================================
# STYLE
# ============================================================
st.markdown(
    """
<style>
:root{
    --navy:#0B1733;
    --blue:#335CFF;
    --violet:#6C4CF1;
    --ink:#172033;
    --muted:#667085;
    --line:#E7EAF0;
    --soft:#F6F8FC;
    --card:#FFFFFF;
}

[data-testid="stSidebar"]{
    display:block !important;
}

.block-container{
    max-width:1160px;
    padding-top:1rem;
    padding-bottom:5rem;
}

.report-hero{
    position:relative;
    overflow:hidden;
    border-radius:30px;
    padding:42px 44px;
    color:white;
    background:
        radial-gradient(circle at 82% 18%, rgba(94,126,255,.25), transparent 24%),
        linear-gradient(125deg,#08152D 0%,#102B59 62%,#3156C8 100%);
    box-shadow:0 20px 52px rgba(15,31,70,.14);
    margin-bottom:18px;
}

.report-hero-kicker{
    font-size:10px;
    font-weight:900;
    letter-spacing:.18em;
    color:#AFC5FF;
}

.report-hero-title{
    margin-top:9px;
    font-size:37px;
    line-height:1.18;
    font-weight:950;
    letter-spacing:-.045em;
}

.report-hero-desc{
    max-width:790px;
    margin-top:12px;
    font-size:13px;
    line-height:1.7;
    color:#D9E3F4;
}

.hero-chips{
    display:flex;
    gap:7px;
    flex-wrap:wrap;
    margin-top:17px;
}

.hero-chip{
    padding:6px 9px;
    border-radius:999px;
    border:1px solid rgba(255,255,255,.13);
    background:rgba(255,255,255,.08);
    font-size:9px;
    font-weight:800;
    color:#EDF3FF;
}

.input-card{
    margin:4px 0 14px;
    padding:18px 20px;
    border:1px solid var(--line);
    border-radius:20px;
    background:white;
    box-shadow:0 8px 24px rgba(15,23,42,.035);
}

.section-kicker{
    color:var(--blue);
    font-size:9px;
    font-weight:900;
    letter-spacing:.12em;
}

.section-title{
    margin-top:4px;
    color:var(--ink);
    font-size:20px;
    font-weight:950;
    letter-spacing:-.03em;
}

.section-desc{
    margin-top:4px;
    color:#7A8698;
    font-size:11px;
    line-height:1.55;
}

.report-shell{
    margin-top:14px;
    padding:28px 30px;
    border:1px solid var(--line);
    border-radius:24px;
    background:#FFFFFF;
    box-shadow:0 12px 34px rgba(15,23,42,.045);
}

.report-label{
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:5px 9px;
    border-radius:999px;
    background:#EEF3FF;
    color:#315EF5;
    font-size:8px;
    font-weight:900;
    letter-spacing:.08em;
}

.report-body{
    margin-top:14px;
    white-space:pre-wrap;
    color:#26364D;
    font-size:13px;
    line-height:1.78;
}

.insight-card{
    padding:16px 18px;
    border:1px solid #E5EAF2;
    border-radius:17px;
    background:linear-gradient(145deg,#FFFFFF,#F8FAFD);
}

.insight-card b{
    color:#1D2C45;
    font-size:12px;
}

.insight-card p{
    margin:6px 0 0;
    color:#768397;
    font-size:10px;
    line-height:1.55;
}

.chart-wrap{
    margin:14px 0 4px;
    padding:17px 18px 13px;
    border:1px solid #E7EAF0;
    border-radius:20px;
    background:linear-gradient(180deg,#FFFFFF,#FAFBFD);
}

.chart-head{
    margin-bottom:10px;
}

.chart-title{
    color:#1A2940;
    font-size:15px;
    font-weight:950;
    letter-spacing:-.02em;
}

.chart-sub{
    margin-top:2px;
    color:#8B96A7;
    font-size:9px;
}

div[data-testid="stTextArea"] textarea{
    min-height:155px !important;
    border-radius:15px !important;
}

div[data-testid="stButton"] button[kind="primary"]{
    min-height:48px;
    border:none;
    border-radius:13px;
    color:white;
    font-weight:900;
    background:linear-gradient(135deg,#315EF5,#674CE8);
    box-shadow:0 9px 22px rgba(49,94,245,.18);
}

div[data-testid="stDownloadButton"] button{
    min-height:44px;
    border-radius:12px;
    font-weight:850;
}

@media(max-width:768px){
    .block-container{
        padding-top:.55rem;
        padding-left:.8rem;
        padding-right:.8rem;
        padding-bottom:4.5rem;
    }

    .report-hero{
        padding:24px 20px;
        border-radius:22px;
        margin-bottom:13px;
    }

    .report-hero-title{
        font-size:27px;
        line-height:1.2;
    }

    .report-hero-desc{
        font-size:10px;
        line-height:1.5;
    }

    .hero-chip{
        font-size:8px;
        padding:5px 7px;
    }

    .input-card{
        padding:14px 14px;
        border-radius:16px;
    }

    .report-shell{
        padding:18px 16px;
        border-radius:18px;
    }

    .report-body{
        font-size:11px;
        line-height:1.68;
    }

    .chart-wrap{
        padding:13px 12px 10px;
        border-radius:16px;
    }
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HERO
# ============================================================
st.markdown(
    """
<div class="report-hero">
    <div class="report-hero-kicker">EXECUTIVE REPORT BUILDER</div>
    <div class="report-hero-title">
        정보를 찾는 데서 끝내지 않고,<br>
        <span style="color:#C9D8FF;">경영진이 읽을 수 있는 보고서로.</span>
    </div>
    <div class="report-hero-desc">
        DART 공시 · 법령 · 웹 검색을 필요한 경우에만 활용하고,
        핵심 메시지 → 주요 근거 → 시사점 → 실행 제안 순서로 재구성합니다.
        단순 요약보다 “그래서 무엇을 해야 하는가”가 드러나는 보고서를 지향합니다. 기본은 빠른 작성이며, 필요할 때만 최신자료 조사를 선택할 수 있습니다.
    </div>
    <div class="hero-chips">
        <span class="hero-chip">Executive Summary</span>
        <span class="hero-chip">DART</span>
        <span class="hero-chip">법령정보</span>
        <span class="hero-chip">Web Search</span>
        <span class="hero-chip">Decision & Action</span>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# CLIENT / KEYS
# ============================================================
client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

DART_API_KEY = st.secrets["DART_API_KEY"]
LAW_OC = st.secrets["LAW_OC"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]

BASE_DIR = Path(__file__).resolve().parent.parent
CORP_CODES_PATH = BASE_DIR / "corp_codes.json"


# ============================================================
# TOOLS
# ============================================================
tools = [
    {
        "name": "get_disclosures",
        "description": "특정 회사의 최근 공시 목록을 DART에서 조회한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "조회할 회사 이름"
                }
            },
            "required": ["company_name"]
        }
    },
    {
        "name": "search_law",
        "description": "키워드로 대한민국 법령을 검색한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 법령 키워드"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "web_search",
        "description": "실시간 뉴스, 최신 정보, 일반적인 인터넷 검색이 필요할 때 사용한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 키워드나 질문"
                }
            },
            "required": ["query"]
        }
    }
]

chart_data_store = {
    "company": None,
    "dates": [],
}


@st.cache_data
def load_corp_codes():
    with open(CORP_CODES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def try_fetch_disclosures(corp_code):
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": "20250101",
        "end_de": "20261231",
        "page_count": 20,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    last_error = None

    for _ in range(2):
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=12,
            )
            data = response.json()

            if data.get("status") == "000" and data.get("list"):
                return data["list"], None

            return None, f"DART 응답: {data.get('message')}"

        except Exception as e:
            last_error = f"에러: {type(e).__name__}"
            time.sleep(0.8)

    return None, last_error


def get_disclosures(company_name):
    try:
        corp_map = load_corp_codes()
    except Exception as e:
        return f"회사 목록 로딩 실패: {str(e)}"

    def normalize(text):
        return text.replace(" ", "").lower()

    query_norm = normalize(company_name)
    exact_matches = []
    partial_matches = []

    for name, codes in corp_map.items():
        name_norm = normalize(name)

        if name_norm == query_norm:
            exact_matches.append((name, codes))
        elif query_norm in name_norm or name_norm in query_norm:
            partial_matches.append((name, codes))

    if exact_matches:
        candidates = exact_matches
    elif len(partial_matches) == 1:
        candidates = partial_matches
    elif len(partial_matches) > 1:
        names = ", ".join(name for name, _ in partial_matches[:10])
        return f"'{company_name}'과 비슷한 회사가 여러 개 있어요: {names}"
    else:
        return f"'{company_name}' 회사를 DART에서 찾지 못했어요."

    matched_name, codes = candidates[0]
    last_error = None

    for code in codes:
        filings, error = try_fetch_disclosures(code)

        if filings:
            results = []
            dates = []

            for item in filings:
                date = item.get("rcept_dt", "")
                report_name = item.get("report_nm", "")
                results.append(f"{date} - {report_name}")

                if date:
                    dates.append(date)

            chart_data_store["company"] = matched_name
            chart_data_store["dates"] = dates

            return f"[{matched_name}]\n" + "\n".join(results)

        last_error = error

    return f"'{matched_name}' 조회 실패. {last_error}"


def search_law(query):
    url = "http://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": LAW_OC,
        "target": "law",
        "type": "XML",
        "query": query,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        root = ET.fromstring(response.content)
    except Exception as e:
        return f"법령 검색 중 오류: {str(e)}"

    results = []

    for law in root.findall("law"):
        name_node = law.find("법령명한글")
        date_node = law.find("공포일자")

        if name_node is None:
            continue

        name = name_node.text or ""
        date = date_node.text if date_node is not None else ""
        results.append(f"{date} - {name}")

    if not results:
        return f"'{query}'와 관련된 법령을 찾지 못했어요."

    return "\n".join(results[:20])


def web_search(query):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": 4,
        "search_depth": "basic",
    }

    try:
        response = requests.post(url, json=payload, timeout=12)
        data = response.json()
        results = data.get("results", [])

        if not results:
            return f"'{query}'에 대한 검색 결과를 찾지 못했어요."

        summary = []

        for item in results:
            title = item.get("title", "")
            content = item.get("content", "")[:500]
            url_text = item.get("url", "")
            summary.append(
                f"- {title}\n"
                f"  핵심: {content}\n"
                f"  출처: {url_text}"
            )

        return "\n".join(summary)

    except Exception as e:
        return f"검색 중 오류: {str(e)}"


def extract_text(content_blocks):
    texts = []

    for block in content_blocks:
        if block.type == "text":
            texts.append(block.text)

    return "\n".join(texts).strip()


# ============================================================
# REPORT GENERATION
# ============================================================
REPORT_SYSTEM_PROMPT = """
당신은 경영진 보고서 작성에 특화된 시니어 전략 컨설턴트다.
사용자의 메모와 외부 근거를 단순 요약하지 말고,
'무엇이 핵심인지 → 왜 중요한지 → 어떤 판단이 필요한지 → 다음 행동은 무엇인지'
순서로 재구성한다.

공통 작성 원칙:
1. 결론을 먼저 제시한다.
2. 사실, 해석, 제안을 구분한다.
3. 불확실한 내용은 확정적으로 단정하지 않는다.
4. 사용자가 준 사실과 외부 검색 결과를 혼동하지 않는다.
5. 최신성이나 외부 근거가 필요한 경우에만 검색 도구를 사용한다.
6. 검색 결과를 나열하지 말고 경영진 판단에 필요한 근거만 선별한다.
7. '혁신', '고도화', '효율화' 같은 추상어는 구체적 변화와 함께 쓴다.
8. 실행 제안은 우선순위와 다음 액션이 보이도록 작성한다.
9. 지나치게 장황한 배경 설명은 줄이고 판단 포인트를 선명하게 만든다.
10. 마크다운 기호(#, ** 등)는 쓰지 않고 일반 텍스트로 작성한다.

공통 품질 기준:
- 첫 20% 안에서 핵심 결론이 보여야 한다.
- 각 문단은 한 가지 메시지만 담는다.
- 수치가 있으면 의미를 해석한다.
- 리스크는 문제뿐 아니라 관리 방안까지 제시한다.
- 실행안은 실제 다음 행동으로 작성한다.
"""


REPORT_STYLE_PROMPTS = {
    "CEO/임원 보고": """
[역할]
CEO 또는 임원이 짧은 시간 안에 현황을 파악하고 의사결정을 내릴 수 있도록 작성한다.

[핵심 관점]
- 그래서 무엇이 중요한가
- 회사에 어떤 영향이 있는가
- 지금 무엇을 결정해야 하는가
- 실행 우선순위는 무엇인가

[반드시 답할 질문]
1. 핵심 결론은 무엇인가?
2. 지금 다루어야 하는 이유는 무엇인가?
3. 경영적 영향은 무엇인가?
4. 경영진이 판단해야 할 선택지는 무엇인가?
5. 가장 먼저 실행해야 할 것은 무엇인가?

[권장 구조]
[보고서 제목]
한 줄로 결론이 느껴지는 제목

[Executive Summary]
결론 → 중요성 → 영향 → 경영진 판단사항

[핵심 메시지]
① 핵심 현황/변화
② 경영적 의미
③ 의사결정 포인트

[주요 분석]
핵심 근거 2~4개

[리스크 및 확인사항]
놓치면 안 되는 리스크

[제안 및 Next Action]
즉시 / 단기 / 중기

[경영진 한 문장]
구두보고용 한 문장

[작성 톤]
짧고 단단하게. 배경보다 판단과 실행을 앞세운다.
""",

    "전략 검토": """
[역할]
경영전략 컨설턴트처럼 전략적 선택지와 우선순위를 비교한다.

[핵심 관점]
- 현재 어떤 변화가 발생하고 있는가
- 기존 방식의 한계는 무엇인가
- 어떤 전략 대안이 가능한가
- 무엇을 선택하고 무엇을 포기할 것인가
- 실행 순서를 어떻게 가져갈 것인가

[반드시 답할 질문]
1. 현재 환경 변화 또는 문제는 무엇인가?
2. 기존 접근의 한계는 무엇인가?
3. 가능한 전략 대안은 무엇인가?
4. 각 대안의 장단점과 전제조건은 무엇인가?
5. 가장 현실적인 권고안은 무엇인가?
6. 단계별 실행 로드맵은 어떻게 구성해야 하는가?

[권장 구조]
[전략적 결론]
권고 방향을 먼저 제시

[환경 및 변화]
시장·고객·기술·내부 역량 변화

[핵심 과제]
해결해야 할 전략적 쟁점

[전략 대안]
대안 A / B / C와 장단점

[권고안]
추천 방향과 선택 이유

[실행 로드맵]
즉시 / 3~6개월 / 중기

[성과 판단 기준]
전략이 제대로 작동하는지 판단할 지표

[작성 톤]
현황 나열보다 선택과 집중, 우선순위, 트레이드오프를 강조한다.
""",

    "이슈·리스크 보고": """
[역할]
운영리스크, 프로젝트 이슈, 감사·준법 이슈를 경영진에게 보고하는 관점으로 작성한다.

[핵심 관점]
- 무엇이 발생했는가
- 왜 발생했는가
- 영향 범위는 어디까지인가
- 리스크 수준은 어느 정도인가
- 즉시 통제와 재발방지는 무엇인가

[반드시 답할 질문]
1. 현재 이슈의 사실관계는 무엇인가?
2. 원인 또는 촉발 요인은 무엇인가?
3. 재무·법률·운영·평판·일정 영향은 무엇인가?
4. 현재 통제되고 있는 부분과 미확인 부분은 무엇인가?
5. 즉시 필요한 조치는 무엇인가?
6. 재발방지를 위해 어떤 구조적 개선이 필요한가?

[권장 구조]
[이슈 요약]
무슨 일이 발생했고 현재 상태가 어떤지

[영향도]
재무 / 법률·규제 / 운영 / 고객·평판 / 일정

[원인 분석]
직접 원인과 구조적 원인 구분

[리스크 수준]
높음 / 중간 / 낮음 또는 정성 평가 + 근거

[즉시 조치]
오늘~단기 대응

[재발방지]
프로세스, 역할, 통제, 시스템 개선

[경영진 요청사항]
승인·의사결정·보고 필요사항

[작성 톤]
책임 회피나 과도한 단정 없이 사실과 대응을 분리한다.
""",

    "시장·경쟁 분석": """
[역할]
시장조사와 경쟁전략 관점에서 외부 변화를 해석하고 필요한 대응을 제안한다.

[핵심 관점]
- 시장이 어떻게 변하고 있는가
- 경쟁사는 무엇을 하고 있는가
- 변화가 일시적인가 구조적인가
- 기회와 위협은 무엇인가
- 필요한 차별화 포인트는 무엇인가

[반드시 답할 질문]
1. 시장의 핵심 변화는 무엇인가?
2. 성장 또는 축소를 만드는 요인은 무엇인가?
3. 주요 경쟁사의 움직임은 무엇인가?
4. 경쟁사 대비 차별화 포인트는 어디에 있는가?
5. 지금 진입·확대·보류 중 무엇이 적절한가?
6. 모니터링해야 할 선행지표는 무엇인가?

[권장 구조]
[시장 한눈에 보기]
핵심 변화 3개

[시장 동향]
수요, 고객, 기술, 규제, 채널 변화

[경쟁 구도]
주요 경쟁사 / 전략 / 차별화 요소

[기회와 위협]
Opportunity / Threat

[시사점]
회사 또는 사업에 의미하는 바

[대응 전략]
단기 대응 / 차별화 / 중기 포지셔닝

[모니터링 지표]
앞으로 계속 봐야 할 지표

[작성 톤]
정보 나열보다 경쟁 구도가 어떻게 달라지는지를 중심으로 쓴다.
""",

    "규제·법률 검토": """
[역할]
법무·준법 검토 초안 수준으로 쟁점과 리스크를 구조화하되 법률 자문처럼 단정하지 않는다.

[핵심 관점]
- 어떤 법적·규제적 쟁점이 있는가
- 어떤 규정이 적용될 가능성이 있는가
- 사실관계에 따라 결론이 어떻게 달라질 수 있는가
- 보고·승인·문서화 등 필요한 절차는 무엇인가
- 리스크를 어떻게 줄일 수 있는가

[반드시 답할 질문]
1. 핵심 법률·규제 쟁점은 무엇인가?
2. 적용 가능성이 있는 법령·규정·가이드라인은 무엇인가?
3. 판단에 필요한 핵심 사실관계는 무엇인가?
4. 위반 또는 미준수 시 예상 가능한 리스크는 무엇인가?
5. 추가 확인이 필요한 부분은 무엇인가?
6. 내부적으로 어떤 절차와 문서화가 필요한가?

[권장 구조]
[검토 결론]
현재 정보 기준의 잠정 판단

[핵심 쟁점]
쟁점 1 / 2 / 3

[적용 규정]
관련 법령·규정·가이드
확실한 것과 추가 확인이 필요한 것을 구분

[사실관계별 판단]
사실 A / 사실 B에 따라 결론이 어떻게 달라지는지

[리스크]
법적 / 감독 / 제재 / 계약 / 평판

[필요 조치]
추가 법률검토 / 내부 승인 / 보고 여부 확인 / 증빙 정비 등

[유의사항]
내부 검토용 초안이며 필요한 경우 법무·준법의 공식 확인이 필요함

[작성 톤]
확정 표현을 피하고 근거와 불확실성을 명확히 한다.
""",

    "사업/투자 검토": """
[역할]
신규 사업, 시스템 투자, 프로젝트 투자안을 경영진의 투자심의 관점에서 검토한다.

[핵심 관점]
- 왜 지금 투자해야 하는가
- 투자하지 않을 경우의 기회비용은 무엇인가
- 비용 대비 효과는 충분한가
- 성공을 좌우하는 전제조건은 무엇인가
- Go / Conditional Go / Hold / No-Go 중 어떤 판단이 적절한가

[반드시 답할 질문]
1. 투자 목적은 무엇인가?
2. 예상 비용과 기대효과는 무엇인가?
3. 정량효과와 정성효과는 무엇인가?
4. 투자회수 또는 성과 확인 시점은 언제인가?
5. 주요 리스크와 실패 가능성은 무엇인가?
6. 단계적 투자 또는 파일럿이 가능한가?
7. 최종 권고는 무엇인가?

[권장 구조]
[투자 판단]
Go / Conditional Go / Hold / No-Go 방향과 근거

[투자 필요성]
문제 또는 기회

[비용·효과]
투자비 / 운영비 / 예상 절감 / 매출·생산성 / 정성효과

[사업성 검토]
시장성 / 실행가능성 / 조직역량 / 기술성

[리스크 및 전제조건]
성공 조건과 실패 요인

[추진 방식]
PoC / 단계적 투자 / 본사업 등

[성과지표]
ROI, 비용절감, 생산성, 고객지표 등

[Next Action]
투자결정 전에 필요한 검증사항

[작성 톤]
낙관적 사업계획보다 투자 판단에 필요한 냉정한 근거와 전제조건을 강조한다.
""",
}


REPORT_DEPTH_PROMPTS = {
    "핵심 중심": """
[분량·깊이]
- 임원이 1~2분 안에 읽을 수 있는 수준
- 핵심 결론과 의사결정 포인트를 최우선
- 배경 설명은 최소화
- 핵심 메시지는 최대 3개
- 실행안은 가장 중요한 3개 이내
- 중복 설명 금지
""",

    "표준": """
[분량·깊이]
- 임원이 3~5분 안에 읽을 수 있는 수준
- 결론, 근거, 리스크, 실행안을 균형 있게 포함
- 핵심 메시지 3~4개
- 주요 근거와 판단 이유를 충분히 설명
- 실행안에는 우선순위와 다음 단계를 포함
""",

    "상세": """
[분량·깊이]
- 분석 근거와 대안 비교가 필요한 상세 검토 수준
- 핵심 메시지 3~5개
- 원인, 영향, 대안, 리스크, 전제조건을 구체적으로 설명
- 가능한 경우 선택지별 장단점과 트레이드오프 포함
- 실행 로드맵, 확인사항, 성과지표까지 구체화
- 장황한 배경 설명은 피하고 정보 밀도를 높일 것
""",
}



def generate_report(
    topic,
    report_style,
    report_depth,
    research_mode="빠른 작성",
):
    chart_data_store["company"] = None
    chart_data_store["dates"] = []

    style_prompt = REPORT_STYLE_PROMPTS.get(
        report_style,
        REPORT_STYLE_PROMPTS["CEO/임원 보고"],
    )

    depth_prompt = REPORT_DEPTH_PROMPTS.get(
        report_depth,
        REPORT_DEPTH_PROMPTS["표준"],
    )

    system_prompt = (
        REPORT_SYSTEM_PROMPT
        + "\n\n[선택된 보고서 유형별 작성 지침]\n"
        + style_prompt
        + "\n\n[선택된 보고 깊이 지침]\n"
        + depth_prompt
    )

    user_prompt = f"""
선택된 보고서 유형: {report_style}
선택된 보고 깊이: {report_depth}
작성 모드: {research_mode}

다음 내용을 바탕으로 보고서를 작성해줘.

{topic}

추가 지침:
- 선택된 보고서 유형의 분석 관점과 권장 구조를 우선 적용할 것
- 사용자의 입력이 짧아도 합리적으로 구조화하되 사실을 임의로 만들지 말 것
- 사용자가 제공한 내용이 충분하면 불필요한 외부조사는 하지 말 것
- 외부자료를 사용한 경우 핵심 근거만 반영할 것
- 사용자가 적어준 사실과 외부자료의 사실을 명확히 구분할 것
"""

    messages = [
        {
            "role": "user",
            "content": user_prompt,
        }
    ]

    if research_mode == "빠른 작성":
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2600 if report_depth != "상세" else 3400,
            system=system_prompt,
            messages=messages,
        )
        return extract_text(response.content)

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=3000 if report_depth != "상세" else 3800,
        system=system_prompt,
        tools=tools,
        messages=messages,
    )

    tool_round = 0
    max_tool_rounds = 2

    while (
        response.stop_reason == "tool_use"
        and tool_round < max_tool_rounds
    ):
        tool_round += 1

        messages.append(
            {
                "role": "assistant",
                "content": response.content,
            }
        )

        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "get_disclosures":
                result = get_disclosures(
                    block.input["company_name"]
                )
            elif block.name == "search_law":
                result = search_law(
                    block.input["query"]
                )
            elif block.name == "web_search":
                result = web_search(
                    block.input["query"]
                )
            else:
                result = "알 수 없는 도구입니다."

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": tool_results,
            }
        )

        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=3000 if report_depth != "상세" else 3800,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

    if response.stop_reason == "tool_use":
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
            }
        )

        messages.append(
            {
                "role": "user",
                "content": (
                    "추가 검색은 하지 말고 지금까지 확보한 정보만으로 "
                    "선택된 보고서 유형의 구조에 맞춰 최종 보고서를 작성해줘."
                ),
            }
        )

        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=3000 if report_depth != "상세" else 3800,
            system=system_prompt,
            messages=messages,
        )

    return extract_text(response.content)


# ============================================================
# CHART
# ============================================================
def get_korean_font_name():
    preferred = [
        "Malgun Gothic",
        "AppleGothic",
        "NanumGothic",
        "Noto Sans CJK KR",
        "Noto Sans KR",
    ]

    available = {
        font.name
        for font in fm.fontManager.ttflist
    }

    for font_name in preferred:
        if font_name in available:
            return font_name

    return "DejaVu Sans"


def build_monthly_disclosure_data(dates):
    month_counts = Counter()

    for date in dates:
        if not date or len(date) < 6:
            continue

        month = date[:6]
        month_counts[month] += 1

    sorted_months = sorted(month_counts)

    labels = [
        f"{m[:4]}.{m[4:]}"
        for m in sorted_months
    ]

    values = [
        month_counts[m]
        for m in sorted_months
    ]

    return labels, values


def create_chart_image(company, dates):
    labels, values = build_monthly_disclosure_data(dates)

    if not labels:
        return None

    plt.rcParams["font.family"] = get_korean_font_name()
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(9, 3.6))

    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    bars = ax.bar(
        labels,
        values,
        width=0.58,
    )

    # matplotlib 기본 색상을 그대로 사용하되 투명도와 라운드 느낌을 최소한으로 정리
    for bar in bars:
        bar.set_alpha(0.88)

    ax.set_title(
        f"{company} 월별 공시 추이",
        loc="left",
        fontsize=14,
        fontweight="bold",
        pad=18,
    )

    ax.text(
        0,
        1.02,
        "최근 조회된 DART 공시 건수를 월별로 집계",
        transform=ax.transAxes,
        fontsize=9,
        color="#667085",
    )

    ax.grid(
        axis="y",
        linestyle="-",
        linewidth=0.7,
        alpha=0.14,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_alpha(0.18)

    ax.tick_params(
        axis="y",
        length=0,
        labelsize=9,
    )

    ax.tick_params(
        axis="x",
        labelsize=9,
        rotation=0,
    )

    ax.set_ylabel("공시 건수", fontsize=9)

    max_value = max(values) if values else 1
    ax.set_ylim(0, max_value * 1.25 + 0.5)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_value * 0.035,
            str(value),
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    plt.tight_layout()

    img_buffer = io.BytesIO()
    plt.savefig(
        img_buffer,
        format="png",
        dpi=180,
        bbox_inches="tight",
        facecolor="#FFFFFF",
    )
    plt.close(fig)

    img_buffer.seek(0)
    return img_buffer


# ============================================================
# PDF
# ============================================================
def create_pdf(report_text, chart_buffer=None):
    pdfmetrics.registerFont(
        UnicodeCIDFont("HYSMyeongJo-Medium")
    )

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_x = 46
    y = height - 48

    # Header band
    c.setFillColor(HexColor("#102B59"))
    c.roundRect(
        margin_x,
        y - 36,
        width - margin_x * 2,
        44,
        10,
        fill=1,
        stroke=0,
    )

    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("HYSMyeongJo-Medium", 14)

    first_line = (
        report_text.splitlines()[0][:40]
        if report_text.strip()
        else "AI 보고서"
    )

    c.drawString(
        margin_x + 14,
        y - 11,
        first_line,
    )

    y -= 58

    # Chart
    if chart_buffer is not None:
        chart_buffer.seek(0)
        reader = ImageReader(chart_buffer)

        chart_w = width - margin_x * 2
        chart_h = 190

        c.drawImage(
            reader,
            margin_x,
            y - chart_h,
            width=chart_w,
            height=chart_h,
            preserveAspectRatio=True,
            mask="auto",
        )

        y -= chart_h + 18

    c.setFillColor(HexColor("#27364C"))
    c.setFont("HYSMyeongJo-Medium", 10.5)

    line_height = 16
    max_chars = 48

    for paragraph in report_text.split("\n"):
        paragraph = paragraph.strip()

        if not paragraph:
            y -= 8
            continue

        is_heading = (
            paragraph.startswith("[")
            and paragraph.endswith("]")
        )

        if is_heading:
            y -= 6

            if y < 72:
                c.showPage()
                y = height - 55

            c.setFillColor(HexColor("#315EF5"))
            c.setFont("HYSMyeongJo-Medium", 11.5)
            c.drawString(margin_x, y, paragraph.strip("[]"))
            y -= 20

            c.setFillColor(HexColor("#27364C"))
            c.setFont("HYSMyeongJo-Medium", 10.5)
            continue

        wrapped = textwrap.wrap(
            paragraph,
            width=max_chars,
            break_long_words=False,
        ) or [""]

        for line in wrapped:
            if y < 55:
                c.showPage()
                y = height - 55
                c.setFillColor(HexColor("#27364C"))
                c.setFont("HYSMyeongJo-Medium", 10.5)

            c.drawString(
                margin_x,
                y,
                line,
            )

            y -= line_height

    c.save()
    buffer.seek(0)
    return buffer


# ============================================================
# INPUT
# ============================================================
st.markdown(
    """
<div class="input-card">
    <div class="section-kicker">REPORT REQUEST</div>
    <div class="section-title">어떤 보고가 필요하신가요?</div>
    <div class="section-desc">
        메모 수준으로 적어도 됩니다. AI가 핵심 메시지와 논리구조를 다시 설계합니다.
    </div>
</div>
""",
    unsafe_allow_html=True,
)

style_col, depth_col, mode_col = st.columns([1.1, .8, 1.1])

with style_col:
    report_style = st.selectbox(
        "보고서 유형",
        [
            "CEO/임원 보고",
            "전략 검토",
            "이슈·리스크 보고",
            "시장·경쟁 분석",
            "규제·법률 검토",
            "사업/투자 검토",
        ],
        index=0,
    )

    style_help = {
        "CEO/임원 보고": "결론 · 영향 · 의사결정 · Next Action 중심",
        "전략 검토": "대안 비교 · 우선순위 · 로드맵 중심",
        "이슈·리스크 보고": "사실관계 · 영향도 · 통제 · 재발방지 중심",
        "시장·경쟁 분석": "시장 변화 · 경쟁구도 · 기회 · 대응전략 중심",
        "규제·법률 검토": "쟁점 · 적용규정 · 리스크 · 필요조치 중심",
        "사업/투자 검토": "사업성 · 비용효과 · 투자판단 · 성과지표 중심",
    }[report_style]

    st.caption(style_help)

with depth_col:
    report_depth = st.selectbox(
        "보고 깊이",
        [
            "핵심 중심",
            "표준",
            "상세",
        ],
        index=1,
    )

with mode_col:
    research_mode = st.selectbox(
        "생성 모드",
        [
            "빠른 작성",
            "최신자료 포함",
        ],
        index=0,
        help=(
            "빠른 작성: 입력 내용 중심으로 한 번에 생성합니다. "
            "최신자료 포함: DART·법령·웹검색이 필요한 경우 조사합니다."
        ),
    )

if research_mode == "빠른 작성":
    st.caption("⚡ 빠른 작성 모드 · 외부 검색 없이 입력 내용을 경영진 보고 구조로 재구성합니다.")
else:
    st.caption("🔎 최신자료 포함 모드 · 필요한 경우에만 DART·법령·웹검색을 수행합니다.")

topic = st.text_area(
    "보고할 내용",
    height=170,
    placeholder=(
        "예) 신규 고객 서비스 출시를 검토하고 있어. 최근 고객 문의가 증가하고 있고 "
        "기존 처리 방식으로는 대응 시간이 길어지는 문제가 있어. "
        "서비스 도입 필요성, 기대효과, 예상 리스크, 추진 우선순위와 "
        "향후 실행계획이 드러나도록 경영진 보고용으로 정리해줘.\n\n"
        "또는 메모처럼 간단히 입력해도 됩니다.\n"
        "예) 신규 사업 검토 / 경쟁사 동향 / 비용 증가 원인 / 규제 변경 영향 / "
        "프로젝트 추진현황 / 운영 프로세스 개선"
    ),
)

generate_col, clear_col = st.columns([3, 1])

with generate_col:
    generate_clicked = st.button(
        "✨ 경영진 보고서 생성",
        type="primary",
        use_container_width=True,
    )

with clear_col:
    clear_clicked = st.button(
        "초기화",
        use_container_width=True,
    )

if clear_clicked:
    for key in [
        "report_text",
        "chart_company",
        "chart_dates",
    ]:
        st.session_state.pop(key, None)

    st.rerun()


if generate_clicked:
    if not topic.strip():
        st.warning("보고할 내용을 입력해주세요.")

    else:
        with st.spinner(
            "선택한 보고 유형에 맞춰 핵심 논리를 설계하고 있습니다..."
            if research_mode == "빠른 작성"
            else "선택한 보고 유형에 맞춰 최신 자료를 확인하고 분석하고 있습니다..."
        ):
            report_text = generate_report(
                topic,
                report_style,
                report_depth,
                research_mode,
            )

        st.session_state.report_text = report_text
        st.session_state.chart_company = chart_data_store["company"]
        st.session_state.chart_dates = chart_data_store["dates"]


# ============================================================
# OUTPUT
# ============================================================
if "report_text" in st.session_state:
    st.markdown("---")

    st.markdown(
        """
<div class="section-kicker">GENERATED REPORT</div>
<div class="section-title">생성된 보고서</div>
<div class="section-desc">
    단순 검색 결과가 아니라 경영진 의사결정 관점으로 재구성된 결과입니다.
</div>
""",
        unsafe_allow_html=True,
    )

    report_text = st.session_state.report_text

    has_chart = bool(
        st.session_state.get("chart_company")
        and st.session_state.get("chart_dates")
    )

    chart_buf = None

    if has_chart:
        chart_buf = create_chart_image(
            st.session_state.chart_company,
            st.session_state.chart_dates,
        )

        if chart_buf is not None:
            st.markdown(
                f"""
<div class="chart-wrap">
    <div class="chart-head">
        <div class="chart-title">{st.session_state.chart_company} 공시 흐름</div>
        <div class="chart-sub">
            월별 공시 건수 자체보다 공시 활동의 집중 시점을 빠르게 확인하기 위한 보조 시각화입니다.
        </div>
    </div>
</div>
""",
                unsafe_allow_html=True,
            )

            st.image(
                chart_buf,
                use_container_width=True,
            )

            chart_buf.seek(0)

    st.markdown(
        f"""
<div class="report-shell">
    <div class="report-label">EXECUTIVE REPORT</div>
    <div class="report-body">{report_text}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")

    pdf_buffer = create_pdf(
        report_text,
        chart_buf,
    )

    download_col, copy_col = st.columns([1, 1])

    with download_col:
        st.download_button(
            label="📥 PDF 다운로드",
            data=pdf_buffer,
            file_name="executive_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    with copy_col:
        if st.button(
            "📋 보고서 다시 보기",
            use_container_width=True,
        ):
            st.info("현재 화면의 보고서가 최신 생성 결과입니다.")

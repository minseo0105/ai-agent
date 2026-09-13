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
당신은 금융회사 디지털전략/경영기획 부서의 시니어 컨설턴트다.
단순 요약문이 아니라 임원·CEO가 빠르게 읽고 판단할 수 있는 한국어 보고서를 작성한다.

보고 원칙:
1. 입력 내용을 그대로 나열하지 말고 논리를 재구조화한다.
2. 첫 부분에서 반드시 핵심 결론과 경영적 의미가 드러나야 한다.
3. 사실/근거와 해석/제안을 구분한다.
4. 불확실한 정보는 확정적으로 쓰지 않는다.
5. 최신성이나 외부 근거가 필요한 경우에만 DART, 법령, 웹 검색 도구를 사용한다.
6. 검색한 내용을 모두 나열하지 말고 의사결정에 필요한 근거만 선별한다.
7. 표현은 짧고 단단하게 쓴다. 불필요한 수식어와 상투어를 줄인다.
8. '효율화', '혁신', '고도화' 같은 추상어만 쓰지 말고 무엇이 어떻게 달라지는지 설명한다.
9. 실행 제안은 우선순위와 다음 액션이 보이도록 작성한다.
10. 마크다운 기호는 사용하지 않는다.

반드시 아래 구조로 작성한다.

[보고서 제목]
한 줄 제목

[Executive Summary]
3~5문장.
결론 → 왜 중요한지 → 경영진 판단 포인트 순서.

[핵심 메시지]
① 핵심 메시지
- 근거
- 의미

② 핵심 메시지
- 근거
- 의미

③ 핵심 메시지
- 근거
- 의미

[주요 분석]
주제에 맞는 2~4개 소제목을 만들어 분석.
각 소제목은 '현황 나열'보다 '무엇이 달라지는가'를 중심으로 설명.

[리스크 및 확인사항]
사실관계, 규제, 비용, 일정, 데이터 등 반드시 확인해야 할 요소.

[제안 및 Next Action]
1. 즉시
2. 단기
3. 중기
형태로 구체적인 실행방안을 제시.

[경영진 한 문장]
CEO에게 구두로 보고할 수 있는 1문장으로 마무리.
"""


def generate_report(topic, report_style, research_mode="빠른 작성"):
    """
    빠른 작성:
      - 외부 도구를 모델에 제공하지 않음
      - 1회 생성으로 종료
      - 대부분의 내부 보고/기획 문서에 적합

    최신자료 포함:
      - DART/법령/웹검색 도구 제공
      - 필요한 경우에만 도구 사용
      - 도구 반복은 최대 2회로 제한
    """
    chart_data_store["company"] = None
    chart_data_store["dates"] = []

    user_prompt = f"""
보고서 유형: {report_style}
작성 모드: {research_mode}

다음 내용을 바탕으로 경영진 보고용 문서를 작성해줘.

{topic}

중요:
- 단순한 설명문이 아니라 보고/의사결정 문서로 재구성할 것
- 사용자가 제공한 내용이 충분하면 불필요한 외부조사는 하지 말 것
- 외부자료를 사용한 경우 핵심 근거만 반영할 것
- 사용자가 적어준 사실과 외부자료의 사실을 혼동하지 말 것
"""

    messages = [
        {
            "role": "user",
            "content": user_prompt,
        }
    ]

    # 빠른 작성은 tools 자체를 넘기지 않아 tool loop를 원천 차단
    if research_mode == "빠른 작성":
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2400,
            system=REPORT_SYSTEM_PROMPT,
            messages=messages,
        )
        return extract_text(response.content)

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2800,
        system=REPORT_SYSTEM_PROMPT,
        tools=tools,
        messages=messages,
    )

    tool_round = 0
    max_tool_rounds = 2

    while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
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
            max_tokens=2800,
            system=REPORT_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

    # 도구 반복 상한에 도달한 경우 tools 없이 최종 정리 1회
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
                "content": "지금까지 확보한 정보만으로 최종 보고서를 작성해줘. 추가 검색은 하지 마.",
            }
        )

        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2800,
            system=REPORT_SYSTEM_PROMPT,
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
        depth_instruction = {
            "핵심 중심": "분량은 짧게, Executive Summary와 핵심 메시지를 특히 압축",
            "표준": "임원이 3~5분 내 읽을 수 있는 표준 분량",
            "상세": "분석 근거와 리스크, 실행과제를 충분히 구체화",
        }[report_depth]

        final_topic = (
            topic
            + "\n\n추가 작성 기준: "
            + depth_instruction
        )

        with st.spinner(
            "빠르게 핵심 논리를 설계해 보고서를 작성하고 있습니다..." if research_mode == "빠른 작성" else "최신 자료를 필요한 범위에서 확인하고 보고서를 작성하고 있습니다..."
        ):
            report_text = generate_report(
                final_topic,
                report_style,
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

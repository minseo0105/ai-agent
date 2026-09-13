import streamlit as st
import anthropic
import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

st.set_page_config(page_title="AI Workbench", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

tools = [
    {
        "name": "get_current_time",
        "description": "현재 날짜와 시간을 알려준다.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_day_of_week",
        "description": "오늘이 무슨 요일인지 알려준다.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "calculate",
        "description": "수학 계산식을 계산한다. 예: '3 + 5 * 2'",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "계산할 수식"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "get_disclosures",
        "description": "특정 회사의 최근 공시 목록을 DART에서 조회한다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "조회할 회사 이름"}
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
                "query": {"type": "string", "description": "검색할 법령 키워드"}
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
                "query": {"type": "string", "description": "검색할 키워드나 질문"}
            },
            "required": ["query"]
        }
    }
]

DART_API_KEY = st.secrets["DART_API_KEY"]
LAW_OC = st.secrets["LAW_OC"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]

def get_current_time():
    now = datetime.now()
    return now.strftime("%Y년 %m월 %d일 %H시 %M분")

def get_day_of_week():
    now = datetime.now()
    return now.strftime("%A")

def calculate(expression):
    try:
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            return str(eval(expression))
        else:
            return "허용되지 않은 문자가 포함되어 있어요."
    except Exception as e:
        return f"계산 중 오류: {e}"

@st.cache_data
def load_corp_codes():
    with open("corp_codes.json", "r", encoding="utf-8") as f:
        return json.load(f)

def try_fetch_disclosures(corp_code):
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bgn_de": "20250101",
        "end_de": "20261231",
        "page_count": 5
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=25)
            data = response.json()
            if data["status"] == "000" and data["list"]:
                return data["list"], None
            return None, f"DART 응답: status={data.get('status')}, message={data.get('message')}"
        except Exception as e:
            last_error = f"에러 종류: {type(e).__name__}"
            time.sleep(2)
            continue
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
        names = ", ".join([name for name, codes in partial_matches[:10]])
        return f"'{company_name}'과 비슷한 회사가 여러 개 있어요: {names}\n정확한 이름으로 다시 물어봐주세요."
    else:
        return f"'{company_name}' 회사를 DART에서 찾지 못했어요."

    matched_name, codes = candidates[0]

    last_error = None
    for code in codes:
        filings, error = try_fetch_disclosures(code)
        if filings:
            results = []
            for item in filings:
                results.append(item["rcept_dt"] + " - " + item["report_nm"])
            return f"[{matched_name}]\n" + "\n".join(results)
        last_error = error

    return f"'{matched_name}' 조회에 실패했어요 (네트워크 문제일 수 있어요). 잠시 후 다시 시도해주세요. 진단: {last_error}"

def search_law(query):
    url = "http://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": LAW_OC, "target": "law", "type": "XML", "query": query}
    response = requests.get(url, params=params, timeout=30)
    root = ET.fromstring(response.content)
    results = []
    for law in root.findall("law"):
        name = law.find("법령명한글").text
        date = law.find("공포일자").text
        results.append(date + " - " + name)
    if not results:
        return f"'{query}'와 관련된 법령을 찾지 못했어요."
    return "\n".join(results)

def web_search(query):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": 5
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        data = response.json()
        results = data.get("results", [])
        if not results:
            return f"'{query}'에 대한 검색 결과를 찾지 못했어요."
        summary = []
        for item in results:
            title = item.get("title", "")
            content = item.get("content", "")[:200]
            summary.append(f"- {title}: {content}")
        return "\n".join(summary)
    except Exception as e:
        return f"검색 중 오류가 발생했어요: {str(e)}"

def extract_text(content_blocks):
    for block in content_blocks:
        if block.type == "text":
            return block.text
    return ""

def call_claude(messages):
    response = client.messages.create(model="claude-sonnet-5", max_tokens=1000, tools=tools, messages=messages)

    while response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "get_current_time":
                    result = get_current_time()
                elif block.name == "get_day_of_week":
                    result = get_day_of_week()
                elif block.name == "calculate":
                    result = calculate(block.input["expression"])
                elif block.name == "get_disclosures":
                    result = get_disclosures(block.input["company_name"])
                elif block.name == "search_law":
                    result = search_law(block.input["query"])
                elif block.name == "web_search":
                    result = web_search(block.input["query"])
                else:
                    result = "알 수 없는 도구예요."
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": tool_results})
        response = client.messages.create(model="claude-sonnet-5", max_tokens=1000, tools=tools, messages=messages)

    return extract_text(response.content)


# =========================
# UI / HOME
# =========================

# 페이지 스타일
st.markdown("""
<style>
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }

    /* 기본 폰트/타이틀 */
    h1, h2, h3 {
        letter-spacing: -0.03em;
        color: #0F172A;
    }

    .hero {
        padding: 2.2rem 2.3rem;
        border-radius: 28px;
        background:
            radial-gradient(circle at 90% 15%, rgba(59,130,246,.22), transparent 26%),
            linear-gradient(135deg, #0F172A 0%, #172554 55%, #1D4ED8 100%);
        color: white;
        margin-bottom: 1.4rem;
        box-shadow: 0 18px 50px rgba(15,23,42,.16);
    }

    .hero-kicker {
        font-size: .82rem;
        font-weight: 700;
        letter-spacing: .08em;
        text-transform: uppercase;
        opacity: .78;
        margin-bottom: .65rem;
    }

    .hero-title {
        font-size: 2.25rem;
        line-height: 1.16;
        font-weight: 800;
        letter-spacing: -0.04em;
        margin-bottom: .75rem;
    }

    .hero-desc {
        max-width: 760px;
        font-size: 1rem;
        line-height: 1.7;
        opacity: .9;
        margin-bottom: .9rem;
    }

    .hero-badges {
        display: flex;
        flex-wrap: wrap;
        gap: .5rem;
        margin-top: .7rem;
    }

    .hero-badge {
        display: inline-block;
        padding: .42rem .72rem;
        border-radius: 999px;
        background: rgba(255,255,255,.11);
        border: 1px solid rgba(255,255,255,.17);
        font-size: .8rem;
    }

    .section-title {
        margin-top: .3rem;
        margin-bottom: .15rem;
        font-size: 1.3rem;
        font-weight: 800;
        color: #0F172A;
    }

    .section-desc {
        color: #64748B;
        margin-bottom: 1rem;
        font-size: .92rem;
    }

    .service-card {
        min-height: 176px;
        padding: 1.15rem 1.1rem 1rem 1.1rem;
        border: 1px solid #E2E8F0;
        border-radius: 20px;
        background: rgba(255,255,255,.96);
        box-shadow: 0 8px 24px rgba(15,23,42,.055);
        margin-bottom: .65rem;
    }

    .service-icon {
        font-size: 1.5rem;
        margin-bottom: .65rem;
    }

    .service-title {
        font-size: 1.03rem;
        font-weight: 800;
        color: #0F172A;
        margin-bottom: .35rem;
    }

    .service-desc {
        font-size: .84rem;
        line-height: 1.58;
        color: #64748B;
        min-height: 54px;
    }

    .agent-wrap {
        margin-top: 1.2rem;
        padding: 1.3rem 1.35rem .35rem 1.35rem;
        border: 1px solid #E2E8F0;
        border-radius: 24px;
        background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
        box-shadow: 0 10px 30px rgba(15,23,42,.05);
    }

    [data-testid="stChatMessage"] {
        border-radius: 18px;
        padding: .65rem 1rem;
        margin-bottom: .55rem;
        border: 1px solid #E2E8F0;
        background: white;
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        background: #F8FAFC;
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: linear-gradient(135deg, #EFF6FF 0%, #EEF2FF 100%);
    }

    [data-testid="stChatInput"] {
        border-radius: 24px;
        border: 1px solid #CBD5E1 !important;
    }

    .stButton > button {
        border-radius: 12px !important;
        font-weight: 700 !important;
        min-height: 42px;
        transition: all .18s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 18px rgba(37,99,235,.14);
    }

    [data-testid="stSidebar"] {
        min-width: 260px;
    }

    [data-testid="stSidebar"] h2 {
        color: #2563EB;
        font-size: 1.05rem;
    }

    .side-nav {
        display: flex;
        flex-direction: column;
        gap: .45rem;
        margin-top: .55rem;
    }

    .side-nav a {
        display: flex;
        align-items: center;
        gap: .65rem;
        padding: .72rem .8rem;
        border-radius: 12px;
        text-decoration: none !important;
        color: #334155 !important;
        font-size: .9rem;
        font-weight: 700;
        border: 1px solid transparent;
        transition: all .18s ease;
    }

    .side-nav a:hover {
        background: #EFF6FF;
        color: #1D4ED8 !important;
        border-color: #DBEAFE;
        transform: translateX(2px);
    }

    .service-link {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        box-sizing: border-box;
        padding: .72rem .9rem;
        margin-bottom: .8rem;
        border-radius: 12px;
        background: #FFFFFF;
        border: 1px solid #DCE4EF;
        text-decoration: none !important;
        color: #1D4ED8 !important;
        font-size: .88rem;
        font-weight: 800;
        box-shadow: 0 4px 14px rgba(15,23,42,.035);
        transition: all .18s ease;
    }

    .service-link:hover {
        background: #EFF6FF;
        border-color: #BFDBFE;
        transform: translateY(-1px);
        box-shadow: 0 7px 18px rgba(37,99,235,.10);
    }

    .service-link span {
        font-size: 1rem;
    }

    /* 모바일 */
    @media (max-width: 768px) {
        .block-container {
            padding-left: .75rem;
            padding-right: .75rem;
        }
        .hero {
            padding: 1.5rem 1.25rem;
            border-radius: 22px;
        }
        .hero-title {
            font-size: 1.72rem;
        }
        .hero-desc {
            font-size: .92rem;
        }
        .service-card {
            min-height: auto;
        }
    }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ✦ AI WORKBENCH")
    st.caption("직접 만든 AI 서비스와 에이전트를 한 곳에서")

    st.divider()
    st.markdown("**빠른 이동**")

    st.markdown("""
    <div class="side-nav">
        <a href="/내차에서드림카까지" target="_self">🚙 <span>내차에서 드림카까지</span></a>
        <a href="/부동산모니터" target="_self">🏠 <span>부동산 모니터</span></a>
        <a href="/보고서작성기" target="_self">📄 <span>보고서 작성기</span></a>
        <a href="/차량선택기" target="_self">🚗 <span>차량 선택기</span></a>
        <a href="/GIF변환기" target="_self">🎞️ <span>GIF 변환기</span></a>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown("**AI 에이전트 기능**")
    st.caption("DART · 법령 · 웹검색 · 계산 · 시간")

    if st.button("🔄 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Hero
st.markdown("""
<div class="hero">
    <div class="hero-kicker">MY AI WORKBENCH</div>
    <div class="hero-title">아이디어를 직접 서비스로 만드는<br>나만의 AI 실험실</div>
    <div class="hero-desc">
        차량 추천과 금융견적, 부동산 모니터링, 보고서 작성, DART 공시·법령·웹 검색까지.
        지금까지 직접 만든 기능들을 하나의 화면에서 연결하고, 필요한 업무로 바로 이동할 수 있습니다.
    </div>
    <div class="hero-badges">
        <span class="hero-badge">AI Prototype</span>
        <span class="hero-badge">Vibe Coding</span>
        <span class="hero-badge">Agent + API</span>
        <span class="hero-badge">Business Automation</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 서비스 허브
st.markdown('<div class="section-title">내가 만든 서비스</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">각 기능은 독립 서비스이면서, 향후 하나의 AI 업무 플랫폼으로 확장할 수 있도록 구성합니다.</div>',
    unsafe_allow_html=True
)

cards = [
    (
        "🚙", "내차에서 드림카까지",
        "내 차 시세조회부터 다음 차량 탐색·추천까지 연결하는 리텐션형 자동차 서비스",
        "/내차에서드림카까지",
        "서비스 열기"
    ),
    (
        "🏡", "부동산 모니터",
        "청약·실거래·관심지역을 한 곳에서 확인하고 조건별 모니터링하는 부동산 정보 서비스",
        "/부동산모니터",
        "모니터 열기"
    ),
    (
        "📄", "보고서 작성기",
        "업무 내용을 경영진 관점의 구조와 메시지로 정리하는 AI 보고서 작성 도구",
        "/보고서작성기",
        "작성기 열기"
    ),
    (
        "🚗", "차량 선택기",
        "차량 조건과 선호도를 바탕으로 적합한 모델을 탐색하는 차량 선택 프로토타입",
        "/차량선택기",
        "선택기 열기"
    ),
    (
        "🎞️", "GIF 변환기",
        "서비스 시연용 이미지·화면을 움직이는 콘텐츠로 변환하기 위한 제작 도구",
        "pages/5_🎞_GIF변환기.py",
        "도구 열기"
    ),
    (
        "✦", "AI 에이전트",
        "DART 공시, 법령정보, 실시간 웹검색을 도구 호출 방식으로 연결한 개인 업무 에이전트",
        None,
        None
    )
]

row1 = st.columns(3)
row2 = st.columns(3)

for idx, card in enumerate(cards):
    icon, title, desc, path, btn = card
    col = row1[idx] if idx < 3 else row2[idx - 3]

    with col:
        st.markdown(
            f"""
            <div class="service-card">
                <div class="service-icon">{icon}</div>
                <div class="service-title">{title}</div>
                <div class="service-desc">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if path:
            st.markdown(
                f"""
                <a class="service-link" href="{path}" target="_self">
                    {btn} <span>→</span>
                </a>
                """,
                unsafe_allow_html=True
            )

st.markdown("<br>", unsafe_allow_html=True)

# AI 에이전트 영역
st.markdown('<div class="section-title">AI 에이전트</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">공시·법령·웹 검색을 필요한 순간에 호출하는 도구형 에이전트입니다.</div>',
    unsafe_allow_html=True
)

quick1, quick2, quick3, quick4 = st.columns(4)
with quick1:
    st.caption("📊 DART")
    st.markdown("기업 최근 공시 조회")
with quick2:
    st.caption("⚖️ LAW")
    st.markdown("대한민국 법령 검색")
with quick3:
    st.caption("🔍 WEB")
    st.markdown("실시간 웹 검색")
with quick4:
    st.caption("🧮 TOOL")
    st.markdown("계산·시간 확인")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if msg["role"] in ["user", "assistant"] and isinstance(msg["content"], str):
        avatar = "🧑" if msg["role"] == "user" else "✦"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])

user_input = st.chat_input("예: 삼성전자 최근 공시 알려줘 / 전자금융거래법 검색해줘")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user", avatar="🧑"):
        st.write(user_input)

    with st.spinner("에이전트가 필요한 도구를 확인하고 있어요..."):
        reply = call_claude(st.session_state.messages)

    with st.chat_message("assistant", avatar="✦"):
        st.write(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})

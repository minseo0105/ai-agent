import streamlit as st
import anthropic
import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

st.set_page_config(page_title="나만의 AI 에이전트", page_icon="✦", layout="wide")

st.markdown("""
<style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
        max-width: 800px;
    }

    h1 {
        font-size: 1.8rem !important;
        color: #1E293B;
    }

    [data-testid="stChatMessage"] {
        border-radius: 18px;
        padding: 0.6rem 1.1rem;
        margin-bottom: 0.6rem;
        border: 1px solid #E5EAF7;
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        background-color: #F4F6FB;
    }

    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: linear-gradient(135deg, #EEF2FF 0%, #E0E9FF 100%);
    }

    [data-testid="stChatInput"] {
        border-radius: 26px;
        border: 1px solid #D6E0FA !important;
    }

    .stButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
    }

    [data-testid="stSidebar"] {
        min-width: 250px;
    }

    [data-testid="stSidebar"] h2 {
        color: #2563EB;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

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

with st.sidebar:
    st.header("✦ 주요 기능")
    st.markdown("""
    <div style="line-height: 2.2;">
    🕐&nbsp;&nbsp;현재 시각 / 요일<br>
    🧮&nbsp;&nbsp;계산기<br>
    📊&nbsp;&nbsp;DART 기업 공시 조회<br>
    ⚖️&nbsp;&nbsp;법령 검색<br>
    🔍&nbsp;&nbsp;실시간 웹 검색
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.caption("예시: '삼성전자 최근 공시 알려줘'")
    st.divider()
    if st.button("🔄 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

st.title("✦ 나만의 AI 에이전트")
st.caption("DART 공시 조회 · 법령 검색 · 웹 검색 · 계산기 · 시계 기능을 갖춘 어시스턴트예요")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if msg["role"] in ["user", "assistant"] and isinstance(msg["content"], str):
        avatar = "🧑" if msg["role"] == "user" else "✦"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])

user_input = st.chat_input("무엇이든 물어보세요")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.write(user_input)

    with st.spinner("답변을 준비하고 있어요..."):
        reply = call_claude(st.session_state.messages)

    with st.chat_message("assistant", avatar="✦"):
        st.write(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
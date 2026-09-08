import streamlit as st
import anthropic
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from datetime import datetime

st.set_page_config(page_title="AI 에이전트", page_icon="🤖", layout="wide")

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
    }
]

DART_API_KEY = st.secrets["DART_API_KEY"]
LAW_OC = st.secrets["LAW_OC"]

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

@st.cache_data(ttl=86400)
def load_corp_codes():
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    params = {"crtfc_key": DART_API_KEY}
    response = requests.get(url, params=params)

    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    xml_data = zip_file.read("CORPCODE.xml")
    root = ET.fromstring(xml_data)

    corp_map = {}
    for corp in root.findall("list"):
        name = corp.find("corp_name").text
        code = corp.find("corp_code").text
        corp_map[name] = code
    return corp_map

def get_disclosures(company_name):
    corp_map = load_corp_codes()

    corp_code = None
    matched_name = company_name

    if company_name in corp_map:
        corp_code = corp_map[company_name]
    else:
        for name, code in corp_map.items():
            if company_name in name:
                corp_code = code
                matched_name = name
                break

    if corp_code is None:
        return f"'{company_name}' 회사를 DART에서 찾지 못했어요."

    url = "https://opendart.fss.or.kr/api/list.json"
    params = {"crtfc_key": DART_API_KEY, "corp_code": corp_code, "page_count": 5}
    response = requests.get(url, params=params)
    data = response.json()

    if data["status"] != "000":
        return f"'{matched_name}' 조회 실패: {data['message']}"

    results = []
    for item in data["list"]:
        results.append(item["rcept_dt"] + " - " + item["report_nm"])

    if not results:
        return f"'{matched_name}'의 최근 공시가 없어요."

    return f"[{matched_name}]\n" + "\n".join(results)

def search_law(query):
    url = "http://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": LAW_OC, "target": "law", "type": "XML", "query": query}
    response = requests.get(url, params=params)
    root = ET.fromstring(response.content)
    results = []
    for law in root.findall("law"):
        name = law.find("법령명한글").text
        date = law.find("공포일자").text
        results.append(date + " - " + name)
    if not results:
        return f"'{query}'와 관련된 법령을 찾지 못했어요."
    return "\n".join(results)

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
                else:
                    result = "알 수 없는 도구예요."
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": tool_results})
        response = client.messages.create(model="claude-sonnet-5", max_tokens=1000, tools=tools, messages=messages)

    return extract_text(response.content)

with st.sidebar:
    st.header("사용 가능한 기능")
    st.markdown("""
    - 🕐 현재 시각 / 요일
    - 🧮 계산기
    - 📊 DART 기업 공시 조회 (전체 회사)
    - ⚖️ 법령 검색
    """)
    st.divider()
    st.caption("예시: '삼성전자 최근 공시 알려줘'")
    st.divider()
    if st.button("🔄 대화 초기화"):
        st.session_state.messages = []
        st.rerun()

st.title("🤖 나만의 AI 에이전트")
st.caption("DART 공시 조회 · 법령 검색 · 계산기 · 시계 기능을 갖춘 어시스턴트예요")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if msg["role"] in ["user", "assistant"] and isinstance(msg["content"], str):
        avatar = "🧑" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.write(msg["content"])

user_input = st.chat_input("무엇이든 물어보세요")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.write(user_input)

    reply = call_claude(st.session_state.messages)

    with st.chat_message("assistant", avatar="🤖"):
        st.write(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
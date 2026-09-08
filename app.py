import streamlit as st
import anthropic
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

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

def get_disclosures(company_name):
    known_companies = {
        "삼성전자": "00126380",
        "네이버": "00266961",
        "NAVER": "00266961",
        "SK하이닉스": "00164779",
        "카카오": "00258801"
    }
    if company_name not in known_companies:
        return f"'{company_name}'의 고유번호를 아직 몰라요."
    corp_code = known_companies[company_name]
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {"crtfc_key": DART_API_KEY, "corp_code": corp_code, "page_count": 5}
    response = requests.get(url, params=params)
    data = response.json()
    if data["status"] != "000":
        return f"조회 실패: {data['message']}"
    results = []
    for item in data["list"]:
        results.append(item["rcept_dt"] + " - " + item["report_nm"])
    return "\n".join(results)

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

st.title("나만의 AI 에이전트")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if msg["role"] in ["user", "assistant"] and isinstance(msg["content"], str):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

user_input = st.chat_input("무엇이든 물어보세요")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    reply = call_claude(st.session_state.messages)

    with st.chat_message("assistant"):
        st.write(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
import streamlit as st
import anthropic
import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import io
import textwrap

st.set_page_config(page_title="보고서 작성기", page_icon="📄")

st.title("📄 AI 보고서 작성기")
st.caption("DART 공시, 법령, 웹 검색 결과를 활용해서 보고서를 작성해요")

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

DART_API_KEY = st.secrets["DART_API_KEY"]
LAW_OC = st.secrets["LAW_OC"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]

tools = [
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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=25)
            data = response.json()
            if data["status"] == "000" and data["list"]:
                return data["list"], None
            return None, f"DART 응답: {data.get('message')}"
        except Exception as e:
            last_error = f"에러: {type(e).__name__}"
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
        return f"'{company_name}'과 비슷한 회사가 여러 개 있어요: {names}"
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

    return f"'{matched_name}' 조회 실패. {last_error}"

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
    payload = {"api_key": TAVILY_API_KEY, "query": query, "max_results": 5}
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
        return f"검색 중 오류: {str(e)}"

def extract_text(content_blocks):
    for block in content_blocks:
        if block.type == "text":
            return block.text
    return ""

def generate_report(topic):
    messages = [
        {"role": "user", "content": f"다음 주제로 한국어 보고서를 작성해줘. 필요하면 DART 공시 조회, 법령 검색, 웹 검색 도구를 활용해서 최신 정보를 담아줘. 제목, 서론, 본문(소제목 포함), 결론 형식으로 정리해줘. 마크다운 기호(#, * 등)는 쓰지 말고 일반 텍스트로만 작성해줘.\n\n주제: {topic}"}
    ]

    response = client.messages.create(model="claude-sonnet-5", max_tokens=2000, tools=tools, messages=messages)

    while response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "get_disclosures":
                    result = get_disclosures(block.input["company_name"])
                elif block.name == "search_law":
                    result = search_law(block.input["query"])
                elif block.name == "web_search":
                    result = web_search(block.input["query"])
                else:
                    result = "알 수 없는 도구예요."
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": tool_results})
        response = client.messages.create(model="claude-sonnet-5", max_tokens=2000, tools=tools, messages=messages)

    return extract_text(response.content)

topic = st.text_area("보고서 주제나 내용을 입력하세요", height=100,
                      placeholder="예: 삼성전자 최근 공시 내용을 바탕으로 요약 보고서를 작성해줘")

if st.button("보고서 생성"):
    if not topic.strip():
        st.warning("주제를 입력해주세요.")
    else:
        with st.spinner("Claude가 필요한 정보를 찾고 보고서를 작성하고 있어요..."):
            report_text = generate_report(topic)
        st.session_state.report_text = report_text

if "report_text" in st.session_state:
    st.subheader("생성된 보고서")
    st.write(st.session_state.report_text)

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFont("HYSMyeongJo-Medium", 12)

    x_margin = 50
    y = height - 60
    line_height = 20
    max_chars_per_line = 45

    for paragraph in st.session_state.report_text.split("\n"):
        if not paragraph.strip():
            y -= line_height
            continue
        wrapped_lines = textwrap.wrap(paragraph, width=max_chars_per_line)
        if not wrapped_lines:
            wrapped_lines = [""]
        for line in wrapped_lines:
            if y < 60:
                c.showPage()
                c.setFont("HYSMyeongJo-Medium", 12)
                y = height - 60
            c.drawString(x_margin, y, line)
            y -= line_height

    c.save()
    buffer.seek(0)

    st.download_button(
        label="📥 PDF로 다운로드",
        data=buffer,
        file_name="report.pdf",
        mime="application/pdf"
    )
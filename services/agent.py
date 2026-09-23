"""AI 에이전트: Claude / GPT + 도구(DART · 법령 · 웹검색 · 계산 · 시간).

Streamlit(app.py)과 FastAPI(api/main.py)가 공통으로 사용한다.
run_agent()는 진행 이벤트를 순서대로 내보내는 generator이고,
call_selected_model()은 최종 답변 문자열만 필요한 곳을 위한 래퍼다.
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import lru_cache

import anthropic
import requests

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from services.config import PROJECT_ROOT, get_secret

CLAUDE_MODEL = "claude-sonnet-5"
GPT_MODEL = "gpt-5.6-terra"

PROVIDERS = {
    "claude": "Claude Sonnet 5",
    "gpt": "GPT-5.6 Terra",
}
SEARCH_MODES = ("빠르게", "심층 검색")

TOOL_LABELS = {
    "get_current_time": "현재 시간 확인",
    "get_day_of_week": "요일 확인",
    "calculate": "계산",
    "get_disclosures": "DART 공시 조회",
    "search_law": "법령 검색",
    "web_search": "웹 검색",
}


# ==========================================
# 클라이언트
# ==========================================
@lru_cache(maxsize=1)
def _claude_client():
    key = get_secret("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key) if key else None


@lru_cache(maxsize=1)
def _gpt_client():
    key = get_secret("OPENAI_API_KEY")
    return OpenAI(api_key=key) if OpenAI is not None and key else None


# ==========================================
# 도구 정의
# ==========================================
TOOLS = [
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

# OpenAI Responses API 형식으로 변환 (정의는 TOOLS 한 곳에서만 관리)
OPENAI_TOOLS = [
    {
        "type": "function",
        "name": t["name"],
        "description": t["description"],
        "parameters": {**t["input_schema"], "additionalProperties": False},
    }
    for t in TOOLS
]


# ==========================================
# 도구 구현
# ==========================================
def get_current_time():
    return datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")


def get_day_of_week():
    return datetime.now().strftime("%A")


def calculate(expression):
    try:
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            return str(eval(expression))
        return "허용되지 않은 문자가 포함되어 있어요."
    except Exception as e:
        return f"계산 중 오류: {e}"


@lru_cache(maxsize=1)
def load_corp_codes():
    with (PROJECT_ROOT / "corp_codes.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def try_fetch_disclosures(corp_code):
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": get_secret("DART_API_KEY"),
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
            return None, f"DART 응답: status={data.get('status')}, message={data.get('message')}"
        except Exception as e:
            last_error = f"에러 종류: {type(e).__name__}"
            time.sleep(2)
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
            results = [item["rcept_dt"] + " - " + item["report_nm"] for item in filings]
            return f"[{matched_name}]\n" + "\n".join(results)
        last_error = error

    return f"'{matched_name}' 조회에 실패했어요 (네트워크 문제일 수 있어요). 잠시 후 다시 시도해주세요. 진단: {last_error}"


def search_law(query):
    law_oc = get_secret("LAW_OC")
    if not law_oc:
        return "LAW_OC가 설정되지 않았습니다."

    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": law_oc, "target": "law", "type": "XML", "query": query}

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        results = []
        for law in root.findall("law"):
            name_node = law.find("법령명한글")
            date_node = law.find("공포일자")
            if name_node is not None and name_node.text:
                date = date_node.text if date_node is not None and date_node.text else ""
                results.append(f"{date} - {name_node.text}".strip(" -"))

        if not results:
            return f"'{query}'와 관련된 법령을 찾지 못했어요."
        return "\n".join(results[:10])

    except Exception as e:
        return f"법령 검색 중 오류가 발생했어요: {type(e).__name__}: {e}"


def web_search(query, search_mode="빠르게"):
    tavily_key = get_secret("TAVILY_API_KEY")
    if not tavily_key:
        return "TAVILY_API_KEY가 설정되지 않았습니다."

    # 공개 체험용 기본값과 심층 조사용 값을 분리
    if search_mode == "심층 검색":
        search_depth, max_results, content_limit, timeout = "advanced", 8, 1000, 25
    else:
        search_depth, max_results, content_limit, timeout = "basic", 5, 450, 15

    payload = {
        "api_key": tavily_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
    }

    try:
        response = requests.post("https://api.tavily.com/search", json=payload, timeout=timeout)
        response.raise_for_status()
        results = response.json().get("results", [])

        if not results:
            return f"'{query}'에 대한 검색 결과를 찾지 못했어요."

        summary = []
        for item in results:
            title = item.get("title", "")
            content = item.get("content", "")[:content_limit]
            url = item.get("url", "")
            summary.append(f"- {title}\n  {content}\n  출처: {url}")
        return "\n".join(summary)

    except Exception as e:
        return f"웹 검색 중 오류가 발생했어요: {type(e).__name__}: {e}"


def execute_tool(tool_name, tool_input, search_mode="빠르게"):
    """Claude와 GPT가 공통으로 사용하는 실제 도구 실행부."""
    if tool_name == "get_current_time":
        return get_current_time()
    if tool_name == "get_day_of_week":
        return get_day_of_week()
    if tool_name == "calculate":
        return calculate(tool_input.get("expression", ""))
    if tool_name == "get_disclosures":
        return get_disclosures(tool_input.get("company_name", ""))
    if tool_name == "search_law":
        return search_law(tool_input.get("query", ""))
    if tool_name == "web_search":
        return web_search(tool_input.get("query", ""), search_mode)
    return "알 수 없는 도구예요."


def _tool_event(name, tool_input):
    return {
        "type": "tool",
        "name": name,
        "label": TOOL_LABELS.get(name, name),
        "input": tool_input,
    }


# ==========================================
# 모델 루프 (진행 이벤트 generator)
# ==========================================
def _limits(search_mode, quick_tokens):
    deep = search_mode == "심층 검색"
    return (3000 if deep else quick_tokens), (5 if deep else 4)


def _run_claude(messages, search_mode):
    client = _claude_client()
    if client is None:
        yield {"type": "answer", "text": "Claude API를 사용할 수 없습니다. ANTHROPIC_API_KEY를 확인해 주세요."}
        return

    answer_tokens, max_tool_rounds = _limits(search_mode, 1400)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=answer_tokens, tools=TOOLS, messages=messages,
        )

        tool_round = 0
        while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
            tool_round += 1
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                yield _tool_event(block.name, block.input)
                result = execute_tool(block.name, block.input, search_mode)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
                )

            messages.append({"role": "user", "content": tool_results})
            response = client.messages.create(
                model=CLAUDE_MODEL, max_tokens=answer_tokens, tools=TOOLS, messages=messages,
            )

        text = next((b.text for b in response.content if b.type == "text"), "")
        yield {"type": "answer", "text": text or "응답을 생성하지 못했어요."}

    except Exception as e:
        yield {"type": "answer", "text": f"Claude 호출 중 오류가 발생했어요: {type(e).__name__}: {e}"}


def _run_gpt(messages, search_mode):
    if OpenAI is None:
        yield {"type": "answer", "text": "OpenAI Python 패키지가 설치되지 않았습니다. `pip install openai` 후 다시 시작해 주세요."}
        return

    client = _gpt_client()
    if client is None:
        yield {"type": "answer", "text": "GPT API를 사용할 수 없습니다. OPENAI_API_KEY를 확인해 주세요."}
        return

    answer_tokens, max_tool_rounds = _limits(search_mode, 1600)
    input_items = list(messages)

    try:
        response = client.responses.create(
            model=GPT_MODEL,
            instructions=(
                "당신은 민서의 AI Workbench 에이전트다. "
                "질문에 최신 정보, 공시, 법령, 계산이 필요하면 제공된 도구를 사용한다. "
                "검색 결과는 그대로 나열하지 말고 핵심을 이해하기 쉽게 정리한다. "
                "근거가 부족하면 추정하지 말고 그 점을 명시한다."
            ),
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            input=input_items,
            max_output_tokens=answer_tokens,
        )

        tool_round = 0
        while tool_round < max_tool_rounds:
            function_calls = [
                item for item in response.output
                if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                break

            tool_round += 1
            # 모델의 기존 출력 항목을 다음 입력에 유지
            input_items.extend(response.output)

            for call in function_calls:
                try:
                    args = json.loads(call.arguments or "{}")
                except Exception:
                    args = {}
                yield _tool_event(call.name, args)
                result = execute_tool(call.name, args, search_mode)
                input_items.append(
                    {"type": "function_call_output", "call_id": call.call_id, "output": str(result)}
                )

            response = client.responses.create(
                model=GPT_MODEL,
                instructions=(
                    "도구 결과를 바탕으로 질문에 직접 답하라. "
                    "검색 내용은 핵심만 종합하고 불확실성은 명시하라."
                ),
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                input=input_items,
                max_output_tokens=answer_tokens,
            )

        yield {"type": "answer", "text": response.output_text or "응답을 생성하지 못했어요."}

    except Exception as e:
        yield {"type": "answer", "text": f"GPT 호출 중 오류가 발생했어요: {type(e).__name__}: {e}"}


def resolve_provider(provider):
    """'claude' / 'gpt' 키 또는 화면 라벨('GPT-5.6 Terra')을 모두 받는다."""
    if provider in PROVIDERS:
        return provider
    for key, label in PROVIDERS.items():
        if provider == label:
            return key
    return "claude"


def run_agent(messages, provider="claude", search_mode="빠르게"):
    """진행 이벤트를 내보낸다: {"type": "tool", ...}* → {"type": "answer", "text": ...}"""
    # 도구 호출 과정에서 messages가 수정될 수 있으므로 텍스트 대화만 복사해서 사용
    safe_messages = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in messages
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]

    if resolve_provider(provider) == "gpt":
        yield from _run_gpt(safe_messages, search_mode)
    else:
        yield from _run_claude(safe_messages, search_mode)


def call_selected_model(messages, provider, search_mode="빠르게"):
    answer = "응답을 생성하지 못했어요."
    for event in run_agent(messages, provider, search_mode):
        if event["type"] == "answer":
            answer = event["text"]
    return answer

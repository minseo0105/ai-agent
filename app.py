import streamlit as st
import anthropic
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

import requests
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="AI Workbench", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

BASE_DIR = Path(__file__).resolve().parent


# ==========================================
# WELCOME GATE
# ==========================================
def require_login():
    if st.session_state.get("authenticated", False):
        return

    st.markdown("""
<style>
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

.block-container {
    max-width: 780px;
    padding-top: 7vh;
    padding-bottom: 4rem;
}

.welcome-shell {
    max-width: 560px;
    margin: 0 auto;
    text-align: center;
}

.welcome-logo {
    width: 76px;
    height: 76px;
    margin: 0 auto 22px auto;
    border-radius: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 31px;
    color: white;
    background: linear-gradient(135deg, #0F172A 0%, #1D4ED8 100%);
    box-shadow: 0 16px 38px rgba(37, 99, 235, .24);
}

.welcome-kicker {
    font-size: .76rem;
    font-weight: 800;
    letter-spacing: .14em;
    color: #2563EB;
    margin-bottom: .65rem;
}

.welcome-title {
    font-size: 2.35rem;
    line-height: 1.16;
    font-weight: 850;
    letter-spacing: -.05em;
    color: #0F172A;
    margin-bottom: .85rem;
}

.welcome-desc {
    color: #64748B;
    font-size: .98rem;
    line-height: 1.75;
    margin-bottom: 1.7rem;
}

.welcome-card {
    max-width: 560px;
    margin: 0 auto 1.1rem auto;
    padding: 1.3rem 1.25rem;
    border: 1px solid #E2E8F0;
    border-radius: 20px;
    background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
    box-shadow: 0 12px 32px rgba(15, 23, 42, .055);
    text-align: center;
}

.welcome-card-title {
    font-size: 1.08rem;
    font-weight: 850;
    color: #0F172A;
    margin-bottom: .35rem;
}

.welcome-card-desc {
    color: #64748B;
    font-size: .84rem;
    line-height: 1.6;
}

.welcome-tags {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: .45rem;
    margin-top: 1rem;
}

.welcome-tag {
    display: inline-block;
    padding: .4rem .68rem;
    border-radius: 999px;
    background: #EFF6FF;
    border: 1px solid #DBEAFE;
    color: #1D4ED8;
    font-size: .75rem;
    font-weight: 750;
}

.welcome-footnote {
    margin-top: 1.15rem;
    font-size: .79rem;
    line-height: 1.6;
    color: #94A3B8;
    text-align: center;
}

.stButton > button {
    border-radius: 14px !important;
    min-height: 50px;
    font-weight: 800 !important;
    font-size: .98rem !important;
}

@media (max-width: 768px) {
    .block-container {
        padding-top: 5vh;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .welcome-logo {
        width: 66px;
        height: 66px;
        border-radius: 20px;
        font-size: 27px;
        margin-bottom: 18px;
    }

    .welcome-title {
        font-size: 1.9rem;
    }

    .welcome-desc {
        font-size: .9rem;
        line-height: 1.65;
    }

    .welcome-card {
        padding: 1.1rem 1rem;
        border-radius: 18px;
    }
}
</style>
""", unsafe_allow_html=True)

    st.markdown(
        '<div class="welcome-shell">'
        '<div class="welcome-logo">✦</div>'
        '<div class="welcome-kicker">MINSEO&#39;S AI LAB</div>'
        '<div class="welcome-title">민서의 AI Lab</div>'
        '<div class="welcome-desc">'
        '아이디어가 떠오르면, 직접 만들어봅니다.<br>'
        'AI Agent · API · Vibe Coding으로 만든 작은 서비스들을<br>'
        '자유롭게 둘러보고 직접 체험해보세요.'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="welcome-card">'
        '<div class="welcome-card-title">👋 방문해주셔서 반가워요</div>'
        '<div class="welcome-card-desc">'
        '이곳은 아이디어를 실제 서비스 형태로 만들어보는 개인 AI 실험실입니다.<br>'
        '드림카 추천, 부동산 모니터, 보고서 작성기 등 직접 만든 Prototype을 공개합니다.'
        '</div>'
        '<div class="welcome-tags">'
        '<span class="welcome-tag">AI Agent</span>'
        '<span class="welcome-tag">API</span>'
        '<span class="welcome-tag">Vibe Coding</span>'
        '<span class="welcome-tag">Prototype</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )

    left, center, right = st.columns([1, 1.35, 1])

    with center:
        if st.button(
            "민서의 AI Lab 구경하기 →",
            type="primary",
            use_container_width=True,
            key="enter_ai_lab"
        ):
            st.session_state.authenticated = True
            st.toast("✨ 민서의 AI Lab에 오신 걸 환영합니다.")
            st.rerun()

    st.markdown(
        '<div class="welcome-footnote">'
        '개인적으로 기획하고 직접 구현해보는 AI Prototype 공간입니다.'
        '</div>',
        unsafe_allow_html=True
    )

    st.stop()


require_login()

ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")

claude_client = (
    anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if ANTHROPIC_API_KEY
    else None
)

gpt_client = (
    OpenAI(api_key=OPENAI_API_KEY)
    if OpenAI is not None and OPENAI_API_KEY
    else None
)

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

DART_API_KEY = st.secrets.get("DART_API_KEY", "")
LAW_OC = st.secrets.get("LAW_OC", "")
TAVILY_API_KEY = st.secrets.get("TAVILY_API_KEY", "")

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
    with (BASE_DIR / "corp_codes.json").open("r", encoding="utf-8") as f:
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
    if not LAW_OC:
        return "LAW_OC가 설정되지 않았습니다."

    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": LAW_OC, "target": "law", "type": "XML", "query": query}

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
    if not TAVILY_API_KEY:
        return "TAVILY_API_KEY가 설정되지 않았습니다."

    # 공개 체험용 기본값과 심층 조사용 값을 분리
    if search_mode == "심층 검색":
        search_depth = "advanced"
        max_results = 8
        content_limit = 1000
        timeout = 25
    else:
        search_depth = "basic"
        max_results = 5
        content_limit = 450
        timeout = 15

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
    }

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

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

def extract_text(content_blocks):
    for block in content_blocks:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


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


def call_claude(messages, search_mode="빠르게"):
    if claude_client is None:
        return (
            "Claude API를 사용할 수 없습니다. "
            ".streamlit/secrets.toml에 ANTHROPIC_API_KEY를 확인해 주세요."
        )

    try:
        answer_tokens = 3000 if search_mode == "심층 검색" else 1400
        max_tool_rounds = 5 if search_mode == "심층 검색" else 4

        response = claude_client.messages.create(
            model="claude-sonnet-5",
            max_tokens=answer_tokens,
            tools=tools,
            messages=messages,
        )

        tool_round = 0

        while response.stop_reason == "tool_use" and tool_round < max_tool_rounds:
            tool_round += 1

            messages.append(
                {"role": "assistant", "content": response.content}
            )

            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                result = execute_tool(
                    block.name,
                    block.input,
                    search_mode,
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )

            messages.append(
                {"role": "user", "content": tool_results}
            )

            response = claude_client.messages.create(
                model="claude-sonnet-5",
                max_tokens=answer_tokens,
                tools=tools,
                messages=messages,
            )

        return extract_text(response.content) or "응답을 생성하지 못했어요."

    except Exception as e:
        return f"Claude 호출 중 오류가 발생했어요: {type(e).__name__}: {e}"


OPENAI_TOOLS = [
    {
        "type": "function",
        "name": "get_current_time",
        "description": "현재 날짜와 시간을 알려준다.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_day_of_week",
        "description": "오늘이 무슨 요일인지 알려준다.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "calculate",
        "description": "수학 계산식을 계산한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "계산할 수식",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_disclosures",
        "description": "특정 회사의 최근 공시 목록을 DART에서 조회한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {
                    "type": "string",
                    "description": "조회할 회사 이름",
                }
            },
            "required": ["company_name"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_law",
        "description": "키워드로 대한민국 법령을 검색한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 법령 키워드",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "web_search",
        "description": "최신 뉴스나 인터넷 정보 검색이 필요할 때 Tavily로 검색한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 키워드 또는 질문",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


def _to_openai_input(messages):
    """Streamlit 대화기록을 OpenAI Responses API 입력형식으로 변환."""
    converted = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role not in ("user", "assistant"):
            continue

        if not isinstance(content, str):
            continue

        converted.append(
            {
                "role": role,
                "content": content,
            }
        )

    return converted


def call_gpt(messages, search_mode="빠르게"):
    if OpenAI is None:
        return (
            "OpenAI Python 패키지가 설치되지 않았습니다. "
            "터미널에서 `pip install openai`를 실행한 뒤 다시 시작해 주세요."
        )

    if gpt_client is None:
        return (
            "GPT API를 사용할 수 없습니다. "
            ".streamlit/secrets.toml에 OPENAI_API_KEY를 추가해 주세요."
        )

    try:
        input_items = _to_openai_input(messages)
        answer_tokens = 3000 if search_mode == "심층 검색" else 1600
        max_tool_rounds = 5 if search_mode == "심층 검색" else 4

        response = gpt_client.responses.create(
            model="gpt-5.6-terra",
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
                item
                for item in response.output
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

                result = execute_tool(
                    call.name,
                    args,
                    search_mode,
                )

                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": str(result),
                    }
                )

            response = gpt_client.responses.create(
            model="gpt-5.6-terra",
                instructions=(
                    "도구 결과를 바탕으로 질문에 직접 답하라. "
                    "검색 내용은 핵심만 종합하고 불확실성은 명시하라."
                ),
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                input=input_items,
                max_output_tokens=answer_tokens,
            )

        return response.output_text or "응답을 생성하지 못했어요."

    except Exception as e:
        return f"GPT 호출 중 오류가 발생했어요: {type(e).__name__}: {e}"


def call_selected_model(messages, provider, search_mode="빠르게"):
    # 도구 호출 과정에서 messages가 수정될 수 있으므로 복사본 사용
    safe_messages = [
        {
            "role": m.get("role"),
            "content": m.get("content"),
        }
        for m in messages
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
    ]

    if provider == "GPT-5.6 Terra":
        return call_gpt(safe_messages, search_mode)

    return call_claude(safe_messages, search_mode)


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


    .agent-tool-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .6rem;
        margin: .7rem 0 .95rem 0;
    }

    .agent-tool-chip {
        display: flex;
        align-items: center;
        gap: .55rem;
        min-height: 64px;
        padding: .72rem .8rem;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        background: #FFFFFF;
        box-shadow: 0 4px 14px rgba(15,23,42,.035);
    }

    .agent-tool-icon {
        width: 32px;
        height: 32px;
        min-width: 32px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #F8FAFC;
        font-size: 1rem;
    }

    .agent-tool-title {
        font-size: .78rem;
        font-weight: 800;
        color: #334155;
        line-height: 1.15;
    }

    .agent-tool-desc {
        margin-top: .13rem;
        font-size: .72rem;
        color: #94A3B8;
        line-height: 1.2;
        white-space: nowrap;
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

    .service-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .8rem;
        margin-top: .6rem;
    }

    .mini-card {
        display: flex;
        align-items: center;
        gap: .8rem;
        min-height: 92px;
        padding: 1rem;
        border: 1px solid #E2E8F0;
        border-radius: 18px;
        background: #FFFFFF;
        text-decoration: none !important;
        color: #0F172A !important;
        box-shadow: 0 7px 20px rgba(15,23,42,.045);
        transition: all .18s ease;
    }

    .mini-card:hover {
        transform: translateY(-2px);
        border-color: #BFDBFE;
        box-shadow: 0 10px 24px rgba(37,99,235,.10);
    }

    .mini-icon {
        width: 42px;
        height: 42px;
        flex: 0 0 42px;
        border-radius: 13px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #F8FAFC;
        font-size: 1.35rem;
    }

    .mini-body {
        min-width: 0;
        flex: 1;
    }

    .mini-title {
        font-size: .95rem;
        font-weight: 800;
        line-height: 1.35;
        margin-bottom: .22rem;
    }

    .mini-desc {
        font-size: .78rem;
        line-height: 1.45;
        color: #64748B;
    }

    .mini-arrow {
        color: #2563EB;
        font-weight: 800;
        font-size: 1rem;
    }

    /* 모바일 */
    @media (max-width: 768px) {
        .block-container {
            padding-top: .65rem;
            padding-left: .65rem;
            padding-right: .65rem;
            padding-bottom: 1.5rem;
        }

        .hero {
            padding: 1.05rem 1rem;
            border-radius: 18px;
            margin-bottom: .75rem;
            box-shadow: 0 10px 26px rgba(15,23,42,.11);
        }

        .hero-kicker {
            font-size: .68rem;
            margin-bottom: .35rem;
        }

        .hero-title {
            font-size: 1.35rem;
            line-height: 1.2;
            margin-bottom: .35rem;
        }

        .hero-desc {
            font-size: .78rem;
            line-height: 1.45;
            margin-bottom: .45rem;
        }

        .hero-badges {
            gap: .3rem;
            margin-top: .35rem;
        }

        .hero-badge {
            padding: .25rem .48rem;
            font-size: .64rem;
        }

        .section-title {
            font-size: 1.08rem;
            margin-top: .1rem;
            margin-bottom: .45rem;
        }

        .mobile-hide {
            display: none;
        }

        .service-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .5rem;
            margin-top: .25rem;
        }

        .mini-card {
            min-height: 76px;
            padding: .7rem;
            border-radius: 14px;
            gap: .55rem;
            box-shadow: none;
        }

        .mini-icon {
            width: 34px;
            height: 34px;
            flex-basis: 34px;
            border-radius: 10px;
            font-size: 1.05rem;
        }

        .mini-title {
            font-size: .82rem;
            margin-bottom: 0;
        }

        .mini-desc,
        .mini-arrow {
            display: none;
        }

        /* 모바일에서는 보조 도구 3개를 접어서 첫 화면 길이를 줄임 */
        .secondary-card {
            display: none;
        }


        .agent-tool-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: .35rem;
            margin: .45rem 0 .7rem 0;
        }

        .agent-tool-chip {
            min-height: 0;
            padding: .5rem .35rem;
            border-radius: 12px;
            gap: .3rem;
            flex-direction: column;
            justify-content: center;
            text-align: center;
            box-shadow: none;
        }

        .agent-tool-icon {
            width: 28px;
            height: 28px;
            min-width: 28px;
            border-radius: 9px;
            font-size: .9rem;
        }

        .agent-tool-title {
            font-size: .68rem;
            line-height: 1.05;
        }

        .agent-tool-desc {
            display: none;
        }

        [data-testid="stChatMessage"] {
            padding: .48rem .7rem;
            margin-bottom: .4rem;
            border-radius: 14px;
        }

        [data-testid="stChatInput"] {
            border-radius: 18px;
        }
    }
</style>
""", unsafe_allow_html=True)

st.markdown(r"""
<style>
/* 기본 pages 자동 메뉴 강제 숨김 */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] {
    display: none !important;
}

/* 모바일 홈 압축 */
@media (max-width: 768px) {
    .block-container {
        padding-top: .55rem !important;
        padding-left: .85rem !important;
        padding-right: .85rem !important;
        padding-bottom: 4.5rem !important;
    }

    .hero {
        padding: 20px 20px !important;
        border-radius: 20px !important;
        margin-bottom: 16px !important;
        min-height: 0 !important;
    }

    .hero-kicker {
        font-size: 9px !important;
        margin-bottom: 6px !important;
    }

    .hero-title {
        font-size: 1.65rem !important;
        line-height: 1.22 !important;
        margin: 0 !important;
    }

    .hero-desc {
        font-size: .83rem !important;
        line-height: 1.5 !important;
        margin-top: 8px !important;
    }

    .hero-badges {
        margin-top: 12px !important;
        gap: 6px !important;
    }

    .hero-badge {
        font-size: .69rem !important;
        padding: 5px 9px !important;
    }

    h3 {
        margin-top: .65rem !important;
        margin-bottom: .25rem !important;
        font-size: 1.45rem !important;
    }

    div[data-testid="stButton"] {
        margin-bottom: .2rem !important;
    }

    div[data-testid="stButton"] button {
        min-height: 2.65rem !important;
        padding: .45rem .75rem !important;
        border-radius: 13px !important;
        font-size: .92rem !important;
    }

    div[data-testid="stExpander"] {
        margin-top: .35rem !important;
    }
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ✦ AI WORKBENCH")
    st.caption("왼쪽 메뉴에서 원하는 서비스를 선택하세요.")

    st.divider()
    st.markdown("**AI 에이전트 기능**")
    st.caption("DART · 법령 · 웹검색 · 계산 · 시간")

    if st.button("🔄 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    if st.button("🚪 처음 화면으로", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# Hero
st.markdown("""
<div class="hero">
    <div class="hero-kicker">MY AI WORKBENCH</div>
    <div class="hero-title">아이디어를 서비스로 만드는<br>나만의 AI 실험실</div>
    <div class="hero-desc">
        직접 만든 AI 서비스와 업무 도구를 한 곳에서 실행합니다.
    </div>
    <div class="hero-badges">
        <span class="hero-badge">Vibe Coding</span>
        <span class="hero-badge">Agent + API</span>
        <span class="hero-badge">AI Prototype</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 서비스 허브
st.markdown("### 내가 만든 서비스")
st.caption("서비스를 선택하면 바로 이동합니다.")

if st.button(
    "🚙  내차에서 드림카까지  ·  내 차 시세 → 다음 차량 탐색·추천",
    key="open_dreamcar",
    use_container_width=True,
):
    st.switch_page("pages/1_내차에서_드림카까지.py")

if st.button(
    "🏠  부동산 모니터  ·  청약 · 실거래 · 관심지역 모니터링",
    key="open_realestate",
    use_container_width=True,
):
    st.switch_page("pages/2_부동산_모니터.py")

if st.button(
    "📄  보고서 작성기  ·  업무 내용을 경영진 보고 구조로 정리",
    key="open_report",
    use_container_width=True,
):
    st.switch_page("pages/3_보고서_작성기.py")

if st.button(
    "🔮  AI 사주 · 대운 분석  ·  사주팔자 · 오행 · 대운 흐름 분석",
    key="open_saju",
    use_container_width=True,
):
    st.switch_page("pages/saju.py")

with st.expander("기타 도구"):
    if st.button(
        "🚗 차량 선택기",
        key="open_car_selector",
        use_container_width=True,
    ):
        st.switch_page("pages/4_차량_선택기.py")

    if st.button(
        "🎞️ GIF 변환기",
        key="open_gif",
        use_container_width=True,
    ):
        st.switch_page("pages/5_GIF_변환기.py")

st.markdown("<div style='height:.1rem'></div>", unsafe_allow_html=True)

# AI 에이전트 영역
st.markdown('<div id="ai-agent"></div><div class="section-title">AI 에이전트</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-desc">공시·법령·웹 검색을 필요한 순간에 호출하는 도구형 에이전트입니다.</div>',
    unsafe_allow_html=True
)

model_col, depth_col = st.columns(2)

with model_col:
    selected_model = st.radio(
        "검색 · 답변 모델",
        ["Claude Sonnet 5", "GPT-5.6 Terra"],
        horizontal=True,
        key="agent_model_provider",
    )

with depth_col:
    search_mode = st.radio(
        "검색 깊이",
        ["빠르게", "심층 검색"],
        horizontal=True,
        key="agent_search_mode",
    )

if search_mode == "심층 검색":
    st.caption(
        f"🔎 {selected_model} · 심층 검색 — 웹 결과 최대 8건, 본문 확대, 답변 최대 3,000 tokens"
    )
else:
    st.caption(
        f"⚡ {selected_model} · 빠르게 — 웹 결과 최대 5건, 빠른 검색과 핵심 답변"
    )

tool_grid_html = (
    '<div class="agent-tool-grid">'
    '<div class="agent-tool-chip">'
    '<div class="agent-tool-icon">📊</div>'
    '<div class="agent-tool-text">'
    '<div class="agent-tool-title">DART</div>'
    '<div class="agent-tool-desc">기업 공시</div>'
    '</div></div>'
    '<div class="agent-tool-chip">'
    '<div class="agent-tool-icon">⚖️</div>'
    '<div class="agent-tool-text">'
    '<div class="agent-tool-title">LAW</div>'
    '<div class="agent-tool-desc">법령 검색</div>'
    '</div></div>'
    '<div class="agent-tool-chip">'
    '<div class="agent-tool-icon">🔍</div>'
    '<div class="agent-tool-text">'
    '<div class="agent-tool-title">WEB</div>'
    '<div class="agent-tool-desc">실시간 검색</div>'
    '</div></div>'
    '<div class="agent-tool-chip">'
    '<div class="agent-tool-icon">🧮</div>'
    '<div class="agent-tool-text">'
    '<div class="agent-tool-title">TOOL</div>'
    '<div class="agent-tool-desc">계산 · 시간</div>'
    '</div></div>'
    '</div>'
)

st.markdown(tool_grid_html, unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if msg["role"] in ["user", "assistant"] and isinstance(msg["content"], str):
        avatar = "🧑" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant" and msg.get("model"):
                mode_label = msg.get("search_mode", "빠르게")
                st.caption(f"답변 모델 · {msg['model']}  |  검색 · {mode_label}")
            st.write(msg["content"])

user_input = st.chat_input("예: 삼성전자 최근 공시 알려줘 / 전자금융거래법 검색해줘")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user", avatar="🧑"):
        st.write(user_input)

    with st.spinner(
        f"{selected_model} · {search_mode} 모드로 확인하고 있어요..."
    ):
        reply = call_selected_model(
            st.session_state.messages,
            selected_model,
            search_mode,
        )

    with st.chat_message("assistant", avatar="🤖"):
        st.caption(f"답변 모델 · {selected_model}  |  검색 · {search_mode}")
        st.write(reply)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": reply,
            "model": selected_model,
            "search_mode": search_mode,
        }
    )

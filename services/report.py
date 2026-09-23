"""경영진 보고서 작성기 (Streamlit 무관).

pages/3_보고서_작성기.py의 프롬프트·생성·차트·PDF 로직을 옮긴 것.
run_report()는 진행 이벤트를 내보내는 generator:
  {"type": "tool", ...}* → {"type": "answer", "text", "chart"}
"""

import io
import textwrap
from collections import Counter

import anthropic
import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib.colors import HexColor  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from services.agent import TOOL_LABELS, _claude_client, load_corp_codes, search_law, web_search  # noqa: E402
from services.config import get_secret  # noqa: E402

MODEL = "claude-sonnet-5"
# Sonnet 5는 기본으로 생각(thinking)을 먼저 하고 그 토큰도 max_tokens에 포함된다.
# 한도가 낮으면 본문이 잘리므로 넉넉히 둔다(실제 사용한 만큼만 과금).
MAX_TOKENS = 16000
REPORT_STYLES = ["CEO/임원 보고", "전략 검토", "이슈·리스크 보고", "시장·경쟁 분석", "규제·법률 검토", "사업/투자 검토"]
REPORT_DEPTHS = ["핵심 중심", "표준", "상세"]
RESEARCH_MODES = ["빠른 작성", "최신자료 포함"]
STYLE_HELP = {
    "CEO/임원 보고": "결론 · 영향 · 의사결정 · Next Action 중심",
    "전략 검토": "대안 비교 · 우선순위 · 로드맵 중심",
    "이슈·리스크 보고": "사실관계 · 영향도 · 통제 · 재발방지 중심",
    "시장·경쟁 분석": "시장 변화 · 경쟁구도 · 기회 · 대응전략 중심",
    "규제·법률 검토": "쟁점 · 적용규정 · 리스크 · 필요조치 중심",
    "사업/투자 검토": "사업성 · 비용효과 · 투자판단 · 성과지표 중심",
}
DEPTH_HELP = {
    "핵심 중심": "핵심 결론 · 판단 포인트 중심",
    "표준": "원인 · 영향 · 대응방향까지 분석",
    "상세": "구조 진단 · 대안 비교 · 권고 · 로드맵 · KPI까지",
}

TOOLS = [
    {
        "name": "get_disclosures",
        "description": "특정 회사의 최근 공시 목록을 DART에서 조회한다.",
        "input_schema": {"type": "object", "properties": {"company_name": {"type": "string", "description": "조회할 회사 이름"}},
                         "required": ["company_name"]},
    },
    {
        "name": "search_law",
        "description": "키워드로 대한민국 법령을 검색한다.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "검색할 법령 키워드"}},
                         "required": ["query"]},
    },
    {
        "name": "web_search",
        "description": "실시간 뉴스, 최신 정보, 일반적인 인터넷 검색이 필요할 때 사용한다.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "검색할 키워드나 질문"}},
                         "required": ["query"]},
    },
]


# ============================================================
# PROMPTS (pages/3_보고서_작성기.py에서 이동)
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
- 보고서의 가치는 정보량이 아니라 판단에 도움이 되는 분석 깊이로 평가한다.
- 단순 사실 나열, 검색결과 요약, 경쟁사 사례 열거만으로 보고서를 끝내지 않는다.
- 주제에 따라 필요한 분석 프레임을 스스로 선택한다. 예: As-Is/To-Be, 원인-영향, 대안비교, 비용-효과, 고객여정, 가치사슬, 리스크 시나리오, 이해관계자, 실행 로드맵.
- 사용자가 특정 프레임을 요구하지 않아도 의사결정에 필요한 분석 축을 스스로 보완한다.
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
[분석 수준: 핵심 중심]
목표는 '짧은 요약'이 아니라 핵심 판단을 빠르게 도출하는 것이다.
- 핵심 결론 1개와 그 결론을 지지하는 근거를 선별한다.
- 중요한 변화/문제/기회를 최대 3개로 압축한다.
- 경영진이 결정하거나 확인해야 할 사항을 명확히 제시한다.
- 실행안은 우선순위가 높은 항목 중심으로 제시한다.
- 입력에 없는 사실이나 수치를 만들어내지 않는다.
""",

    "표준": """
[분석 수준: 표준]
목표는 현황 설명을 넘어 '왜 그런가, 그래서 무엇을 해야 하는가'까지 분석하는 것이다.
- 현황 → 원인/변화요인 → 영향 → 대응방향의 인과관계를 만든다.
- 핵심 주장마다 근거와 경영적 의미를 붙인다.
- 가능한 경우 대안 또는 선택지를 비교한다.
- 장점뿐 아니라 한계와 리스크를 함께 검토한다.
- 권고안에는 선택 이유와 선결조건을 포함한다.
- 실행과제는 우선순위와 다음 단계가 드러나도록 한다.
- 입력에 없는 사실이나 수치를 만들어내지 않는다.
""",

    "상세": """
[분석 수준: 상세]
목표는 글을 길게 만드는 것이 아니라, 경영진이 실제 판단에 사용할 수 있는 '검토의 깊이'를 만드는 것이다.

반드시 다음 사고 단계를 수행한다.
1. 핵심 질문 정의
   - 사용자가 진짜 판단해야 하는 문제가 무엇인지 1~3개의 핵심 질문으로 재정의한다.
2. As-Is 진단
   - 현재 상태, 구조, 이해관계자, 프로세스 또는 시장 상황을 분석한다.
   - 단순 현상이 아니라 구조적 원인과 제약조건을 찾는다.
3. 원인·변화요인 분석
   - 왜 현재 문제가 발생했는지 또는 왜 변화가 필요한지 설명한다.
   - 내부 요인과 외부 요인을 가능한 범위에서 구분한다.
4. 영향 분석
   - 고객/사업/재무/운영/조직/데이터·기술/규제·리스크 중 주제와 관련 있는 축을 선택해 영향을 분석한다.
   - 모든 축을 억지로 채우지 말고 중요한 축만 깊게 다룬다.
5. 대안 설계
   - 의사결정 주제라면 최소 3개의 현실적인 대안을 만든다.
   - '현행 유지'도 의미 있는 대안이면 포함한다.
6. 대안 비교
   - 효과, 비용·투입, 실행난이도, 소요기간, 리스크, 확장성 등 주제에 맞는 기준을 스스로 선정해 비교한다.
   - 각 대안의 장점과 단점, 트레이드오프를 명확히 한다.
7. 권고안
   - 가장 적절한 방향을 제시하고 '왜 이 대안인가'를 근거와 함께 설명한다.
   - 전제조건과 반대 논리도 함께 검토한다.
8. 실행 설계
   - 즉시 / 단기 / 중기 또는 단계별 로드맵으로 구체화한다.
   - 선행조건, 의사결정 게이트, 필요한 협업 또는 검증사항을 제시한다.
9. 성과 측정
   - 성공 여부를 판단할 KPI 또는 검증지표를 제안한다.
   - 수치 목표를 임의로 만들지 말고, 수치가 없으면 '측정해야 할 지표'로 제시한다.
10. 추가 확인 데이터
   - 더 정확한 판단을 위해 필요한 데이터가 없으면 추정하지 말고 별도 항목으로 제시한다.

상세 분석 품질 규칙:
- 검색 결과와 사실을 길게 나열하는 것을 '상세'로 간주하지 않는다.
- 외부 사례는 사례 소개로 끝내지 말고 우리 판단에 주는 의미를 해석한다.
- 주장마다 가능한 범위에서 '근거 → 해석 → 시사점'을 연결한다.
- 찬성 논리만 쓰지 말고 반대 논리와 실패 가능성도 검토한다.
- 선택지가 있는 주제는 반드시 비교 구조를 만든다.
- 정보가 부족한 부분은 '확인 필요'라고 명시하고 임의로 채우지 않는다.
- 최종 보고서는 분석 결과가 의사결정과 실행으로 이어지도록 작성한다.
""",
}


# ============================================================
# DART (차트용 공시 날짜를 요청 단위로 수집)
# ============================================================

def _fetch_disclosures(corp_code):
    import time

    import requests

    params = {"crtfc_key": get_secret("DART_API_KEY"), "corp_code": corp_code,
              "bgn_de": "20250101", "end_de": "20261231", "page_count": 20}
    last_error = None
    for _ in range(2):
        try:
            data = requests.get("https://opendart.fss.or.kr/api/list.json", params=params, timeout=12,
                                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}).json()
            if data.get("status") == "000" and data.get("list"):
                return data["list"], None
            return None, f"DART 응답: {data.get('message')}"
        except Exception as e:
            last_error = f"에러: {type(e).__name__}"
            time.sleep(0.8)
    return None, last_error


def get_disclosures(company_name, chart):
    """공시 목록 텍스트를 반환하고, 차트용 회사명·공시일을 chart(dict)에 담는다."""
    try:
        corp_map = load_corp_codes()
    except Exception as e:
        return f"회사 목록 로딩 실패: {e}"

    norm = lambda t: t.replace(" ", "").lower()
    q = norm(company_name)
    exact = [(n, c) for n, c in corp_map.items() if norm(n) == q]
    partial = [(n, c) for n, c in corp_map.items() if norm(n) != q and (q in norm(n) or norm(n) in q)]
    if exact:
        candidates = exact
    elif len(partial) == 1:
        candidates = partial
    elif partial:
        return f"'{company_name}'과 비슷한 회사가 여러 개 있어요: {', '.join(n for n, _ in partial[:10])}"
    else:
        return f"'{company_name}' 회사를 DART에서 찾지 못했어요."

    matched, codes = candidates[0]
    last_error = None
    for code in codes:
        filings, error = _fetch_disclosures(code)
        if filings:
            chart["company"] = matched
            chart["dates"] = [f.get("rcept_dt", "") for f in filings if f.get("rcept_dt")]
            return f"[{matched}]\n" + "\n".join(f"{f.get('rcept_dt', '')} - {f.get('report_nm', '')}" for f in filings)
        last_error = error
    return f"'{matched}' 조회 실패. {last_error}"


def _run_tool(name, tool_input, chart):
    if name == "get_disclosures":
        return get_disclosures(tool_input.get("company_name", ""), chart)
    if name == "search_law":
        return search_law(tool_input.get("query", ""))
    if name == "web_search":
        return web_search(tool_input.get("query", ""))
    return "알 수 없는 도구입니다."


def _text(content):
    return "\n".join(b.text for b in content if b.type == "text").strip()


# ============================================================
# GENERATION
# ============================================================

def run_report(topic, report_style="CEO/임원 보고", report_depth="표준", research_mode="빠른 작성"):
    client = _claude_client()
    if client is None:
        yield {"type": "error", "message": "ANTHROPIC_API_KEY가 설정되지 않았습니다."}
        return

    chart = {"company": None, "dates": []}
    style_prompt = REPORT_STYLE_PROMPTS.get(report_style, REPORT_STYLE_PROMPTS["CEO/임원 보고"])
    depth_prompt = REPORT_DEPTH_PROMPTS.get(report_depth, REPORT_DEPTH_PROMPTS["표준"])
    system_prompt = (REPORT_SYSTEM_PROMPT + "\n\n[선택된 보고서 유형별 작성 지침]\n" + style_prompt
                     + "\n\n[선택된 보고 깊이 지침]\n" + depth_prompt)
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
- '상세' 선택 시 분량을 늘리는 방식이 아니라 분석 단계와 판단 근거를 확장할 것
- 자료가 부족하면 억지 결론을 만들지 말고, 현재 정보로 가능한 잠정 판단과 추가 확인 데이터를 구분할 것
- 최종 결과는 검색 요약문이 아니라 실제 회의·보고에서 의사결정에 사용할 수 있는 문서가 되어야 함
"""
    messages = [{"role": "user", "content": user_prompt}]
    deep = report_depth == "상세"

    try:
        if research_mode == "빠른 작성":
            response = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS,
                                              system=system_prompt, messages=messages)
        else:
            max_tokens = MAX_TOKENS
            response = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system_prompt,
                                              tools=TOOLS, messages=messages)
            rounds = 0
            while response.stop_reason == "tool_use" and rounds < 2:
                rounds += 1
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    yield {"type": "tool", "name": block.name, "label": TOOL_LABELS.get(block.name, block.name),
                           "input": block.input}
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": _run_tool(block.name, block.input, chart)})
                messages.append({"role": "user", "content": results})
                response = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system_prompt,
                                                  tools=TOOLS, messages=messages)
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": "추가 검색은 하지 말고 지금까지 확보한 정보만으로 "
                                                            "선택된 보고서 유형의 구조에 맞춰 최종 보고서를 작성해줘."})
                response = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system_prompt,
                                                  messages=messages)
    except anthropic.APIStatusError as e:
        yield {"type": "error", "message": f"보고서 생성 실패 ({e.status_code}): {e.message}"}
        return
    except anthropic.APIConnectionError:
        yield {"type": "error", "message": "Claude API에 연결하지 못했어요. 잠시 후 다시 시도해 주세요."}
        return

    text = _text(response.content) or "보고서를 생성하지 못했어요."
    if response.stop_reason == "max_tokens":
        text += "\n\n※ 응답 길이 한도에 도달해 보고서 끝부분이 잘렸을 수 있습니다. 보고 깊이를 낮추거나 다시 생성해 주세요."
    labels, values = build_monthly_disclosure_data(chart["dates"])
    yield {"type": "answer", "text": text,
           "chart": {"company": chart["company"], "labels": labels, "values": values, "dates": chart["dates"]}
           if labels else None}


def is_heading_line(line):
    """섹션 제목 판별: '[섹션]' 또는 짧고 문장으로 끝나지 않는 줄. web ReportBuilder.headingLevel과 같은 규칙."""
    import re
    t = line.strip()
    if t.startswith("[") and t.endswith("]"):
        return True
    if len(t) > 26 or re.search(r"[.:!?。]$|다$|요$", t) or re.match(r"^[-•·*]|^\d+[.)]\s", t):
        return False
    return bool(t)


def report_pdf(text, chart=None):
    """보고서 텍스트(+선택: 공시 차트)를 PDF bytes로."""
    chart_buf = None
    if chart and chart.get("company") and chart.get("dates"):
        chart_buf = create_chart_image(chart["company"], chart["dates"])
    return create_pdf(text, chart_buf).getvalue()


# ============================================================
# CHART / PDF (pages/3_보고서_작성기.py에서 이동)
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

        is_heading = is_heading_line(paragraph)

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

"""뉴스 속 숨은 종목: 오늘의 뉴스 → AI 해석(영향 경로) → 영향을 받을 수 있는 회사 → 실제 등락(사후 확인, 인과를 단정하지 않는다).

핵심 목적: 일상 뉴스를 보다가 → 그 뉴스와 연결된 상장사를 AI가 찾아낸다. 뉴스 자체는 종목 이야기가 아니어도 되고,
일상 뉴스에서 '이 회사가 연결돼 있었네' 하고 발견하는 것이 차별점이다.

- 토픽 = 기준 뉴스 창에서 일상 뉴스면의 사건·변화(보안 사고·제품 결함·리콜·유가·환율·정책·규제·국제 정세·날씨·질병·
  생활·소비 트렌드·기술 발표). 실적·공시·특징주·관련주·시황 같은 증권 기사(STOCK_RULES)는 이슈 후보에서 뺀다.
  거시 이슈(금리·환율·지수 전반)는 최대 1개('시장 전체 영향 이슈'), 해석 첫 줄에 시장 예상과 같았는지, 연결 회사는 연관도 '약'
  (기사에 그 회사가 직접 나올 때만 AI가 준 연관도). 유가·환율처럼 오르내리는 이슈는 오늘 실제 방향을 먼저 판단해 그 기준으로 해석한다.
- 시점: 이슈의 첫 보도가 15:20 이후(또는 휴장일)면 다음 거래일 등락과 비교하고, 그 거래일 값이 없으면 '반응 대기 중'.
  첫 보도 이후 누적 시장 대비(최대 5거래일)는 공공데이터 일별 시세 + 지금 값으로 계산해 회사 상세·표에만 보인다.
  수집기(stockon-collector)가 기사를 모으고 → Haiku 5.5가 여러 언론이 다룬 이슈를 3~5개(서로 다른 분야) 묶어
  대표 기사 1개 + 관련 기사(토픽당 최대 6개)를 고르고 → 토픽마다 Sonnet 5.5가 'AI 해석' 2~3줄과
  영향 경로(수요 증가·원가 상승·규제·경쟁 변화 등) × 경로당 회사 2곳(긍정 가능/부정 가능·연관도·왜 관련 있나)을 만든다.
  등락 순위는 토픽 선정에 쓰지 않는다. 회사마다 '실제 등락'(등락률)을 붙이는 데에만 쓴다.
  코스피·코스닥 지수 등락 자체(지수 급등·급락 시황)는 이슈로 고르지 않고, 화면 맨 위 '오늘 시장 분위기' 띠로 보여 준다.
- 시장 대비 = 회사 등락률 − 그 회사 시장 지수(코스피/코스닥) 등락률(같은 기준 시각 값). 지수가 크게 움직인 날 모든 회사가
  함께 오르내려 해석이 틀린 것처럼 보이지 않게, '실제 등락 큼'(±3%p)·해석과 반대(±3%p)는 시장 대비로 본다.
  지수 값이 없으면(예전에 만든 이슈·예시) 단순 등락률로 본다(실제 등락 큼 ±5%, 반대 ±3%).
- 회사는 뉴스의 직접 당사자이거나 구체적인 사업 연결(제품·고객·공급·규제)이 있을 때만. 같은 업종일 뿐이면 연관도 '약'.
- 해석 방향과 반대로 시장 대비 ±3%p 이상 움직인 회사는 이슈를 만들 때 한 번만, 그 회사의 같은 날 뉴스(NAVER)로 Haiku가
  '다른 이유로 움직였을 수 있어요: …' 한 줄 + 기사 링크를 붙여 저장한다. 못 찾으면 '이 뉴스 외 다른 요인일 수 있어요'.
- 하루 AI 비용 상한(budget.py, STOCKON_AI_DAILY_USD)을 넘으면 새로 만들지 않고 저장된 이슈·섹터를 그대로 둔다.
- 기준은 뒤로 가지 않는다: 키움 종가 기준(예: 금요일)으로 만든 이슈가 있으면, 주말·공휴일에 공공데이터 기준일(목요일)로
  다시 만들지 않는다.
- 기준(basis): 공공데이터는 D일 시세가 D+1 13시 이후 올라오므로 새 기준일 시세가 들어왔을 때 만들고, 뉴스도 그 기준일 창
  [직전 거래일 15:30, D+1 08:00)만 쓴다(화면 'n/n 장 기준'). 키움 모드로 오늘 시세가 들어오는 날은 10시 이후·마감 뒤
  한 번씩 오늘 뉴스로 다시 만든다('n/n 장중 HH:MM 기준'). 키움 장중에는 수집기가 30분마다 회사 등락률과 지수 등락률을
  같은 때 갱신한다(AI 재호출 없음).
- 섹터(금융·반도체·AI·…): 같은 기준 창의 섹터 뉴스로 같은 구조를 하루 한 번(장 마감 뒤 기준: 키움 종가·공공 기준일) 만든다.
  키움 장중 재생성은 오늘의 이슈만(비용). 직접 입력한 단어는 그 단어의 최근 뉴스로 만든다.
- AI가 낸 회사는 공공데이터 전 종목 목록(stocks.json)의 종목명과 맞춰 보고, 없는 회사는 지운다(종목코드는 목록에서 붙인다).
- 새 단어: AI LAB 앱(ailab)에서 같은 엔진으로 만든다. 동시 호출 상한·대기열·1인 횟수·하루 상한을 둔다. 같은 단어는 재사용.
- AI가 실패하면 저장된 예시(data/stockon/lifemap_examples.json)로 대체한다. 화면이 비지 않게.
- 문장에는 예측·권유('오를 것'·'매수'·'추천'·'수혜'·'기회'·'덜 올랐다')를 쓰지 않는다. '숨은'은 탭 이름에만 쓴다.

출처와 이슈 고르기(2026-10-30 개편):
- '오늘 무슨 일이 있었나'는 종합 언론사·방송사 일상 뉴스면 RSS(rss.py, data/stockon/news_sources.json)에서 찾는다.
  Haiku가 같은 사건 기사를 묶고 '산업·기업과 이어지는 이슈'만 고른다(사건 종류 kind가 같으면 하나만).
  '얼마나 많이 다뤘나'(최근 24시간 기사 수·언론사 수)·관련 기사·첫 보도는 NAVER 뉴스 검색으로 센다.
  대표 기사는 종합지·방송사(RSS) 기사, 경제지·전문지 기사는 관련 기사에만. 첫 보도가 24시간 안인 이슈를 먼저,
  더 오래된 이슈는 최대 1개('계속되는 이슈'). RSS가 너무 적으면(예전 기준일) 예전 방식(NAVER 검색어)으로 만든다.
- 이름: 분야 이름(label)은 업종명이 아니라 일상 말('개인정보 유출'·'전기차 리콜'). 카드 제목·요약에 증권 표현을 쓰지 않는다.
- 회사: 기사에 이름이 나온 상장사(또는 상장 모회사)는 '뉴스 당사자'(최대 2), 나머지는 기사에 없는 근거 있는 연결
  (공급사·고객사·경쟁사·대체재·사고 대응 업체 등, 1차/2차). 이슈당 최대 6곳. 회사마다 KRX 업종(관련 업종 칩용, 모르면 비움),
  근거 기사, 한 줄 회사 소개(회사별로 lifemap_intros.json에 저장해 재사용).
- 관련 업종 칩: 회사 업종을 '오늘 시장' 탭과 같은 키움 업종 등락(market_extra.json)으로 시장 대비 %p. 화면은 pulse()로 15초마다 숫자만 갱신.
"""

import json
import logging
import re
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from services.stockon import ai, budget, news, public_data, rss, store
from services.stockon.public_data import KST
from services.stockon.safety import banned_hits
from services.stockon.service import news_window, price_note

log = logging.getLogger("stockon.lifemap")

TOPIC_MODEL = "claude-haiku-5-5"
CHAIN_MODEL = "claude-sonnet-5-5"
SECTORS = ["금융", "반도체", "AI", "자동차", "보험", "보안", "2차전지", "바이오", "방산", "조선"]
EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "data" / "stockon" / "lifemap_examples.json"

MAX_PATHS = 4              # 영향 경로(마인드맵 1단계) 최대 수
PER_PATH = 2               # 경로당 회사 수
RELEVANCE = ("강", "중", "약")
DIRECTIONS = {"긍정": "pos", "부정": "neg", "불확실": "unk"}  # unk = 방향 불확실('영향 가능'만 표시)
MOVES = ("상승", "하락", "보합", "불확실")  # 유가·환율·금리처럼 오르내리는 이슈의 오늘 실제 방향
EXPECTED = ("예상대로", "예상과 다름", "판단 어려움")  # 거시 이슈가 시장 예상과 같았는지
EXPECTED_LINE = {"예상대로": "시장 예상대로였어요 → 주가 영향이 작을 수 있어요.",
                 "예상과 다름": "시장 예상과 달랐어요 → 시장 전체가 크게 반응할 수 있어요.",
                 "판단 어려움": "시장 예상과 같았는지는 기사로 판단하기 어려워요."}
NEWS_FIELDS = ("보안 사고", "제품 결함·리콜", "유가·원자재", "환율·금리", "정책·규제", "국제 정세", "날씨·질병",
               "생활·소비", "기술 발표", "산업 사고", "산업 동향")
LINKS = ("직접 당사자", "사업 연결", "같은 업종")  # 회사가 뉴스와 이어지는 방식(같은 업종만이면 연관도 '약')
MIN_COMPANIES = 3          # 검증 뒤 회사가 이보다 적거나 경로가 하나뿐이면 한 번 다시 그린다
TOPICS_MIN, TOPICS_MAX = 3, 5
RESERVE_MAX = 2           # 관리자가 숨기면 채울 다음 후보(이슈 + AI 해석까지 미리 만든다)
ARTICLES_MAX = 6           # 토픽당 기사 수(대표 기사 포함)
MOVED_PP = 3.0             # 시장 대비(%p)가 이 이상(절댓값)이면 '실제 등락 큼' 강조
MOVED_PCT = 5.0            # 지수 값이 없을 때(예전 이슈·예시)만: 단순 등락률 기준
OPPOSITE_PCT = 3.0         # AI 해석 방향과 반대로 시장 대비 이 이상(%p, 지수 없으면 단순 %) 움직인 회사는 같은 날 뉴스로 다른 이유 한 줄
INDEX_MARKET = {"코스피": "KOSPI", "코스닥": "KOSDAQ"}  # 지수 이름 → 종목 목록의 시장
MOOD_SHARE = 0.6           # 오른(내린) 종목이 이 비율 이상이면 '대부분 종목이 올랐어요(내렸어요)'
# 지수 시황 기사(코스피 급등·코스닥 마감 등)는 이슈 카드가 아니라 '오늘 시장 분위기' 띠로
INDEX_NEWS = re.compile(r"코스피|코스닥|주가\s*지수|증시\s*(급|폭|마감|상승|하락|반등|랠리)")
OPPOSITE_MAX = 6           # 이슈 하나에서 다른 이유를 찾는 회사 수 상한(비용)
OTHER_MODEL = TOPIC_MODEL  # 다른 이유 한 줄(Haiku)
OTHER_FALLBACK = "이 뉴스 외 다른 요인일 수 있어요"
TOPIC_TRIES = 3            # 같은 기준으로 최대 시도(실패 시 30분 간격)
KIWOOM_TOPIC_FROM = (10, 0)  # 키움 오늘 뉴스로 토픽을 만드는 가장 이른 시각
KIWOOM_FRESH_SEC = 15 * 60
LIVE_RATES_SEC = 30 * 60   # 키움 장중 실제 등락률 갱신 간격(수집기)
LIVE_RATES_STALE = 45 * 60  # 이보다 오래된 장중 등락률은 쓰지 않는다
WORD_NEWS_DAYS = 3         # 직접 입력 단어는 최근 3일 뉴스로 해석
SIMILAR_PP = 2.0           # 시장 대비 ±2%p 이내 = '시장과 비슷해요'(잡음 구간, 반대 움직임으로 보지 않는다)
CLOSE_CUTOFF = (15, 20)    # 첫 보도가 이 시각 이후면 다음 거래일 반응과 비교(장 마감 동시호가부터는 반영이 어렵다)
CUM_DAYS = 5               # 첫 보도 이후 누적은 최대 5거래일
FIRST_LOOKBACK_DAYS = 7    # 첫 보도를 찾는 범위(기준 뉴스 창 끝에서 거슬러)
# 한국거래소 휴장일(주말 제외). 지난 날은 지수 추이의 실제 거래일로도 맞춘다. 매년 연말에 다음 해를 더한다.
KRX_HOLIDAYS = {"20261225", "20261231", "20270101", "20270208", "20270209", "20270301"}

# RSS 이슈 발견(오늘 무슨 일이 있었나) → NAVER로 기사 수·언론사 수(얼마나 많이 다뤘나)
FRESH_HOURS = 24           # 첫 보도가 이 안이면 오늘 이슈, 더 오래되면 '계속되는 이슈'(최대 ONGOING_MAX개)
ONGOING_MAX = 1
RSS_MIN = 20               # 기준 창 안 RSS 기사가 이보다 적으면(예전 기준일 등) 예전 방식(NAVER 검색어)으로
RSS_PER_FEED = 30          # 피드마다 최신 기사 수(Haiku 입력 토큰)
CANDIDATES_MAX = 9         # Haiku가 고르는 이슈 후보 수
COVER_MIN_PRESS = 2        # 최근 24시간 이 수 이상의 언론사가 다뤄야 이슈
COMPANIES_MAX = 6          # 이슈당 회사(뉴스 당사자 포함)
PARTY_MAX = 2              # 뉴스 당사자
# 사건 종류: 분야 이름이 달라도 종류가 같으면 같은 이슈로 본다(예: 거래소 유출·은행 해킹 = 해킹·정보유출)
EVENT_KINDS = ("해킹·정보유출", "제품 결함·리콜", "산업 사고·화재", "재난·날씨", "질병·건강", "정책·규제", "국제 정세·외교",
               "무역·관세", "유가·원자재", "환율·금리", "물가·소비", "기술·신제품", "노사·파업", "법원·수사", "교통·인프라", "기타")
# 회사가 뉴스와 이어지는 관계: 당사자·모회사는 '뉴스 당사자', 공급·고객·사고 대응·규제 대상은 1차, 경쟁·대체재·같은 업종은 2차
RELATIONS = {"당사자": 0, "모회사·지분": 0, "공급사": 1, "고객사": 1, "사고 대응": 1, "규제 대상": 1, "경쟁사": 2, "대체재": 2, "같은 업종": 2}
# 키움 업종(ka20003, '오늘 시장' 탭과 같은 목록). 관련 업종 칩은 이 이름으로만(모르면 칩을 뺀다)
KRX_INDUSTRIES = ("음식료/담배", "섬유/의류", "종이/목재", "화학", "제약", "비금속", "금속", "기계/장비", "전기/전자", "의료/정밀기기",
                  "운송장비/부품", "유통", "전기/가스", "건설", "운송/창고", "통신", "금융", "증권", "보험", "부동산", "IT 서비스",
                  "오락/문화", "출판/매체복제", "기타제조")
INDUSTRIES_MAX = 4
INDUSTRY_STALE_DAYS = 5    # 이보다 오래된 업종 등락은 칩을 숨긴다
# 카드 제목·요약(일반 뉴스 말투)에 쓰지 않는 증권 표현
CARD_BANNED = re.compile(r"주가|급등|급락|상한가|하한가|종목|증시|코스피|코스닥|시가총액|투자자|강세|약세|테마|특징주|관련주|수혜|매수|매도")
INTRO_MODEL = TOPIC_MODEL  # 한 줄 회사 소개(Haiku, 회사별로 한 번)
INTRO_MAX = 32
PULSE_CACHE_SEC = 5.0

# 일상 뉴스 검색어(분야, 검색어). 기준 뉴스 창 안 기사만 쓴다. 등락 순위·특징주·실적 검색은 하지 않는다.
ISSUE_QUERIES = [
    ("보안", "해킹 개인정보 유출"), ("결함", "리콜 결함"), ("결함", "제품 결함 논란"), ("유가", "국제유가"),
    ("환율", "원달러 환율"), ("금리", "기준금리"), ("정책", "정부 규제 발표"), ("정책", "금융당국 발표"),
    ("국제", "관세 무역"), ("국제", "미중 갈등"), ("국제", "중동 정세"), ("날씨", "폭염 한파 폭우 피해"),
    ("질병", "감염병 확산"), ("생활", "소비 트렌드 인기"), ("생활", "장바구니 물가"), ("기술", "신기술 공개 발표"),
    ("사고", "공장 화재 사고"), ("산업", "업황 산업 동향"),
]

# 처음부터 종목·주가가 주인공인 증권 기사. 이슈 후보에서 빼고('왜 움직였나'·'오늘 시장 분위기' 띠에만 쓴다), 규칙 이름을 남긴다.
STOCK_RULES = [
    ("실적·공시", re.compile(r"(\d\s*분기|반기|연간|잠정)\s*(실적|영업\s*(이익|익|손실)|매출|순이익|순손실)|영업\s*(이익|익|손실)\s*[\d,.]+|"
                         r"흑자\s*전환|적자\s*(전환|지속)|어닝\s*(서프라이즈|쇼크)|실적\s*(발표|시즌|호조|부진|개선|악화)|공시(?!가)")),
    ("특징주·관련주", re.compile(r"특징주|관련주|테마주|급등주|수혜주|상한가|하한가|목표\s*(주가|가)|투자\s*의견|52주\s*신고가|"
                           r"주가\s*(급등|급락|강세|약세|상승|하락|껑충|뚝)|(급등|급락|강세|약세)\s*(출발|마감)")),
    ("시황·지수", re.compile(r"코스피|코스닥|증시|시황|주가\s*지수|외국인\s*(순매수|순매도)")),
]
STOCK_TOPIC = re.compile(r"실적|공시|특징주|관련주|주가|시황|증시")  # 이슈 이름에 이 말이 있으면 증권 기사 이슈
MACRO = re.compile(r"금리|환율|원.?달러|달러.?원|국채|통화\s*정책|FOMC|연준|한국은행|한은|증시\s*전반")
SECTOR_QUERIES = ["{s} 업계", "{s} 산업"]

# 새 단어 실시간 생성 안전장치(100명 동시 접속 기준, 11/17 시연). Anthropic 한도는 분당 1만 요청이라 여유가 크다.
LIVE_CONCURRENCY = 10      # 동시에 AI를 부르는 수
LIVE_QUEUE_MAX = 30        # 대기열(그리는 중 포함). 넘치면 '지금 많이 그리고 있어요' + 예시
LIVE_PER_SESSION = 3       # 한 사람(브라우저)당 새 단어 10분에 3개
LIVE_SESSION_WINDOW = 600
# 하루 새 단어 생성 상한(서버 전체, 1개 약 $0.01). 넘으면 저장된 것·예시만. 날짜(KST)로 자동 전환:
# 평소 50개, 시연 주간(11/14~11/17, 양 끝 포함) 400개. live_daily_limit()으로 읽는다.
LIVE_DAILY_MAX_NORMAL = 50
LIVE_DAILY_MAX_DEMO = 400
DEMO_WEEK = ("2026-11-14", "2026-11-17")
TRY_ISSUES = "위 '지금 뜨는 이슈'를 눌러 보세요."
LIVE_TIMEOUT = 45          # AI 한 번 호출 최대 초
WORDS_KEEP = 300           # 저장해 두는 새 단어 수(오래된 것부터 지움)
RESULT_KEEP_SEC = 120      # 실패 결과를 폴링에 알려 주는 시간

# safety.banned_hits(권유·목표가·방향 예측) 위에 더 막는 말. '급등·급락'은 이미 일어난 움직임이라 허용한다.
EXTRA_BANNED = [re.compile(p) for p in (r"수혜", r"추천", r"주목", r"기대", r"유망", r"관심\s*종목", r"테마주", r"매수", r"매도",
                                        r"기회", r"덜\s*(오|올)", r"숨은", r"오를\s*것", r"내릴\s*것")]
# 이유가 추측·약한 연결이면 그 회사를 넣지 않는다(예: '연계 가능', '직접 관련 낮음')
WEAK_REASON = re.compile(r"불확실|여부|가능성|낮[음다은]|없[음다]|추정|예상|것으로\s*보")
WORD_RE = re.compile(r"^[0-9A-Za-z가-힣][0-9A-Za-z가-힣 ]{0,11}$")
BLOCKED_WORDS = re.compile(r"(시발|씨발|개새|병신|좆|섹스|자살|살인|마약|도박|급등주|작전주|리딩방|추천주|수혜주)")


def _read(name: str, default=None):
    """store.read + 잠깐의 파일 잠금(Windows에서 교체 중인 파일) 재시도. 서버(Linux)의 교체는 원자적이다."""
    for attempt in range(3):
        try:
            value = store.read(name, default)
            return value if value is not None else default
        except OSError:
            time.sleep(0.02 * (attempt + 1))
    return default


def _unsafe(text: str) -> bool:
    return bool(banned_hits(text)) or any(p.search(text or "") for p in EXTRA_BANNED)


def normalize_word(word: str) -> str:
    return re.sub(r"\s+", " ", (word or "").strip())


def check_word(word: str) -> str:
    """새 단어 입력 검사. 문제 없으면 빈 문자열, 있으면 화면에 보일 이유."""
    if not word:
        return "단어를 입력해 주세요."
    if not WORD_RE.match(word):
        return "한글·영문·숫자로 12자까지 입력해 주세요."
    if BLOCKED_WORDS.search(word.replace(" ", "")):
        return "다른 단어로 입력해 주세요."
    return ""


# ---------------------------------------------------------
# 종목 목록(공공데이터) 대조
# ---------------------------------------------------------

_dir_cache: dict = {"mtime": None, "directory": {}, "index": {}, "as_of": None}
_dir_lock = threading.Lock()


def _norm_name(name: str) -> str:
    name = re.sub(r"\(주\)|㈜|주식회사", "", name or "")
    return re.sub(r"[\s·.,\-]", "", name).lower()


def directory() -> tuple[dict, dict, str | None]:
    """(코드→종목, 정규화한 이름→코드, 기준일). stocks.json이 바뀔 때만 다시 읽는다(약 350KB, 방문자마다 읽지 않게)."""
    path = store.DATA_DIR / "stocks.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}, {}, None
    with _dir_lock:
        if _dir_cache["mtime"] != mtime:
            raw = _read("stocks", {})
            stocks = raw.get("stocks") or {}
            index: dict[str, str] = {}
            for code, s in stocks.items():
                key = _norm_name(s.get("name", ""))
                # 같은 이름이 둘이면 시가총액 큰 쪽(보통주)
                if key and (key not in index or (s.get("cap") or 0) > (stocks[index[key]].get("cap") or 0)):
                    index[key] = code
            _dir_cache.update(mtime=mtime, directory=stocks, index=index, as_of=raw.get("as_of"))
        return _dir_cache["directory"], _dir_cache["index"], _dir_cache["as_of"]


def match_company(name: str, index: dict) -> str | None:
    return index.get(_norm_name(name))


def _evidence(n, context: list[dict]) -> dict | None:
    """AI가 고른 근거 기사 번호 → 화면용 {title, url, press, press_name, pub}."""
    if not isinstance(n, int) or not 1 <= n <= len(context):
        return None
    a = context[n - 1]
    return {**{k: a.get(k) for k in ("title", "url", "press", "pub")}, "press_name": a.get("press_name") or rss.press_name(a.get("url", ""))}


def validate_paths(raw: dict, index: dict, stocks: dict, macro_text: str | None = None,
                   context: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """AI가 낸 영향 경로 → (화면용 경로 목록, 지운 회사 이름). 경로 최대 4, 경로당 2곳, 회사는 한 번만, 방향(긍정/부정/불확실) 필수.
    macro_text(거시 이슈의 기사 제목·요약문)가 있으면 연관도는 '약'으로 고정하고, 그 회사가 기사에 직접 나올 때만 AI 연관도를 둔다.
    context(이슈 기사)가 있으면: 기사에 이름이 나온 회사는 '뉴스 당사자'(party, 최대 PARTY_MAX), relation으로 1차/2차(hop),
    KRX 업종(industry, 목록에 없으면 비움), 근거 기사(evidence). 이슈 전체 회사는 COMPANIES_MAX곳까지(당사자 → 1차 → 2차 순으로 남김)."""
    paths: list[dict] = []
    removed: list[str] = []
    used: set[str] = set()
    labels: set[str] = set()
    text = " ".join(f"{a.get('title', '')} {a.get('snippet') or ''}" for a in context or [])
    for p in (raw or {}).get("paths") or []:
        label = normalize_word(str(p.get("label") or ""))[:10]
        if not label or label in labels or _unsafe(label):
            continue
        detail = str(p.get("detail") or "").strip()[:24]
        companies = []
        for c in p.get("companies") or []:
            name = str(c.get("name") or "").strip()
            reason = str(c.get("reason") or "").strip()
            code = match_company(name, index)
            if not code:
                if name:
                    removed.append(name)
                continue
            direction = DIRECTIONS.get(c.get("direction"))
            if code in used or not direction or not reason or _unsafe(reason) or WEAK_REASON.search(reason):
                continue
            used.add(code)
            rel = c.get("relevance") if c.get("relevance") in RELEVANCE else "약"
            link = c.get("link") if c.get("link") in LINKS else ""
            row: dict = {}
            if c.get("relation") in RELATIONS:
                relation = c["relation"]
                named = bool(text) and (stocks[code]["name"] in text or (name and name in text))
                party = RELATIONS[relation] == 0 or named  # 기사에 이름이 나오면 숨은 연결이 아니라 뉴스 당사자
                hop = 0 if party else RELATIONS[relation]
                link = "직접 당사자" if party else "같은 업종" if relation == "같은 업종" else "사업 연결"
                ind = c.get("industry") if c.get("industry") in KRX_INDUSTRIES else ""
                ev = _evidence(c.get("evidence"), context or [])
                row = {"relation": "당사자" if named and RELATIONS[relation] else relation, "hop": hop, "party": party,
                       **({"industry": ind} if ind else {}), **({"evidence": ev} if ev else {})}
            if link == "같은 업종":
                rel = "약"  # 같은 업종이라는 것만으로는 연관이 약하다
            if macro_text is not None and stocks[code]["name"] not in macro_text and name not in macro_text:
                rel = "약"  # 금리·환율 같은 거시 이슈는 시장 전체에 닿는다. 회사 고유의 연결이 기사로 확인될 때만 '중' 이상
            companies.append({"code": code, "name": stocks[code]["name"], "relevance": rel, "reason": reason[:60],
                              "direction": direction, **({"link": link} if link else {}), **row})
            if len(companies) == PER_PATH:
                break
        if companies:
            labels.add(label)
            paths.append({"key": f"p{len(paths)}", "label": label, "detail": "" if _unsafe(detail) else detail,
                          "companies": companies})
            if len(paths) == MAX_PATHS:
                break
    return cap_companies(paths), removed


def cap_companies(paths: list[dict]) -> list[dict]:
    """뉴스 당사자는 PARTY_MAX곳까지, 이슈 전체는 COMPANIES_MAX곳까지. 넘치면 2차 → 1차, 연관도 약한 것부터 뺀다.
    회사가 모두 빠진 경로는 지운다. relation이 없는 예전 결과는 그대로 둔다."""
    rows = [(i, c) for i, p in enumerate(paths) for c in p["companies"]]
    if not any("hop" in c for _, c in rows):
        return paths
    order = sorted(rows, key=lambda r: (r[1].get("hop", 1), RELEVANCE.index(r[1]["relevance"])))
    keep, parties = set(), 0
    for _, c in order:
        if c.get("party"):
            if parties >= PARTY_MAX:
                continue
            parties += 1
        if len(keep) < COMPANIES_MAX:
            keep.add(c["code"])
    out = []
    for p in paths:
        companies = [c for c in p["companies"] if c["code"] in keep]
        if companies:
            out.append({**p, "key": f"p{len(out)}", "companies": companies})
    return out


# ---------------------------------------------------------
# AI 호출
# ---------------------------------------------------------

INTERP_SYSTEM = """너는 일상 뉴스를 읽고, 그 뉴스가 어떤 한국 상장사들과 이어져 있는지 쉬운 말로 알려 주는 해설가다.
읽는 사람은 주식을 잘 모르는 일반인이다. 애널리스트 말투(수혜·모멘텀·밸류에이션·업황 개선 등) 대신 일상 말로 쓴다.
규칙:
- interpretation: 이 뉴스가 어떤 회사들과 어떻게 이어지는지 2~3문장(문장당 60자 이내). 예: '해킹 사고가 잇따르면 회사들이 보안 프로그램을 더 사게 될 수 있어요.'
  자료에 있는 사실에서 출발하고, '~할 수 있어요'처럼 가능성으로 쓴다. 주가가 오르거나 내릴 것이라고 쓰지 않는다.
- paths: 영향 경로 2~4개. label은 경로 이름 2~8자, 일상 말로(예: '보안 수요', '보상 비용', '부품 교체', '원가 부담', '규제 강화'), detail은 한 줄(20자 이내).
- 경로마다 영향을 받을 수 있는 한국거래소(코스피·코스닥) 상장사를 3곳까지, 상장 종목명 그대로. 비상장사·해외 회사·비상장 자회사는 쓰지 않는다.
- 이 기능의 목적은 '기사에는 이름이 안 나왔지만 이어져 있는 회사'를 찾는 것이다. 회사는 relation으로 관계를 밝힌다:
  · '당사자': 기사에 이름이 직접 나온 사건·발표의 주체(상장사). '모회사·지분': 당사자가 비상장이면 지분 관계가 확인되는 상장 모회사·대주주.
    당사자·모회사는 합쳐 1~2곳만. 당사자가 비상장이고 지분 관계를 확실히 모르면 넣지 않는다.
  · 나머지는 기사에 이름이 나오지 않은 회사: '공급사'(당사자·제품에 부품·서비스를 대는 회사), '고객사', '사고 대응'(복구·보안·검사·보상을 맡는 업체),
    '규제 대상', '경쟁사', '대체재'(대신 쓰일 제품·서비스를 만드는 회사), '같은 업종'. 그 회사의 실제 사업 내용으로 연결이 설명될 때만 넣는다.
  '같은 업종'이라는 이유만으로는 넣지 않는다. 예: 한 은행의 개인정보 유출 뉴스에 다른 금융지주를 '신뢰 하락'으로 넣지 않는다.
  같은 업종 회사를 꼭 넣어야 하면 relation을 '같은 업종', relevance를 '약'으로 쓰고, 그 회사에 생기는 구체적인 변화를 reason에 쓴다.
- 이슈 전체 회사는 6곳 이하로(당사자 포함), 근거가 확실한 회사만.
- industry: 그 회사가 속한 한국거래소 업종(목록 중 하나). 확실하지 않으면 '모름'.
- evidence: 그 회사와의 연결을 보여 주는 기사 번호(자료의 '번호'). 당사자는 이름이 나온 기사, 나머지는 영향 경로의 출발점이 되는 사실이 담긴 기사.
- 회사마다 direction: '긍정' 또는 '부정'(그 경로로 사업에 좋은 영향/나쁜 영향을 받을 수 있는 쪽). 긍정과 부정을 모두 살핀다.
- move: 유가·환율·금리·물가처럼 오르내릴 수 있는 이슈면 subject에 그 이름(2~6자, 예: '유가'), today에 기사로 판단한 오늘 실제 방향
  ('상승'/'하락'/'보합', 기사로 판단하기 어려우면 '불확실'). 오르내리는 값이 아닌 사건이면 subject는 빈 문자열, today는 '해당 없음'.
  회사별 긍정/부정은 이 실제 방향 기준으로 쓴다(예: 유가 하락이면 항공사는 연료비 부담이 줄어 긍정). '불확실'이면 회사 direction을 '불확실'로 쓴다.
- expected: '거시 이슈'(금리·환율·지수 전반)면 기사로 판단해 시장 예상과 같았으면 '예상대로', 달랐으면 '예상과 다름', 기사로 알 수 없으면
  '판단 어려움'. 거시 이슈면 interpretation 첫 문장에 그 판단을 쓴다(예: '시장 예상대로 동결돼 주가 영향이 작을 수 있다.'). 거시 이슈가 아니면 '해당 없음'.
- 거시 이슈의 회사는 relevance를 '약'으로 쓰고, 그 회사 고유의 직접 연결(수출 비중·차입 구조 등)이 기사에 나올 때만 '중' 이상.
- relevance: 강 = 직접 당사자이거나 그 회사 핵심 사업과 직접 이어짐, 중 = 주요 사업 중 하나, 약 = 간접적으로 이어짐.
- reason: 연결 근거 한 줄(30자 이내) — 그 회사의 사업 내용으로 뉴스와 어떻게 이어지는지(예: '은행에 이상 거래 탐지 시스템을 공급한다').
  확실하지 않은 회사는 쓰지 않는다.
- 금지: 주가 방향 예측('오를 것' 등), 매수·매도 권유, '추천', '수혜', '유망', '기대', '주목', '기회', '덜 올랐다', '숨은'. 한국어."""

INTERP_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["interpretation", "move", "expected", "paths"],
    "properties": {
        "interpretation": {"type": "array", "items": {"type": "string"}},
        "move": {"type": "object", "additionalProperties": False, "required": ["subject", "today"],
                 "properties": {"subject": {"type": "string"}, "today": {"type": "string", "enum": [*MOVES, "해당 없음"]}}},
        "expected": {"type": "string", "enum": [*EXPECTED, "해당 없음"]},
        "paths": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "detail", "companies"],
            "properties": {
                "label": {"type": "string"}, "detail": {"type": "string"},
                "companies": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["name", "direction", "relation", "relevance", "reason", "industry", "evidence"],
                    "properties": {"name": {"type": "string"}, "direction": {"type": "string", "enum": list(DIRECTIONS)},
                                   "relation": {"type": "string", "enum": list(RELATIONS)},
                                   "relevance": {"type": "string", "enum": list(RELEVANCE)}, "reason": {"type": "string"},
                                   "industry": {"type": "string", "enum": [*KRX_INDUSTRIES, "모름"]},
                                   "evidence": {"type": "integer"}}}},
            }}},
    },
}

TOPIC_SYSTEM = """너는 일상 뉴스 편집자다. 사용자가 종목 이야기가 아닌 일상 뉴스를 보다가 '이 회사가 연결돼 있었네' 하고 발견하도록,
주어진 기사에서 오늘 일상 뉴스면에 나온 사건·변화 중 한국 상장사(산업·기업)에 영향이 있을 만한 이슈를 고른다.
규칙:
- 고를 뉴스: 보안 사고, 제품 결함·리콜, 유가·환율 변화, 정책·규제, 국제 정세, 날씨·질병, 생활·소비 트렌드, 기술 발표, 산업 사고처럼 일반 뉴스면에 나오는 사건·변화.
- 고르지 않는 뉴스: 기업 실적 발표·공시, 특징주·관련주·급등 기사, 증시 시황, 코스피·코스닥 지수 등락 자체처럼 처음부터 종목·주가가 주인공인 증권 기사.
- 여러 언론이 다룬 이슈(같은 사건을 다룬 기사가 많은 것)를 먼저 고른다. 이슈는 서로 다른 분야·업종에서 고른다. 같은 기사를 두 이슈에 쓰지 않는다.
- macro: 금리·환율·지수 전반처럼 시장 전체에 영향을 주는 거시 이슈면 true. 거시 이슈는 최대 1개.
- keyword: 이슈 지도 가운데 둘 이름 2~8자. 대표 기사 제목에 나온 핵심 사건 그대로, 제목에 있는 말로 쓴다(예: '금융권 해킹', '아이폰 듀오 결함').
  요약문에 한 번 나온 부수 주제를 가운데 두지 않는다.
- representative: 그 사건이 제목에 직접 드러나는 기사 번호 1개(articles 안에서). articles: 같은 사건을 다룬 기사 번호(최대 6개, 다른 언론 기사 우선).
- field: 뉴스 분야(목록 중 하나). title: 무슨 일이 있었나 한 줄(25자 이내). summary: 사실만 한 줄(45자 이내). sector: 영향이 가장 큰 업종 2~8자.
- 주가 방향 예측, 매수·매도 권유, '추천', '수혜', '유망', '기대', '주목', '기회', '숨은' 같은 말을 쓰지 않는다. 한국어."""

TOPIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "summary", "keyword", "field", "macro", "sector", "articles", "representative"],
        "properties": {"title": {"type": "string"}, "summary": {"type": "string"}, "keyword": {"type": "string"},
                       "field": {"type": "string", "enum": list(NEWS_FIELDS)}, "macro": {"type": "boolean"},
                       "sector": {"type": "string"}, "articles": {"type": "array", "items": {"type": "integer"}},
                       "representative": {"type": "integer"}}}}},
}

RSS_TOPIC_SYSTEM = """너는 종합 일간지·방송사의 일상 뉴스 편집자다. 주어진 기사는 오늘 종합 언론사·방송사의 사회·생활/문화·IT/과학·국제 뉴스면 기사다.
사용자가 종목 이야기가 아닌 일상 뉴스를 보다가 '이 회사가 연결돼 있었네' 하고 발견하도록, 같은 사건을 다룬 기사들을 묶어 이슈 후보를 만든다.
규칙:
- 같은 사건을 다룬 기사들을 하나로 묶는다(articles: 기사 번호, representative: 그 사건이 제목에 가장 잘 드러난 기사 1개).
- linked: 이 사건이 한국의 산업·기업(제품·서비스·공급망·규제·소비)과 이어지면 true. 정치 공방·범죄 사건·연예·스포츠·인물 부고처럼
  기업과 이어지지 않으면 false. 기업과 이어지는 사건을 먼저 고른다.
- 고르지 않는 기사: 기업 실적 발표·공시, 특징주·관련주·급등 기사, 증시 시황·지수 기사처럼 처음부터 종목·주가가 주인공인 기사.
- kind: 사건 종류(목록 중 하나). 분야 이름이 달라도 사건 종류가 같으면(예: 거래소 개인정보 유출과 은행 해킹은 둘 다 '해킹·정보유출')
  하나로 묶거나 기사가 많은 하나만 고른다.
- macro: 금리·환율·지수 전반처럼 시장 전체에 영향을 주는 거시 이슈면 true(최대 1개).
- keyword: 이슈 지도 가운데 둘 이름 2~8자. 대표 기사 제목에 나온 핵심 사건 그대로, 제목에 있는 말로(예: '금융권 해킹', '아이폰 듀오 결함').
- label: 분야 이름 2~8자. 업종명이 아니라 사람들이 일상에서 부르는 말로(예: '개인정보 유출', '전기차 리콜', '스마트폰 결함', '은행 해킹', '폭우 피해').
  '가상자산 거래소'·'2차전지'·'스마트폰 부품'·'금융' 같은 업종명은 쓰지 않는다.
- title: 무슨 일이 있었나 한 줄(25자 이내), summary: 사실만 한 줄(45자 이내). 일반 뉴스 말투로 쓰고, 종목명·주가·급등·급락·증시 같은 증권 표현을 쓰지 않는다.
- query: 이 사건을 다룬 다른 기사를 찾을 네이버 뉴스 검색어 2~4단어(예: '빗썸 개인정보 유출').
- field: 뉴스 분야(목록 중 하나).
- 주가 방향 예측, 매수·매도 권유, '추천', '수혜', '유망', '기대', '주목', '기회', '숨은' 같은 말을 쓰지 않는다. 한국어."""

RSS_TOPIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "summary", "keyword", "label", "kind", "field", "macro", "linked", "query", "articles", "representative"],
        "properties": {"title": {"type": "string"}, "summary": {"type": "string"}, "keyword": {"type": "string"},
                       "label": {"type": "string"}, "kind": {"type": "string", "enum": list(EVENT_KINDS)},
                       "field": {"type": "string", "enum": list(NEWS_FIELDS)}, "macro": {"type": "boolean"},
                       "linked": {"type": "boolean"}, "query": {"type": "string"},
                       "articles": {"type": "array", "items": {"type": "integer"}}, "representative": {"type": "integer"}}}}},
}

INTRO_SYSTEM = """너는 일반인에게 회사를 소개하는 편집자다. 회사마다 무엇을 하는 회사인지 한 줄로 쓴다.
규칙:
- intro: '~하는 회사' 꼴의 한 줄(25자 이내). 예: '폴더블폰 힌지 부품을 만드는 회사', '은행에 보안 프로그램을 파는 회사'.
- 그 회사의 대표 사업을 쓴다. 확실하지 않으면 빈 문자열.
- 주가·투자 이야기, '추천', '수혜', '유망', '기대', '주목', '기회'를 쓰지 않는다. 한국어."""

INTRO_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["companies"],
    "properties": {"companies": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["code", "intro"],
        "properties": {"code": {"type": "string"}, "intro": {"type": "string"}}}}},
}


_usage_lock = threading.Lock()


def _record_usage(model: str, usage, live: bool) -> None:
    """하루 호출 수·토큰을 남긴다(비용 확인용). 프로세스가 둘(ailab·수집기)이라 파일을 따로 쓴다."""
    try:
        with _usage_lock:
            name = "lifemap_usage_live" if live else "lifemap_usage_daily"
            today = datetime.now(KST).strftime("%Y-%m-%d")
            data = _read(name, {})
            if data.get("day") != today:
                data = {"day": today, "models": {}}
            m = data["models"].setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
            m["calls"] += 1
            m["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
            m["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)
            store.write(name, data)
    except Exception as e:
        log.warning("lifemap usage write failed: %s", type(e).__name__)


def _ask(model: str, system: str, task: str, payload, schema: dict, max_tokens: int, live: bool = False) -> dict | None:
    client = ai._claude_client()
    if client is None:
        raise RuntimeError("AI 키 없음")
    budget.check()  # 하루 비용 상한을 넘었으면 BudgetExceeded → 부르는 쪽이 저장된 것·예시로 대신한다
    args = dict(model=model, max_tokens=max_tokens, system=system, timeout=LIVE_TIMEOUT,
                messages=[{"role": "user", "content": f"{task}\n\n자료(JSON):\n{json.dumps(payload, ensure_ascii=False)}"}],
                output_config={"effort": ai.EFFORT, "format": {"type": "json_schema", "schema": schema}})
    if model in ai.FALLBACK_MODELS:
        args.update(extra_headers={"anthropic-beta": ai.FALLBACK_BETA}, extra_body={"fallbacks": "default"})
    resp = client.messages.create(**args)
    _record_usage(model, getattr(resp, "usage", None), live)
    budget.record(model, getattr(resp, "usage", None))
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"stop_reason={resp.stop_reason}")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def read_move(raw: dict | None) -> dict | None:
    """AI가 판단한 오늘 실제 방향 {"subject": "유가", "today": "하락"}. 오르내리는 이슈가 아니면 None."""
    mv = (raw or {}).get("move") or {}
    subject = normalize_word(str(mv.get("subject") or ""))[:8]
    today = mv.get("today")
    return {"subject": subject, "today": today} if subject and today in MOVES and not _unsafe(subject) else None


def interpret(word: str, articles: list[dict], live: bool = False, macro: bool = False) -> dict:
    """뉴스(기사 제목·요약문) → AI 해석 + 영향 경로 × 회사. 실패하면 예외(호출하는 쪽이 예시로 대체).
    macro(거시 이슈)면 해석 첫 줄에 시장 예상과 같았는지, 회사 연관도는 '약'(기사에 직접 나온 회사만 예외)."""
    stocks, index, as_of = directory()
    if not stocks:
        raise RuntimeError("종목 목록 없음")
    task = f"'{word}' 뉴스가 한국 상장사들에 어떤 경로로 영향을 줄 수 있는지 해석하라."
    used = articles[:ARTICLES_MAX]
    payload: dict = {"이슈": word, "거시 이슈": macro, "업종 목록": list(KRX_INDUSTRIES),
                     "기사": [{"번호": i + 1, "언론사": a.get("press_name") or a.get("press") or "", "제목": a["title"],
                              "요약문": (a.get("snippet") or "")[:120]} for i, a in enumerate(used)]}
    macro_text = " ".join(f"{a['title']} {a.get('snippet') or ''}" for a in used) if macro else None
    removed_all: list[str] = []
    paths: list[dict] = []
    sentences: list[str] = []
    best: dict = {}
    count = lambda ps: sum(len(p["companies"]) for p in ps)  # noqa: E731
    for attempt in range(2):
        raw = _ask(CHAIN_MODEL, INTERP_SYSTEM, task, payload, INTERP_SCHEMA, 2000, live)
        got, removed = validate_paths(raw, index, stocks, macro_text, used)
        removed_all += removed
        lines = [str(x).strip()[:120] for x in (raw or {}).get("interpretation") or [] if str(x).strip()]
        lines = [x for x in lines if not _unsafe(x)][:3]
        if count(got) >= count(paths):
            paths, sentences, best = got, lines or sentences, raw or {}  # 다시 그린 것이 더 적으면 처음 것을 둔다
        if (count(paths) >= MIN_COMPANIES and len(paths) >= 2 and sentences) or attempt == 1:
            break
        if removed:
            task += (f"\n\n주의: 직전 결과의 {', '.join(removed[:6])}은(는) 상장 종목 목록에 없었다. "
                     "상장된 회사만 상장 종목명 그대로 다시 써라.")
        elif len(paths) == 1 or not sentences:
            task += "\n\n주의: 직전 결과는 영향 경로가 하나뿐이거나 해석 문장이 없었다. 다른 경로(수요·원가·규제·경쟁 등)도 살펴 2개 이상 써라."
        else:
            break  # 지운 회사 없이 적게 나왔으면 다시 불러도 비슷하다(빈 결과 = 이어지는 회사 없음)
    move = read_move(best)
    if move and move["today"] == "불확실":
        for p in paths:  # 오늘 방향을 모르면 회사별 긍정/부정도 말하지 않는다('영향 가능'만)
            for c in p["companies"]:
                c["direction"] = "unk"
    expected = best.get("expected") if macro and best.get("expected") in EXPECTED else ""
    if macro and sentences and "예상" not in sentences[0]:
        sentences = [EXPECTED_LINE[expected or "판단 어려움"], *sentences][:3]
    return {"word": word, "interpretation": sentences, "stages": paths, "removed": list(dict.fromkeys(removed_all))[:10],
            **({"move": move} if move else {}), **({"macro": True, "expected": expected} if macro else {}),
            "ai": True, "model": CHAIN_MODEL, "directory_as_of": as_of, "created_ts": time.time()}


# ---------------------------------------------------------
# 기준(basis): 어느 시점의 뉴스·등락률로 만드나
# ---------------------------------------------------------

def _md(ymd: str) -> str:
    return f"{int(ymd[4:6])}/{int(ymd[6:8])}"


def index_rates(market: dict) -> dict[str, float]:
    """시세 스냅샷의 지수 등락률 → {"KOSPI": 6.63, "KOSDAQ": 3.69}. 종목 시세와 같은 날 값만(지수 자료가 늦으면 비운다)."""
    out = {}
    for i in market.get("indices") or []:
        code = INDEX_MARKET.get(i.get("name"))
        if code and i.get("rate") is not None and i.get("same_day", True) and i.get("as_of", market.get("as_of")) == market.get("as_of"):
            out[code] = i["rate"]
    return out


def topic_basis(now: datetime | None = None) -> dict | None:
    """기준. 키움 오늘 시세(키움 모드·10시 이후·15분 안 갱신 또는 마감)가 있으면 오늘 뉴스, 아니면 공공데이터 최신 기준일.
    {key, source, as_of, label, window, rates, indices, breadth}. rates = 그 시점 등락률(실제 등락 표시용),
    indices = 같은 스냅샷의 지수 등락률(시장 대비 계산용), breadth = 오른·내린 종목 수. 시세가 없으면 None."""
    now = now or datetime.now(KST)
    public = _read("market", {})
    status = _read("kiwoom_status", {})
    kw = _read("market_kiwoom", {})
    today = now.strftime("%Y%m%d")
    session = kw.get("session")
    fresh = session == "closed" or (session in ("open", "closing_auction") and time.time() - kw.get("fetched_ts", 0) <= KIWOOM_FRESH_SEC)
    if status.get("price_source") == "kiwoom" and kw.get("as_of") == today and (now.hour, now.minute) >= KIWOOM_TOPIC_FROM and fresh:
        closed = session == "closed"
        start_day = public.get("as_of") or (now - timedelta(days=1)).strftime("%Y%m%d")
        start = datetime.strptime(start_day, "%Y%m%d").replace(tzinfo=KST, hour=15, minute=30)
        stamp = datetime.fromtimestamp(kw.get("fetched_ts") or time.time(), KST).strftime("%H:%M")
        rates = {s["code"]: s.get("rate") for lst in (kw.get("heatmap") or {}).values() for s in lst if s.get("code")}
        for kind in ("up", "down", "value"):
            rates.update({s["code"]: s.get("rate") for s in (kw.get("movers") or {}).get(kind) or [] if s.get("code")})
        label = f"{_md(today)} 종가 기준" if closed else f"{_md(today)} 장중 {stamp} 기준"
        return {"key": f"kiwoom:{today}:{'close' if closed else 'open'}", "source": "kiwoom", "as_of": today,
                "label": label, "window": (start, now), "rates": rates, "indices": index_rates(kw), "breadth": kw.get("breadth")}
    if not public.get("as_of"):
        return None
    stocks, _, dir_as_of = directory()
    same = dir_as_of == public["as_of"]
    rates = {c: s.get("rate") for c, s in stocks.items()} if same else {}
    return {"key": f"public:{public['as_of']}", "source": "public", "as_of": public["as_of"],
            "label": f"{_md(public['as_of'])} 장 기준", "window": news_window(public), "rates": rates,
            "indices": index_rates(public) if same else {}, "breadth": public.get("breadth")}


def basis_info(basis: dict) -> dict:
    """화면·저장용(등락률 표·뉴스 창 제외). 지수 등락률·오른/내린 종목 수는 '오늘 시장 분위기' 띠에 쓴다."""
    return {**{k: basis[k] for k in ("key", "source", "as_of", "label")},
            **{k: basis[k] for k in ("indices", "breadth") if basis.get(k)}}


def versus(rate, market: str | None, indices: dict | None) -> tuple[float | None, float | None]:
    """(그 회사 시장 지수 등락률, 시장 대비 %p). 지수나 등락률이 없으면 (None, None)."""
    idx = (indices or {}).get(market or "")
    if rate is None or idx is None:
        return None, None
    return idx, round(rate - idx, 2)


def big_move(rate, vs) -> bool:
    """실제 등락 큼: 시장 대비 ±3%p 이상. 시장 대비를 모르면 단순 등락률 ±5% 이상."""
    if vs is not None:
        return abs(vs) >= MOVED_PP
    return rate is not None and abs(rate) >= MOVED_PCT


# 키움 기준일 때 회사 등락률과 지수 등락률을 같은 때 묻는 함수(수집기가 넣는다: codes → ({code: rate}, {"KOSPI": rate, …}))
rate_source = None


def similar(vs) -> bool:
    """시장 대비 ±2%p 이내: '시장과 비슷해요'(잡음 구간)."""
    return vs is not None and abs(vs) <= SIMILAR_PP


# ---------------------------------------------------------
# 시점: 첫 보도 → 비교할 거래일, 첫 보도 이후 누적 시장 대비
# ---------------------------------------------------------

def trading_day(ymd: str) -> bool:
    return datetime.strptime(ymd, "%Y%m%d").weekday() < 5 and ymd not in KRX_HOLIDAYS


def next_trading_day(ymd: str) -> str:
    d = datetime.strptime(ymd, "%Y%m%d")
    while True:
        d += timedelta(days=1)
        if trading_day(d.strftime("%Y%m%d")):
            return d.strftime("%Y%m%d")


def trading_days_between(a: str, b: str) -> int:
    """[a, b] 거래일 수."""
    n, d, end = 0, datetime.strptime(a, "%Y%m%d"), datetime.strptime(b, "%Y%m%d")
    while d <= end:
        n += trading_day(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return n


def reaction_day(first: datetime) -> tuple[str, bool]:
    """(뉴스 반응을 볼 거래일, 장 마감 뒤 뉴스인지). 15:20 이후·휴장일 첫 보도는 다음 거래일."""
    first = first.astimezone(KST)
    ymd = first.strftime("%Y%m%d")
    if trading_day(ymd) and (first.hour, first.minute) < CLOSE_CUTOFF:
        return ymd, False
    return next_trading_day(ymd), True


def first_report(name: str, context: list[dict], end: datetime, http=None) -> dict | None:
    """이슈의 첫 보도 {pub, title, url, press}: 이슈 기사 + 이슈 이름 검색(관련도순 100건) 중 이름의 말이 모두 제목에 든 가장 이른 기사.
    end에서 FIRST_LOOKBACK_DAYS일 안. 증권 기사는 첫 보도로 보지 않는다."""
    tokens = _issue_tokens(name) or {name}
    found = list(context)
    try:
        found += news.search(name, display=100, sort="sim", **({"http": http} if http else {}))
    except news.NewsError as e:
        log.warning("lifemap first report %s: %s", name, e.code)
    start = end - timedelta(days=FIRST_LOOKBACK_DAYS)
    best = None
    for a in found:
        try:
            pub = datetime.fromisoformat(a["pub"]) if a.get("pub") else None
        except ValueError:
            pub = None
        if not pub or not start <= pub <= end or stock_article(a):
            continue
        if a not in context and not all(t in a.get("title", "") for t in tokens):
            continue  # 검색으로 찾은 기사는 이슈 이름의 말이 제목에 모두 있어야 같은 사건으로 본다
        if best is None or pub < best[0]:
            best = (pub, a)
    if not best:
        return None
    return {"pub": best[0].isoformat(), **{k: best[1].get(k) for k in ("title", "url", "press")}}


def add_history(m: dict, rday: str, http=None) -> int:
    """반응 거래일부터 기준일 전날까지(최대 5거래일) 회사마다 일별 등락률·그 시장 지수 등락률(공공데이터)을 c['hist']에 둔다.
    기준일·장중 값은 화면에서 더한다. 공공데이터에 없는 날(아직 안 올라온 날)은 비워 둔다. 붙인 회사 수."""
    as_of = m.get("as_of") or ""
    market = _read("market", {})
    pub_day = market.get("as_of") or ""
    last = min(pub_day, (datetime.strptime(as_of, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")) if as_of else ""
    if not rday or not last or rday > last:
        return 0  # 반응 거래일이 기준일이거나 그 뒤면 과거 일별 값이 필요 없다
    idx_daily = public_data.index_daily_rates(market)
    stocks, _, _ = directory()
    done = 0
    for st in m.get("stages") or []:
        for c in st.get("companies") or []:
            try:
                rates = public_data.stock_history(c["code"], rday, last)
            except public_data.PublicDataError as e:
                log.warning("lifemap history %s: %s", c["code"], e.code)
                continue
            mk = (stocks.get(c["code"]) or {}).get("market")
            c["hist"] = [{"d": d, "r": r, "i": (idx_daily.get(mk) or {}).get(d)} for d, r in sorted(rates.items())][:CUM_DAYS]
            done += 1
    return done


def since_first(hist: list[dict] | None, day: str | None, rate, idx, rday: str | None) -> dict | None:
    """첫 보도 이후 누적 {rate: 주가 %, vs: 시장 대비 %p, days, from, to}. 반응 거래일부터 지금 값의 날까지(최대 5거래일),
    빠진 거래일이 있으면 None(틀린 누적보다 비워 둔다)."""
    if not rday or not day or day < rday:
        return None
    days = {h["d"]: (h["r"], h["i"]) for h in hist or [] if h.get("r") is not None and h.get("i") is not None}
    if rate is not None and idx is not None:
        days[day] = (rate, idx)
    use = sorted(d for d in days if rday <= d <= day)[:CUM_DAYS]
    if not use or len(use) < min(CUM_DAYS, trading_days_between(rday, day)):
        return None
    cr = ci = 1.0
    trail = []  # 거래일마다 첫 보도 이후 누적 시장 대비(%p) — 회사 상세의 작은 추이선
    for d in use:
        cr *= 1 + days[d][0] / 100
        ci *= 1 + days[d][1] / 100
        trail.append({"d": _md(d), "vs": round((cr - ci) * 100, 2)})
    return {"rate": round((cr - 1) * 100, 2), "vs": round((cr - ci) * 100, 2), "days": len(use), "from": _md(use[0]), "to": _md(use[-1]),
            "trail": trail}


def timing(item: dict) -> dict | None:
    """이슈 카드용: 첫 보도 시각·기사, 장 마감 뒤 뉴스인지, 비교할 거래일. 첫 보도를 모르면(예전 이슈) None."""
    first = item.get("first") or {}
    try:
        pub = datetime.fromisoformat(first["pub"]).astimezone(KST)
    except (KeyError, TypeError, ValueError):
        return None
    rday, after = reaction_day(pub)
    return {"first": f"{pub.month}/{pub.day} {pub:%H:%M}", "first_title": first.get("title") or "", "first_url": first.get("url") or "",
            "first_press": first.get("press") or "", "after_close": after, "reaction_day": rday, "reaction_label": _md(rday)}


def mark_reaction(m: dict, basis: dict) -> dict:
    """기준 시점 등락률·시장 대비를 회사에 저장하고 실제 등락 큼(moved)을 표시한다.
    키움 기준이면 rate_source로 지도 회사 전부와 지수를 같은 때 다시 묻는다(시장 대비 = 같은 시각 값끼리).
    실패하면 기준 스냅샷의 등락률·지수(같은 스냅샷)를 쓰고, 거기 없는 회사는 비워 둔다(화면은 최신 값)."""
    rates, indices = basis["rates"], basis.get("indices") or {}
    codes = [c["code"] for st in m.get("stages") or [] for c in st.get("companies") or []]
    if codes and basis.get("source") == "kiwoom" and rate_source:
        try:
            got, idx = rate_source(codes)
            if idx:
                rates, indices = {**rates, **{k: v for k, v in (got or {}).items() if v is not None}}, idx
        except Exception as e:
            log.warning("lifemap rate_source failed: %s", type(e).__name__)
    stocks, _, _ = directory()
    for st in m.get("stages") or []:
        for c in st.get("companies") or []:
            r = rates.get(c["code"])
            if r is not None:
                idx, vs = versus(r, (stocks.get(c["code"]) or {}).get("market"), indices)
                c.update(rate=r, moved=big_move(r, vs))
                if vs is not None:
                    c.update(market_rate=idx, vs_market=vs)
    m["basis_label"] = basis["label"]
    m["as_of"] = basis.get("as_of")  # 이 등락률의 날(첫 보도 뒤 반응 거래일과 비교)
    if indices:
        m["indices"] = dict(indices)
    return m


# ---------------------------------------------------------
# 토픽: 오늘의 뉴스 → 이슈 묶기
# ---------------------------------------------------------

def _article(a: dict, rep: bool = False) -> dict:
    """화면용 기사. press_name = 종합지·방송사 이름(경제지·전문지는 빈 문자열 → 화면은 도메인), section = RSS 섹션."""
    name = a.get("press_name") or rss.press_name(a.get("url") or "")
    return {**{k: a.get(k) for k in ("title", "url", "press", "pub")}, **({"press_name": name} if name else {}),
            **({"section": a["section"]} if a.get("section") else {}), "rep": rep}


def collect_issue_news(basis: dict, http=None) -> list[dict]:
    """기준 뉴스 창 안의 정책·금리·환율·유가·국제·산업·사고 기사(제목 중복 제거). 날짜 표현 검색을 더해 지난 기준일도 찾는다."""
    start, end = basis["window"]
    day = datetime.strptime(basis["as_of"], "%Y%m%d")
    kw = {"http": http} if http else {}
    out, seen = [], set()
    for category, q in ISSUE_QUERIES:
        try:
            found = news.search_window(q, start, end, limit=12, max_pages=2,
                                       extra_queries=[f"{q} {day.month}월 {day.day}일"], **kw)
        except news.NewsError as e:
            log.warning("lifemap news %s: %s", q, e.code)
            continue
        for n in found:
            if n["title"] not in seen:
                seen.add(n["title"])
                out.append({**n, "category": category})
    return out


_last_rejects: dict[str, int] = {}  # 마지막 토픽 선정에서 버린 이유별 개수(상태 파일에 남겨 원인 확인용)
# 이슈 이름에서 같은 이슈인지 볼 때 빼는 흔한 말(이것만 겹치면 다른 이슈)
GENERIC_TOKENS = {"급등", "급락", "상승", "하락", "인상", "인하", "발표", "확대", "축소", "논란", "우려", "사고", "협상", "결정", "강화"}


def _issue_tokens(keyword: str) -> set[str]:
    return {t for t in re.split(r"[\s·,/]+", keyword) if len(t) >= 2 and t not in GENERIC_TOKENS}


def index_news(t: dict) -> bool:
    """코스피·코스닥 지수 등락 자체를 다룬 시황 이슈(이름·제목). 이슈 카드에서 빼고 '오늘 시장 분위기' 띠로 보여 준다."""
    return bool(INDEX_NEWS.search(f"{t.get('name', '')} {t.get('title', '')}"))


def stock_article(a: dict) -> str:
    """처음부터 종목·주가가 주인공인 증권 기사면 걸린 규칙 이름('실적·공시'·'특징주·관련주'·'시황·지수'), 아니면 빈 문자열(제목 기준)."""
    title = a.get("title") or ""
    return next((name for name, rule in STOCK_RULES if rule.search(title)), "")


def centered(keyword: str, titles: list[str]) -> bool:
    """이슈 이름이 뉴스의 핵심 사건인지: 이름의 말이 대표 기사 제목(titles[0])에 있고, 기사가 둘 이상이면 두 제목 이상에 있다.
    요약문에 한 번 나온 부수 주제를 가운데 두지 않게."""
    tokens = _issue_tokens(keyword) or {keyword}
    hit = [any(t in x for t in tokens) for x in titles]
    return bool(hit) and hit[0] and (len(titles) < 2 or sum(hit) >= 2)


_last_excluded: list[dict] = []  # 마지막 토픽 선정에서 증권 기사로 뺀 기사(상태 파일에 예시로 남긴다)


def pick_issues(basis: dict, articles: list[dict], task: str = "", max_topics: int = TOPICS_MAX,
                min_articles: int = 2, min_press: int = 2) -> list[dict]:
    """Haiku가 묶은 이슈. 증권 기사는 먼저 빼고, 대표 기사·기사 번호·언론사 수·섹터 중복·중심 주제·거시 이슈 수·표현을 검사해
    통과한 것만(최대 max_topics)."""
    _last_excluded.clear()
    kept = []
    for a in articles:
        rule = stock_article(a)
        if rule:
            _last_excluded.append({"rule": rule, **{k: a.get(k) for k in ("title", "press", "pub", "url")}})
        else:
            kept.append(a)
    articles = kept
    if not articles:
        _last_rejects.clear()
        return []
    payload = {"기준": basis["label"],
               "기사": [{"번호": i + 1, "분야": a.get("category", ""), "언론사": a.get("press", ""), "제목": a["title"],
                        "요약문": (a.get("snippet") or "")[:70], "발행": a.get("pub")} for i, a in enumerate(articles)]}
    raw = _ask(TOPIC_MODEL, TOPIC_SYSTEM, task or f"{basis['label']} 일상 뉴스에서 상장사에 영향이 있을 만한 이슈를 여러 언론이 다룬 순서로 7개까지 골라라.",
               payload, TOPIC_SCHEMA, 3000)
    topics, keywords, sectors, used, seen_tokens = [], set(), [], set(), set()
    macros = 0
    rejects = _last_rejects
    rejects.clear()
    for t in (raw or {}).get("topics") or []:
        keyword = normalize_word(str(t.get("keyword") or ""))[:12]
        sector = normalize_word(str(t.get("sector") or ""))[:12]
        title = str(t.get("title") or "").strip()[:40]
        summary = str(t.get("summary") or "").strip()[:80]
        nums = [n for n in dict.fromkeys(t.get("articles") or []) if isinstance(n, int) and 1 <= n <= len(articles)]
        rep = t.get("representative")
        if rep in nums:
            nums = [rep] + [n for n in nums if n != rep]
        nums = nums[:ARTICLES_MAX]
        sec = _norm_name(sector)
        presses = {articles[n - 1].get("press") for n in nums}
        tokens = _issue_tokens(keyword)
        macro = bool(t.get("macro")) or bool(MACRO.search(keyword))
        # 다른 이슈('AI 해킹 유출'과 '개인정보 유출'은 같은 이슈)·다른 섹터('반도체'와 '반도체장비'는 같은 섹터)·
        # 다른 기사·여러 언론·대표 기사·핵심 사건이 가운데·거시 이슈 1개까지여야 이슈
        why = ("market" if index_news({"name": keyword, "title": title}) else
               "stock" if STOCK_TOPIC.search(keyword) or stock_article({"title": title}) else
               "word" if not keyword or check_word(keyword) or keyword in keywords or not sec or tokens & seen_tokens else
               "sector" if any(sec in x or x in sec for x in sectors) else
               "text" if not title or not summary or any(_unsafe(x) for x in (title, summary, keyword, sector)) else
               "articles" if len(nums) < min_articles or rep not in nums or used & set(nums) else
               "center" if not centered(keyword, [articles[n - 1]["title"] for n in nums]) else
               "press" if len(presses) < min_press else
               "macro" if macro and macros else "")
        if why:
            rejects[why] = rejects.get(why, 0) + 1
            continue
        keywords.add(keyword)
        seen_tokens.update(tokens)
        sectors.append(sec)
        used.update(nums)
        macros += macro
        field = t.get("field") if t.get("field") in NEWS_FIELDS else ""
        topics.append({"name": keyword, "title": title, "summary": summary, "sector": sector, "field": field, "macro": macro,
                       "articles": [_article(articles[n - 1], n == rep) for n in nums],
                       "_context": [articles[n - 1] for n in nums]})
        if len(topics) == max_topics:
            break
    return topics


_last_rss: dict = {}  # 마지막 RSS 수집 결과(피드별 기사 수, 상태 파일에 남긴다)


def _ref_time(basis: dict) -> datetime:
    """이슈를 세는 기준 시각: 기준 뉴스 창 끝과 지금 중 이른 쪽."""
    end = basis["window"][1] if basis.get("window") else datetime.now(KST)
    return min(end, datetime.now(KST))


def card_unsafe(text: str) -> bool:
    """카드 제목·요약에 증권 표현(주가·급등·종목·증시 등)이나 권유 표현이 있으면 True."""
    return bool(CARD_BANNED.search(text or "")) or _unsafe(text)


def pick_rss_issues(basis: dict, articles: list[dict], max_topics: int = CANDIDATES_MAX) -> list[dict]:
    """RSS 기사 → Haiku가 같은 사건 기사를 묶은 이슈 후보(기업과 이어지는 것만). 증권 기사는 먼저 빼고,
    대표 기사·기사 번호·사건 종류 중복·중심 주제·거시 이슈 수·카드 표현을 검사해 통과한 것만. 언론사 수는 cover()에서 센다."""
    _last_excluded.clear()
    kept = []
    for a in articles:
        rule = stock_article(a)
        if rule:
            _last_excluded.append({"rule": rule, **{k: a.get(k) for k in ("title", "press", "pub", "url")}})
        else:
            kept.append(a)
    articles = kept
    _last_rejects.clear()
    if not articles:
        return []

    def stamp(pub):
        d = datetime.fromisoformat(pub).astimezone(KST)
        return f"{d.month}/{d.day} {d:%H:%M}"

    payload = {"기준": basis["label"], "사건 종류": list(EVENT_KINDS),
               "기사": [f"{i + 1}|{a.get('press_name', '')}|{a.get('section', '')}|{stamp(a['pub'])}|{a['title']}" for i, a in enumerate(articles)]}
    raw = _ask(TOPIC_MODEL, RSS_TOPIC_SYSTEM,
               f"기사는 '번호|언론사|섹션|발행|제목'이다. 같은 사건 기사를 묶어 한국 산업·기업과 이어지는 이슈를 기사가 많은 순서로 {max_topics}개까지 골라라.",
               payload, RSS_TOPIC_SCHEMA, 4000)
    topics, keywords, kinds, used, seen_tokens = [], set(), set(), set(), set()
    macros = 0
    rejects = _last_rejects
    for t in (raw or {}).get("topics") or []:
        keyword = normalize_word(str(t.get("keyword") or ""))[:12]
        label = normalize_word(str(t.get("label") or ""))[:12]
        kind = t.get("kind") if t.get("kind") in EVENT_KINDS else "기타"
        title = str(t.get("title") or "").strip()[:40]
        summary = str(t.get("summary") or "").strip()[:80]
        query = normalize_word(str(t.get("query") or ""))[:30] or keyword
        nums = [n for n in dict.fromkeys(t.get("articles") or []) if isinstance(n, int) and 1 <= n <= len(articles)]
        rep = t.get("representative")
        if rep in nums:
            nums = [rep] + [n for n in nums if n != rep]
        nums = nums[:ARTICLES_MAX]
        tokens = _issue_tokens(keyword)
        macro = bool(t.get("macro")) or bool(MACRO.search(keyword))
        # '기타'는 종류로 묶지 않는다(서로 다른 사건일 수 있다)
        why = ("unlinked" if not t.get("linked") else
               "market" if index_news({"name": keyword, "title": title}) else
               "stock" if STOCK_TOPIC.search(keyword) or stock_article({"title": title}) else
               "word" if not keyword or check_word(keyword) or keyword in keywords or tokens & seen_tokens else
               "kind" if kind != "기타" and kind in kinds else
               "text" if not title or not summary or not label or any(card_unsafe(x) for x in (title, summary, keyword, label)) else
               "articles" if not nums or rep not in nums or used & set(nums) else
               "center" if not centered(keyword, [articles[n - 1]["title"] for n in nums]) else
               "macro" if macro and macros else "")
        if why:
            rejects[why] = rejects.get(why, 0) + 1
            continue
        keywords.add(keyword)
        seen_tokens.update(tokens)
        kinds.add(kind)
        used.update(nums)
        macros += macro
        field = t.get("field") if t.get("field") in NEWS_FIELDS else ""
        topics.append({"name": keyword, "title": title, "summary": summary, "label": label, "kind": kind, "sector": label,
                       "field": field, "macro": macro, "query": query,
                       "_context": [articles[n - 1] for n in nums]})
        if len(topics) == max_topics:
            break
    return topics


def _matches(title: str, tokens: set[str]) -> bool:
    """검색으로 찾은 기사가 같은 사건인지: 이슈 이름·검색어의 말이 제목에 둘 이상(말이 하나뿐이면 그 하나) 있다."""
    return bool(tokens) and sum(t in title for t in tokens) >= min(2, len(tokens))


def cover(t: dict, ref: datetime, http=None) -> dict:
    """이슈 하나의 '얼마나 많이 다뤘나'(최근 24시간 기사 수·언론사 수), 관련 기사, 첫 보도(최근 7일 안 가장 이른 기사)를 NAVER로.
    t에 articles(대표 = RSS 종합지·방송사 기사 → 다른 RSS 기사 → NAVER 기사, 최대 ARTICLES_MAX), coverage, first, ongoing을 채운다."""
    context = t["_context"]
    tokens = _issue_tokens(t["name"]) | _issue_tokens(t.get("query") or "")
    kw = {"http": http} if http else {}
    found: list[dict] = []
    for sort in ("date", "sim"):
        try:
            found += news.search(t.get("query") or t["name"], display=100, sort=sort, **kw)
        except news.NewsError as e:
            log.warning("lifemap cover %s: %s", t["name"], e.code)
    fresh_from, old_from = ref - timedelta(hours=FRESH_HOURS), ref - timedelta(days=FIRST_LOOKBACK_DAYS)
    seen, matched = set(), []
    for a in found:
        try:
            pub = datetime.fromisoformat(a["pub"]) if a.get("pub") else None
        except ValueError:
            pub = None
        if not pub or not old_from <= pub <= ref or a["url"] in seen or stock_article(a) or not _matches(a["title"], tokens):
            continue
        seen.add(a["url"])
        matched.append({**a, "press_name": rss.press_name(a["url"]), "_pub": pub})
    rss_pubs = [(datetime.fromisoformat(a["pub"]), a) for a in context]
    recent = [a for a in matched if a["_pub"] >= fresh_from]
    presses = {a.get("press_name") or a["press"] for a in recent} | {a.get("press_name") or a["press"] for a in context}
    urls = {a["url"] for a in recent} | {a["url"] for a in context}
    first_pub, first = min([(a["_pub"], a) for a in matched] + rss_pubs, key=lambda x: x[0])
    rep = context[0]
    arts = [_article(rep, True)] + [_article(a) for a in context[1:]]
    titles = {a["title"] for a in arts}
    for a in sorted(recent, key=lambda a: a["_pub"], reverse=True):
        if len(arts) >= ARTICLES_MAX:
            break
        if a["title"] not in titles:
            titles.add(a["title"])
            arts.append(_article(a))
    t.update(articles=arts, coverage={"articles": len(urls), "presses": len(presses), "hours": FRESH_HOURS},
             first={"pub": first_pub.isoformat(), **{k: first.get(k) for k in ("title", "url", "press")}},
             ongoing=first_pub < fresh_from)
    return t


def rank_issues(topics: list[dict], limit: int) -> list[dict]:
    """언론사 COVER_MIN_PRESS곳 이상이 다룬 이슈만. 첫 보도가 24시간 안인 이슈를 언론사·기사 수 순으로 먼저, 계속되는 이슈는 최대 ONGOING_MAX개 뒤에."""
    ok = []
    for t in topics:
        if t["coverage"]["presses"] < COVER_MIN_PRESS:
            _last_rejects["press"] = _last_rejects.get("press", 0) + 1
        else:
            ok.append(t)
    key = lambda t: (-t["coverage"]["presses"], -t["coverage"]["articles"])  # noqa: E731
    fresh = sorted((t for t in ok if not t["ongoing"]), key=key)
    ongoing = sorted((t for t in ok if t["ongoing"]), key=key)
    if len(ongoing) > ONGOING_MAX:
        _last_rejects["ongoing"] = _last_rejects.get("ongoing", 0) + len(ongoing) - ONGOING_MAX
    return (fresh[:limit - min(len(ongoing), ONGOING_MAX)] + ongoing[:ONGOING_MAX])[:limit]


def rss_issues(basis: dict, limit: int, http=None) -> list[dict] | None:
    """RSS로 오늘 이슈 후보 → 기사 수·언론사 수 → 순서. 기준 창 안 RSS 기사가 RSS_MIN개 미만이면 None(예전 방식으로)."""
    ref = _ref_time(basis)
    arts, report = rss.collect(ref - timedelta(hours=FRESH_HOURS), ref + timedelta(minutes=1), per_feed=RSS_PER_FEED,
                               **({"http": http} if http else {}))
    _last_rss.clear()
    _last_rss.update(articles=len(arts), feeds=report)
    if len(arts) < RSS_MIN:
        return None
    picked = pick_rss_issues(basis, arts)
    return rank_issues([cover(t, ref, http) for t in picked], limit)


def _finish(t: dict, basis: dict, live: bool = False, http=None) -> dict | None:
    """이슈 하나 → AI 해석 + 회사 지도 + 실제 등락 + 첫 보도(비교할 거래일·누적용 일별 시세)
    + (해석과 반대로 움직인 회사의) 다른 이유. 회사가 없으면 None."""
    context = t.pop("_context")
    m = interpret(t["name"], context, live, macro=bool(t.get("macro")))
    if not m["stages"]:
        return None
    m = mark_reaction(m, basis)
    # RSS 이슈는 cover()가 첫 보도를 이미 찾았다(NAVER 최신순·관련도순 + RSS 기사 중 가장 이른 것)
    first = t.get("first") or first_report(t["name"], context, _ref_time(basis), http)
    rday = reaction_day(datetime.fromisoformat(first["pub"]))[0] if first else None
    if first:
        t["first"] = first
        add_history(m, rday)
    if not rday or rday <= (basis.get("as_of") or ""):
        explain_opposites(t, m, basis, http)  # 반응 거래일 값이 아직 없으면(장 마감 뒤 뉴스) 반대 움직임도 따지지 않는다
    ensure_intros([c for st in m["stages"] for c in st["companies"]], live)
    t.pop("query", None)
    return {**t, "basis_label": basis["label"], "map": m}


# ---------------------------------------------------------
# 한 줄 회사 소개: 회사별로 한 번 만들어 lifemap_intros.json에 저장해 재사용
# ---------------------------------------------------------

INTROS = "lifemap_intros"
_intro_lock = threading.Lock()


def intros() -> dict[str, str]:
    """{종목코드: 한 줄 소개}."""
    return {k: v.get("text", "") for k, v in (_read(INTROS, {}) or {}).items() if isinstance(v, dict) and v.get("text")}


def ensure_intros(companies: list[dict], live: bool = False) -> int:
    """소개가 없는 회사만 Haiku 한 번으로 만든다(같은 회사는 다시 만들지 않는다). 실패해도 이슈는 그대로. 새로 만든 수."""
    have = intros()
    need = list({c["code"]: c for c in companies if c["code"] not in have}.values())
    if not need:
        return 0
    payload = {"회사": [{"code": c["code"], "이름": c["name"], "참고(뉴스와의 연결)": c.get("reason", "")} for c in need]}
    try:
        raw = _ask(INTRO_MODEL, INTRO_SYSTEM, "회사마다 무엇을 하는 회사인지 한 줄로 소개하라.", payload, INTRO_SCHEMA, 1500, live)
    except Exception as e:
        log.warning("lifemap intros failed: %s", type(e).__name__)
        return 0
    codes = {c["code"] for c in need}
    made = {}
    for r in (raw or {}).get("companies") or []:
        text = normalize_word(str(r.get("intro") or "")).strip(" .")[:INTRO_MAX]
        if r.get("code") in codes and text and not card_unsafe(text):
            made[r["code"]] = {"text": text, "ts": time.time(), "model": INTRO_MODEL}
    if made:
        with _intro_lock:
            store.write(INTROS, {**(_read(INTROS, {}) or {}), **made})
    return len(made)


# ---------------------------------------------------------
# 해석과 반대로 움직인 회사: 그 회사의 같은 날 뉴스로 다른 이유 한 줄(이슈를 만들 때 한 번만)
# ---------------------------------------------------------

OTHER_SYSTEM = """너는 증시 뉴스 편집자다. 어떤 회사의 주가가 주어진 이슈와는 다른 이유로 움직였을 수 있는지, 그 회사의 같은 날 기사 제목에서 찾는다.
규칙:
- 주어진 이슈(이슈 이름·이슈 기사)와 다른, 그 회사 자체의 소식(실적 발표·수주·계약·신제품·인수합병·지분 변동·증자·소송 등)을 다룬 기사 하나를 고른다.
- article: 고른 기사 번호. 그 회사 소식이 없거나 주어진 이슈와 같은 내용이면 0.
- reason: 그 기사의 사실을 명사구로 짧게(20자 이내). 예: '3분기 실적 발표', '2조 원 규모 수주 공시'. 기사에 없는 내용은 쓰지 않는다.
- 주가가 그 때문에 움직였다고 단정하지 않는다. 주가 방향 예측, 매수·매도 권유, '추천', '수혜', '기대', '주목', '기회'를 쓰지 않는다. 한국어."""

OTHER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["article", "reason"],
    "properties": {"article": {"type": "integer"}, "reason": {"type": "string"}},
}


def opposite(c: dict) -> bool:
    """AI 해석 방향(긍정/부정)과 반대로 시장 대비 ±OPPOSITE_PCT(%p) 이상 움직임. 시장 대비를 모르면 단순 등락률로."""
    r = c["vs_market"] if c.get("vs_market") is not None else c.get("rate")
    if r is None:
        return False
    return (c.get("direction") == "pos" and r <= -OPPOSITE_PCT) or (c.get("direction") == "neg" and r >= OPPOSITE_PCT)


def _company_news(name: str, basis: dict, skip: set[str], http=None) -> list[dict]:
    """그 회사 이름이 제목에 든 기준 창 안 기사(이슈 기사 제외). 이슈는 다음 날 만들기도 해서 최신순 앞쪽이 창 밖일 수 있다
    → 최신순 3쪽 + 날짜 표현 검색(대형주는 하루 기사가 많다)."""
    start, end = basis["window"]
    day = datetime.strptime(basis["as_of"], "%Y%m%d")
    kw = {"http": http} if http else {}
    found = news.search_window(name, start, end, limit=10, max_pages=3, must_contain=name,
                               extra_queries=[f"{name} {day.month}월 {day.day}일", f"{name} {day.day}일"], **kw)
    return [n for n in found if name in n["title"] and n["url"] not in skip][:8]


def other_reason(issue: str, issue_titles: list[str], c: dict, basis: dict, skip: set[str], http=None) -> dict:
    """{"text", "title"?, "url"?}. 그 회사의 같은 날 다른 소식이 있으면 '다른 이유로 움직였을 수 있어요: …', 없으면 OTHER_FALLBACK."""
    fallback = {"text": OTHER_FALLBACK}
    try:
        found = _company_news(c["name"], basis, skip, http)
    except news.NewsError as e:
        log.warning("lifemap other news %s: %s", c["code"], e.code)
        return fallback
    if not found:
        return fallback
    payload = {"이슈": issue, "이슈 기사": issue_titles[:6], "회사": c["name"],
               "기사": [{"번호": i + 1, "제목": n["title"], "요약문": (n.get("snippet") or "")[:80]} for i, n in enumerate(found)]}
    try:
        raw = _ask(OTHER_MODEL, OTHER_SYSTEM, f"'{c['name']}'의 같은 날 기사 중 '{issue}'와 다른 그 회사 자체 소식을 하나 골라라.",
                   payload, OTHER_SCHEMA, 1000)  # effort 설정상 300이면 max_tokens로 끊겼다
    except Exception as e:
        log.warning("lifemap other ai %s: %s", c["code"], type(e).__name__)
        return fallback
    n = (raw or {}).get("article")
    reason = normalize_word(str((raw or {}).get("reason") or "")).strip(" .")[:24]
    if not isinstance(n, int) or not 1 <= n <= len(found) or not reason or _unsafe(reason):
        return fallback
    a = found[n - 1]
    return {"text": f"다른 이유로 움직였을 수 있어요: {reason}", "title": a["title"], "url": a["url"]}


def explain_opposites(t: dict, m: dict, basis: dict, http=None) -> int:
    """해석 방향과 반대로 시장 대비 ±3%p 이상 움직인 회사마다 c['other']를 붙인다(최대 OPPOSITE_MAX곳). 붙인 수."""
    if not basis.get("window") or not basis.get("as_of"):
        return 0
    skip = {a.get("url") for a in t.get("articles") or []}
    titles = [a.get("title") or "" for a in t.get("articles") or []]
    done = 0
    for st in m.get("stages") or []:
        for c in st.get("companies") or []:
            if done < OPPOSITE_MAX and opposite(c):
                c["other"] = other_reason(t["name"], titles, c, basis, skip, http)
                done += 1
    return done


# ---------------------------------------------------------
# 예시(대체용)
# ---------------------------------------------------------

_examples_cache: dict = {"value": None}


def examples() -> dict:
    if _examples_cache["value"] is None:
        try:
            _examples_cache["value"] = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _examples_cache["value"] = {"topics": [], "sectors": {}}
    return _examples_cache["value"]


def example_item(word: str = "") -> dict:
    """같은 단어 예시가 있으면 그것, 없으면 첫 토픽 예시."""
    ex = examples()
    sectors = ex.get("sectors") or {}
    topics = ex.get("topics") or []
    chosen = sectors.get(word) or next((t for t in topics if t.get("name") == word), None) or (topics[0] if topics else None) \
        or next(iter(sectors.values()), None)
    if not chosen:
        return {"name": word, "title": word, "summary": "", "articles": [], "example": True,
                "map": {"word": word, "stages": [], "interpretation": [], "ai": False}}
    return {**chosen, "example": True, "map": {**chosen["map"], "example": True}}


# ---------------------------------------------------------
# 토픽·섹터 생성(수집기) — 새 기준이 생길 때마다
# ---------------------------------------------------------

def _status(**kw) -> None:
    try:
        s = _read("lifemap_status", {})
        s.update(kw)
        store.write("lifemap_status", s)
    except Exception:
        pass


def run_topics(basis: dict, http=None) -> dict:
    """오늘의 뉴스 토픽 3~5개(이슈 + AI 해석 + 회사 지도). 3개가 안 되면 같은 기준의 이전 토픽으로 채운다.
    하나도 못 만들었을 때만 예시(다른 날 기준)로 채운다 — 오늘 이슈 사이에 다른 날 토픽이 섞이지 않게."""
    prev = _read("lifemap", {})
    topics: list[dict] = []
    error = ""
    source = "rss"
    try:
        picked = rss_issues(basis, TOPICS_MAX + RESERVE_MAX, http)
        if picked is None:  # RSS가 너무 적다(예전 기준일) → 예전 방식(NAVER 검색어)
            source = "naver"
            picked = pick_issues(basis, collect_issue_news(basis, http), max_topics=TOPICS_MAX + RESERVE_MAX)
        for t in picked:
            try:
                done = _finish(t, basis, http=http)
            except Exception as e:
                error = f"interpret:{type(e).__name__}"
                continue
            if done:
                topics.append(done)
    except Exception as e:
        error = f"topics:{type(e).__name__}"
        log.warning("lifemap topics failed: %s", error)
    names = {t["name"] for t in topics}
    same_basis = (prev.get("basis") or {}).get("key") == basis["key"]
    fillers = (prev.get("topics") or []) if same_basis else []
    if not topics:
        fillers = fillers + [{**t, "example": True} for t in examples().get("topics") or []]
    for t in fillers:
        if len(topics) >= TOPICS_MIN:
            break
        if t["name"] not in names and not t.get("carried"):
            names.add(t["name"])
            topics.append({**t, "carried": True})
    topics, reserve = topics[:TOPICS_MAX], [t for t in topics[TOPICS_MAX:] if not t.get("carried")]
    fresh = sum(1 for t in topics if not t.get("carried"))
    data = {"day": datetime.now(KST).strftime("%Y-%m-%d"), "basis": basis_info(basis), "topics": topics, "reserve": reserve,
            "fresh": fresh, "topic_model": TOPIC_MODEL, "chain_model": CHAIN_MODEL, "news_source": source, "created_ts": time.time()}
    store.write("lifemap", data)
    _status(basis_key=basis["key"], ok=fresh >= TOPICS_MIN, fresh=fresh, error=error, rejects=dict(_last_rejects),
            excluded=len(_last_excluded), excluded_examples=_last_excluded[:10], ts=time.time(), news_source=source,
            rss=dict(_last_rss))
    return data


def run_sectors(basis: dict, http=None) -> int:
    """섹터마다: 같은 기준 창의 섹터 뉴스 → Haiku가 가장 큰 이슈 1개 → 같은 구조. 실패한 섹터는 이전 것을 둔다."""
    saved = _read("lifemap_sectors", {})
    items = dict(saved.get("items") or {})
    start, end = basis["window"]
    day = datetime.strptime(basis["as_of"], "%Y%m%d")
    kw = {"http": http} if http else {}
    made = 0
    for sector in SECTORS:
        found: list[dict] = []
        seen: set[str] = set()
        for q in SECTOR_QUERIES:
            q = q.format(s=sector)
            try:
                for n in news.search_window(q, start, end, limit=8, max_pages=1,
                                            extra_queries=[f"{q} {day.month}월 {day.day}일"], **kw):
                    if n["title"] not in seen:
                        seen.add(n["title"])
                        found.append({**n, "category": sector})
            except news.NewsError:
                pass
        if not found:
            continue
        try:
            picked = pick_issues(basis, found, task=f"{basis['label']} '{sector}' 업종 뉴스에서 이 업종에 영향을 줄 만한 가장 큰 이슈 1개를 골라라.",
                                 max_topics=1, min_articles=1, min_press=1)
            done = _finish({**picked[0], "sector": sector}, basis, http=http) if picked else None
        except Exception as e:
            log.warning("lifemap sector %s failed: %s", sector, type(e).__name__)
            continue
        if done:
            items[sector] = done
            made += 1
    store.write("lifemap_sectors", {"basis": basis_info(basis), "items": items, "created_ts": time.time()})
    return made


_daily_lock = threading.Lock()


def topics_due(basis: dict | None) -> bool:
    """새 기준(새 공공 기준일, 키움 장중·마감)이 생겼고 아직 토픽을 못 만들었으면 True. 같은 기준은 30분 간격 최대 3번."""
    if not basis:
        return False
    cur = _read("lifemap", {})
    done = (cur.get("basis") or {}).get("key") == basis["key"]
    if done and cur.get("fresh", 0) >= TOPICS_MIN:
        return False
    have = cur.get("basis") or {}
    if have.get("source") == "kiwoom" and basis["source"] == "public" and (have.get("as_of") or "") >= basis["as_of"] \
            and cur.get("fresh", 0) >= 1:
        return False  # 기준은 뒤로 가지 않는다(키움 종가 기준 이슈를 더 오래된 공공 기준일로 바꾸지 않음)
    s = _read("lifemap_status", {})
    tries = s.get("tries", 0) if s.get("try_key") == basis["key"] else 0
    if done and tries >= 1 and cur.get("fresh", 0) >= 1:
        return False  # 이 기준으로 일부라도 만들었으면 다시 부르지 않는다(비용)
    return tries < TOPIC_TRIES and time.time() - s.get("try_ts", 0) > 1800


def sectors_due(basis: dict | None) -> bool:
    """섹터 이슈는 하루 한 번: 장 마감 뒤 기준(키움 종가·공공 기준일)이고 저장된 섹터가 그보다 이전 날일 때만.
    키움 장중 기준으로는 만들지 않는다(장중 재생성은 오늘의 이슈만)."""
    if not basis or basis["key"].endswith(":open"):
        return False
    have = (_read("lifemap_sectors", {}).get("basis") or {}).get("as_of") or ""
    return have < basis["as_of"]


def maybe_run_daily(now: datetime | None = None) -> bool:
    """수집기 루프에서 매번 부른다. 할 때가 됐으면 스레드 하나로 돌린다(키움 수집을 막지 않게)."""
    if not ai.available() or not news.configured() or not budget.allowed():
        return False  # 비용 상한을 넘은 날은 저장된 이슈·섹터를 그대로 둔다
    basis = topic_basis(now)
    do_topics, do_sectors = topics_due(basis), sectors_due(basis)
    if not (do_topics or do_sectors) or not _daily_lock.acquire(blocking=False):
        return False
    if do_topics:
        s = _read("lifemap_status", {})
        _status(try_key=basis["key"], tries=(s.get("tries", 0) if s.get("try_key") == basis["key"] else 0) + 1, try_ts=time.time())

    def work():
        try:
            if do_topics:
                run_topics(basis)
            if do_sectors:
                run_sectors(basis)
        except Exception as e:
            log.warning("lifemap daily failed: %s", type(e).__name__)
        finally:
            _daily_lock.release()

    threading.Thread(target=work, name="lifemap-daily", daemon=True).start()
    return True


# ---------------------------------------------------------
# 실제 등락: 키움 장중 30분마다 등락률만 갱신(수집기, AI 재호출 없음)
# ---------------------------------------------------------

def reaction_codes() -> list[str]:
    """지금 화면에 나오는 토픽·섹터 회사 코드."""
    cur = _read("lifemap", {})
    items = (cur.get("topics") or []) + (cur.get("reserve") or []) + list((_read("lifemap_sectors", {}).get("items") or {}).values())
    return list(dict.fromkeys(c["code"] for t in items for st in (t.get("map") or {}).get("stages") or [] for c in st["companies"]))


def rates_due(now: datetime, closed: bool = False) -> bool:
    """장중: 30분마다. 종가(closed): 그날 종가 값이 아직 없을 때 한 번. 둘 다 화면 회사가 바뀌었으면(새 이슈) 바로."""
    saved = _read("lifemap_rates", {})
    if saved.get("as_of") != now.strftime("%Y%m%d"):
        return True
    if set(reaction_codes()) - set(saved.get("codes") or saved.get("rates") or {}):
        return True  # 물어본 코드 기준(상장 폐지 등으로 값이 안 오는 코드 때문에 매번 다시 묻지 않게)
    if "indices" not in saved:
        return True  # 지수 없이 저장된 예전 값이면 한 번 다시(시장 대비 계산용)
    if closed:
        return not saved.get("closed")
    return time.time() - saved.get("ts", 0) >= LIVE_RATES_SEC


def save_live_rates(rates: dict[str, float], now: datetime, closed: bool = False, codes: list[str] | None = None,
                    indices: dict[str, float] | None = None) -> None:
    """회사 등락률과 같은 때 읽은 지수 등락률(indices)을 함께 남긴다 → 시장 대비는 같은 시각 값끼리."""
    md = _md(now.strftime("%Y%m%d"))
    store.write("lifemap_rates", {"as_of": now.strftime("%Y%m%d"), "ts": time.time(), "rates": rates, "closed": closed,
                                  "indices": indices or {},
                                  "codes": codes if codes is not None else list(rates),
                                  "label": f"{md} 종가" if closed else f"{md} {now.strftime('%H:%M')} 장중"})


def _live_rates() -> dict | None:
    """오늘 키움 등락률. 장중 값은 45분 안에 갱신된 것만, 종가 값은 그날 하루."""
    saved = _read("lifemap_rates", {})
    if saved.get("as_of") == datetime.now(KST).strftime("%Y%m%d") and (
            saved.get("closed") or time.time() - saved.get("ts", 0) <= LIVE_RATES_STALE):
        return saved
    return None


# ---------------------------------------------------------
# 화면 데이터(읽기 전용)
# ---------------------------------------------------------

def with_reaction(item: dict, live: dict | None = None, fallback_indices: dict | None = None) -> dict:
    """회사마다 실제 등락률(키움 장중 갱신값 → 생성 때 기준 값 → 최신 종가 순)과 시장 대비·시장·종가·시총,
    해석과 반대면 다른 이유를 붙인다. 시장 대비는 등락률과 같은 때의 지수로만 계산한다(장중 값은 같이 읽은 지수,
    생성 때 값은 생성 때 지수, 최신 종가는 그 기준일 지수 = fallback_indices)."""
    """+ 첫 보도가 장 마감 뒤라 비교할 거래일 값이 아직 없으면 waiting('반응 대기 중', 등락으로 판단하지 않음),
    첫 보도 이후 누적(since, 화면은 회사 상세·표에만), 오늘 값과 누적 방향이 다르면 reflected('첫 보도 때 이미 반영됐을 수 있어요')."""
    stocks, _, as_of = directory()
    m = item.get("map") or {}
    stages = []
    label = m.get("basis_label") or (f"{_md(as_of)} 장 기준" if as_of else "")
    used_live = False
    live_idx = (live or {}).get("indices") or {}
    when = timing(item)
    rday = (when or {}).get("reaction_day")
    days: set[str] = set()
    intro = intros()
    for st in m.get("stages") or []:
        companies = []
        for c in st.get("companies") or []:
            s = stocks.get(c.get("code"))
            if not s:  # 상장 폐지 등으로 목록에서 빠진 회사는 보이지 않는다
                continue
            rate, indices, day = (c["rate"], m.get("indices"), m.get("as_of")) if "rate" in c else (s.get("rate"), fallback_indices, as_of)
            if live and live["rates"].get(c["code"]) is not None:
                rate, indices, day, used_live = live["rates"][c["code"]], live_idx, live.get("as_of"), True
            idx, vs = versus(rate, s.get("market"), indices)
            waiting = bool(rday and day and day < rday)
            row = {**{k: v for k, v in c.items() if k not in ("market_rate", "vs_market", "hist")}, "name": s["name"],
                   **{k: s.get(k) for k in ("market", "close", "cap", "value")},
                   "rate": rate, "market_rate": idx, "vs_market": vs, "moved": big_move(rate, vs) and not waiting, "waiting": waiting,
                   **({"intro": intro[c["code"]]} if c.get("code") in intro else {})}
            since = None if waiting else since_first(c.get("hist"), day, rate, idx, rday)
            if since:
                row["since"] = since
                # 오늘 값과 누적 방향이 다르면(2거래일 이상) 첫 보도 때 이미 움직였을 수 있다
                row["reflected"] = since["days"] >= 2 and vs is not None and vs * since["vs"] < 0
            if day:
                days.add(day)
            # 다른 이유는 지금 보여 주는 값도 해석과 반대(시장 대비 ±3%p 이상)일 때만. 장중에 새로 반대가 됐으면 기본 문구.
            row.pop("other", None)
            row["opposite"] = opposite(row) and not waiting
            if row["opposite"]:
                row["other"] = c.get("other") or {"text": OTHER_FALLBACK}
            companies.append(row)
        if companies:
            stages.append({**st, "companies": companies})
    reaction = f"{live['label']} 등락률" if used_live else f"{label.replace(' 기준', '')} 등락률" if label else "등락률"
    out_map = {k: v for k, v in m.items() if k != "removed"}
    shown_idx = live_idx if used_live else m.get("indices") or {}
    if when:
        rows = [c for st in stages for c in st["companies"]]
        when = {**when, "waiting": bool(rows) and all(c["waiting"] for c in rows),
                "value_label": ", ".join(_md(d) for d in sorted(days))}
    return {**item, "map": {**out_map, "stages": stages, "basis_label": label, "reaction_label": reaction,
                            **({"indices": shown_idx} if shown_idx else {}), **({"timing": when} if when else {})}}


def _signed(v: float) -> str:
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def market_mood(basis: dict, live: dict | None) -> dict | None:
    """'오늘 시장 분위기' 띠: 지수 등락률(장중 갱신값이 있으면 그것, 아니면 이슈 기준 시점)과 오른·내린 종목 비율 한 줄.
    지수 값이 없으면 None(띠를 숨긴다)."""
    indices, breadth, label = basis.get("indices") or {}, basis.get("breadth") or {}, basis.get("label", "")
    if live and live.get("indices"):
        indices, label = live["indices"], live.get("label", label)
        kw = _read("market_kiwoom", {})
        breadth = kw.get("breadth") if kw.get("as_of") == live.get("as_of") else {}
    if not indices:
        return None
    names = {v: k for k, v in INDEX_MARKET.items()}
    total = (breadth or {}).get("total") or 0
    up, down = ((breadth or {}).get("up") or 0) / total if total else 0, ((breadth or {}).get("down") or 0) / total if total else 0
    crowd = ("대부분 종목이 올랐어요" if up >= MOOD_SHARE else "대부분 종목이 내렸어요" if down >= MOOD_SHARE else
             "오른 종목과 내린 종목이 섞여 있어요" if total else "")
    return {"label": label, "indices": [{"name": names[k], "market": k, "rate": indices[k]} for k in ("KOSPI", "KOSDAQ") if k in indices],
            "crowd": crowd, "text": " · ".join([*(f"{names[k]} {_signed(indices[k])}" for k in ("KOSPI", "KOSDAQ") if k in indices),
                                                *([crowd] if crowd else [])])}


def _public_indices() -> dict:
    """최신 공공 기준일 지수(종목 목록과 같은 날일 때만). 등락률을 저장하지 않은 회사가 최신 종가를 쓸 때의 시장 대비용."""
    stocks_as_of = directory()[2]
    market = _read("market", {})
    return index_rates(market) if market.get("as_of") and market.get("as_of") == stocks_as_of else {}


def overview() -> dict:
    cur = _read("lifemap", {})
    ex = examples()
    live = _live_rates()
    pub_idx = _public_indices()
    cfg = curation()
    topics = curate(cfg)["shown"]  # 관리자 숨김·순서·제외 키워드·지수 시황 이슈 제외 적용
    saved = _read("lifemap_sectors", {}).get("items") or {}
    ex_sectors = ex.get("sectors") or {}
    sector_items = {}
    for sector in SECTORS:
        # 숨김·제외 키워드에 걸린 섹터 이슈는 예시로, 예시도 걸리면 뺀다(화면은 있는 섹터만 보여 준다)
        for it in (saved.get(sector), {**ex_sectors[sector], "example": True} if sector in ex_sectors else None):
            if it and not _blocked(it, cfg):
                sector_items[sector] = with_reaction(it, live, pub_idx)
                break
    basis = cur.get("basis") or ex.get("basis") or {}
    return {
        "day": cur.get("day"),
        "basis": basis,
        "market": market_mood(basis, live),
        "topics": [with_reaction(t, live, pub_idx) for t in topics],
        "hot": [t["name"] for t in topics],
        "sectors": SECTORS,
        "sector_items": sector_items,
        "live": live_config(),
        "price_note": price_note("kiwoom" if basis.get("source") == "kiwoom" or live else "public"),
    }


# ---------------------------------------------------------
# 시연 안전장치(관리자): 이슈 숨기기·순서·제외 키워드·금융회사 사고 이슈는 첫 카드 아님
# ---------------------------------------------------------
# 설정은 lifemap_curation.json(수집기가 lifemap.json을 다시 만들어도 그대로). 화면을 읽을 때만 적용한다.
# - 숨김: 이슈 키(대표 기사 주소) 또는 이슈 이름이 같으면 숨긴다. 날짜가 바뀌어도 남는다.
# - 순서: 그날만. 날짜가 바뀌면 처음 순서로 돌아간다.
# - 제외 키워드: 이슈 이름·제목·대표 기사 제목에 들어 있으면 숨긴다.
# 숨긴 만큼 다음 후보(reserve) → 같은 기준의 섹터 이슈 → 예시 순으로 채워 TOPICS_MIN개 이상을 유지한다.

CURATION = "lifemap_curation"
HIDDEN_KEEP = 200
EXCLUDE_MAX = 50
FIN_COMPANY = re.compile(r"은행|카드사|(신한|삼성|현대|국민|롯데|우리|하나|비씨|BC|농협)카드|신용카드|보험|손보|생보|증권|금융지주|"
                         r"캐피탈|금융사|금융회사|금융권|생명(?!과학|공학|연구)|(삼성|현대|DB|KB|메리츠|한화|흥국|롯데|농협)화재")
FIN_INCIDENT = re.compile(r"사고|제재|징계|과징금|과태료|유출|해킹|횡령|배임|부당|불완전\s*판매|영업\s*정지|전산\s*장애|먹통|"
                          r"검사\s*결과|압수\s*수색|기소|소송|피해")
FIN_SECTORS = {"금융", "은행", "보험", "증권", "카드"}
_curation_lock = threading.Lock()


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _rep(t: dict) -> dict:
    arts = t.get("articles") or []
    return next((a for a in arts if a.get("rep")), arts[0] if arts else None) or {}


def item_key(t: dict) -> str:
    """수집기가 다시 만들어도 같은 이슈면 같은 키: 대표 기사 주소(없으면 이름)."""
    return _rep(t).get("url") or f"name:{t.get('name', '')}"


def curation() -> dict:
    raw = _read(CURATION, {}) or {}
    order = raw.get("order") if isinstance(raw.get("order"), dict) else {}
    return {"hidden": [h for h in raw.get("hidden") or [] if isinstance(h, dict) and h.get("key")],
            "words": [str(w) for w in raw.get("words") or [] if str(w).strip()],
            "fin_first": raw.get("fin_first", True) is not False,
            "order": order if order.get("day") == _today() else {"day": _today(), "keys": []}}


def excluded_by(t: dict, words: list[str]) -> str:
    """제외 키워드 중 이슈 이름·제목·대표 기사 제목에 들어 있는 첫 단어(띄어쓰기·대소문자 무시)."""
    text = re.sub(r"\s+", "", f"{t.get('name', '')} {t.get('title', '')} {_rep(t).get('title', '')}").lower()
    return next((w for w in words if re.sub(r"\s+", "", w).lower() in text), "")


def fin_incident(t: dict) -> bool:
    """국내 금융회사(은행·카드·보험·증권)의 사고·제재·유출 이슈로 보이면 True(이름·제목·요약·대표 기사·섹터)."""
    text = f"{t.get('name', '')} {t.get('title', '')} {t.get('summary', '')} {_rep(t).get('title', '')}"
    fin = FIN_COMPANY.search(text) or normalize_word(str(t.get("sector") or "")) in FIN_SECTORS
    return bool(fin and FIN_INCIDENT.search(text))


def _hidden(t: dict, cfg: dict) -> bool:
    key, name = item_key(t), t.get("name")
    return any(h["key"] == key or (name and h.get("name") == name) for h in cfg["hidden"])


def _blocked(t: dict, cfg: dict) -> bool:
    return _hidden(t, cfg) or bool(excluded_by(t, cfg["words"]))


def candidates() -> list[dict]:
    """첫 화면 카드가 될 수 있는 이슈 순서대로: 오늘 이슈 → 다음 후보 → 같은 기준의 섹터 이슈 → 예시. 키·이름마다 하나."""
    cur = _read("lifemap", {})
    out: list[dict] = []
    if cur.get("topics"):
        out += [{**t, "_src": "topic"} for t in cur["topics"]]
        out += [{**t, "_src": "reserve"} for t in cur.get("reserve") or []]
        sec = _read("lifemap_sectors", {})
        if (sec.get("basis") or {}).get("key") == (cur.get("basis") or {}).get("key"):
            out += [{**t, "_src": "sector"} for t in (sec.get("items") or {}).values()]
    out += [{**t, "carried": True, "example": True, "_src": "example"} for t in examples().get("topics") or []]
    keys, names, uniq = set(), set(), []
    for t in out:
        k = item_key(t)
        if t.get("map") and k not in keys and t.get("name") not in names and not index_news(t):
            keys.add(k)
            names.add(t.get("name"))
            uniq.append(t)
    return uniq


def curate(cfg: dict | None = None) -> dict:
    """화면에 보일 이슈(shown)와 관리자용 전체 후보(pool). 원래 보이던 수(최소 TOPICS_MIN)만큼 숨기지 않은 후보로 채운다.
    예시(다른 날 기준)는 오늘 후보로 TOPICS_MIN개를 못 채울 때만 쓴다."""
    cfg = cfg or curation()
    pool = candidates()
    base = sum(1 for t in pool if t["_src"] == "topic")
    want = min(TOPICS_MAX, max(TOPICS_MIN, base))
    open_ = [t for t in pool if not _blocked(t, cfg)]
    today = [t for t in open_ if t["_src"] != "example"]
    shown = today[:want] if len(today) >= TOPICS_MIN else today + [t for t in open_ if t["_src"] == "example"][:TOPICS_MIN - len(today)]
    # 관리자 순서(그날만): 지정한 이슈를 그 순서로 맨 앞에. 숨긴 것은 건너뛰고, 아래 후보도 지정하면 끌어온다.
    keys = [k for k in cfg["order"]["keys"] if k in {item_key(t) for t in open_}]
    if keys:
        by_key = {item_key(t): t for t in open_}
        rest = [t for t in shown if item_key(t) not in keys]
        shown = ([by_key[k] for k in keys] + rest)[:max(len(shown), len(keys))]
    # 금융회사 사고·제재·유출 이슈는 첫 카드에 두지 않는다(관리자가 직접 맨 앞에 지정했으면 그대로)
    if cfg["fin_first"] and shown and not keys and fin_incident(shown[0]):
        i = next((i for i, t in enumerate(shown) if not fin_incident(t)), None)
        if i is None:  # 보이는 것이 모두 금융 사고면 다음 후보에서 하나 끌어온다
            extra = next((t for t in open_ if t not in shown and not fin_incident(t) and t["_src"] != "example"), None)
            if extra:
                shown = [extra] + shown[:-1] if len(shown) >= want else [extra] + shown
        else:
            shown.insert(0, shown.pop(i))
    return {"shown": [{k: v for k, v in t.items() if k != "_src"} for t in shown], "pool": pool, "cfg": cfg}


def admin_curation() -> dict:
    """관리자 화면: 후보마다 키·이름·제목·대표 기사·출처(오늘 이슈/다음 후보/섹터/예시)·보임 순서·숨김·제외 키워드·금융 사고 여부."""
    c = curate()
    cfg = c["cfg"]
    pos = {item_key(t): i + 1 for i, t in enumerate(c["shown"])}
    items = []
    for t in c["pool"]:
        k, rep = item_key(t), _rep(t)
        items.append({"key": k, "name": t.get("name", ""), "title": t.get("title", ""), "sector": t.get("sector", ""),
                      "rep_title": rep.get("title", ""), "rep_press": rep.get("press", ""), "rep_url": rep.get("url", ""),
                      "source": t["_src"], "position": pos.get(k), "hidden": _hidden(t, cfg),
                      "excluded_by": excluded_by(t, cfg["words"]), "fin_incident": fin_incident(t)})
    keys_now = {i["key"] for i in items}
    return {"day": _today(), "basis": _read("lifemap", {}).get("basis") or {}, "items": items,
            "hidden_other": [h for h in cfg["hidden"] if h["key"] not in keys_now],
            "words": cfg["words"], "fin_first": cfg["fin_first"], "order": cfg["order"]["keys"],
            "min": TOPICS_MIN, "max": TOPICS_MAX}


def _save_curation(change) -> dict:
    with _curation_lock:
        cfg = curation()
        change(cfg)
        cfg["hidden"] = cfg["hidden"][-HIDDEN_KEEP:]
        cfg["updated_ts"] = time.time()
        store.write(CURATION, cfg)
    return admin_curation()


def set_hidden(key: str, hidden: bool) -> dict:
    """이슈 하나 숨기기/다시 보이기. 숨길 때 이름·제목도 저장한다(수집기가 대표 기사를 바꿔도 같은 이름이면 숨김)."""
    found = next((t for t in candidates() if item_key(t) == key), None)
    if hidden and not found:
        raise KeyError(key)

    def change(cfg):
        old = next((h for h in cfg["hidden"] if h["key"] == key), None)
        name = (found or old or {}).get("name", "")
        cfg["hidden"] = [h for h in cfg["hidden"] if h["key"] != key and not (name and h.get("name") == name)]
        if hidden:
            cfg["hidden"].append({"key": key, "name": name, "title": found.get("title", ""), "ts": time.time()})
            cfg["order"]["keys"] = [k for k in cfg["order"]["keys"] if k != key]
    return _save_curation(change)


def set_order(keys: list[str]) -> dict:
    """오늘 첫 화면 순서(앞에 둘 이슈 키 순서). 날짜가 바뀌면 처음 순서로. 빈 목록이면 처음 순서로."""
    valid = {item_key(t) for t in candidates()}
    keys = [k for k in dict.fromkeys(keys) if k in valid][:TOPICS_MAX]

    def change(cfg):
        cfg["order"] = {"day": _today(), "keys": keys}
    return _save_curation(change)


def set_words(words: list[str]) -> dict:
    clean = list(dict.fromkeys(w.strip()[:20] for w in words if w and w.strip()))[:EXCLUDE_MAX]

    def change(cfg):
        cfg["words"] = clean
    return _save_curation(change)


def set_fin_first(on: bool) -> dict:
    def change(cfg):
        cfg["fin_first"] = bool(on)
    return _save_curation(change)


# ---------------------------------------------------------
# 새 단어 실시간 생성(ailab) — 대기열
# ---------------------------------------------------------

_pool = ThreadPoolExecutor(max_workers=LIVE_CONCURRENCY, thread_name_prefix="lifemap-live")
_jobs: dict[str, dict] = {}      # 단어 → {state: queued|running|failed, seq, done_ts, reason}
_jobs_lock = threading.Lock()
_words_lock = threading.Lock()
_sessions: dict[str, deque] = {}
_seq = {"n": 0}


def live_daily_limit(now: datetime | None = None) -> dict:
    """지금(KST) 적용 중인 직접 입력 하루 상한. 시연 주간이면 400, 아니면 50."""
    day = (now or datetime.now(KST)).astimezone(KST).strftime("%Y-%m-%d")
    demo = DEMO_WEEK[0] <= day <= DEMO_WEEK[1]
    return {"max": LIVE_DAILY_MAX_DEMO if demo else LIVE_DAILY_MAX_NORMAL, "demo_week": demo, "day": day,
            "normal": LIVE_DAILY_MAX_NORMAL, "demo": LIVE_DAILY_MAX_DEMO, "demo_from": DEMO_WEEK[0], "demo_to": DEMO_WEEK[1]}


def live_config() -> dict:
    return {"enabled": ai.available(), "concurrency": LIVE_CONCURRENCY, "queue_max": LIVE_QUEUE_MAX,
            "per_session": LIVE_PER_SESSION, "window_min": LIVE_SESSION_WINDOW // 60}


_live_count: dict = {}  # 오늘 새 단어 생성 수. ailab 프로세스만 쓰므로 메모리가 기준이고 파일은 재시작 대비


def _live_today() -> int:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if _live_count.get("day") != today:
        saved = _read("lifemap_live_count", {})
        _live_count.update(day=today, n=saved.get("n", 0) if saved.get("day") == today else 0)
    return _live_count["n"]


def _bump_live_today() -> None:
    """_jobs_lock 안에서 부른다(같은 프로세스 안에서 읽기·쓰기가 겹치지 않게)."""
    _live_today()
    _live_count["n"] += 1
    try:
        store.write("lifemap_live_count", dict(_live_count))
    except OSError as e:
        log.warning("lifemap live count write failed: %s", type(e).__name__)


def stored_item(word: str) -> dict | None:
    """섹터·토픽 키워드·전에 그린 새 단어·저장소 예시 중 같은 단어(AI를 다시 부르지 않음)."""
    sectors = _read("lifemap_sectors", {}).get("items") or {}
    if word in sectors:
        return sectors[word]
    for t in _read("lifemap", {}).get("topics") or []:
        if t.get("name") == word and t.get("map"):
            return t
    it = _read("lifemap_words", {}).get(word)
    if it:
        return it
    ex = examples()
    found = (ex.get("sectors") or {}).get(word) or next((t for t in ex.get("topics") or [] if t.get("name") == word), None)
    return {**found, "example": True} if found else None


def _save_word(word: str, item: dict) -> None:
    with _words_lock:
        words = _read("lifemap_words", {})
        words[word] = item
        if len(words) > WORDS_KEEP:
            for old in sorted(words, key=lambda w: words[w].get("created_ts", 0))[: len(words) - WORDS_KEEP]:
                words.pop(old, None)
        store.write("lifemap_words", words)


def word_item(word: str) -> dict:
    """직접 입력한 단어: 최근 뉴스(있으면)로 해석. 뉴스 검색 실패는 뉴스 없이 해석한다."""
    cutoff = datetime.now(KST) - timedelta(days=WORD_NEWS_DAYS)
    found: list[dict] = []
    if news.configured():
        try:
            found = [n for n in news.search(word, display=30, sort="sim")
                     if n.get("pub") and datetime.fromisoformat(n["pub"]) >= cutoff][:ARTICLES_MAX]
        except news.NewsError:
            found = []
    m = interpret(word, found, live=True)
    stocks, _, as_of = directory()
    m["basis_label"] = f"{_md(as_of)} 장 기준" if as_of else ""
    rep = found[0] if found else None
    return {"name": word, "title": rep["title"] if rep else f"‘{word}’", "summary": (rep.get("snippet") or "")[:80] if rep else "",
            "sector": "", "articles": [_article(a, i == 0) for i, a in enumerate(found)], "created_ts": time.time(), "map": m}


def _run_job(word: str) -> None:
    with _jobs_lock:
        _jobs[word]["state"] = "running"
    try:
        _save_word(word, word_item(word))  # 빈 결과(이어지는 회사 없음)도 저장해서 같은 단어로 다시 부르지 않는다
        with _jobs_lock:
            _jobs.pop(word, None)
    except Exception as e:
        log.warning("lifemap live %s failed: %s", word, type(e).__name__)
        with _jobs_lock:
            _jobs[word].update(state="failed", done_ts=time.time(), reason=type(e).__name__)


def _position(word: str) -> int:
    """앞에서 기다리는 단어 수(그리는 중인 것 제외)."""
    job = _jobs.get(word) or {}
    return sum(1 for j in _jobs.values() if j["state"] == "queued" and j["seq"] < job.get("seq", 0))


def _cleanup() -> None:
    now = time.time()
    for w in [w for w, j in _jobs.items() if j["state"] == "failed" and now - j.get("done_ts", now) > RESULT_KEEP_SEC]:
        _jobs.pop(w, None)


def _ready(word: str, item: dict) -> dict:
    return {"status": "ready", "word": word, "item": with_reaction(item, _live_rates(), _public_indices())}


def _fallback(word: str, status: str, message: str) -> dict:
    return {"status": status, "word": word, "message": message, "item": with_reaction(example_item(word))}


def word_status(word: str) -> dict:
    """폴링용. 저장된 결과 → 진행 중 → 실패(예시로 대체) → 없음 순."""
    word = normalize_word(word)
    it = stored_item(word)
    if it:
        return _ready(word, it)
    with _jobs_lock:
        _cleanup()
        job = _jobs.get(word)
        if job and job["state"] in ("queued", "running"):
            return {"status": job["state"], "word": word, "position": _position(word)}
        if job and job["state"] == "failed":
            return _fallback(word, "failed", f"AI가 지금 해석하지 못해서 준비된 예시를 보여 드려요. {TRY_ISSUES}")
    return {"status": "none", "word": word}


def request_word(word: str, session: str) -> dict:
    """새 단어 요청. 저장된 것이 있으면 바로, 없으면 대기열에 넣는다(같은 단어는 하나로 묶임)."""
    word = normalize_word(word)
    problem = check_word(word)
    if problem:
        return {"status": "invalid", "word": word, "message": problem}
    it = stored_item(word)
    if it:
        return _ready(word, it)
    with _jobs_lock:
        _cleanup()
        job = _jobs.get(word)
        if job and job["state"] in ("queued", "running"):
            return {"status": job["state"], "word": word, "position": _position(word)}  # 다른 사람이 이미 요청함
        if not ai.available():
            return _fallback(word, "unavailable", f"지금은 새 단어를 해석할 수 없어서 준비된 예시를 보여 드려요. {TRY_ISSUES}")
        if _live_today() >= live_daily_limit()["max"]:
            return _fallback(word, "daily_limit", f"오늘 직접 입력을 다 써서 준비된 예시를 보여 드려요. {TRY_ISSUES}")
        hits = _sessions.setdefault(session or "anon", deque())
        while hits and time.time() - hits[0] > LIVE_SESSION_WINDOW:
            hits.popleft()
        if len(hits) >= LIVE_PER_SESSION:
            return {"status": "limited", "word": word,
                    "message": f"직접 입력은 {LIVE_SESSION_WINDOW // 60}분에 {LIVE_PER_SESSION}개까지 할 수 있어요. {TRY_ISSUES}"}
        active = sum(1 for j in _jobs.values() if j["state"] in ("queued", "running"))
        if active >= LIVE_QUEUE_MAX:
            return _fallback(word, "busy", f"지금 해석하는 단어가 많아요. 준비된 예시를 보여 드려요. {TRY_ISSUES}")
        hits.append(time.time())
        if len(_sessions) > 2000:  # 오래된 세션 정리
            for k in [k for k, v in _sessions.items() if not v or time.time() - v[-1] > LIVE_SESSION_WINDOW]:
                _sessions.pop(k, None)
        _seq["n"] += 1
        _jobs[word] = {"state": "queued", "seq": _seq["n"]}
        position = _position(word)
        _bump_live_today()
    _pool.submit(_run_job, word)
    return {"status": "queued", "word": word, "position": position}


# ---------------------------------------------------------
# 수동 실행
#   python -m services.stockon.lifemap --daily      지금 기준으로 토픽 + 섹터 다시 만들기(수집기와 같은 일)
#   python -m services.stockon.lifemap --topics     토픽만 다시
#   python -m services.stockon.lifemap --sectors    섹터만 다시
#   python -m services.stockon.lifemap --examples   저장소 예시 파일(data/stockon/lifemap_examples.json) 다시 만들기
# ---------------------------------------------------------

def _strip(item: dict) -> dict:
    return {**item, "map": {k: v for k, v in item["map"].items() if k != "removed"}}


def build_examples() -> dict:
    basis = topic_basis()
    if not basis:
        raise RuntimeError("시세 스냅샷 없음")
    topics = [t for t in run_topics(basis)["topics"] if not t.get("carried")]
    run_sectors(basis)
    sectors = {k: _strip(it) for k, it in (_read("lifemap_sectors", {}).get("items") or {}).items()}
    data = {"note": "AI가 실패할 때 쓰는 예시. 같은 엔진(Haiku 5.5 이슈 선정·Sonnet 5.5 해석)으로 만들고 종목 목록과 대조함.",
            "built": datetime.now(KST).strftime("%Y-%m-%d"), "basis": basis_info(basis),
            "topics": [_strip(t) for t in topics], "sectors": sectors}
    EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--examples" in sys.argv:
        d = build_examples()
        print(f"예시: {d['basis']['label']} · 토픽 {len(d['topics'])}개, 섹터 {len(d['sectors'])}개")
    else:
        b = topic_basis()
        if not b:
            print("시세 스냅샷이 없어 만들 수 없어요.")
            sys.exit(1)
        if "--daily" in sys.argv or "--topics" in sys.argv:
            d = run_topics(b)
            print(f"{b['label']} · 토픽: 새로 {d['fresh']}개 / {len(d['topics'])}개")
        if "--daily" in sys.argv or "--sectors" in sys.argv:
            print(f"섹터: {run_sectors(b)}개")

"""MONEY:ON AI 기능(오라클 전용): 꿀벌의 주간 편지 · 목표 저축 코치 · 부모 리포트. docs/MONEYON_AI_PLAN.md

- 숫자는 이 파일의 코드가 계산한다. AI는 그 숫자를 받아 설명 문장만 쓴다.
- AI에는 금액·카테고리·날짜와 계산 결과만 보낸다. 아이 이름·쓴 곳 메모·통장 이름은 보내지 않는다.
- 금지 표현이나 계산과 다른 숫자가 나오면, 첫 글자가 늦거나 실패하면 준비된 결과로 바꾼다.
- 기능 스위치: MONEYON_AI_ENABLED=1, MONEYON_AI_FEATURES=letter,coach,parent
"""
import asyncio
import hashlib
import json
import os
import re
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
FEATURES = ('letter', 'coach', 'parent')
DEFAULT_MODEL = 'claude-haiku-5-5'
# 100만 토큰당 (입력, 출력) USD — 하루 비용 상한 계산용
PRICES = {'claude-haiku-5-5': (0.10, 0.50), 'claude-sonnet-5-5': (2.0, 10.0), 'claude-opus-5-5': (4.0, 20.0)}
PREPARED_PATH = Path(__file__).resolve().parent.parent / 'data' / 'ai_prepared.json'


def env(name, default=''):
    return (os.environ.get(name) or default).strip()


def config():
    features = {f.strip() for f in env('MONEYON_AI_FEATURES', ','.join(FEATURES)).split(',') if f.strip() in FEATURES}
    return {
        'enabled': env('MONEYON_AI_ENABLED') == '1',
        'features': [f for f in FEATURES if f in features],
        'fake': env('MONEYON_AI_FAKE') == '1',
        'daily_usd': float(env('MONEYON_AI_DAILY_USD', '3') or 3),
        'concurrency': int(env('MONEYON_AI_CONCURRENCY', '8') or 8),
        'queue_max': int(env('MONEYON_AI_QUEUE', '30') or 30),
        'queue_wait': float(env('MONEYON_AI_QUEUE_WAIT', '6') or 6),
        'first_token': float(env('MONEYON_AI_FIRST_TOKEN', '4') or 4),
        'total': float(env('MONEYON_AI_TOTAL', '15') or 15),
        'demo_entry': env('MONEYON_DEMO_ENTRY') == '1',
    }


def model_for(feature):
    return env(f'MONEYON_AI_MODEL_{feature.upper()}', DEFAULT_MODEL)


def won(n):
    return f'{int(n):,}원'


# ---------------------------------------------------------------
# 사실 계산 (화면 상태 → AI에 보낼 숫자). 이름·메모·통장 이름 없음.
# ---------------------------------------------------------------

def _cycles(state):
    return sorted(state.get('cycles') or [], key=lambda c: c['start'])


def _cycle_txs(state, cycle_id):
    return [t for t in state.get('transactions') or [] if t.get('cycle') == cycle_id]


def _spent(txs):
    return sum(-t['wallet'] for t in txs if t['kind'] == 'expense')


def letter_facts(state):
    cycles = _cycles(state)
    current = cycles[-1] if cycles else None
    txs = _cycle_txs(state, current['id']) if current else []
    expenses = [{'날짜': t['created'][:10], '카테고리': t.get('category') or '기타', '금액': -t['wallet']}
                for t in txs if t['kind'] == 'expense']
    by_cat = {}
    for e in expenses:
        by_cat[e['카테고리']] = by_cat.get(e['카테고리'], 0) + e['금액']
    prev = _spent(_cycle_txs(state, cycles[-2]['id'])) if len(cycles) > 1 else None
    saved = sum(t['vault'] for t in txs if t['kind'] == 'deposit')
    received = sum(t['wallet'] for t in txs if t['kind'] == 'payment')
    top = max(by_cat.items(), key=lambda kv: kv[1])[0] if by_cat else None
    return {
        '기간': f"{current['start']}~{current['end']}" if current else None,
        '받은 용돈': received,
        '쓴 돈 합계': sum(by_cat.values()),
        '쓴 돈 기록': sorted(expenses, key=lambda e: e['날짜'])[:12],
        '카테고리별 쓴 돈': by_cat,
        '가장 많이 쓴 카테고리': top,
        '저금한 돈': saved,
        '지난주 쓴 돈': prev,
        '지금 남은 용돈': state.get('wallet', 0),
        '저축통장 잔액 합계': state.get('vault', 0),
        '이번 주 받을 보너스(예상)': (state.get('rewards') or {}).get('expected_total', 0),
        '기록한 날 수': len({e['날짜'] for e in expenses}),
    }


def _savings_rule(state):
    # 가장 최근 주기(시작일 기준)의 규칙. state['cycles']는 최신이 앞이라 그냥 [-1]을 쓰면 옛 주기(이자 규칙 없음)를 읽는다.
    cycles = _cycles(state)
    child_policy = (cycles[-1] if cycles else {}).get('policy') or {}
    rule = (child_policy.get('dual_rewards') or {}).get('savings_interest') or {}
    return int(rule.get('rate_bps') or 0), rule.get('cap'), int(rule.get('unit') or 1)


def simulate_goal(balance, target, weekly, rate_bps, cap=None, unit=1, max_weeks=104):
    """매주: 저금(weekly) → 그 주 잔액에 저축 이자(rate_bps, unit 단위 버림, cap 상한). 목표에 닿는 주를 찾는다."""
    rows, interest_total, b = [], 0, int(balance)
    if b >= target:
        return {'weeks': 0, 'rows': [], 'interest_total': 0, 'final': b, 'reachable': True}
    for week in range(1, max_weeks + 1):
        b += weekly
        interest = (b * rate_bps // 10000) // unit * unit if unit else b * rate_bps // 10000
        if cap is not None:
            interest = min(interest, int(cap))
        b += interest
        interest_total += interest
        rows.append({'주': week, '저금': weekly, '이자': interest, '잔액': b})
        if b >= target:
            return {'weeks': week, 'rows': rows, 'interest_total': interest_total, 'final': b, 'reachable': True}
    return {'weeks': None, 'rows': rows[:8], 'interest_total': interest_total, 'final': b, 'reachable': False}


def coach_facts(state, book_id, weekly):
    book = next((b for b in state.get('books') or [] if b['id'] == book_id), None)
    if not book:
        raise ValueError('저축통장을 찾을 수 없어요.')
    if type(weekly) is not int or not 0 <= weekly <= 1000000 or weekly % 100:
        raise ValueError('일주일 저금액은 100원 단위로 골라 주세요.')
    rate, cap, unit = _savings_rule(state)
    plan = simulate_goal(book['balance'], book['target'], weekly, rate, cap, unit)
    no_interest = simulate_goal(book['balance'], book['target'], weekly, 0) if weekly else {'weeks': None}
    return {
        '목표 금액': book['target'], '지금 모은 돈': book['balance'], '남은 금액': max(0, book['target'] - book['balance']),
        '일주일 저금액': weekly, '주간 저축 이자율(%)': rate / 100,
        '목표까지 주 수(이자 포함)': plan['weeks'], '이자 없이 주 수': no_interest['weeks'],
        '이자로 줄어든 주 수': (no_interest['weeks'] - plan['weeks']) if plan['weeks'] and no_interest['weeks'] else 0,
        '목표까지 받는 이자 합계': plan['interest_total'], '목표 도달 가능': plan['reachable'],
        '주별 계획(앞 4주)': plan['rows'][:4],
    }


def parent_facts(state):
    cycles = _cycles(state)[-4:]
    weekly = [{'주': f"{c['start']}~{c['end']}", '쓴 돈': _spent(_cycle_txs(state, c['id'])),
               '저금': sum(t['vault'] for t in _cycle_txs(state, c['id']) if t['kind'] == 'deposit')} for c in cycles]
    report = state.get('report') or {}
    deposits = sum(1 for t in state.get('transactions') or [] if t['kind'] == 'deposit')
    return {
        '주별 쓴 돈·저금': weekly,
        '카테고리별 쓴 돈(전체)': report.get('categories') or {},
        '받은 용돈 합계': report.get('paid', 0), '쓴 돈 합계': report.get('spent', 0),
        '받은 보너스·이자 합계': report.get('interest', 0), '저금 비율(%)': report.get('savings_rate', 0),
        '기록한 날 수': report.get('record_days', 0), '저금 횟수': deposits,
        '지금 남은 용돈': state.get('wallet', 0), '저축통장 잔액 합계': state.get('vault', 0),
    }


def facts_for(feature, state, book_id=None, weekly=None):
    if feature == 'letter':
        return letter_facts(state)
    if feature == 'coach':
        return coach_facts(state, book_id, weekly)
    return parent_facts(state)


def facts_hash(feature, facts):
    return hashlib.sha256(json.dumps([feature, facts], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------
# 지시문 · 금지 표현 · 숫자 검사
# ---------------------------------------------------------------

KID_RULES = """너는 MONEY:ON의 꿀벌 친구야. 초등학교 저학년 아이에게 말하듯 다정하고 쉬운 반말로 쓴다.
- 한 문장은 짧게(30자 안팎). 어려운 말은 풀어서(이자 = 모아 둔 돈에 붙는 보너스).
- 아이 이름은 부르지 않고 '너'라고 한다.
- 숫자(금액·주 수)는 자료에 있는 값만 그대로 쓴다. 새로 계산하거나 반올림하지 않는다. 금액은 '18,000원'처럼 쉼표와 '원'('1만 8,000원'처럼 쓰지 않는다).
- 상품·카드·앱·은행 상품을 권하거나 광고하지 않는다. 대출·투자·주식 이야기는 하지 않는다.
- 다른 아이와 비교하거나 꾸짖거나 겁주는 말을 하지 않는다. 잘한 점을 먼저 말한다.
- 마크다운(#, *, **)을 쓰지 않는다. 이모지는 2개까지."""

PARENT_RULES = """너는 MONEY:ON의 부모용 리포트를 쓰는 도우미다. 짧은 존댓말로 쓴다.
- 판단·훈계 대신 관찰한 사실과 대화 제안만 쓴다. 아이를 다른 아이와 비교하지 않는다.
- 숫자(금액·횟수·비율)는 자료에 있는 값만 그대로 쓴다. 금액은 '1,500원'처럼 쉼표와 '원'.
- 금융 상품·카드·앱을 권하거나 광고하지 않는다. 대출·투자 이야기는 하지 않는다.
- 마크다운 기호(#, *, **)는 쓰지 않는다. 아래 형식을 그대로 따른다."""

TASKS = {
    'letter': '이번 주 기록으로 꿀벌의 주간 편지를 4~5문장으로 써 줘. 순서: 이번 주 요약 1~2문장, 잘한 점 칭찬 1문장, 다음 주 응원 1문장.',
    'coach': ('목표 저축 계획을 3~4문장으로 설명해 줘. 목표까지 몇 주가 걸리는지, 이자가 얼마나 도와주는지 말해 줘. '
              '"이자로 줄어든 주 수"가 0이면 이자 때문에 더 빨라진다고 말하지 말고, 이자가 목표 금액을 넉넉하게 채워 준다고만 말해. '
              '1 이상이면 그만큼 빨라진다고 말해. 자료에 없는 비교는 하지 마. '
              '마지막 줄은 "이번 주 할 일: "로 시작하는 한 문장. 목표 도달 가능이 false면 저금액을 조금 늘려 보자고 다정하게 말해 줘.'),
    'parent': ('부모님께 드리는 이번 주 리포트를 아래 형식으로 써 줘.\n'
               '소비 패턴: (2문장)\n칭찬 포인트:\n- (1문장)\n- (1문장)\n대화 팁:\n- (1문장)\n- (1문장)'),
}

BANNED = [re.compile(p) for p in (
    r'추천', r'가입', r'상품', r'할인', r'이벤트', r'쿠폰', r'광고', r'대출', r'투자', r'주식', r'코인', r'보험',
    r'신용카드', r'체크카드', r'카드를\s*(만들|쓰)', r'앱을\s*(깔|설치)', r'바보', r'한심', r'못났', r'혼날', r'큰일',
    r'망했', r'멍청', r'게으르',
)]


def banned_hits(text):
    return [m.group(0) for p in BANNED for m in [p.search(text or '')] if m]


def _numbers(obj, out):
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(int(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    return out


def number_errors(text, facts):
    """AI가 쓴 금액('…원')과 주 수('…주')가 계산 자료에 있는 값인지 본다. 없는 숫자 목록을 돌려준다."""
    allowed = _numbers(facts, set())
    bad = []
    # '1만 8,000원'·'3만 원'처럼 만 단위로 쓴 금액도 원 단위로 읽는다(지시는 '18,000원' 형식이지만 검사는 값으로)
    for m in re.finditer(r'(?:(\d+)\s*만\s*)?(\d[\d,]*)?\s*원', text or ''):
        if not (m.group(1) or m.group(2)):
            continue
        n = int(m.group(1) or 0) * 10000 + int((m.group(2) or '0').replace(',', ''))
        if n not in allowed:
            bad.append(m.group(0).strip())
    for m in re.finditer(r'(\d+)\s*주(?![가-힣]*일)', text or ''):
        n = int(m.group(1))
        if n not in allowed and n > 4:  # '1주', '2주' 같은 작은 수는 문장 표현으로 허용
            bad.append(m.group(0))
    return bad


def check(text, facts):
    """문제가 있으면 이유(짧은 코드)를, 없으면 ''."""
    if banned_hits(text):
        return 'banned'
    if number_errors(text, facts):
        return 'numbers'
    if len((text or '').strip()) < 10:
        return 'empty'
    return ''


# ---------------------------------------------------------------
# 준비된 결과: ① 미리 만든 AI 결과(시연 데이터) ② 규칙 문장
# ---------------------------------------------------------------

def rule_text(feature, facts):
    if feature == 'letter':
        top = facts.get('가장 많이 쓴 카테고리')
        lines = [f"이번 주에 용돈 {won(facts['받은 용돈'])}을 받았어."]
        if facts['쓴 돈 합계']:
            lines.append(f"{won(facts['쓴 돈 합계'])}을 썼고, {top}에 가장 많이 썼구나.")
        if facts['저금한 돈']:
            lines.append(f"저축통장에 {won(facts['저금한 돈'])}이나 모았어. 정말 멋져!")
        else:
            lines.append('쓴 돈을 꼼꼼히 적은 것도 아주 잘했어.')
        lines.append('다음 주에도 꿀벌이 응원할게! 🐝')
        return ' '.join(lines)
    if feature == 'coach':
        if not facts['목표 도달 가능']:
            return (f"목표까지 {won(facts['남은 금액'])} 남았어. 일주일에 {won(facts['일주일 저금액'])}씩이면 조금 오래 걸려. "
                    "저금액을 조금만 늘려 볼까?\n이번 주 할 일: 저금할 금액을 다시 골라 보기")
        return (f"일주일에 {won(facts['일주일 저금액'])}씩 모으면 {facts['목표까지 주 수(이자 포함)']}주 뒤에 목표에 닿아. "
                f"그동안 이자가 {won(facts['목표까지 받는 이자 합계'])} 도와줘.\n"
                f"이번 주 할 일: 저축통장에 {won(facts['일주일 저금액'])} 넣기")
    weekly = facts.get('주별 쓴 돈·저금') or []
    last = weekly[-1] if weekly else {'쓴 돈': 0, '저금': 0}
    cats = facts.get('카테고리별 쓴 돈(전체)') or {}
    top = max(cats.items(), key=lambda kv: kv[1])[0] if cats else '기타'
    return (f"소비 패턴: 이번 주에는 {won(last['쓴 돈'])}을 썼고, 전체로는 {top}에 가장 많이 썼어요. "
            f"저금 비율은 {facts['저금 비율(%)']}%예요.\n"
            f"칭찬 포인트:\n- 쓴 돈을 {facts['기록한 날 수']}일 동안 기록했어요.\n- 저축통장에 {facts['저금 횟수']}번 저금했어요.\n"
            f"대화 팁:\n- {top}에 쓴 돈이 어땠는지 아이에게 먼저 물어봐 주세요.\n- 다음 주 저금 목표를 함께 정해 보세요.")


def prepared_text(feature, facts):
    try:
        data = json.loads(PREPARED_PATH.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return None
    return (data.get(feature) or {}).get(facts_hash(feature, facts))


def fallback(feature, facts):
    """(글, 출처). 출처 'prepared'는 미리 만든 AI 글('AI가 작성했어요 · 미리 준비'), 'rule'은 규칙 문장(배지 없음)."""
    text = prepared_text(feature, facts)
    return (text, 'prepared') if text else (rule_text(feature, facts), 'rule')


# ---------------------------------------------------------------
# 보호 장치: 동시 호출 상한 + 대기열 순번, 1인 횟수, 하루 비용 상한
# ---------------------------------------------------------------

class Gate:
    """동시에 limit개까지. 넘치면 순번표를 받아 기다린다(최대 queue_max명). 순번은 대기열 표시용."""

    def __init__(self, limit, queue_max):
        self.limit, self.queue_max = limit, queue_max
        self.active, self.waiting = 0, deque()
        self.cond = None

    def _cond(self):
        if self.cond is None:
            self.cond = asyncio.Condition()
        return self.cond

    def position(self, ticket):
        try:
            return self.waiting.index(ticket) + 1
        except ValueError:
            return 0

    async def acquire(self, wait_s, on_wait=None):
        cond = self._cond()
        async with cond:
            if self.active < self.limit and not self.waiting:
                self.active += 1
                return True
            if len(self.waiting) >= self.queue_max:
                return False
            ticket = object()
            self.waiting.append(ticket)
        deadline = time.monotonic() + wait_s
        last_pos = None
        try:
            while True:
                async with cond:
                    if self.active < self.limit and self.waiting and self.waiting[0] is ticket:
                        self.waiting.popleft()
                        self.active += 1
                        return True
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return False
                    pos = self.position(ticket)
                if on_wait and pos != last_pos:  # 잠금 밖에서 알린다(느린 전송이 다른 대기자를 막지 않게)
                    last_pos = pos
                    await on_wait(pos)
                async with cond:
                    try:
                        await asyncio.wait_for(cond.wait(), timeout=min(1.0, max(0.01, deadline - time.monotonic())))
                    except asyncio.TimeoutError:
                        pass
        finally:
            async with cond:
                if ticket in self.waiting:
                    self.waiting.remove(ticket)
                cond.notify_all()

    async def release(self):
        cond = self._cond()
        async with cond:
            self.active = max(0, self.active - 1)
            cond.notify_all()


_gate = {'gate': None}


def gate():
    cfg = config()
    g = _gate['gate']
    if g is None or (g.limit, g.queue_max) != (cfg['concurrency'], cfg['queue_max']):
        _gate['gate'] = g = Gate(cfg['concurrency'], cfg['queue_max'])
    return g


PER_FEATURE, PER_FEATURE_WINDOW, PER_HOUR = 3, 600, 12
_usage_lock = threading.Lock()
_person = {}


def person_allowed(digest, feature, now=None):
    """체험(토큰)마다 기능별 10분에 3번, 전체 1시간 12번. IP로는 막지 않는다(강의장 Wi-Fi는 같은 IP)."""
    now = now or time.time()
    with _usage_lock:
        hits = [h for h in _person.get(digest, []) if now - h[0] < 3600]
        same = [h for h in hits if h[1] == feature and now - h[0] < PER_FEATURE_WINDOW]
        if len(same) >= PER_FEATURE or len(hits) >= PER_HOUR:
            _person[digest] = hits
            return False
        hits.append((now, feature))
        _person[digest] = hits
        if len(_person) > 5000:
            _person.pop(next(iter(_person)))
        return True


def usage_path():
    return Path(env('MONEYON_AI_USAGE', 'runtime/ai_usage.json'))


def today_usage():
    try:
        data = json.loads(usage_path().read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        data = {}
    return data.get(datetime.now(KST).strftime('%Y-%m-%d'), {'usd': 0.0, 'calls': 0, 'fallbacks': 0})


def add_usage(model, input_tokens=0, output_tokens=0, fallback_used=False):
    pin, pout = PRICES.get(model, PRICES['claude-sonnet-5-5'])
    usd = input_tokens / 1e6 * pin + output_tokens / 1e6 * pout
    day = datetime.now(KST).strftime('%Y-%m-%d')
    with _usage_lock:
        try:
            data = json.loads(usage_path().read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError):
            data = {}
        row = data.setdefault(day, {'usd': 0.0, 'calls': 0, 'fallbacks': 0})
        row['usd'] = round(row['usd'] + usd, 6)
        row['calls'] += 1 if (input_tokens or output_tokens) else 0
        row['fallbacks'] += 1 if fallback_used else 0
        data = {k: data[k] for k in sorted(data)[-14:]}  # 2주만 보관
        usage_path().parent.mkdir(parents=True, exist_ok=True)
        tmp = usage_path().with_suffix('.tmp')
        tmp.write_text(json.dumps(data), encoding='utf-8')
        os.replace(tmp, usage_path())
    return usd


def budget_left():
    return today_usage()['usd'] < config()['daily_usd']


# ---------------------------------------------------------------
# 모델 호출(스트리밍)
# ---------------------------------------------------------------

def request_kwargs(feature, facts, model):
    system = PARENT_RULES if feature == 'parent' else KID_RULES
    kwargs = dict(model=model, max_tokens=700, system=system,
                  messages=[{'role': 'user', 'content': f"{TASKS[feature]}\n\n자료(JSON):\n{json.dumps(facts, ensure_ascii=False)}"}],
                  output_config={'effort': 'low'})
    # 첫 글자를 빨리: Haiku 5.5는 생각 끄기(effort high 이하에서 허용), Sonnet 5.5는 between_tools(도구가 없으니 사실상 끔).
    if model.startswith('claude-haiku-5'):
        kwargs['thinking'] = {'type': 'disabled'}
    elif model == 'claude-sonnet-5-5':
        kwargs['thinking'] = {'type': 'between_tools'}
    return kwargs


_client = {'c': None}


def async_client():
    if _client['c'] is None:
        key = env('ANTHROPIC_API_KEY')
        if not key:
            return None
        try:
            import anthropic
        except ImportError:
            return None
        _client['c'] = anthropic.AsyncAnthropic(api_key=key, max_retries=0, timeout=20)
    return _client['c']


async def fake_stream(feature, facts):
    """부하 테스트용(MONEYON_AI_FAKE=1): 3초 동안 규칙 문장을 글자 단위로 흘린다. 비용 0."""
    text = rule_text(feature, facts)
    step = max(1, len(text) // 30)
    for i in range(0, len(text), step):
        await asyncio.sleep(0.1)
        yield text[i:i + step]

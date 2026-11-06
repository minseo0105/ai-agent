"""공식 14단계를 화면 8단계 타임라인으로 바꾼다. 표현 계층이며 DB 값·단계 판정은 바꾸지 않는다.

원칙(설계 §3): 공식 정보가 항상 우선한다. 화면의 8단계와 유형별 흐름은 안내용 규칙이고,
공식 날짜가 있으면 안내용 흐름과 무관하게 그대로 보여 준다. 공식 데이터에 없는 단계를
도달로 추정하지 않는다. 예외는 '공식 현재 단계가 그 단계보다 뒤에 있는 경우'의 지난 단계뿐이며,
그때도 '일자 미공개'로 따로 표시한다. 법적 거래 가능 여부는 판정하지 않는다.
"""
import re

# 서울시 정비사업 정보몽땅 상세 페이지의 단계 목록(유형과 무관하게 같다).
OFFICIAL_ORDER = ['기본계획수립', '안전진단', '정비구역지정', '조합설립추진위원회승인', '조합설립인가',
                  '사업시행인가', '관리처분인가', '철거신고', '착공신고', '일반분양승인', '준공인가',
                  '이전고시', '조합해산', '조합청산']
_INDEX = {name: i for i, name in enumerate(OFFICIAL_ORDER)}
CLOSING_FROM = _INDEX['조합해산']

# 목록 기반 사업은 공식 이름이 아니라 화면용 라벨로 현재 단계를 갖는다. 같은 단계로 이어 준다.
_LABEL_ALIASES = {
    '조합설립인가': '조합설립인가', '추진위원회승인': '조합설립추진위원회승인',
    '사업시행인가': '사업시행인가', '관리처분인가': '관리처분인가', '철거': '철거신고', '착공': '착공신고',
    '준공': '준공인가', '분양': '일반분양승인', '정비구역지정': '정비구역지정', '안전진단': '안전진단',
    '이전고시': '이전고시', '조합해산': '조합해산', '조합청산': '조합청산',
}

# (key, 화면 라벨, 공식 단계명, 주요 의미, 거래·권리 확인 질문). 질문형이며 법적 판정을 하지 않는다.
_STEPS = [
    ('ZONE_DESIGNATION', '정비구역 지정', ['정비구역지정'],
     '정비사업을 할 구역의 범위가 공식적으로 정해진 단계예요.',
     ['보는 물건이 지정된 구역 범위 안에 있는지 확인', '권리산정기준일이 언제로 정해졌는지 확인']),
    ('COMMITTEE', '추진위원회 승인', ['조합설립추진위원회승인'],
     '조합 설립을 준비하는 추진위원회가 승인된 단계예요.',
     ['주민 동의 현황과 추진 속도 확인', '조합 설립 이후 적용되는 거래 조건이 있는지 미리 확인']),
    ('ASSOCIATION', '조합설립 인가', ['조합설립인가'],
     '조합이 법적으로 설립돼 사업의 주체가 정해진 단계예요.',
     ['조합원 지위 양도 제한이 시작되는 시점은 유형·지역에 따라 달라요. 이 단계가 그 시점의 전인지 후인지 관할 구청·조합에 확인',
      '조합원 분양 대상 요건이 무엇인지 확인']),
    ('IMPLEMENTATION', '사업시행계획 인가', ['사업시행인가'],
     '건축 계획과 세대 구성 등 사업 내용이 인가된 단계예요.',
     ['사업계획상 세대 구성과 예상 분담금 확인', '관리처분 일정과 소송·민원 여부 확인']),
    ('MANAGEMENT', '관리처분계획 인가', ['관리처분인가'],
     '조합원별 분양 대상과 권리가액·분담금이 정해지는 단계예요.',
     ['내 권리가액, 분양 대상 평형, 추가분담금 확인', '조합원 지위 양도 제한이 시작되는 시점의 전인지 후인지 확인',
      '분양 신청 여부와 현금청산 대상이 될 가능성 확인']),
    ('RELOCATION', '이주·철거', ['철거신고'],
     '조합원이 이주하고 기존 건물을 철거하는 단계예요. 이주 시점은 공식 데이터에 별도 항목이 없어요.',
     ['이주 기간 중 거주와 자금 계획 확인', '이주비 대출 등 금융 조건이 달라지는지 확인']),
    ('CONSTRUCTION', '착공', ['착공신고'],
     '실제 공사가 시작된 단계예요.',
     ['준공·입주 예상 시점과 공사비 변동 확인', '총 부담 비용 확인']),
    ('COMPLETION', '준공·이전고시', ['준공인가', '이전고시'],
     '건물이 완공되고 소유권을 새 주택으로 정리하는 단계예요. 준공인가와 이전고시를 각각 표시해요.',
     ['등기와 정산 상태 확인', '청산금 정산 항목 확인']),
]
_NEXT_LABEL = {i: (_STEPS[i + 1][1] if i + 1 < len(_STEPS) else None) for i in range(len(_STEPS))}

_PRE = [('기본계획수립', '기본계획 수립'), ('안전진단', '안전진단')]
_EXTRA = [('일반분양승인', '일반분양 승인')]
_CLOSING = [('조합해산', '조합 해산'), ('조합청산', '조합 청산')]

GUIDE_NOTE = ('8단계는 안내용 요약입니다. 공식 데이터는 단계 이름과 날짜만 제공하며, '
              '둘이 다르면 공식 정보를 우선 표시합니다.')
_FLOWS = {
    'REDEVELOPMENT': ('재개발', '재개발은 일반적으로 안전진단을 거치지 않습니다. 공식 기록이 있으면 표시합니다. '
                               '이 흐름은 안내용 규칙이며 공식 사실이 아닙니다.'),
    'RECONSTRUCTION': ('재건축', '재건축은 안전진단이 사전 단계입니다. 이 흐름은 안내용 규칙이며 공식 사실이 아닙니다.'),
    'GENERIC': ('정비사업', '이 유형의 별도 절차는 정의하지 않았습니다. 공식 단계 이름을 그대로 표시합니다.'),
}
CLOSING_NOTE = ('사업 종료 기록(조합 해산·청산)이 있습니다. 사업이 끝났는지 중단됐는지는 공식 자료로 별도 확인이 필요합니다.')
UNVERIFIED_NOTE = ('공식 상세 확인 전이라 단계별 진행은 표시하지 않습니다. 서울시 공식 목록 기준의 현재 단계만 보여 줍니다.')


def _compact(value):
    return re.sub(r'\s+', '', value or '')


def flow_of(project_type):
    code = project_type if project_type in ('REDEVELOPMENT', 'RECONSTRUCTION') else 'GENERIC'
    label, note = _FLOWS[code]
    return {'code': code, 'label': label, 'note': note, 'basis': 'GUIDE_RULE'}


def _official_name(name):
    """공식 이름 또는 화면용 라벨을 공식 14단계 이름으로. 모르면 None."""
    key = _compact(name)
    if key in _INDEX:
        return key
    return _LABEL_ALIASES.get(key)


def _date_of(milestone):
    """공식 날짜. 연도 2자리 원문은 세기를 추정하지 않고 원문 그대로 보여 준다."""
    if not milestone:
        return {'has_date': False, 'date': None, 'date_display': None, 'date_precision': None}
    raw = milestone.get('date_raw') or milestone.get('stage_date')
    precision = milestone.get('date_precision')
    iso = milestone.get('stage_date') if (precision == 'ISO_DATE' or
                                          re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(milestone.get('stage_date') or ''))) else None
    return {'has_date': bool(raw), 'date': iso, 'date_display': raw or None, 'date_precision': precision}


def _status(name, idx, dated, current_name, current_idx, closing):
    """공식 기록 우선. 위치로 추정하는 것은 '현재 단계보다 앞선 단계'의 지난 단계뿐."""
    if name is not None and name == current_name:  # None == None으로 '현재'가 되지 않게
        return 'CURRENT'
    if dated:
        return 'REACHED_DATED'
    if current_idx is None or closing:
        return 'NOT_RECORDED'
    if current_idx > idx:
        return 'REACHED_UNDATED'
    return 'UPCOMING'


def process_timeline(*, project_type, program, stage_history, current_official_stage, verified_level, source):
    """공식 단계 이력을 8단계 구조로. 입력을 수정하지 않는다."""
    flow = flow_of(project_type)
    current_name = _official_name(current_official_stage)
    current_idx = _INDEX.get(current_name)
    closing = current_idx is not None and current_idx >= CLOSING_FROM
    milestones = {}
    for item in stage_history or []:
        name = _compact(item.get('stage_name'))
        if name in _INDEX and name not in milestones:
            milestones[name] = item
    verified = verified_level == 'OFFICIAL_DETAIL_VERIFIED' and bool(milestones)
    standard_names = {n for step in _STEPS for n in step[2]}
    src = None if not source else {'name': source.get('name'), 'url': source.get('url'),
                                   'fetched_at': source.get('fetched_at')}
    result = {
        'verified': verified, 'flow': flow, 'guide_note': GUIDE_NOTE, 'source': src,
        'program_label': (program or {}).get('label') if isinstance(program, dict) else None,
        'current_official': {'name': current_official_stage or None, 'official_name': current_name,
                             'index': current_idx, 'recognised': current_name is not None,
                             'in_standard_steps': current_name in standard_names},
        'steps': [], 'pre_steps': [], 'extra_steps': [], 'closing_steps': [],
        'progress': None, 'closing_note': None, 'unverified_note': None,
    }
    if not verified:
        result['unverified_note'] = UNVERIFIED_NOTE
        return result

    def row(official, label):
        meta = _date_of(milestones.get(official))
        idx = _INDEX[official]
        status = _status(official, idx, meta['has_date'], current_name, current_idx, closing)
        return dict(meta, official_name=official, label=label, order_index=idx,
                    is_current=official == current_name, status=status)

    for index, (key, label, names, meaning, questions) in enumerate(_STEPS):
        subs = [row(n, n) for n in names]
        for sub in subs:
            sub.pop('label')
        has_date = any(s['has_date'] for s in subs)
        if len(names) == 1:
            sub = subs[0]
            status = sub['status']
            date = {k: sub[k] for k in ('date', 'date_display', 'date_precision')}
        else:
            current_in = any(s['is_current'] for s in subs)
            status = ('CURRENT' if current_in else 'REACHED_DATED' if has_date else
                      _status(None, max(_INDEX[n] for n in names), False, current_name, current_idx, closing))
            date = {'date': None, 'date_display': None, 'date_precision': None}
        step = {'order': index + 1, 'key': key, 'label': label, 'official_names': list(names),
                'status': status, 'has_date': has_date, 'applicability': 'STANDARD' if flow['code'] != 'GENERIC' else 'UNDEFINED',
                'meaning': meaning, 'next_label': _NEXT_LABEL[index], 'questions': list(questions),
                'doc': {'state': 'PROJECT_LEVEL_ONLY', 'url': (src or {}).get('url'),
                        'note': '단계별 문서 링크는 공식 데이터에 없습니다. 사업 상세 페이지로 연결합니다.'}}
        step.update(date)
        if len(names) > 1:
            step['sub_items'] = [{k: s[k] for k in ('official_name', 'date', 'date_display', 'date_precision', 'status')}
                                 for s in subs]
        result['steps'].append(step)

    for official, label in _PRE:
        item = row(official, label)
        skipped = flow['code'] == 'REDEVELOPMENT' and official == '안전진단'
        item['applicability'] = 'USUALLY_SKIPPED' if skipped else 'STANDARD' if (
            flow['code'] == 'RECONSTRUCTION' and official == '안전진단') else 'UNDEFINED'
        if item['status'] in ('UPCOMING', 'NOT_RECORDED', 'REACHED_UNDATED') and not item['has_date']:
            item['status'] = 'USUALLY_SKIPPED' if skipped else (
                'UPCOMING' if current_idx is not None and current_idx < item['order_index'] and not closing
                else 'NOT_RECORDED')
        result['pre_steps'].append(item)
    result['extra_steps'] = [row(o, l) for o, l in _EXTRA]
    result['closing_steps'] = [dict(row(o, l), status=('CURRENT' if o == current_name else
                                                      'REACHED_DATED' if _date_of(milestones.get(o))['has_date'] else 'NOT_RECORDED'))
                               for o, l in _CLOSING]

    if closing:
        result['closing_note'] = CLOSING_NOTE
    elif current_idx is not None:
        reached = [s for s in result['steps'] if s['status'] in ('CURRENT', 'REACHED_DATED', 'REACHED_UNDATED')]
        dated = [s for s in reached if s['has_date']]
        result['progress'] = {
            'reached': len(reached), 'dated': len(dated), 'total': len(_STEPS),
            'phrase': f'8개 주요 단계 중 {len(reached)}단계 도달 (일자 확인 {len(dated)})'}
    return result

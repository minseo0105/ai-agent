"""정비사업 단계별 투자 접근 안내와 데이터 신선도 판정.

둘 다 표현 계층이다. DB 값이나 단계 판정을 바꾸지 않는다.

- investor_guide: 단계마다 '일반적으로' 어떤 성격의 위험이 있는지와 무엇을 확인하는지.
  특정 사업의 전망이나 수익을 말하지 않고, 법규·세금·대출 수치도 적지 않는다
  (지역과 시점에 따라 달라지므로 확인 대상으로만 안내한다).
- freshness: 마지막 공식 확인일이 오래됐는지. 날짜가 없으면 '최신'으로 보지 않는다.
"""
from datetime import datetime, timezone

STALE_AFTER_DAYS = 14
PHASES = ('EARLY', 'MID', 'LATE', 'DONE', 'STOPPED', 'UNKNOWN')
RISK_LEVELS = ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')
PHASE_LABELS = {'EARLY': '초기', 'MID': '중기', 'LATE': '후기', 'DONE': '완료 이후',
                'STOPPED': '중단·종료', 'UNKNOWN': '확인 중'}
RISK_LABELS = {'HIGH': '불확실성 큼', 'MEDIUM': '불확실성 중간', 'LOW': '불확실성 작음',
               'UNKNOWN': '확인 중'}
DISCLAIMER = ('이 내용은 단계별 일반 정보이며 투자 권유가 아닙니다. 이 사업에서 확인된 사실도 '
              '아닙니다. 거래 규제·세금·대출 조건은 지역과 시점에 따라 달라 매수 전에 관할 '
              '구청, 공인중개사, 전문가에게 반드시 확인하세요.')

# stage: (phase, risk_level, risk_note, watch_next, pitfalls)
_GUIDE = {
    'CANDIDATE': (
        'EARLY', 'HIGH',
        '후보지 단계라 실제 사업으로 이어질지 자체가 불확실하고, 기간도 가장 길 수 있어요.',
        ('정비계획 수립 착수 여부', '주민 동의와 반대 움직임'),
        ('기대감이 가격에 먼저 반영돼 있을 수 있음', '사업이 무산되면 보유 기간만 길어짐',
         '구역 범위가 바뀌면 내 물건이 빠질 수 있음')),
    'PLANNING': (
        'EARLY', 'HIGH',
        '계획이 바뀔 수 있는 단계라 구역 범위와 사업 방식이 아직 정해지지 않았어요.',
        ('정비계획안 공람·심의 일정', '구역 경계 변경 여부'),
        ('계획안과 최종 고시 내용이 다를 수 있음', '자금이 오래 묶일 수 있음')),
    'PLAN_DELIBERATION': (
        'EARLY', 'HIGH',
        '심의 결과에 따라 계획이 조정되거나 보류될 수 있어요.',
        ('심의 통과·보류 결과', '조정된 구역 범위'),
        ('심의 결과를 단정하고 매수하면 일정이 밀릴 수 있음',)),
    'PLAN_NOTICED': (
        'EARLY', 'MEDIUM',
        '정비계획이 고시돼 방향은 정해졌지만 실제 추진 조직과 동의 확보는 이제부터예요.',
        ('권리산정기준일', '추진위원회 구성 움직임'),
        ('고시 이후에도 주민 갈등으로 지연될 수 있음',
         '기준일 이후 취득은 권리 인정 범위가 달라질 수 있음')),
    'DESIGNATED': (
        'EARLY', 'MEDIUM',
        '정비구역이 지정돼 사업의 틀은 생겼지만 추진 주체와 세부 계획은 아직이에요.',
        ('추진위원회·조합 설립 진행', '권리산정기준일', '거래 관련 규제 적용 여부'),
        ('구역 지정이 곧 사업 확정은 아님', '지분 쪼개기 등으로 권리 인정이 제한될 수 있음')),
    'IMPLEMENTER_DESIGNATED': (
        'MID', 'MEDIUM',
        '시행 주체가 정해졌지만 사업 방식에 따라 주민 부담과 권리 구조가 달라져요.',
        ('사업 방식과 주민 동의', '사업시행계획 일정'),
        ('시행 방식별 권리 차이를 확인하지 않고 접근하는 경우',)),
    'SAFETY_DIAGNOSIS': (
        'EARLY', 'HIGH',
        '재건축 가능 여부를 가르는 절차라 결과에 따라 사업이 멈출 수 있어요.',
        ('진단 결과 등급', '결과 이후 정비구역 지정 절차'),
        ('진단 통과가 사업 확정은 아님', '결과가 기대에 못 미치면 장기 정체될 수 있음')),
    'COMMITTEE': (
        'MID', 'MEDIUM',
        '추진 조직이 생겼지만 조합 설립에 필요한 동의를 얻는 과정에서 속도가 갈려요.',
        ('조합설립 동의율 진행', '추진위 내부 갈등 여부', '권리산정기준일'),
        ('추진위가 있어도 조합 설립이 지연되거나 무산될 수 있음',
         '조합 설립 이후 조합원 지위 승계 제한을 받는지 미리 확인')),
    'ASSOCIATION_APPROVED': (
        'MID', 'MEDIUM',
        '조합이 설립돼 사업이 본격화됐지만, 이 시점부터 거래와 조합원 자격에 제한이 걸리는 '
        '지역이 있어요.',
        ('조합원 지위 승계(양도) 가능 여부', '사업시행 인가 일정', '추정 분담금'),
        ('물건을 샀는데 입주 권리를 받지 못하는 경우', '분담금이 예상보다 커질 수 있음',
         '대출 가능 범위가 일반 주택과 다를 수 있음')),
    'IMPLEMENTATION_APPROVED': (
        'MID', 'MEDIUM',
        '사업계획이 구체화돼 불확실성은 줄었지만 이후 관리처분과 이주 단계가 남아 있어요.',
        ('조합원 분양 신청 시기', '시공사 선정·공사비', '관리처분 일정'),
        ('공사비 상승이 분담금에 반영될 수 있음', '소송·민원으로 일정이 밀릴 수 있음')),
    'MANAGEMENT_DISPOSITION': (
        'LATE', 'MEDIUM',
        '권리와 분담금 구조가 상당히 확정되는 단계예요. 다만 이주·철거와 실제 공사가 남았어요.',
        ('내 권리가격과 분담금', '이주·철거 일정', '조합원 자격 유지 조건'),
        ('권리가액 대비 분담금을 확인하지 않은 매수', '이주 기간 중 거주·자금 부담',
         '전매·거래 제한 여부를 모르고 접근하는 경우')),
    'SALES': (
        'LATE', 'MEDIUM',
        '분양 절차 단계라 내가 취득하는 것이 조합원 권리인지 일반 분양인지에 따라 조건이 달라요.',
        ('취득 권리의 종류', '계약 조건과 납부 일정'),
        ('권리 종류에 따라 전매 제한과 대출 조건이 달라짐',)),
    'DEMOLITION': (
        'LATE', 'MEDIUM',
        '철거·이주 단계라 공사 착수까지 일정이 남아 있고 추가 비용 가능성이 있어요.',
        ('철거 완료와 착공 시점', '이주비·추가 비용 정산'),
        ('이주 지연이 전체 일정을 늦출 수 있음',)),
    'CONSTRUCTION': (
        'LATE', 'LOW',
        '공사가 시작돼 사업 무산 위험은 줄었지만 공사 지연과 비용 변동은 남아 있어요.',
        ('준공·입주 예상 시점', '공사비 증액 여부', '총 부담 비용'),
        ('공사 지연으로 입주가 늦어질 수 있음', '분담금 정산이 입주 직전에 확정될 수 있음')),
    'PARTIAL_COMPLETION': (
        'LATE', 'LOW',
        '일부만 준공된 상태라 남은 공정과 입주 조건을 따로 확인해야 해요.',
        ('남은 공정과 일정', '내 동·호수의 준공 여부'),
        ('일부 준공을 전체 준공으로 오해하는 경우',)),
    'COMPLETED': (
        'DONE', 'LOW',
        '사업이 마무리돼 신축 주택으로 보면 돼요. 개발 기대감이 아니라 현재 시세 기준으로 봐야 해요.',
        ('등기·정산 상태', '실제 매물의 거래 조건'),
        ('개발 호재가 이미 가격에 반영돼 있을 수 있음',)),
    'TRANSFER_NOTICE': (
        'DONE', 'LOW',
        '소유권 정리 단계라 사업 위험은 작지만 정산과 등기 상태가 남아 있을 수 있어요.',
        ('등기 완료 여부', '남은 청산·정산 항목'),
        ('청산 정산금이 거래 가격에 영향을 줄 수 있음',)),
    'ASSOCIATION_DISSOLVED': (
        'STOPPED', 'HIGH',
        '조합 해산이 기록돼 있어요. 사업이 끝났는지 중단됐는지는 공식 자료로 따로 확인해야 해요.',
        ('공식 사업정보의 현재 상태', '해산 사유와 이후 계획'),
        ('해산을 사업 완료로 착각하는 경우', '중단된 사업이면 가격 기대의 근거가 사라질 수 있음')),
    'ASSOCIATION_LIQUIDATION': (
        'STOPPED', 'HIGH',
        '조합 청산 절차가 기록돼 있어요. 종료 여부는 공식 자료로 확인이 필요해요.',
        ('공식 사업정보의 현재 상태', '남은 정산 항목'),
        ('청산을 완료로 단정하는 경우',)),
    'CANCELLED': (
        'STOPPED', 'HIGH',
        '사업이 취소된 것으로 기록돼 있어요. 개발을 전제로 한 접근은 근거가 없어요.',
        ('구역 해제 여부와 이후 재추진 계획',),
        ('취소된 사업의 기대감이 가격에 남아 있을 수 있음',)),
}

_UNKNOWN = {
    'stage': 'UNKNOWN', 'interpreted': False, 'phase': 'UNKNOWN', 'phase_label': PHASE_LABELS['UNKNOWN'],
    'risk_level': 'UNKNOWN', 'risk_label': RISK_LABELS['UNKNOWN'],
    'risk_note': '공식 자료에서 현재 단계가 확인되지 않아 단계별 안내를 드릴 수 없어요.',
    'watch_next': ['공식 사업정보에서 현재 단계 확인'], 'pitfalls': [], 'disclaimer': DISCLAIMER,
}


def investor_guide(normalized_stage):
    """단계 하나에 대한 일반적인 투자 접근 안내. 확인된 사실과 섞지 않도록 별도 블록."""
    known = _GUIDE.get(normalized_stage)
    if not known:
        return dict(_UNKNOWN, watch_next=list(_UNKNOWN['watch_next']), pitfalls=[])
    phase, risk, note, watch, pitfalls = known
    return {'stage': normalized_stage, 'interpreted': True,
            'phase': phase, 'phase_label': PHASE_LABELS[phase],
            'risk_level': risk, 'risk_label': RISK_LABELS[risk], 'risk_note': note,
            'watch_next': list(watch), 'pitfalls': list(pitfalls), 'disclaimer': DISCLAIMER}


def _parse(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def freshness(checked_values, *, now=None, stale_after_days=STALE_AFTER_DAYS):
    """가장 최근 단계 정보 수집일 기준 신선도(공식 확인일이 아니다). 읽을 수 있는 날짜가 없으면 unknown."""
    now = now or datetime.now(timezone.utc)
    dates = [d for d in (_parse(v) for v in checked_values or []) if d]
    if not dates:
        return {'state': 'unknown', 'stale': None, 'latest': None, 'age_days': None,
                'threshold_days': stale_after_days,
                'label': '단계 정보 수집일이 없어 최신 여부를 알 수 없어요.'}
    latest = max(dates)
    age = max((now.date() - latest.astimezone(timezone.utc).date()).days, 0)
    stale = age > stale_after_days
    day = latest.astimezone(timezone.utc).date().isoformat()
    label = (f'단계 정보 수집일이 {age}일 전({day})이라 최신이 아닐 수 있어요.' if stale
             else f'단계 정보 수집일 {day} ({age}일 전)')
    return {'state': 'stale' if stale else 'fresh', 'stale': stale, 'latest': day,
            'age_days': age, 'threshold_days': stale_after_days, 'label': label}

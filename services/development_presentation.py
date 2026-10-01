"""User-facing wording for development-project data.

The database and the canonical artifacts speak in enums (NEEDS_REVIEW,
ASSOCIATION_APPROVED, UNKNOWN_OFFICIAL_COLUMN). None of that belongs on screen,
and neither does a claim the evidence does not support: a stage read from an
official list is shown as list-based, never as confirmed.
"""
import re

from services.development_official import STATUS_FROM_STAGE, STATUS_HYPOTHESIS, normalize_stage
from services.development_stage import observation, stage_view, DESCRIPTIONS


STAGE_LABELS = {
    'CANDIDATE': '후보지 선정', 'PLANNING': '정비계획 수립', 'PLAN_DELIBERATION': '심의 진행',
    'PLAN_NOTICED': '정비계획 고시', 'DESIGNATED': '정비구역 지정',
    'IMPLEMENTER_DESIGNATED': '시행자 지정', 'SAFETY_DIAGNOSIS': '안전진단',
    'COMMITTEE': '추진위원회 승인', 'ASSOCIATION_APPROVED': '조합설립 인가',
    'IMPLEMENTATION_APPROVED': '사업시행 인가', 'MANAGEMENT_DISPOSITION': '관리처분 인가',
    'SALES': '분양', 'DEMOLITION': '철거', 'CONSTRUCTION': '착공',
    'PARTIAL_COMPLETION': '부분 준공', 'COMPLETED': '준공', 'TRANSFER_NOTICE': '이전고시',
    'ASSOCIATION_DISSOLVED': '조합 해산', 'ASSOCIATION_LIQUIDATION': '조합 청산',
    'CANCELLED': '취소', 'UNKNOWN': '세부 진행단계 확인 중',
}
# SHINTONG은 정책 프로그램으로 수집된 행이라 사업유형(재개발/재건축)은 아직 확정되지 않았다.
# 유형 자리에 프로그램 이름을 넣지 않는다.
TYPE_LABELS = {'RECONSTRUCTION': '재건축', 'REDEVELOPMENT': '재개발', 'MOATOWN': '모아타운',
               'MOAHOUSE': '모아주택', 'SHINTONG': '정비사업', 'FAST_TRACK': '정비사업',
               'MAINTENANCE_AREA': '정비구역', 'STATION_AREA': '역세권',
               'DISTRICT_UNIT_PLAN': '지구단위계획', 'PUBLIC_HOUSING': '공공주택',
               'URBAN_DEVELOPMENT': '도시개발', 'TRANSPORT': '교통', 'OTHER': '기타'}
PROGRAM_LABELS = {'FAST_TRACK': '신속통합기획', 'MOATOWN': '모아타운'}
STATUS_LABELS = {'ACTIVE': '진행 중', 'COMPLETED': '완료', 'CANCELLED': '취소',
                 'WITHDRAWN': '지정 해제', 'SUSPENDED': '중단', 'UNKNOWN': '공식 확인 진행 중'}
# What the reader may rely on. Presence in an official list is not confirmation.
TRUST_LABELS = {
    'VERIFIED': {'label': '공식 확인', 'tone': 'ok',
                 'note': '서울시 공식 상세정보로 확인된 내용입니다.'},
    'NEEDS_REVIEW': {'label': '공식자료 확인', 'tone': 'info',
                     'note': '서울시 공식 목록에서 확인한 내용입니다. 상세 확인은 계속 진행 중입니다.'},
    'UNVERIFIED': {'label': '공식자료 확인', 'tone': 'info',
                   'note': '서울시 공식 목록에 공개된 값입니다.'},
    'MISSING_FROM_SOURCE': {'label': '최근 목록 미게재', 'tone': 'warn',
                            'note': '최근 공식 목록에서 확인되지 않았습니다. 취소나 종료를 뜻하지 않습니다.'},
    'REJECTED': {'label': '검토 제외', 'tone': 'muted', 'note': '검토에서 제외된 자료입니다.'},
}
STAGE_BASIS_LABELS = {'OFFICIAL_DETAIL_PAGE': '공식 상세정보 확인',
                      'OFFICIAL_LIST_CELL': '서울시 공식 목록 확인', None: '서울시 공식 목록 확인'}
# official-list-mapped와 official-detail-verified를 절대 같게 표시하지 않는다.
STAGE_VERIFIED_LEVEL = {'OFFICIAL_DETAIL_PAGE': 'OFFICIAL_DETAIL_VERIFIED',
                        'OFFICIAL_LIST_CELL': 'OFFICIAL_LIST_MAPPED', None: 'OFFICIAL_LIST_MAPPED'}
# 사용자에게 보여주는 단계 진행 순서. 공식 자료에 없는 단계는 추정하지 않는다.
STAGE_TIMELINE = (('CANDIDATE', '후보지'), ('PLANNING', '정비계획'), ('DESIGNATED', '정비구역 지정'),
                  ('COMMITTEE', '추진위원회'), ('ASSOCIATION_APPROVED', '조합설립'),
                  ('IMPLEMENTATION_APPROVED', '사업시행인가'),
                  ('MANAGEMENT_DISPOSITION', '관리처분인가'), ('DEMOLITION', '이주·철거'),
                  ('CONSTRUCTION', '착공'), ('COMPLETED', '준공'), ('TRANSFER_NOTICE', '이전고시'))
# 타임라인에 자리가 없는 공식 단계는 가장 가까운 앞 단계에 붙여 표시한다.
STAGE_TIMELINE_ALIAS = {'PLAN_DELIBERATION': 'PLANNING', 'PLAN_NOTICED': 'PLANNING',
                        'SAFETY_DIAGNOSIS': 'PLANNING', 'IMPLEMENTER_DESIGNATED': 'DESIGNATED',
                        'SALES': 'CONSTRUCTION', 'PARTIAL_COMPLETION': 'COMPLETED',
                        'ASSOCIATION_DISSOLVED': None, 'ASSOCIATION_LIQUIDATION': None,
                        'CANCELLED': None, 'UNKNOWN': None}
# 정책 프로그램은 근거가 있는 경우만. project_type과 혼동하지 않는다.
# 모아타운·모아주택은 사업체계 자체로 유형에 표시되므로 프로그램을 중복 표기하지 않는다.
PROGRAM_FROM_TYPE = {'SHINTONG': 'FAST_TRACK'}
PROGRAM_LABELS_ALL = {'FAST_TRACK': '신속통합기획', 'MOATOWN': '모아타운', 'MOAHOUSE': '모아주택'}
# 지도 표시 정확도. 대표 위치만으로 구역 내부를 말하지 않는다.
LOCATION_ACCURACY = {
    'OFFICIAL_BOUNDARY': {'label': '공식 경계', 'note': '공식 GIS 경계가 확인된 사업입니다.'},
    'REPRESENTATIVE_POINT': {'label': '대표 위치', 'note': '대표 주소 좌표입니다. 구역 내부 여부는 판별하지 않습니다.'},
    'NO_LOCATION': {'label': '위치 데이터 준비 중', 'note': '아직 좌표를 확보하지 못해 지도에 표시하지 않습니다.'},
}
DISTANCE_BUCKETS = ((100, '100m 이내'), (300, '300m 이내'), (500, '500m 이내'), (1000, '1km 이내'))
INSIDE_UNKNOWN_NOTICE = '아직 정확한 구역 경계를 확보하지 못해 구역 내부 여부는 판별하지 않았습니다.'
NO_TRADE_POINT_NOTICE = '이 거래의 정확한 좌표가 확보되면 주변 개발사업과의 거리를 계산합니다.'
# Spatial wording. INSIDE is only ever shown for a verified boundary.
RELATION_LABELS = {'INSIDE': '정비구역 내부', 'NEARBY': '주변 개발사업',
                   'UNKNOWN': '위치 확인 필요', 'OUTSIDE': '해당 없음'}
DATE_ROLE_LABELS = {'UNKNOWN_OFFICIAL_COLUMN': '공식 목록에 표기된 날짜 (항목 확인 필요)'}
NO_LOCATION_NOTICE = '정확한 위치 확인 후 주변 개발정보를 연결할 수 있습니다.'



# ---------------------------------------------------------------------------
# 매수자 관점의 단계 해석.
#
# 공식 단계값(normalized_stage)은 그대로 두고, 그 위에 "쉽게 말하면"과
# "매수 전 체크"만 덧붙인다. 새 단계를 만들거나 공식 데이터를 바꾸지 않는다.
#
# 지키는 선:
#   * 투자 판단을 하지 않는다. 매수 적기·유망·수익 같은 말을 쓰지 않는다.
#   * 단계가 뒤라고 더 좋은 매수 시점이라고 말하지 않는다.
#   * 확인된 사실과 일반 체크포인트를 섞지 않는다. 금액·날짜를 지어내지 않는다.
#   * 안전하게 해석할 수 없으면 해석하지 않는다.
# ---------------------------------------------------------------------------
STAGE_GUIDE = {
    'CANDIDATE': (
        '아직 사업 초기 단계예요. 개발 가능성은 있지만 실제 사업까지 오래 걸리거나 '
        '계획이 바뀔 수도 있어요.',
        ('실제 대상 구역인지 확인', '사업 추진 근거 확인', '앞으로의 일정 확인')),
    'PLANNING': (
        '개발계획이 구체화되고 있는 단계예요.',
        ('예정 구역 범위 확인', '권리 기준 확인', '계획 변경 가능성 확인')),
    'PLAN_DELIBERATION': (
        '계획안을 심의받고 있는 단계예요. 내용이 조정될 수 있어요.',
        ('심의 결과 확인', '구역 범위 변경 가능성 확인', '앞으로의 일정 확인')),
    'PLAN_NOTICED': (
        '정비계획이 공식적으로 고시된 단계예요.',
        ('고시된 구역 범위 확인', '권리산정기준일 확인', '거래 관련 조건 확인')),
    'DESIGNATED': (
        '공식적인 정비사업 구역이 된 단계예요.',
        ('보는 매물이 실제 구역 안인지 확인', '권리산정기준일 확인', '거래·권리 관련 조건 확인')),
    'IMPLEMENTER_DESIGNATED': (
        '사업을 시행할 주체가 정해진 단계예요.',
        ('시행 주체 확인', '사업 방식 확인', '앞으로의 일정 확인')),
    'SAFETY_DIAGNOSIS': (
        '재건축을 위한 안전진단 절차가 진행되는 단계예요.',
        ('진단 결과와 다음 절차 확인', '사업 추진 일정 확인', '권리 기준 확인')),
    'COMMITTEE': (
        '사업을 추진할 조직이 만들어지고 있는 단계예요.',
        ('주민 동의 현황 확인', '사업 진행 속도 확인', '권리산정기준일 확인')),
    'ASSOCIATION_APPROVED': (
        '사업을 추진할 조합이 공식적으로 만들어져 사업이 본격화된 단계예요.',
        ('조합원 지위 승계 가능 여부 확인', '권리산정기준일 확인', '추가분담금 확인')),
    'IMPLEMENTATION_APPROVED': (
        '어떻게 개발할지가 상당히 구체화된 단계예요.',
        ('사업계획 확인', '예상 분담금 확인', '권리관계 확인', '앞으로의 일정 확인')),
    'MANAGEMENT_DISPOSITION': (
        '새 주택 배분과 비용 부담 구조가 상당히 구체화된 단계예요.',
        ('입주권·분양권 관련 권리 확인', '조합원 지위 확인', '추가분담금 확인', '거래 가능 여부 확인')),
    'SALES': (
        '분양 절차가 진행되는 단계예요.',
        ('취득하게 되는 권리의 종류 확인', '분양 조건 확인', '총 부담 비용 확인')),
    'DEMOLITION': (
        '기존 건물을 비우거나 철거하는 사업 후반 단계예요.',
        ('취득하게 되는 권리의 종류 확인', '추가 비용 확인', '입주 예상 일정 확인')),
    'CONSTRUCTION': (
        '실제 공사가 시작된 단계예요.',
        ('취득 권리 확인', '총 부담 비용 확인', '준공·입주 예상 일정 확인')),
    'PARTIAL_COMPLETION': (
        '일부가 준공된 단계예요. 남은 공정이 있을 수 있어요.',
        ('남은 공정과 일정 확인', '취득 권리 확인', '입주 조건 확인')),
    'COMPLETED': (
        '정비사업이 사실상 완료된 단계예요.',
        ('신축 주택 관점의 가격 확인', '입주·등기 상태 확인', '실제 매물 조건 확인')),
    'TRANSFER_NOTICE': (
        '새 주택의 소유권을 정리하는 절차까지 끝나가는 단계예요.',
        ('등기 상태 확인', '실제 매물 조건 확인', '남은 정산 항목 확인')),
    'ASSOCIATION_DISSOLVED': (
        '조합이 해산된 상태로 기록되어 있어요. 사업이 끝났는지 중단됐는지는 '
        '공식 자료로 확인이 필요해요.',
        ('공식 사업정보에서 현재 상태 확인', '해산 사유 확인', '해당 구역의 현재 계획 확인')),
    'ASSOCIATION_LIQUIDATION': (
        '조합 청산 절차가 기록되어 있어요. 사업 종료 여부는 공식 자료로 확인이 필요해요.',
        ('공식 사업정보에서 현재 상태 확인', '남은 정산 항목 확인', '해당 구역의 현재 계획 확인')),
}
# 해석할 근거가 없을 때. 억지로 풀지 않는다.
STAGE_GUIDE_UNKNOWN = (
    '공식 자료에서 현재 단계를 추가로 확인할 필요가 있어요.',
    ('공식 사업정보를 먼저 확인',))
# 일반 안내라는 것을 화면에서도 분명히 한다. 이 사업에서 확인된 값이 아니다.
BUYER_CHECK_NOTE = '이 사업에서 확인된 값이 아니라, 이 단계에서 일반적으로 확인하는 항목이에요.'


def stage_guide(normalized_stage):
    """단계 하나에 대한 쉬운 설명과 매수 전 체크 항목.

    확인된 사실(단계·인가일·출처)과 섞지 않도록 별도 블록으로 돌려준다.
    투자 판단은 하지 않는다.
    """
    known = STAGE_GUIDE.get(normalized_stage)
    plain, checks = known or STAGE_GUIDE_UNKNOWN
    return {'stage': normalized_stage or 'UNKNOWN',
            'label': STAGE_LABELS.get(normalized_stage or 'UNKNOWN', STAGE_LABELS['UNKNOWN']),
            'plain': plain, 'checks': list(checks),
            'interpreted': bool(known), 'checks_note': BUYER_CHECK_NOTE}


# ---------------------------------------------------------------------------
# 네이버부동산 연결. 지금은 링크를 만들지 않는다.
#
# 이 프로젝트에서 실제로 동작이 확인된 네이버 링크는 두 가지뿐이고, 둘 다 이 화면에
# 쓸 수 없다.
#   * services.realestate_monitor.build_naver_land_url —
#     m.land.naver.com/search/result/<검색어>. 운영에서 쓰이지만 검색어가 '잠실엘스
#     아파트'처럼 단지명이다. 개발사업이 가진 것은 '천호동 423-200' 같은 지번이고,
#     지번을 이 경로에 넣으면 엉뚱한 결과나 빈 화면이 된다(840a9dc의 실패 원인).
#   * services.golf_service — map.naver.com/p/search/<검색어>. 네이버 지도이고
#     네이버부동산이 아니다.
#
# 좌표를 중심으로 네이버부동산 지도를 여는 URL 구조는 이 저장소 어디에도 없고,
# land.naver.com / new.land.naver.com / m.land.naver.com은 이 환경에서 접근할 수
# 없어(HTTP 000) 형식을 확인할 수 없다. 확인하지 못한 파라미터를 넣으면 깨진 링크나
# 엉뚱한 위치가 되므로, 추측 대신 링크를 제공하지 않는다. 화면은 버튼을 감추고
# 이유를 적는다.
#
# 형식이 확인되면 아래 함수 하나만 고치면 된다. 호출부(present_project,
# DevelopmentCard)는 이미 None을 다루고 있어 수정이 필요 없다.
# 폴리곤 centroid는 쓰지 않는다. MultiPolygon이나 오목한 구역에서는 centroid가 구역
# 밖에 놓일 수 있다.
# ---------------------------------------------------------------------------
NAVER_LINK_UNAVAILABLE = 'NAVER_LAND_DEEPLINK_FORMAT_UNVERIFIED'
NO_LOCATION_LINK_NOTE = ('네이버부동산 지도를 이 사업 위치로 여는 링크 형식을 확인하지 '
                         '못해 연결을 제공하지 않습니다.')


def naver_real_estate_link(row):
    """네이버부동산 링크. 확인된 deep-link 형식이 없으므로 항상 None이다.

    틀린 위치로 보내는 것보다 연결하지 않는 것이 낫다. 좌표나 주소를 검증되지 않은
    URL 경로에 끼워 넣지 않는다.
    """
    return None


def stage_label(normalized_stage, raw_stage=None):
    label = STAGE_LABELS.get(normalized_stage or 'UNKNOWN', '세부 진행단계 확인 중')
    return {'label': label, 'official_text': (label if raw_stage in STAGE_LABELS and raw_stage != 'UNKNOWN'
                                             else None if raw_stage == 'UNKNOWN' else raw_stage or None)}


def trust(validation_status):
    return dict(TRUST_LABELS.get(validation_status or 'UNVERIFIED',
                                 TRUST_LABELS['UNVERIFIED']), code=validation_status or 'UNVERIFIED')


def relation(spatial_relation, *, boundary_verified=False):
    """A boundary that is not verified can never read as 정비구역 내."""
    code = spatial_relation or 'UNKNOWN'
    if code == 'INSIDE' and not boundary_verified:
        code = 'NEARBY'
    return {'code': code, 'label': RELATION_LABELS.get(code, RELATION_LABELS['UNKNOWN']),
            'confirmed_boundary': bool(boundary_verified and code == 'INSIDE')}


def present_project(row):
    """One development project, shaped for the screen. Input is a DB/RPC row."""
    # zipon_development_search는 project_stage / official_source / source_url / verified_at을
    # 돌려주고, REST 직접 조회는 stage_raw / source_name을 돌려준다. 둘 다 받는다.
    detail, listed = observation(row)
    verified = stage_view(detail)
    # RPC UNKNOWN/blank placeholders must not hide a known official-list stage.
    stage_raw = next((v.strip() for v in (row.get('stage_raw'), row.get('project_stage'),
                      row.get('stage'), listed.get('raw_stage'))
                      if isinstance(v, str) and v.strip() and v.strip() != 'UNKNOWN'), None)
    normalized = row.get('normalized_stage')
    if not normalized or normalized == 'UNKNOWN':
        normalized = stage_raw if stage_raw in STAGE_LABELS else normalize_stage(stage_raw)['normalized_stage']
    if verified:
        stage_raw = verified['label']
        normalized = normalize_stage(stage_raw)['normalized_stage']
    # 경계 검증 신호는 SQL의 geometry_verified에서만 온다. 대표좌표만으로는 True가 되지
    # 않는다. 공식 출처의 verified_at(evidence_verified)은 경계 확인이 아니므로 쓰지 않는다.
    verified_boundary = bool(row.get('boundary_verified') or row.get('geometry_verified'))
    spatial = relation(row.get('spatial_relation') or row.get('relation'),
                       boundary_verified=verified_boundary)
    latitude, longitude = row.get('latitude'), row.get('longitude')
    return {
        'project_id': row.get('project_id'),
        'name': row.get('project_name'),
        'official_id': row.get('external_id'),
        'official_authority': row.get('official_authority'),
        'type_label': TYPE_LABELS.get(row.get('project_type'), '기타'),
        'district': row.get('sigungu'), 'dong': row.get('dong'),
        'address': row.get('address'),
        'stage': dict(stage_label(normalized, stage_raw), **({'label': verified['label']} if verified else {})),
        # 확인된 사실(위)과 일반 안내(아래)를 섞지 않는다. 금액·날짜를 만들어 내지 않는다.
        'stage_guide': stage_guide(normalized),
        'naver_real_estate': naver_real_estate_link(row),
        'stage_description': verified['description'] if verified else DESCRIPTIONS.get(normalized),
        'stage_history': (detail or {}).get('milestones') or [],
        'stage_basis': '서울시 공식 상세정보 확인' if verified else STAGE_BASIS_LABELS.get(row.get('stage_basis'),
                                              STAGE_BASIS_LABELS['OFFICIAL_LIST_CELL']),
        'stage_verified_level': 'OFFICIAL_DETAIL_VERIFIED' if verified else STAGE_VERIFIED_LEVEL.get(row.get('stage_basis'),
                                                        'OFFICIAL_LIST_MAPPED'),
        'stage_timeline': verified['timeline'] if verified else dict(stage_timeline(normalized),
            steps=[stage_label(normalized)['label']] if normalized != 'UNKNOWN' else [],
            current_index=0 if normalized != 'UNKNOWN' else None,
            total=1 if normalized != 'UNKNOWN' else 0),
        'program': program_of(row),
        'program_label': (program_of(row) or {}).get('label'),
        'location_accuracy': location_accuracy(row),
        'status_label': STATUS_LABELS.get(row.get('status') or 'UNKNOWN', '공식 확인 진행 중'),
        'trust': trust(row.get('validation_status')),
        'official_source': {'name': '서울시 정비사업 정보몽땅' if verified else row.get('source_name') or row.get('official_source') or listed.get('source_name'),
                            'url': (detail or {}).get('evidence_url') or row.get('evidence_url') or row.get('source_url') or listed.get('source_url')},
        'last_checked': (detail or {}).get('fetched_at') or row.get('last_verified_at') or row.get('collected_at')
                        or row.get('verified_at') or listed.get('verified_at'),
        'spatial': spatial,
        'distance_m': row.get('meters') if row.get('meters') is not None else row.get('distance_m'),
        'distance_label': distance_bucket(
            row.get('meters') if row.get('meters') is not None else row.get('distance_m'),
            spatial['code']),
        # 카드가 자기 좌표를 들고 있어야 지도와 목록이 같은 위치를 말한다. 좌표가 있어도
        # 대표 위치일 뿐이므로 spatial 관계는 바뀌지 않고 INSIDE도 생기지 않는다.
        'latitude': latitude, 'longitude': longitude,
        'mappable': latitude is not None and longitude is not None,
        'has_location': spatial['code'] != 'UNKNOWN' or (latitude is not None
                                                         and longitude is not None),
        'location_notice': (None if spatial['code'] != 'UNKNOWN'
                            or (latitude is not None and longitude is not None)
                            else NO_LOCATION_NOTICE),
    }


def present_context(context):
    """The development block attached to one trade row."""
    if not context:
        return None
    spatial = relation(context.get('relation'), boundary_verified=False)
    projects = [present_project(p) for p in context.get('nearby_projects') or []]
    ready = context.get('status') == 'ok' and bool(projects)
    return {'label': spatial['label'] if ready else '위치 확인 필요',
            'available': ready, 'projects': projects,
            'notice': None if ready else NO_LOCATION_NOTICE,
            'reason_label': {'needs_geocode': '이 거래의 정확한 좌표가 아직 없습니다.',
                             'EXACT_ADDRESS_COORDINATES_REQUIRED': '정확한 주소 좌표가 필요합니다.',
                             'DEVELOPMENT_UNAVAILABLE': '개발정보를 잠시 불러올 수 없습니다.',
                             'NOT_CONFIGURED': '개발정보 저장소가 연결되지 않았습니다.',
                             'LOOKUP_BUDGET': '이번 조회에서는 확인하지 못했습니다.'}
                            .get(context.get('reason') or context.get('status'))}


def program_of(row):
    """정책 프로그램은 근거가 있을 때만. project_type과 별개로 표시한다."""
    code = row.get('program') or PROGRAM_FROM_TYPE.get(row.get('project_type'))
    if not code:
        return None
    return {'code': code, 'label': PROGRAM_LABELS_ALL.get(code, code)}


def stage_timeline(normalized_stage):
    """사용자 표시용 단계 진행. 공식 자료에 없는 단계는 추정하지 않는다."""
    anchor = STAGE_TIMELINE_ALIAS.get(normalized_stage, normalized_stage)
    codes = [code for code, _ in STAGE_TIMELINE]
    index = codes.index(anchor) if anchor in codes else None
    return {'steps': [label for _, label in STAGE_TIMELINE], 'current_index': index,
            'current_label': STAGE_LABELS.get(normalized_stage) if index is not None else None,
            'total': len(codes),
            'note': None if index is not None else '공식 자료로 확인된 진행 단계가 아직 없습니다.'}


def location_accuracy(row):
    if row.get('geometry_verified') and row.get('boundary'):
        code = 'OFFICIAL_BOUNDARY'
    elif row.get('latitude') is not None and row.get('longitude') is not None:
        code = 'REPRESENTATIVE_POINT'
    else:
        code = 'NO_LOCATION'
    return dict(LOCATION_ACCURACY[code], code=code)


def distance_bucket(meters, relation_code=None):
    if relation_code == 'INSIDE':
        return '구역 내부'
    if meters is None:
        return None
    for limit, label in DISTANCE_BUCKETS:
        if meters <= limit:
            return label
    return '1km 초과'


def inside_verdict(projects):
    """구역 내부 여부. 공식 경계가 확인된 사업만 '내부'라고 말한다."""
    confirmed = [p for p in projects if p['spatial']['confirmed_boundary']]
    if confirmed:
        return {'code': 'INSIDE', 'label': '정비구역 내부', 'project': confirmed[0]['name'],
                'notice': None}
    return {'code': 'NOT_DETERMINED', 'label': '아직 판별할 수 없음', 'project': None,
            'notice': INSIDE_UNKNOWN_NOTICE}


def impact(context, *, trade_has_point=None):
    """실거래 카드의 '개발사업 영향' 블록. 내부 상태값은 노출하지 않는다."""
    projects = (context or {}).get('projects') or []
    nearest = next((p for p in projects if p['distance_m'] is not None), projects[0] if projects else None)
    verdict = inside_verdict(projects)
    if not projects and trade_has_point is False:
        verdict = dict(verdict, notice=NO_TRADE_POINT_NOTICE)
    return {
        'inside': verdict,
        'nearest': None if nearest is None else {
            'project_id': nearest['project_id'], 'name': nearest['name'],
            'type_label': nearest['type_label'], 'program_label': nearest['program_label'],
            'stage_label': nearest['stage']['label'], 'stage_basis': nearest['stage_basis'],
            'distance_m': nearest['distance_m'],
            'distance_label': distance_bucket(nearest['distance_m'], nearest['spatial']['code']),
            'official_source': nearest['official_source'], 'trust_label': nearest['trust']['label']},
        'count': len(projects),
        'has_map_point': bool(trade_has_point),
        'available': bool(projects),
    }


def map_point(row):
    """지도용 경량 payload. 상세는 선택했을 때 따로 가져온다."""
    program = program_of(row)
    presented = present_project(row)
    accuracy = location_accuracy(row)
    layers = map_layer_of(row)
    boundary = boundary_layer(row)
    life = lifecycle(row)
    return {'project_id': row.get('project_id'), 'name': row.get('project_name'),
            'lifecycle': life['code'], 'lifecycle_label': life['label'],
            'lifecycle_basis': life['basis'], 'in_default_map': life['in_default_map'],
            'latitude': row.get('latitude'), 'longitude': row.get('longitude'),
            'boundary': boundary['geometry'],
            'boundary_status': boundary['boundary_status'],
            'boundary_status_label': boundary['status_label'],
            'allows_inside': boundary['allows_inside'],
            'development_layer': layers['development'], 'program_layer': layers['program'],
            'address': row.get('address'),
            'last_checked': (row.get('last_verified_at') or '')[:10] or None,
            'official_url': presented['official_source']['url'],
            'type_code': row.get('project_type'),
            'type_label': TYPE_LABELS.get(row.get('project_type'), '기타'),
            'program_code': (program or {}).get('code'),
            'program_label': (program or {}).get('label'),
            'stage_label': presented['stage']['label'],
            'district': row.get('sigungu'), 'dong': row.get('dong'),
            'accuracy': accuracy['code'], 'accuracy_label': accuracy['label'],
            'confidence': trust(row.get('validation_status'))['label'],
            'mappable': accuracy['code'] != 'NO_LOCATION'}


# 지도 레이어. project_type과 program은 서로 다른 레이어이며 섞지 않는다.
MAP_LAYERS = {
    'PROPERTY': {'label': '선택 부동산', 'marker': 'star', 'color': '#111827'},
    'REDEVELOPMENT': {'label': '재개발', 'marker': 'circle', 'color': '#B42332', 'layer': 'DEVELOPMENT'},
    'RECONSTRUCTION': {'label': '재건축', 'marker': 'circle', 'color': '#1D4ED8', 'layer': 'DEVELOPMENT'},
    'OTHER_PROJECT': {'label': '기타 정비사업', 'marker': 'circle', 'color': '#64748B', 'layer': 'DEVELOPMENT'},
    'FAST_TRACK': {'label': '신속통합기획', 'marker': 'ring', 'color': '#7C3AED', 'layer': 'PROGRAM'},
    'MOATOWN': {'label': '모아타운', 'marker': 'square', 'color': '#0F766E', 'layer': 'PROGRAM'},
    'BOUNDARY': {'label': '공식 사업구역', 'marker': 'polygon', 'color': '#B42332', 'layer': 'BOUNDARY'},
    'POINT': {'label': '사업 대표위치', 'marker': 'circle', 'color': '#B42332', 'layer': 'POINT'},
}
MAP_FILTERS = ('전체', '재개발', '재건축', '신속통합기획', '모아타운', '기타 정비사업')
# 향후 공식 경계를 넣을 때 반드시 함께 저장할 provenance.
BOUNDARY_PROVENANCE_FIELDS = ('source', 'source_url', 'verified_at', 'boundary_status')
BOUNDARY_STATUS = {'OFFICIAL_VERIFIED': '공식 경계 확인', 'PENDING': '공식 경계 확보 전',
                   'NOT_AVAILABLE': '공식 경계 미공개'}


def map_layer_of(row):
    """마커를 그릴 레이어 키. 유형은 DEVELOPMENT, 정책은 PROGRAM으로 따로 나간다."""
    kind = row.get('project_type')
    if kind in ('REDEVELOPMENT', 'RECONSTRUCTION'):
        development = kind
    elif kind in ('MOATOWN', 'MOAHOUSE'):
        development = 'OTHER_PROJECT'
    else:
        development = 'OTHER_PROJECT'
    program = (program_of(row) or {}).get('code')
    if kind in ('MOATOWN', 'MOAHOUSE'):
        program = 'MOATOWN'
    return {'development': development, 'program': program}


# 사업의 생애주기. 단계(stage)와 별개다. 공식 종결 단계만 COMPLETED로 본다.
# 착공/공사중은 완료가 아니다. 애매하면 UNKNOWN으로 남기고 지도에서 숨기지 않는다.
LIFECYCLE_LABELS = {'ACTIVE': '진행 중', 'CONSTRUCTION': '공사 중', 'COMPLETED': '사업 완료',
                    'CANCELLED': '취소·해제', 'UNKNOWN': '진행 상태 확인 중'}
# 기본 지도에 그리는 생애주기. 앞으로 변화가 남은 사업에 집중한다.
DEFAULT_LIFECYCLES = ('ACTIVE', 'CONSTRUCTION', 'UNKNOWN')


def lifecycle(row):
    """공식 단계에서만 생애주기를 정한다. 사업명이나 오래됐다는 이유로 완료라고 하지 않는다.

    근거가 없으면 UNKNOWN이다. UNKNOWN은 기본 지도에서 숨기지 않는다. 확인하지 못한 것을
    끝난 것으로 다루면, 아직 진행 중인 사업이 지도에서 조용히 사라진다.
    """
    stored = str(row.get('lifecycle') or row.get('status') or '').strip().upper()
    stage = row.get('normalized_stage') or normalize_stage(
        row.get('stage_raw') or row.get('project_stage') or row.get('stage'))['normalized_stage']
    from_stage = STATUS_FROM_STAGE.get(stage)
    if from_stage:
        code, basis = from_stage, 'OFFICIAL_TERMINAL_STAGE'
    elif stage == 'CONSTRUCTION':
        code, basis = 'CONSTRUCTION', 'OFFICIAL_STAGE'
    elif stored in ('COMPLETED', 'CANCELLED', 'ACTIVE', 'SUSPENDED') and stored != 'UNKNOWN':
        # 데이터베이스가 공식 근거로 이미 정해 둔 값. 단계와 충돌하지 않을 때만 쓴다.
        code, basis = ('ACTIVE' if stored == 'SUSPENDED' else stored), 'STORED_STATUS'
    else:
        code, basis = 'UNKNOWN', 'UNRESOLVED'
    return {'code': code, 'label': LIFECYCLE_LABELS[code], 'basis': basis,
            'stage': stage, 'in_default_map': code in DEFAULT_LIFECYCLES,
            'hypothesis': STATUS_HYPOTHESIS.get(stage) if code == 'UNKNOWN' else None}


def boundary_layer(row):
    """경계 레이어 계약. 추정 polygon은 만들지 않고 provenance 없이 표시하지 않는다."""
    geometry = row.get('boundary') or row.get('geometry')
    verified = bool(row.get('geometry_verified'))
    status = 'OFFICIAL_VERIFIED' if (geometry and verified) else (
        'PENDING' if not geometry else 'NOT_AVAILABLE')
    return {'geometry': geometry if status == 'OFFICIAL_VERIFIED' else None,
            'boundary_status': status, 'status_label': BOUNDARY_STATUS[status],
            'source': row.get('geometry_source'), 'source_url': row.get('source_url'),
            'verified_at': row.get('geometry_verified_at'),
            'allows_inside': status == 'OFFICIAL_VERIFIED'}

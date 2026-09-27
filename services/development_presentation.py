"""User-facing wording for development-project data.

The database and the canonical artifacts speak in enums (NEEDS_REVIEW,
ASSOCIATION_APPROVED, UNKNOWN_OFFICIAL_COLUMN). None of that belongs on screen,
and neither does a claim the evidence does not support: a stage read from an
official list is shown as list-based, never as confirmed.
"""

STAGE_LABELS = {
    'CANDIDATE': '후보지 선정', 'PLANNING': '정비계획 수립', 'PLAN_DELIBERATION': '심의 진행',
    'PLAN_NOTICED': '정비계획 고시', 'DESIGNATED': '정비구역 지정',
    'IMPLEMENTER_DESIGNATED': '시행자 지정', 'SAFETY_DIAGNOSIS': '안전진단',
    'COMMITTEE': '추진위원회 승인', 'ASSOCIATION_APPROVED': '조합설립 인가',
    'IMPLEMENTATION_APPROVED': '사업시행 인가', 'MANAGEMENT_DISPOSITION': '관리처분 인가',
    'SALES': '분양', 'DEMOLITION': '철거', 'CONSTRUCTION': '착공',
    'PARTIAL_COMPLETION': '부분 준공', 'COMPLETED': '준공', 'TRANSFER_NOTICE': '이전고시',
    'ASSOCIATION_DISSOLVED': '조합 해산', 'ASSOCIATION_LIQUIDATION': '조합 청산',
    'CANCELLED': '취소', 'UNKNOWN': '단계 확인 필요',
}
TYPE_LABELS = {'RECONSTRUCTION': '재건축', 'REDEVELOPMENT': '재개발', 'MOATOWN': '모아타운',
               'MOAHOUSE': '모아주택', 'SHINTONG': '신속통합기획', 'FAST_TRACK': '신속통합기획',
               'MAINTENANCE_AREA': '정비구역', 'STATION_AREA': '역세권',
               'DISTRICT_UNIT_PLAN': '지구단위계획', 'PUBLIC_HOUSING': '공공주택',
               'URBAN_DEVELOPMENT': '도시개발', 'TRANSPORT': '교통', 'OTHER': '기타'}
PROGRAM_LABELS = {'FAST_TRACK': '신속통합기획', 'MOATOWN': '모아타운'}
STATUS_LABELS = {'ACTIVE': '진행 중', 'COMPLETED': '완료', 'CANCELLED': '취소',
                 'SUSPENDED': '중단', 'UNKNOWN': '상태 확인 필요'}
# What the reader may rely on. Presence in an official list is not confirmation.
TRUST_LABELS = {
    'VERIFIED': {'label': '공식 확인', 'tone': 'ok',
                 'note': '공식 상세정보로 확인된 내용입니다.'},
    'NEEDS_REVIEW': {'label': '확인 필요', 'tone': 'warn',
                     'note': '공식 목록에서 수집한 내용으로, 상세 확인이 남아 있습니다.'},
    'UNVERIFIED': {'label': '공식 목록 기준', 'tone': 'info',
                   'note': '공식 목록에 공개된 값이며 상세 확인 전입니다.'},
    'MISSING_FROM_SOURCE': {'label': '목록에서 미확인', 'tone': 'warn',
                            'note': '최근 공식 목록에서 확인되지 않았습니다. 취소나 종료를 뜻하지 않습니다.'},
    'REJECTED': {'label': '검토 제외', 'tone': 'muted', 'note': '검토에서 제외된 자료입니다.'},
}
STAGE_BASIS_LABELS = {'OFFICIAL_DETAIL_PAGE': '공식 상세정보 기준',
                      'OFFICIAL_LIST_CELL': '공식 목록 기준', None: '근거 확인 필요'}
# Spatial wording. INSIDE is only ever shown for a verified boundary.
RELATION_LABELS = {'INSIDE': '정비구역 내', 'NEARBY': '주변 개발사업',
                   'UNKNOWN': '위치 확인 필요', 'OUTSIDE': '해당 없음'}
DATE_ROLE_LABELS = {'UNKNOWN_OFFICIAL_COLUMN': '공식 목록에 표기된 날짜 (항목 확인 필요)'}
NO_LOCATION_NOTICE = '정확한 위치 확인 후 주변 개발정보를 연결할 수 있습니다.'


def stage_label(normalized_stage, raw_stage=None):
    label = STAGE_LABELS.get(normalized_stage or 'UNKNOWN', '단계 확인 필요')
    return {'label': label, 'official_text': raw_stage or None}


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
    stage_raw = row.get('stage_raw') or row.get('stage')
    normalized = row.get('normalized_stage') or row.get('stage')
    verified_boundary = bool(row.get('evidence_verified') or row.get('geometry_verified'))
    spatial = relation(row.get('spatial_relation') or row.get('relation'),
                       boundary_verified=verified_boundary)
    return {
        'project_id': row.get('project_id'),
        'name': row.get('project_name'),
        'type_label': TYPE_LABELS.get(row.get('project_type'), '기타'),
        'program_label': PROGRAM_LABELS.get(row.get('program')),
        'district': row.get('sigungu'), 'dong': row.get('dong'),
        'address': row.get('address'),
        'stage': stage_label(normalized, stage_raw),
        'stage_basis': STAGE_BASIS_LABELS.get(row.get('stage_basis'),
                                              STAGE_BASIS_LABELS['OFFICIAL_LIST_CELL']),
        'status_label': STATUS_LABELS.get(row.get('status') or 'UNKNOWN', '상태 확인 필요'),
        'trust': trust(row.get('validation_status')),
        'official_source': {'name': row.get('source_name'), 'url': row.get('evidence_url')
                            or row.get('source_url')},
        'last_checked': row.get('last_verified_at') or row.get('collected_at')
                        or row.get('verified_at'),
        'spatial': spatial,
        'distance_m': row.get('meters') if row.get('meters') is not None else row.get('distance_m'),
        'has_location': spatial['code'] != 'UNKNOWN',
        'location_notice': None if spatial['code'] != 'UNKNOWN' else NO_LOCATION_NOTICE,
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

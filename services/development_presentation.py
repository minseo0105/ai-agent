"""User-facing wording for development-project data.

The database and the canonical artifacts speak in enums (NEEDS_REVIEW,
ASSOCIATION_APPROVED, UNKNOWN_OFFICIAL_COLUMN). None of that belongs on screen,
and neither does a claim the evidence does not support: a stage read from an
official list is shown as list-based, never as confirmed.
"""
from services.development_official import normalize_stage
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
    stage_raw = row.get('stage_raw') or row.get('project_stage') or row.get('stage') or listed.get('raw_stage')
    normalized = row.get('normalized_stage') or (stage_raw if stage_raw in STAGE_LABELS else normalize_stage(stage_raw)['normalized_stage'])
    if verified:
        stage_raw = verified['label']
        normalized = normalize_stage(stage_raw)['normalized_stage']
    # 경계 검증 신호는 SQL에서만 온다. 대표좌표만으로는 절대 True가 되지 않는다.
    verified_boundary = bool(row.get('boundary_verified') or row.get('geometry_verified')
                             or row.get('evidence_verified'))
    spatial = relation(row.get('spatial_relation') or row.get('relation'),
                       boundary_verified=verified_boundary)
    return {
        'project_id': row.get('project_id'),
        'name': row.get('project_name'),
        'official_id': row.get('external_id'),
        'official_authority': row.get('official_authority'),
        'type_label': TYPE_LABELS.get(row.get('project_type'), '기타'),
        'district': row.get('sigungu'), 'dong': row.get('dong'),
        'address': row.get('address'),
        'stage': dict(stage_label(normalized, stage_raw), **({'label': verified['label']} if verified else {})),
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
    return {'project_id': row.get('project_id'), 'name': row.get('project_name'),
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

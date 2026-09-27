"""개발사업 전체(주소 보유 128건) NAVER 지오코딩. DB write 없음.

Canary와 같은 판정 정책을 그대로 쓴다: 첫 후보를 자동 채택하지 않고, 후보가 여러 개면
주소 구성요소 검증을 모두 통과하는 것이 정확히 하나일 때만 그것을 쓴다. 통과가 0개거나
2개 이상이면 REVIEW_REQUIRED로 남기고 좌표를 만들지 않는다. 이상한 좌표를 고쳐서
살리지 않는다 — 고치는 순간 무엇을 근거로 찍힌 핀인지 알 수 없게 된다.

한 번에 128건을 호출하면 요청 하나가 너무 길어지므로 slice로 나눠 돌린다. 주소 캐시가
있어 같은 주소를 두 번 사지 않고, aggregate 모드는 provider를 아예 부르지 않고 캐시만
읽어 전체 보고서를 다시 만든다.
"""
from services import development_canary as canary
from services import development_geocode as geo
from services.development_geocode_targets import targets

BULK_VERSION = 'zipon-bulk-geocode-v1'
# 한 요청에서 호출할 수 있는 최대 건수. 실수로 전체를 한 번에 태우는 것을 막는다.
MAX_SLICE = 50
DEFAULT_SLICE = 32
# 결과 artifact 한 행이 담는 것. 좌표와 판정 근거만 담고 자격증명은 담지 않는다.
ARTIFACT_FIELDS = ('project_id', 'project_name', 'canonical_address', 'district', 'dong',
                   'project_type', 'program', 'matched_address', 'longitude', 'latitude',
                   'accuracy', 'confidence', 'candidate_count', 'outcome', 'acceptance_reason')


def artifact_rows(records):
    """요구된 열만 남긴 결과 행. dong은 저장된 값을 쓰고 provider 응답으로 바꾸지 않는다."""
    rows = []
    for record in records:
        rows.append({'project_id': record['project_id'],
                     'project_name': record['project_name'],
                     'canonical_address': record['canonical_address'],
                     'district': record['district'], 'dong': record.get('stored_dong'),
                     'project_type': record['project_type'], 'program': record['program'],
                     'matched_address': record['matched_address'],
                     'longitude': record['longitude'], 'latitude': record['latitude'],
                     'accuracy': record['accuracy'],
                     'confidence': record['geocode_confidence'],
                     'candidate_count': record['candidate_count'],
                     'outcome': record['outcome'],
                     'acceptance_reason': record['acceptance_reason']})
    return rows


def review_rows(records):
    """사람이 공식 주소와 NAVER 후보를 나란히 보고 판단할 수 있게 만든 목록.

    자동 선택은 하지 않는다. 후보를 그대로 보여주고, 각 후보가 어떤 검사에서
    걸렸는지만 덧붙인다.
    """
    rows = []
    for record in records:
        if record['outcome'] != 'REVIEW_REQUIRED':
            continue
        rows.append({'project_id': record['project_id'],
                     'project_name': record['project_name'],
                     'official_address': record['canonical_address'],
                     'district': record['district'], 'dong': record.get('stored_dong'),
                     'candidate_count': record['candidate_count'],
                     'review_reason': record['acceptance_reason'],
                     'naver_candidates': record.get('candidate_summaries') or [],
                     'returned_district': record['returned_district'],
                     'returned_dong': record['returned_dong'],
                     'returned_lot': record['returned_lot'],
                     'wanted_dong': record['wanted_dong'], 'wanted_lot': record['wanted_lot'],
                     'decision': None, 'decided_by': None, 'decided_at': None})
    return rows


def apply_ready(records):
    """다음 단계에서 scripts/apply_zipon_geocode.py가 그대로 먹을 수 있는 입력.

    ACCEPTED만 담는다. REVIEW_REQUIRED는 제외한다. 기존 좌표·검증된 폴리곤 보호는
    apply 쪽 preflight와 RPC가 그대로 판단하므로 여기서 우회하지 않는다.
    """
    items = []
    for record in records:
        if record['outcome'] != 'ACCEPTED':
            continue
        items.append({'project_id': record['project_id'],
                      'canonical_address': record['canonical_address'],
                      'district': record['district'],
                      'geocode_status': 'ACCEPTED', 'coordinate_verified': True,
                      'geocode_confidence': 'EXACT',
                      'coordinate_orientation': record['coordinate_orientation'],
                      'geocode_source': record['geocode_source'],
                      'longitude': record['longitude'], 'latitude': record['latitude'],
                      'matched_address': record['matched_address'],
                      'road_address': record['matched_road_address'],
                      'jibun_address': record['matched_jibun_address'],
                      'english_address': record['english_address'],
                      'address_elements': record.get('address_elements'),
                      'checks': record['checks'], 'geocoded_at': record.get('geocoded_at')})
    return {'format': 'zipon-geocode-queue-v1', 'db_write': False,
            'provider': 'naver', 'source': BULK_VERSION,
            'policy': ['ACCEPTED만 담는다; REVIEW_REQUIRED는 제외한다',
                       '기존 좌표와 검증된 폴리곤 보호는 apply 단계에서 다시 판단한다',
                       'apply는 reviewed RPC zipon_set_project_location으로만 쓴다'],
            'totals': {'eligible': len(items)}, 'items': items}


def map_readiness(report):
    """지도에 몇 건이 찍히는지와 자치구·유형별 분포. INSIDE 판정은 하지 않는다."""
    payload = report['map']
    by_district, by_type, by_program = {}, {}, {}
    for point in payload['points']:
        by_district[point['district']] = by_district.get(point['district'], 0) + 1
        by_type[point['type_code']] = by_type.get(point['type_code'], 0) + 1
        key = point['program_code'] or 'NONE'
        by_program[key] = by_program.get(key, 0) + 1
    return {'mappable_projects': payload['mappable'], 'bbox': payload['bbox'],
            'center': payload['center'], 'suggested_zoom': payload['suggested_zoom'],
            'by_district': by_district, 'by_type': by_type, 'by_program': by_program,
            'redevelopment': by_type.get('REDEVELOPMENT', 0),
            'reconstruction': by_type.get('RECONSTRUCTION', 0),
            'other': sum(count for code, count in by_type.items()
                         if code not in ('REDEVELOPMENT', 'RECONSTRUCTION')),
            'fast_track': by_program.get('FAST_TRACK', 0),
            'moatown': by_program.get('MOATOWN', 0),
            'inside_judgement': payload['inside_judgement']}


def run(get_secret, http_get=None, cache=None, offset=0, size=DEFAULT_SLICE,
        cache_only=False, preferred=None):
    """한 slice만 조회하거나(cache_only=False) 캐시만 읽어 전체를 다시 만든다.

    size는 MAX_SLICE를 넘지 못한다. cache_only면 offset·size를 무시하고 전체를 본다.
    어느 경우에도 데이터베이스에는 쓰지 않는다.
    """
    rows = targets()
    if cache_only:
        window, offset, size = rows, 0, len(rows)
    else:
        size = max(1, min(int(size), MAX_SLICE))
        offset = max(0, min(int(offset), len(rows)))
        window = rows[offset:offset + size]
    report = canary.run_rows(window, get_secret, http_get, cache, preferred, cache_only)
    stored = {row['project_id']: row['dong'] for row in rows}
    for record in report['results']:
        record['stored_dong'] = stored.get(record['project_id'])
    remaining = max(0, len(rows) - (offset + len(window)))
    return dict(report, format=BULK_VERSION, target_total=len(rows),
                offset=offset, size=len(window), next_offset=(offset + len(window)
                                                              if remaining else None),
                remaining=remaining, max_slice=MAX_SLICE,
                scope={'canonical_total': 183, 'address_available': 149,
                       'address_missing': 34, 'in_database': 130,
                       'geocode_target': len(rows),
                       'in_database_without_address': 2, 'address_but_quarantined': 21},
                artifact={'format': 'zipon-bulk-geocode-artifact-v1',
                          'fields': list(ARTIFACT_FIELDS),
                          'items': artifact_rows(report['results'])},
                review={'format': 'zipon-bulk-geocode-review-v1',
                        'note': '자동 선택하지 않는다. 사람이 공식 주소와 후보를 비교한다.',
                        'items': review_rows(report['results'])},
                apply_ready=apply_ready(report['results']),
                map_readiness=map_readiness(report))

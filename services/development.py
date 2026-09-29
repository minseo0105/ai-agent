"""Optional development context. All database I/O uses REST/RPC, no psycopg."""
import binascii
import math
import struct
from uuid import UUID

from services import realestate_monitor as rm

MAP_COLUMNS = ('project_id,project_name,project_type,sigungu,dong,address,stage_raw,status,'
               'validation_status,location,geometry_verified,last_verified_at')

# in.() 필터는 id마다 37자를 쓴다. 서울시 전체를 한 번에 물으면 질의문자열이 5KB에
# 가까워지고, 중간 프록시가 자르면 카드의 단계 상세가 통째로 비어버린다. 그래서 나눠 묻는다.
STAGE_BATCH = 50


def stage_metadata(rows):
    """One read-only batch fills columns omitted by the spatial RPC. No SQL change."""
    ids = []
    for row in rows or []:
        try:
            ids.append(str(UUID(str(row.get('project_id')))))
        except (ValueError, TypeError):
            continue
    unique = sorted(set(ids))
    if not unique:
        return rows
    metadata = {}
    for start in range(0, len(unique), STAGE_BATCH):
        chunk = unique[start:start + STAGE_BATCH]
        try:
            found = rm._remote_request('GET', 'development_projects', params={
                'select':'project_id,stage,stage_raw,field_evidence,external_id,official_authority',
                'project_id':'in.(' + ','.join(chunk) + ')', 'limit':len(chunk)})
        except Exception:
            # 한 묶음이 실패해도 나머지 단계 상세는 살린다. 단계를 추정하지는 않는다.
            continue
        metadata.update({p['project_id']:p for p in found})
    return [dict(row, **{k:v for k,v in metadata.get(row.get('project_id'), {}).items() if k != 'project_id'}) for row in rows]


def _point(value):
    """geography(Point) EWKB hex -> (경도, 위도). 좌표가 없으면 (None, None).

    PostgREST는 geography 컬럼을 EWKB hex로 돌려준다. 포인트 외 형태는 읽지 않는다.
    """
    if not isinstance(value, str) or len(value) < 42:
        return None, None
    try:
        raw = binascii.unhexlify(value)
        little = raw[0] == 1
        kind = struct.unpack_from('<I' if little else '>I', raw, 1)[0]
        if kind & 0xFF != 1:  # POINT만 처리
            return None, None
        offset = 5 + (4 if kind & 0x20000000 else 0)  # SRID 포함 여부
        longitude, latitude = struct.unpack_from('<dd' if little else '>dd', raw, offset)
    except (binascii.Error, struct.error, IndexError):
        return None, None
    if not (math.isfinite(longitude) and math.isfinite(latitude)):
        return None, None
    return longitude, latitude


def map_projects(sigungu=None, limit=500, bbox=None):
    """지도용 경량 목록. 상세는 선택 시 따로 조회한다.

    bbox(north, south, east, west)는 좌표를 해석한 뒤 서버에서 걸러낸다. 좌표가
    없는 사업은 bbox 조회에서 제외되지만 목록에서 사라지지는 않는다.
    """
    if not 1 <= limit <= 500:
        raise ValueError('Invalid limit')
    if bbox is not None:
        north, south, east, west = (bbox['north'], bbox['south'], bbox['east'], bbox['west'])
        if not all(math.isfinite(v) for v in (north, south, east, west)) or north < south \
                or east < west or not (-90 <= south <= north <= 90) \
                or not (-180 <= west <= east <= 180):
            raise ValueError('Invalid bbox')
    if not rm._using_remote_db():
        return {'status': 'unavailable', 'projects': [], 'reason': 'NOT_CONFIGURED'}
    rows, boundary_source = _map_rows(sigungu, limit)
    if rows is None:
        return {'status': 'unavailable', 'projects': [], 'reason': 'DEVELOPMENT_UNAVAILABLE'}
    # 목록과 지도가 같은 응답을 쓰므로 단계 상세도 여기서 함께 채운다. 단계 판정 로직은
    # 건드리지 않고, 탐색 경로가 이미 쓰는 읽기 전용 배치를 그대로 재사용한다.
    rows = stage_metadata(rows)
    result = []
    for row in rows or []:
        longitude, latitude = _coordinates(row)
        if bbox is not None:
            if longitude is None or latitude is None:
                continue
            if not (bbox['south'] <= latitude <= bbox['north']
                    and bbox['west'] <= longitude <= bbox['east']):
                continue
        # 경계는 RPC가 확인된 것만 GeoJSON으로 준다. 추정 polygon은 만들지 않는다.
        result.append(dict(row, longitude=longitude, latitude=latitude,
                           boundary=row.get('boundary')))
    return {'status': 'ok', 'projects': result, 'reason': None,
            'bbox_filtered': bbox is not None, 'boundary_source': boundary_source}


def _map_rows(sigungu, limit):
    """(행, 경계를 어디서 얻었는지). 경계 RPC가 없는 서버에서도 지도는 계속 나온다."""
    try:
        rows = rm._remote_request('POST', 'rpc/zipon_development_map', payload={
            'p_sigungu': sigungu, 'p_limit': limit})
        return rows, 'RPC'
    except Exception:
        # 경계 RPC가 아직 설치되지 않은 서버. 좌표만으로 이전과 같이 그린다.
        pass
    params = {'select': MAP_COLUMNS, 'limit': limit}
    if sigungu:
        params['sigungu'] = 'eq.' + sigungu
    try:
        rows = rm._remote_request('GET', 'development_projects', params=params)
    except Exception:
        return None, None
    return [dict(row, boundary=None) for row in rows or []], 'NONE'


def _coordinates(row):
    """RPC는 경위도를 숫자로 주고, REST fallback은 geography hex를 준다."""
    longitude, latitude = row.get('longitude'), row.get('latitude')
    if isinstance(longitude, (int, float)) and isinstance(latitude, (int, float)) \
            and math.isfinite(longitude) and math.isfinite(latitude):
        return longitude, latitude
    return _point(row.get('location'))


def search_projects(*, longitude=None, latitude=None, sigungu=None, radius_m=1000, limit=30):
    if (longitude is None) != (latitude is None):
        raise ValueError('Both coordinates are required')
    if longitude is not None and not (math.isfinite(longitude) and math.isfinite(latitude)
            and -180 <= longitude <= 180 and -90 <= latitude <= 90):
        raise ValueError('Invalid coordinates')
    if not 0 <= radius_m <= 10000 or not 1 <= limit <= 100:
        raise ValueError('Invalid search bounds')
    if not rm._using_remote_db():
        return {'status': 'unavailable', 'nearby_projects': [], 'reason': 'NOT_CONFIGURED'}
    try:
        rows = rm._remote_request('POST', 'rpc/zipon_development_search', payload={
            'p_longitude': longitude, 'p_latitude': latitude, 'p_sigungu': sigungu,
            'p_radius_m': radius_m, 'p_limit': limit})
        return {'status': 'ok', 'nearby_projects': stage_metadata(rows), 'reason': None}
    except Exception:
        # No raw errors/URLs/credentials in browser responses.
        return {'status': 'unavailable', 'nearby_projects': [], 'reason': 'DEVELOPMENT_UNAVAILABLE'}

def district_summary(limit=1000):
    """자치구별 적재 현황. 읽기 전용 REST GET 한 번으로 계산한다."""
    if not rm._using_remote_db():
        return {'status': 'unavailable', 'districts': [], 'total': 0, 'reason': 'NOT_CONFIGURED'}
    try:
        rows = rm._remote_request('GET', 'development_projects', params={
            'select': 'sigungu,project_type,validation_status', 'limit': limit})
    except Exception:
        return {'status': 'unavailable', 'districts': [], 'total': 0, 'reason': 'DEVELOPMENT_UNAVAILABLE'}
    grouped = {}
    for row in rows or []:
        district = row.get('sigungu') or '미확인'
        bucket = grouped.setdefault(district, {'district': district, 'total': 0, 'by_type': {},
                                               'verified': 0})
        bucket['total'] += 1
        kind = row.get('project_type') or 'OTHER'
        bucket['by_type'][kind] = bucket['by_type'].get(kind, 0) + 1
        if row.get('validation_status') == 'VERIFIED':
            bucket['verified'] += 1
    districts = sorted(grouped.values(), key=lambda b: (-b['total'], b['district']))
    return {'status': 'ok', 'districts': districts, 'total': sum(b['total'] for b in districts),
            'reason': None}


def attach_context(rows, *, radius_m=1000, budget=10):
    """Bound lookups per request. Never guess coordinates from a dong centroid."""
    cache = {}
    result = []
    for original in rows:
        row = dict(original)
        lat, lon = row.get('latitude'), row.get('longitude')
        # Current MOLIT trade payloads have no coordinates: preserve UNKNOWN explicitly.
        if lat is None or lon is None:
            row['development_context'] = {'relation': 'UNKNOWN', 'status': 'needs_geocode',
                'nearby_projects': [], 'reason': 'EXACT_ADDRESS_COORDINATES_REQUIRED'}
        else:
            key = (lon, lat)
            if key not in cache and len(cache) < budget:
                try:
                    cache[key] = search_projects(longitude=lon, latitude=lat, radius_m=radius_m)
                except (TypeError, ValueError):
                    cache[key] = {'status': 'unavailable', 'nearby_projects': [], 'reason': 'INVALID_COORDINATES'}
            row['development_context'] = cache.get(key, {'status': 'deferred',
                'nearby_projects': [], 'reason': 'LOOKUP_BUDGET'})
        result.append(row)
    return result

"""Optional development context. All database I/O uses REST/RPC, no psycopg."""
import binascii
import math
import struct

from services import realestate_monitor as rm

MAP_COLUMNS = ('project_id,project_name,project_type,sigungu,dong,address,stage_raw,status,'
               'validation_status,location,geometry_verified,last_verified_at')


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


def map_projects(sigungu=None, limit=200):
    """지도용 경량 목록. 상세는 선택 시 따로 조회한다."""
    if not 1 <= limit <= 500:
        raise ValueError('Invalid limit')
    if not rm._using_remote_db():
        return {'status': 'unavailable', 'projects': [], 'reason': 'NOT_CONFIGURED'}
    params = {'select': MAP_COLUMNS, 'limit': limit}
    if sigungu:
        params['sigungu'] = 'eq.' + sigungu
    try:
        rows = rm._remote_request('GET', 'development_projects', params=params)
    except Exception:
        return {'status': 'unavailable', 'projects': [], 'reason': 'DEVELOPMENT_UNAVAILABLE'}
    result = []
    for row in rows or []:
        longitude, latitude = _point(row.get('location'))
        # 검증된 경계 GeoJSON은 아직 제공 경로가 없다. 추정 polygon은 만들지 않는다.
        result.append(dict(row, longitude=longitude, latitude=latitude, boundary=None))
    return {'status': 'ok', 'projects': result, 'reason': None}




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
        return {'status': 'ok', 'nearby_projects': rows, 'reason': None}
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

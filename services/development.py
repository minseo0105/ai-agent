"""Optional development context. All database I/O uses REST/RPC, no psycopg."""
import math
from services import realestate_monitor as rm

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

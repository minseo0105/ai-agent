from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def put(name,text):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')

put('services/supabase_auth.py','''"""Server-only authentication shared by all Supabase REST consumers."""
def supabase_headers(key, *, prefer=None):
    if not key or any(c.isspace() for c in key):
        raise ValueError("Invalid backend Supabase credential")
    if key.startswith('sb_publishable_'):
        raise ValueError("Backend requires a server credential")
    headers = {'apikey': key, 'Content-Type': 'application/json'}
    if not key.startswith('sb_secret_'):
        headers['Authorization'] = 'Bearer ' + key
    if prefer:
        headers['Prefer'] = prefer
    return headers
''')
p=ROOT/'services/realestate_monitor.py';s=p.read_text(encoding='utf-8')
s=s.replace('from services.config import get_secret','from services.config import get_secret\nfrom services.supabase_auth import supabase_headers')
start=s.index('    headers = {',s.index('def _remote_request'));end=s.index('\n    response = requests.request',start)
s=s[:start]+'''    headers = supabase_headers(key, prefer=prefer)
'''+s[end:];p.write_text(s,encoding='utf-8')
p=ROOT/'services/access.py';s=p.read_text(encoding='utf-8').replace('from services.config import get_secret','from services.config import get_secret\nfrom services.supabase_auth import supabase_headers')
s=s.replace('headers={"apikey": key, "Authorization": f"Bearer {key}"}', 'headers=supabase_headers(key)')
s=s.replace('headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",\n                               "Prefer": "resolution=merge-duplicates,return=minimal"}', 'headers=supabase_headers(key, prefer="resolution=merge-duplicates,return=minimal")')
p.write_text(s,encoding='utf-8')
put('services/development.py','''"""Optional development context. All database I/O uses REST/RPC, no psycopg."""
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
''')
p=ROOT/'api/realestate.py';s=p.read_text(encoding='utf-8').replace('from services import realestate_monitor as rm','from services import realestate_monitor as rm\nfrom services import development')
s=s.replace('    max_area: float | None = Field(None, gt=0, le=100000, allow_inf_nan=False)', '    max_area: float | None = Field(None, gt=0, le=100000, allow_inf_nan=False)\n    include_development: bool = False')
s=s.replace('    counts = {}\n', '    if q.include_development:\n        rows = await run_in_threadpool(development.attach_context, rows)\n    counts = {}\n')
s+='''

class DevelopmentQuery(BaseModel):
    longitude: float | None = Field(None, ge=-180, le=180, allow_inf_nan=False)
    latitude: float | None = Field(None, ge=-90, le=90, allow_inf_nan=False)
    sigungu: str | None = Field(None, max_length=40)
    radius_m: float = Field(1000, ge=0, le=10000, allow_inf_nan=False)
    limit: int = Field(30, ge=1, le=100)


@router.post('/development/search')
async def development_search(q: DevelopmentQuery):
    if (q.longitude is None) != (q.latitude is None):
        raise HTTPException(422, '위도와 경도를 함께 입력해주세요.')
    if q.longitude is None and not q.sigungu:
        raise HTTPException(422, '좌표 또는 자치구를 입력해주세요.')
    return await run_in_threadpool(development.search_projects, **q.model_dump())
''';p.write_text(s,encoding='utf-8')
put('supabase/migrations/20260927_zipon_spatial_rpc.sql','''-- REVIEW ONLY. Apply only to NEW zipon-realestate after base migration.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
CREATE OR REPLACE FUNCTION public.zipon_development_search(
 p_longitude double precision DEFAULT NULL, p_latitude double precision DEFAULT NULL,
 p_sigungu text DEFAULT NULL, p_radius_m double precision DEFAULT 1000, p_limit integer DEFAULT 30)
RETURNS TABLE(project_id uuid, project_name text, project_type text, project_stage text,
 status text, validation_status text, relation text, distance_m double precision,
 official_source text, source_url text, verified_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = pg_catalog, public, extensions
AS $fn$
DECLARE q extensions.geometry;
BEGIN
 IF (p_longitude IS NULL) <> (p_latitude IS NULL)
 OR (p_longitude IS NOT NULL AND NOT (p_longitude BETWEEN -180 AND 180 AND p_latitude BETWEEN -90 AND 90))
 OR p_radius_m IS NULL OR NOT (p_radius_m BETWEEN 0 AND 10000)
 OR p_limit IS NULL OR NOT (p_limit BETWEEN 1 AND 100)
 OR (p_longitude IS NULL AND NULLIF(btrim(p_sigungu),'') IS NULL) THEN
   RAISE EXCEPTION 'Invalid spatial search bounds' USING ERRCODE='22023';
 END IF;
 IF p_longitude IS NOT NULL THEN q:=extensions.ST_SetSRID(extensions.ST_MakePoint(p_longitude,p_latitude),4326); END IF;
 RETURN QUERY
 WITH candidates AS (
 SELECT p.*, s.source_name, s.source_url AS evidence_url, s.verified_at AS evidence_verified,
 CASE WHEN q IS NULL THEN NULL
 ELSE LEAST(
 CASE WHEN p.geometry IS NOT NULL THEN extensions.ST_Distance(p.geometry::extensions.geography,q::extensions.geography) END,
 CASE WHEN p.location IS NOT NULL THEN extensions.ST_Distance(p.location,q::extensions.geography) END) END AS meters,
 CASE WHEN q IS NULL THEN 'UNKNOWN'
 WHEN p.geometry_verified AND p.geometry IS NOT NULL AND extensions.ST_Contains(p.geometry,q) THEN 'INSIDE'
 WHEN (p.geometry IS NOT NULL AND extensions.ST_DWithin(p.geometry::extensions.geography,q::extensions.geography,p_radius_m))
   OR (p.location IS NOT NULL AND extensions.ST_DWithin(p.location,q::extensions.geography,p_radius_m)) THEN 'NEARBY'
 WHEN p.geometry IS NULL AND p.location IS NULL THEN 'UNKNOWN'
 ELSE 'OUTSIDE' END AS spatial_relation
 FROM public.development_projects p
 LEFT JOIN public.development_project_sources s ON s.source_id=p.canonical_source_id
   AND s.project_id=p.project_id AND s.is_official AND s.validation_status='VERIFIED'
 WHERE (p_sigungu IS NULL OR p.sigungu=p_sigungu)
   AND p.validation_status <> 'REJECTED'
   AND (q IS NULL
     OR (p.geometry IS NOT NULL AND extensions.ST_DWithin(p.geometry::extensions.geography,q::extensions.geography,p_radius_m))
     OR (p.location IS NOT NULL AND extensions.ST_DWithin(p.location,q::extensions.geography,p_radius_m))
     OR (p_sigungu IS NOT NULL AND p.geometry IS NULL AND p.location IS NULL))
 )
 SELECT c.project_id,c.project_name,c.project_type,c.stage,c.status,c.validation_status,
 c.spatial_relation,c.meters,c.source_name,c.evidence_url,c.evidence_verified
 FROM candidates c WHERE c.spatial_relation<>'OUTSIDE'
 ORDER BY CASE c.spatial_relation WHEN 'INSIDE' THEN 0 WHEN 'NEARBY' THEN 1 ELSE 2 END,
 c.meters NULLS LAST,c.project_id LIMIT p_limit;
END;
$fn$;
REVOKE ALL ON FUNCTION public.zipon_development_search(double precision,double precision,text,double precision,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_development_search(double precision,double precision,text,double precision,integer) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;
''')
put('supabase/review/20260927_zipon_spatial_postcheck.sql','''-- Read-only; run AFTER spatial migration. No synthetic table inserts.
BEGIN READ ONLY;
SELECT p.proname,NOT p.prosecdef AS security_invoker,
 has_function_privilege('service_role',p.oid,'EXECUTE') AS service_execute,
 has_function_privilege('anon',p.oid,'EXECUTE') AS anon_execute,
 has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_execute
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname='zipon_development_search';
SELECT * FROM public.zipon_development_search(127.005,37.005,'강동구',1000,10);
SELECT * FROM public.zipon_development_search(NULL,NULL,'서초구',1000,10);
ROLLBACK;
''')
print('Auth, API and spatial migration files written; no DB execution')

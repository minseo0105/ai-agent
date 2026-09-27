-- REVIEW ONLY. Apply only to NEW zipon-realestate after base migration.
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
SET search_path = pg_catalog, public, extensions, pg_temp
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
 LEFT JOIN LATERAL (
   SELECT src.source_name,src.source_url,src.verified_at
   FROM public.development_project_sources src
   WHERE src.project_id=p.project_id AND src.is_official AND src.validation_status<>'REJECTED'
   ORDER BY (src.source_id=p.canonical_source_id) DESC NULLS LAST,src.collected_at DESC,src.source_id
   LIMIT 1
 ) s ON true
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

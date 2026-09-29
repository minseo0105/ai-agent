-- REVIEWED INSTALL SQL. Not executed by this task.
--
-- 공식 사업구역 polygon을 반영하는 유일한 데이터베이스 경로. 좌표 RPC와 같은 방식으로,
-- 검토를 통과한 값만 받고 그 밖의 경우는 고치지 않고 거절한다.
--
-- 쓰는 것: geometry, geometry_source, geometry_verified, geometry_verified_at,
--          field_evidence.boundary, revision 증가.
-- 건드리지 않는 것: location, location_source, status, stage, validation_status,
--          confidence_level, canonical_source_id, project identity(external_id/authority).
--
-- 거절하는 조건(고치지 않고 거절한다):
--   * project_id가 없거나 revision이 어긋난다
--   * 이미 verified 경계가 있다 → skipped(덮어쓰지 않는다)
--   * verified가 아닌 geometry가 이미 있다 → 사람 검토로 넘긴다
--   * 저장된 자치구가 호출자가 기대한 자치구와 다르다
--   * Polygon / MultiPolygon이 아니거나 유효하지 않거나 2D가 아니다
--   * 서울 bounding box를 벗어난다
--   * 면적이 정비사업 구역으로 볼 수 없는 크기다
--   * 저장된 대표좌표가 그 polygon 안에 없다
--   * 검토 근거(EXACT / 자동반영 후보 / 검사 전부 통과 / 원천 판·해시)가 빠져 있다
--   * canonical_source_id가 없다(테이블 CHECK가 verified 경계에 이것을 요구한다)
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- 정비사업 구역의 크기 범위. 이 밖은 원천이나 매칭이 잘못된 것으로 본다.
-- 100 m^2 미만은 점에 가깝고, 5 km^2를 넘으면 자치구 단위 도형이다.
CREATE OR REPLACE FUNCTION public.zipon_set_project_boundary(
  p_project_id uuid, p_geometry jsonb, p_geometry_source text, p_source_url text,
  p_expected_sigungu text, p_expected_revision bigint, p_evidence jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $fn$
DECLARE oldrow public.development_projects; newrow public.development_projects;
 shape extensions.geometry; next_revision bigint; evidence jsonb; area double precision;
BEGIN
 IF p_project_id IS NULL OR p_expected_revision IS NULL OR p_expected_revision<=0
 OR jsonb_typeof(p_evidence) IS DISTINCT FROM 'object'
 OR jsonb_typeof(p_geometry) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Invalid boundary request' USING ERRCODE='22023'; END IF;
 IF NULLIF(btrim(COALESCE(p_geometry_source,'')),'') IS NULL
 OR NULLIF(btrim(COALESCE(p_source_url,'')),'') IS NULL THEN
   RETURN jsonb_build_object('result','refused','reason','NO_BOUNDARY_SOURCE',
     'project_id',p_project_id); END IF;
 IF p_geometry->>'type' NOT IN ('Polygon','MultiPolygon') THEN
   RETURN jsonb_build_object('result','refused','reason','GEOMETRY_TYPE_NOT_ALLOWED',
     'project_id',p_project_id,'type',p_geometry->>'type'); END IF;

 -- 검토 근거. 등급이 EXACT이고 자동반영 후보이며 검사가 전부 통과한 것만 받는다.
 IF p_evidence->>'match_status' IS DISTINCT FROM 'EXACT'
 OR p_evidence->'auto_apply_candidate' IS DISTINCT FROM 'true'::jsonb
 OR p_evidence->'representative_point_inside_polygon' IS DISTINCT FROM 'true'::jsonb THEN
   RETURN jsonb_build_object('result','refused','reason','EXACT_AUTO_APPLY_EVIDENCE_REQUIRED',
     'project_id',p_project_id); END IF;
 IF NULLIF(btrim(COALESCE(p_evidence->>'source_dataset','')),'') IS NULL
 OR NULLIF(btrim(COALESCE(p_evidence->>'source_version','')),'') IS NULL
 OR NULLIF(btrim(COALESCE(p_evidence->>'source_sha256','')),'') IS NULL
 OR NULLIF(btrim(COALESCE(p_evidence->>'official_name','')),'') IS NULL THEN
   RETURN jsonb_build_object('result','refused','reason','SOURCE_PROVENANCE_REQUIRED',
     'project_id',p_project_id); END IF;
 IF jsonb_typeof(p_evidence->'checks') IS DISTINCT FROM 'object'
 OR NOT (p_evidence->'checks' @> '{"geometry_valid":true,"ring_closed":true,"crs_converted":true,"normalized_name_match":true,"district_match":true,"single_candidate":true,"not_identity_protected":true,"point_in_polygon":true}'::jsonb)
 OR EXISTS (SELECT 1 FROM jsonb_each(p_evidence->'checks') AS c(k,v) WHERE c.v IS DISTINCT FROM 'true'::jsonb) THEN
   RETURN jsonb_build_object('result','refused','reason','BOUNDARY_CHECKS_NOT_PASSED',
     'project_id',p_project_id); END IF;

 BEGIN
   shape:=extensions.ST_SetSRID(extensions.ST_GeomFromGeoJSON(p_geometry::text),4326);
 EXCEPTION WHEN others THEN
   RETURN jsonb_build_object('result','refused','reason','GEOMETRY_UNREADABLE',
     'project_id',p_project_id);
 END;
 IF shape IS NULL OR extensions.GeometryType(shape) NOT IN ('POLYGON','MULTIPOLYGON')
 OR extensions.ST_NDims(shape)<>2 OR extensions.ST_IsEmpty(shape)
 OR NOT extensions.ST_IsValid(shape) THEN
   RETURN jsonb_build_object('result','refused','reason','GEOMETRY_NOT_VALID',
     'project_id',p_project_id); END IF;
 -- 좌표계를 잘못 읽은 polygon은 여기서 걸린다. 서울 밖이면 반영하지 않는다.
 IF extensions.ST_XMin(extensions.Box3D(shape))<126.734
 OR extensions.ST_XMax(extensions.Box3D(shape))>127.270
 OR extensions.ST_YMin(extensions.Box3D(shape))<37.413
 OR extensions.ST_YMax(extensions.Box3D(shape))>37.715 THEN
   RETURN jsonb_build_object('result','refused','reason','BOUNDARY_OUTSIDE_SEOUL',
     'project_id',p_project_id); END IF;
 area:=extensions.ST_Area(shape::extensions.geography);
 IF area IS NULL OR area<100 OR area>5000000 THEN
   RETURN jsonb_build_object('result','refused','reason','BOUNDARY_AREA_IMPLAUSIBLE',
     'project_id',p_project_id,'area_m2',area); END IF;

 SELECT * INTO oldrow FROM public.development_projects WHERE project_id=p_project_id FOR UPDATE;
 IF NOT FOUND THEN
   RETURN jsonb_build_object('result','refused','reason','PROJECT_NOT_FOUND',
     'project_id',p_project_id); END IF;
 IF oldrow.revision IS DISTINCT FROM p_expected_revision THEN
   RETURN jsonb_build_object('result','refused','reason','REVISION_CONFLICT',
     'project_id',p_project_id,'revision',oldrow.revision); END IF;
 IF oldrow.geometry_verified IS TRUE THEN
   -- 이미 확인된 경계는 덮어쓰지 않는다. 교체는 별도 검토 절차의 일이다.
   RETURN jsonb_build_object('result','skipped','reason','BOUNDARY_ALREADY_VERIFIED',
     'project_id',p_project_id,'revision',oldrow.revision); END IF;
 IF oldrow.geometry IS NOT NULL THEN
   RETURN jsonb_build_object('result','refused','reason','UNVERIFIED_GEOMETRY_PRESENT',
     'project_id',p_project_id); END IF;
 IF btrim(COALESCE(oldrow.sigungu,'')) IS DISTINCT FROM btrim(COALESCE(p_expected_sigungu,'')) THEN
   RETURN jsonb_build_object('result','refused','reason','DISTRICT_MISMATCH',
     'project_id',p_project_id,'stored_sigungu',oldrow.sigungu); END IF;
 IF oldrow.canonical_source_id IS NULL THEN
   RETURN jsonb_build_object('result','refused','reason','NO_CANONICAL_SOURCE',
     'project_id',p_project_id); END IF;
 -- 저장된 대표좌표가 그 polygon 안에 있어야 한다. 밖이면 다른 사업의 구역일 수 있다.
 IF oldrow.location IS NOT NULL
 AND NOT extensions.ST_Contains(shape,oldrow.location::extensions.geometry) THEN
   RETURN jsonb_build_object('result','refused','reason','STORED_POINT_OUTSIDE_BOUNDARY',
     'project_id',p_project_id); END IF;

 next_revision:=oldrow.revision+1;
 evidence:=jsonb_strip_nulls(jsonb_build_object(
   'source',p_geometry_source,'source_url',p_source_url,
   'source_dataset',p_evidence->>'source_dataset','source_version',p_evidence->>'source_version',
   'source_sha256',p_evidence->>'source_sha256',
   'official_name',p_evidence->>'official_name',
   'official_source_record_id',p_evidence->>'official_source_record_id',
   'normalized_name',p_evidence->>'normalized_name',
   'match_status',p_evidence->>'match_status','match_signals',p_evidence->'match_signals',
   'geometry_type',p_geometry->>'type','area_m2',area,
   'representative_point_inside_polygon',p_evidence->'representative_point_inside_polygon',
   'checks',p_evidence->'checks','legal_note',p_evidence->>'legal_note',
   'reviewed_by',p_evidence->>'reviewed_by','reviewed_at',p_evidence->>'reviewed_at',
   'recorded_at',to_jsonb(now())));
 UPDATE public.development_projects SET
   geometry=shape, geometry_source=p_geometry_source, geometry_verified=true,
   geometry_verified_at=now(),
   field_evidence=COALESCE(field_evidence,'{}'::jsonb)||jsonb_build_object('boundary',evidence),
   revision=next_revision, updated_at=now()
 WHERE project_id=p_project_id RETURNING * INTO newrow;
 RETURN jsonb_build_object('result','boundary_set','project_id',p_project_id,
   'revision',newrow.revision,'geometry_source',newrow.geometry_source,
   'geometry_verified',newrow.geometry_verified,'area_m2',area,
   'geometry_type',extensions.GeometryType(newrow.geometry),
   'location_untouched',newrow.location IS NOT DISTINCT FROM oldrow.location,
   'stage_untouched',newrow.stage IS NOT DISTINCT FROM oldrow.stage,
   'identity_untouched',newrow.external_id IS NOT DISTINCT FROM oldrow.external_id
     AND newrow.official_authority IS NOT DISTINCT FROM oldrow.official_authority);
END;
$fn$;

REVOKE ALL ON FUNCTION public.zipon_set_project_boundary(uuid,jsonb,text,text,text,bigint,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_set_project_boundary(uuid,jsonb,text,text,text,bigint,jsonb) TO service_role;
COMMENT ON FUNCTION public.zipon_set_project_boundary(uuid,jsonb,text,text,text,bigint,jsonb) IS
  'Writes one reviewed official boundary. Never overwrites a verified boundary, never touches location/stage/identity, refuses a district mismatch or a stored point outside the polygon.';

-- 지도용 읽기 전용 목록. 경계를 GeoJSON으로 내보내는 유일한 경로다. PostgREST가 geometry를
-- EWKB hex로 주기 때문에, 화면이 쓸 수 있는 형태는 여기서 만든다. 확인된 경계만 내보낸다.
CREATE OR REPLACE FUNCTION public.zipon_development_map(
  p_sigungu text DEFAULT NULL, p_limit integer DEFAULT 500)
RETURNS TABLE(project_id uuid, project_name text, project_type text, sigungu text, dong text,
 address text, stage_raw text, status text, validation_status text,
 longitude double precision, latitude double precision,
 boundary jsonb, geometry_verified boolean, geometry_source text,
 geometry_verified_at timestamptz, boundary_area_m2 double precision,
 last_verified_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $fn$
BEGIN
 IF p_limit IS NULL OR NOT (p_limit BETWEEN 1 AND 500) THEN
   RAISE EXCEPTION 'Invalid map limit' USING ERRCODE='22023'; END IF;
 RETURN QUERY
 SELECT p.project_id,p.project_name,p.project_type,p.sigungu,p.dong,p.address,p.stage_raw,
   p.status,p.validation_status,
   CASE WHEN p.location IS NOT NULL THEN extensions.ST_X(p.location::extensions.geometry) END,
   CASE WHEN p.location IS NOT NULL THEN extensions.ST_Y(p.location::extensions.geometry) END,
   -- 확인되지 않은 geometry는 내보내지 않는다. 화면이 구역으로 그릴 수 없게 한다.
   CASE WHEN p.geometry_verified AND p.geometry IS NOT NULL
        THEN extensions.ST_AsGeoJSON(p.geometry)::jsonb END,
   p.geometry_verified,p.geometry_source,p.geometry_verified_at,
   CASE WHEN p.geometry_verified AND p.geometry IS NOT NULL
        THEN extensions.ST_Area(p.geometry::extensions.geography) END,
   p.last_verified_at
 FROM public.development_projects p
 WHERE p.validation_status<>'REJECTED'
   AND (p_sigungu IS NULL OR p.sigungu=p_sigungu)
 ORDER BY p.sigungu,p.project_name,p.project_id
 LIMIT p_limit;
END;
$fn$;

REVOKE ALL ON FUNCTION public.zipon_development_map(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_development_map(text,integer) TO service_role;
COMMENT ON FUNCTION public.zipon_development_map(text,integer) IS
  'Read-only map list. Emits a boundary only when it is officially verified.';

-- 탐색 RPC가 경계와 그 provenance도 함께 돌려주도록 한다. INSIDE 판정 규칙은 그대로다:
-- geometry_verified이고 점이 polygon 안에 있을 때만 INSIDE다.
DROP FUNCTION IF EXISTS public.zipon_development_search(double precision,double precision,text,double precision,integer);
CREATE OR REPLACE FUNCTION public.zipon_development_search(
 p_longitude double precision DEFAULT NULL, p_latitude double precision DEFAULT NULL,
 p_sigungu text DEFAULT NULL, p_radius_m double precision DEFAULT 1000, p_limit integer DEFAULT 30)
RETURNS TABLE(project_id uuid, project_name text, project_type text, project_stage text,
 status text, validation_status text, relation text, distance_m double precision,
 official_source text, source_url text, verified_at timestamptz,
 longitude double precision, latitude double precision,
 boundary jsonb, geometry_verified boolean, geometry_source text,
 geometry_verified_at timestamptz, sigungu text, dong text, address text)
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
 c.spatial_relation,c.meters,c.source_name,c.evidence_url,c.evidence_verified,
 CASE WHEN c.location IS NOT NULL THEN extensions.ST_X(c.location::extensions.geometry) END,
 CASE WHEN c.location IS NOT NULL THEN extensions.ST_Y(c.location::extensions.geometry) END,
 CASE WHEN c.geometry_verified AND c.geometry IS NOT NULL
      THEN extensions.ST_AsGeoJSON(c.geometry)::jsonb END,
 c.geometry_verified,c.geometry_source,c.geometry_verified_at,c.sigungu,c.dong,c.address
 FROM candidates c WHERE c.spatial_relation<>'OUTSIDE'
 ORDER BY CASE c.spatial_relation WHEN 'INSIDE' THEN 0 WHEN 'NEARBY' THEN 1 ELSE 2 END,
 c.meters NULLS LAST,c.project_id LIMIT p_limit;
END;
$fn$;
REVOKE ALL ON FUNCTION public.zipon_development_search(double precision,double precision,text,double precision,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_development_search(double precision,double precision,text,double precision,integer) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;

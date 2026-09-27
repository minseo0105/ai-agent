-- REVIEWED INSTALL/REPAIR SQL. Not executed by this task. A geocoded representative
-- point onto an existing development project, so the only database path for a
-- geocoder result is one reviewed function instead of a PATCH on the table.
--
-- What it writes: location, location_source, location_verified_at, a location entry
-- in field_evidence, and the revision bump.
-- What it never touches: geometry, geometry_source, geometry_verified (a verified
-- boundary is not derivable from a point), status, stage, validation_status,
-- confidence_level and canonical_source_id.
--
-- Guards, all of which refuse the write instead of correcting it:
--   * the project_id must exist and match exactly, with an optimistic revision check
--   * an existing location is never overwritten; the call returns skipped
--   * the caller's expected 자치구 must equal the stored sigungu
--   * the point must sit inside the Seoul bounding box and carry a finite coordinate
--   * only an EXACT result from a named geocoder is accepted
--   * ACCEPTED, coordinate_verified, longitude-first orientation and all address checks are required
--   * a row with verified geometry is refused while holding its row lock
-- It writes no development_updates row on purpose: a geocode is not an official
-- source snapshot, and development_updates requires an official source_id.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

CREATE OR REPLACE FUNCTION public.zipon_set_project_location(
  p_project_id uuid, p_longitude double precision, p_latitude double precision,
  p_expected_sigungu text, p_geocode_source text, p_confidence text,
  p_expected_revision bigint, p_evidence jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $fn$
DECLARE oldrow public.development_projects; newrow public.development_projects;
 next_revision bigint; evidence jsonb;
BEGIN
 IF p_project_id IS NULL OR p_expected_revision IS NULL OR p_expected_revision<=0
 OR jsonb_typeof(p_evidence) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'Invalid location request' USING ERRCODE='22023'; END IF;
 IF p_confidence IS DISTINCT FROM 'EXACT' THEN
   RETURN jsonb_build_object('result','refused','reason','CONFIDENCE_NOT_EXACT',
     'project_id',p_project_id); END IF;
 IF p_geocode_source IS NULL OR p_geocode_source NOT IN ('NAVER_MAP_GEOCODE','KAKAO_ADDRESS','VWORLD_ADDRESS') THEN
   RETURN jsonb_build_object('result','refused','reason','UNKNOWN_GEOCODE_SOURCE',
     'project_id',p_project_id); END IF;
 IF p_longitude IS NULL OR p_latitude IS NULL
 OR p_longitude<>p_longitude OR p_latitude<>p_latitude
 OR p_longitude NOT BETWEEN 126.734 AND 127.270
 OR p_latitude NOT BETWEEN 37.413 AND 37.715 THEN
   RETURN jsonb_build_object('result','refused','reason','COORDINATE_OUTSIDE_SEOUL',
     'project_id',p_project_id); END IF;
 IF NULLIF(btrim(COALESCE(p_evidence->>'matched_address','')),'') IS NULL
 OR NULLIF(btrim(COALESCE(p_evidence->>'address_used','')),'') IS NULL THEN
   RETURN jsonb_build_object('result','refused','reason','NO_GEOCODE_EVIDENCE',
     'project_id',p_project_id); END IF;
 -- A backend-reviewed ACCEPTED record is required; mere address strings are insufficient.
 IF p_evidence->>'geocode_status' IS DISTINCT FROM 'ACCEPTED'
 OR p_evidence->'coordinate_verified' IS DISTINCT FROM 'true'::jsonb
 OR p_evidence->>'coordinate_orientation' IS DISTINCT FROM 'X_IS_LONGITUDE'
 OR jsonb_typeof(p_evidence->'checks') IS DISTINCT FROM 'object' THEN
   RETURN jsonb_build_object('result','refused','reason','ACCEPTED_EVIDENCE_REQUIRED',
     'project_id',p_project_id); END IF;
 IF NOT (p_evidence->'checks' @> '{"accuracy":true,"bounds":true,"axis_order":true,"seoul":true,"sido_match":true,"district_match":true,"dong_match":true,"lot_match":true}'::jsonb)
 OR EXISTS (SELECT 1 FROM jsonb_each(p_evidence->'checks') AS c(k,v) WHERE c.v IS DISTINCT FROM 'true'::jsonb) THEN
   RETURN jsonb_build_object('result','refused','reason','GEOCODE_CHECKS_NOT_PASSED',
     'project_id',p_project_id); END IF;

 SELECT * INTO oldrow FROM public.development_projects WHERE project_id=p_project_id FOR UPDATE;
 IF NOT FOUND THEN
   RETURN jsonb_build_object('result','refused','reason','PROJECT_NOT_FOUND',
     'project_id',p_project_id); END IF;
 IF oldrow.revision IS DISTINCT FROM p_expected_revision THEN
   RETURN jsonb_build_object('result','refused','reason','REVISION_CONFLICT',
     'project_id',p_project_id,'revision',oldrow.revision); END IF;
 IF oldrow.geometry_verified IS TRUE THEN
   RETURN jsonb_build_object('result','refused','reason','VERIFIED_BOUNDARY_PRESENT',
     'project_id',p_project_id); END IF;
 IF oldrow.location IS NOT NULL THEN
   -- 이미 있는 좌표는 덮어쓰지 않는다. 교체는 별도 검토 절차의 일이다.
   RETURN jsonb_build_object('result','skipped','reason','LOCATION_ALREADY_SET',
     'project_id',p_project_id,'revision',oldrow.revision); END IF;
 IF btrim(COALESCE(oldrow.sigungu,'')) IS DISTINCT FROM btrim(COALESCE(p_expected_sigungu,'')) THEN
   RETURN jsonb_build_object('result','refused','reason','DISTRICT_MISMATCH',
     'project_id',p_project_id,'stored_sigungu',oldrow.sigungu); END IF;

 next_revision:=oldrow.revision+1;
 evidence:=jsonb_strip_nulls(jsonb_build_object(
   'value',jsonb_build_object('longitude',p_longitude,'latitude',p_latitude),
   'source',p_geocode_source,'confidence',p_confidence,
   'address_used',p_evidence->>'address_used','matched_address',p_evidence->>'matched_address',
   'road_address',p_evidence->>'road_address','jibun_address',p_evidence->>'jibun_address',
   'english_address',p_evidence->>'english_address',
   'address_elements',p_evidence->'address_elements','checks',p_evidence->'checks',
   'geocode_status',p_evidence->>'geocode_status','coordinate_verified',p_evidence->'coordinate_verified',
   'axis_order','x=longitude,y=latitude','geocoded_at',p_evidence->>'geocoded_at',
   'recorded_at',to_jsonb(now())));
 UPDATE public.development_projects SET
   location=extensions.ST_SetSRID(extensions.ST_MakePoint(p_longitude,p_latitude),4326)::extensions.geography,
   location_source=p_geocode_source, location_verified_at=now(),
   field_evidence=COALESCE(field_evidence,'{}'::jsonb)||jsonb_build_object('location',evidence),
   revision=next_revision, updated_at=now()
 WHERE project_id=p_project_id RETURNING * INTO newrow;
 RETURN jsonb_build_object('result','location_set','project_id',p_project_id,
   'revision',newrow.revision,'location_source',newrow.location_source,
   'geometry_untouched',newrow.geometry IS NOT DISTINCT FROM oldrow.geometry,
   'geometry_verified',newrow.geometry_verified);
END;
$fn$;

REVOKE ALL ON FUNCTION public.zipon_set_project_location(uuid,double precision,double precision,text,text,text,bigint,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_set_project_location(uuid,double precision,double precision,text,text,text,bigint,jsonb) TO service_role;
COMMENT ON FUNCTION public.zipon_set_project_location(uuid,double precision,double precision,text,text,text,bigint,jsonb) IS
  'Writes a geocoded representative point only. Never sets geometry, never overwrites an existing location, refuses a 자치구 mismatch.';
NOTIFY pgrst,'reload schema';
COMMIT;

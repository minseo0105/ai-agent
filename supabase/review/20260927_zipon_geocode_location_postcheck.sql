-- NEW zipon-realestate only. Run the ENTIRE file as Dashboard postgres.
-- Rollback-only functional test for zipon_set_project_location. NOT read-only: it
-- writes inside a subtransaction and rolls every write back, on success and on
-- failure alike. No DELETE, no TRUNCATE, no DDL, no credential value anywhere.
--
-- The test input is SELECTed from the database: the target project's own revision
-- and sigungu are read, never hand-written. The fixture coordinate is a throwaway
-- Seoul point that exists only inside the rolled-back subtransaction.
-- After the final ROLLBACK the target project is byte-for-byte unchanged and the
-- table counts match the values captured before the test.
BEGIN;
SET LOCAL statement_timeout='60s';
SET LOCAL lock_timeout='5s';
DO $test$
DECLARE target_id uuid:='0922ac26-1436-5158-853d-49d3c5aed7fb';
 fixture_longitude double precision:=127.0; fixture_latitude double precision:=37.55;
 before_row public.development_projects; after_row public.development_projects;
 evidence jsonb; answer jsonb; rev bigint;
 before_projects bigint; before_updates bigint; before_located bigint; before_verified_geometry bigint;
 updates_now bigint; results jsonb:='[]'; ok boolean;
BEGIN
 SELECT * INTO before_row FROM public.development_projects WHERE project_id=target_id;
 SELECT count(*) INTO before_projects FROM public.development_projects;
 SELECT count(*) INTO before_updates FROM public.development_updates;
 SELECT count(*) INTO before_located FROM public.development_projects WHERE location IS NOT NULL;
 SELECT count(*) INTO before_verified_geometry FROM public.development_projects WHERE geometry_verified;
 evidence:=jsonb_build_object('address_used',COALESCE(before_row.address,'POSTCHECK_ADDRESS'),
   'matched_address',COALESCE(before_row.address,'POSTCHECK_ADDRESS'),
   'address_elements',jsonb_build_object('SIDO','서울특별시','SIGUGUN',before_row.sigungu),
   'checks',jsonb_build_object('axis_order',true),'geocoded_at',to_jsonb(now()));
 BEGIN
 SELECT COALESCE((to_regprocedure('public.zipon_set_project_location(uuid,double precision,double precision,text,text,text,bigint,jsonb)') IS NOT NULL),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','zipon_set_project_location exists','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE((SELECT NOT p.prosecdef
 AND has_function_privilege('service_role',p.oid,'EXECUTE')
 AND NOT has_function_privilege('anon',p.oid,'EXECUTE')
 AND NOT has_function_privilege('authenticated',p.oid,'EXECUTE')
 AND NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
   WHERE a.grantee=0 AND a.privilege_type='EXECUTE')
 AND EXISTS(SELECT 1 FROM unnest(p.proconfig) c
   WHERE replace(c,' ','')='search_path=pg_catalog,public,extensions,pg_temp')
 FROM pg_proc p WHERE p.oid=to_regprocedure('public.zipon_set_project_location(uuid,double precision,double precision,text,text,text,bigint,jsonb)')),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','invoker rights, fixed search_path, service_role only','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE((before_row.project_id=target_id AND before_row.location IS NULL
 AND before_row.location_source IS NULL AND NOT before_row.geometry_verified),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','baseline target has no coordinate yet','passed',ok,
   'observed',jsonb_build_object('project_name',before_row.project_name,'revision',before_row.revision,
     'sigungu',before_row.sigungu,'located_rows',before_located,'verified_geometry_rows',before_verified_geometry)));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SET LOCAL ROLE service_role;
 rev:=before_row.revision;

 -- 1. Only an EXACT result from a named geocoder is accepted.
 answer:=public.zipon_set_project_location(target_id,fixture_longitude,fixture_latitude,
   before_row.sigungu,'NAVER_MAP_GEOCODE','GEOCODE_REVIEW',rev,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='CONFIDENCE_NOT_EXACT'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a non EXACT confidence is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 answer:=public.zipon_set_project_location(target_id,fixture_longitude,fixture_latitude,
   before_row.sigungu,'GUESSED_FROM_DONG_CENTROID','EXACT',rev,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='UNKNOWN_GEOCODE_SOURCE'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','an unnamed geocode source is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 2. A coordinate outside Seoul, including a swapped axis pair, is refused.
 answer:=public.zipon_set_project_location(target_id,128.6,35.87,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',rev,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='COORDINATE_OUTSIDE_SEOUL'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a coordinate outside Seoul is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 answer:=public.zipon_set_project_location(target_id,fixture_latitude,fixture_longitude,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',rev,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='COORDINATE_OUTSIDE_SEOUL'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a swapped longitude and latitude pair is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 3. Provenance is mandatory.
 answer:=public.zipon_set_project_location(target_id,fixture_longitude,fixture_latitude,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',rev,'{}'::jsonb);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='NO_GEOCODE_EVIDENCE'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a write without geocode evidence is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 4. Identity guards: wrong 자치구, wrong revision, unknown project.
 answer:=public.zipon_set_project_location(target_id,fixture_longitude,fixture_latitude,
   before_row.sigungu||'_OTHER','NAVER_MAP_GEOCODE','EXACT',rev,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='DISTRICT_MISMATCH'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a 자치구 mismatch is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 answer:=public.zipon_set_project_location(target_id,fixture_longitude,fixture_latitude,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',rev+41,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='REVISION_CONFLICT'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a stale revision is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 answer:=public.zipon_set_project_location(gen_random_uuid(),fixture_longitude,fixture_latitude,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',1,evidence);
 SELECT COALESCE((answer->>'result'='refused' AND answer->>'reason'='PROJECT_NOT_FOUND'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','an unknown project_id is refused','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE(((SELECT to_jsonb(p) IS NOT DISTINCT FROM to_jsonb(before_row)
   FROM public.development_projects p WHERE p.project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','every refusal left the master row untouched','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 5. The accepted write sets the point, the provenance and nothing else.
 SELECT count(*) INTO updates_now FROM public.development_updates WHERE project_id=target_id;
 answer:=public.zipon_set_project_location(target_id,fixture_longitude,fixture_latitude,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',rev,evidence);
 SELECT * INTO after_row FROM public.development_projects WHERE project_id=target_id;
 SELECT COALESCE((answer->>'result'='location_set'
 AND after_row.revision=rev+1 AND after_row.location IS NOT NULL
 AND after_row.location_source='NAVER_MAP_GEOCODE' AND after_row.location_verified_at IS NOT NULL
 AND round(extensions.ST_X(after_row.location::extensions.geometry)::numeric,6)=round(fixture_longitude::numeric,6)
 AND round(extensions.ST_Y(after_row.location::extensions.geometry)::numeric,6)=round(fixture_latitude::numeric,6)
 AND after_row.field_evidence->'location'->>'source'='NAVER_MAP_GEOCODE'
 AND after_row.field_evidence->'location'->>'axis_order'='x=longitude,y=latitude'
 AND (after_row.field_evidence->'location'->'value'->>'longitude')::double precision=fixture_longitude),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','the point, its source and its evidence are written','passed',ok,
   'observed',jsonb_build_object('result',answer->>'result','revision',after_row.revision,
     'location_source',after_row.location_source)));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE((after_row.geometry IS NOT DISTINCT FROM before_row.geometry
 AND after_row.geometry_source IS NOT DISTINCT FROM before_row.geometry_source
 AND after_row.geometry_verified=before_row.geometry_verified
 AND after_row.geometry_verified_at IS NOT DISTINCT FROM before_row.geometry_verified_at
 AND after_row.status=before_row.status AND after_row.stage IS NOT DISTINCT FROM before_row.stage
 AND after_row.validation_status=before_row.validation_status
 AND after_row.confidence_level=before_row.confidence_level
 AND after_row.canonical_source_id IS NOT DISTINCT FROM before_row.canonical_source_id
 AND (SELECT count(*)=updates_now FROM public.development_updates WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','boundary, status, stage and validation are never touched','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 6. An existing coordinate is protected from a second geocode.
 answer:=public.zipon_set_project_location(target_id,127.01,37.56,
   before_row.sigungu,'NAVER_MAP_GEOCODE','EXACT',rev+1,evidence);
 SELECT COALESCE((answer->>'result'='skipped' AND answer->>'reason'='LOCATION_ALREADY_SET'
 AND (SELECT revision=rev+1
   AND round(extensions.ST_X(location::extensions.geometry)::numeric,6)=round(fixture_longitude::numeric,6)
   FROM public.development_projects WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','an existing coordinate is never overwritten','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 RAISE EXCEPTION 'Rollback successful test fixtures' USING ERRCODE='ZP001';
 EXCEPTION
 WHEN SQLSTATE 'ZP001' THEN NULL;
 WHEN OTHERS THEN
 results:=results||jsonb_build_array(jsonb_build_object('check_item','execution SQLSTATE '||SQLSTATE,'passed',false));
 END;
 -- The inner subtransaction has rolled back: SET LOCAL ROLE and every write are gone.
 SELECT * INTO after_row FROM public.development_projects WHERE project_id=target_id;
 SELECT count(*) INTO updates_now FROM public.development_updates;
 SELECT COALESCE((to_jsonb(after_row) IS NOT DISTINCT FROM to_jsonb(before_row)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','TARGET_PROJECT_UNCHANGED','passed',ok,
   'observed',jsonb_build_object('revision',after_row.revision,'location_source',after_row.location_source,
     'has_location',after_row.location IS NOT NULL)));
 SELECT COALESCE(((SELECT count(*)=before_projects FROM public.development_projects)
 AND updates_now=before_updates
 AND (SELECT count(*)=before_located FROM public.development_projects WHERE location IS NOT NULL)
 AND (SELECT count(*)=before_verified_geometry FROM public.development_projects WHERE geometry_verified)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','ROW_COUNTS_AND_COORDINATE_COVERAGE_INTACT','passed',ok,
   'observed',jsonb_build_object('projects',before_projects,'updates',before_updates,
     'located',before_located,'verified_geometry',before_verified_geometry)));
 PERFORM set_config('zipon.geocode_location_postcheck',results::text,true);
END;
$test$;
WITH checks AS (
 SELECT ordinality AS n,value->>'check_item' AS check_item,(value->>'passed')::boolean AS passed,
 value->'observed' AS observed
 FROM jsonb_array_elements(current_setting('zipon.geocode_location_postcheck')::jsonb) WITH ORDINALITY
), combined AS (
 SELECT n,check_item,CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS actual,'PASS'::text AS expected,
 passed,observed FROM checks
 UNION ALL SELECT 9999,'ALL_CHECKS',CASE WHEN bool_and(passed) THEN 'PASS' ELSE 'FAIL' END,'PASS',
 bool_and(passed),NULL FROM checks
)
SELECT check_item,actual,expected,passed,observed FROM combined ORDER BY n;
ROLLBACK;

-- NEW zipon-realestate only. Run ENTIRE file as Dashboard postgres.
-- This is a rollback-only functional test, NOT a read-only query.
-- All fixture writes use random TEST_ZIPON UUID identifiers inside a subtransaction.
-- Success AND failure roll back every fixture before returning results. No DELETE/TRUNCATE.
BEGIN;
SET LOCAL statement_timeout='60s';
SET LOCAL lock_timeout='5s';
DO $test$
DECLARE pid uuid:=gen_random_uuid(); sid uuid:=gen_random_uuid();
 unverified_id uuid:=gen_random_uuid(); point_id uuid:=gen_random_uuid(); empty_id uuid:=gen_random_uuid(); failed_id uuid:=gen_random_uuid();
 tag text; candidate jsonb; evidence jsonb; answer jsonb;
 results jsonb:='[]'; ok boolean; rejected boolean;
BEGIN
 tag:='TEST_ZIPON_'||pid::text;
 BEGIN
 SELECT COALESCE((to_regprocedure('public.zipon_development_search(double precision,double precision,text,double precision,integer)') IS NOT NULL AND to_regprocedure('public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid)') IS NOT NULL),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','function signatures','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT COALESCE(((SELECT count(*)=2 AND bool_and(NOT p.prosecdef
 AND has_function_privilege('service_role',p.oid,'EXECUTE')
 AND NOT has_function_privilege('anon',p.oid,'EXECUTE')
 AND NOT has_function_privilege('authenticated',p.oid,'EXECUTE')
 AND NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE')
 AND EXISTS(SELECT 1 FROM unnest(p.proconfig) c WHERE replace(c,' ','')='search_path=pg_catalog,public,extensions,pg_temp'))
 FROM pg_proc p WHERE p.oid IN (
 to_regprocedure('public.zipon_development_search(double precision,double precision,text,double precision,integer)'),
 to_regprocedure('public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid)')))),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','security and execution privileges','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SET LOCAL ROLE service_role;
 candidate:=jsonb_build_object('project_id',pid,'project_name',tag,'project_type','OTHER','sigungu',tag,'address',tag);
 evidence:=jsonb_build_object('source_name',tag,'source_type','OFFICIAL_WEBSITE','source_url',
 'https://cleanup.seoul.go.kr/TEST/'||tag,'is_official',true,'collected_at',now(),
 'content_hash',repeat('a',64),'raw_snapshot',jsonb_build_object('TEST',tag));
 answer:=public.zipon_ingest_candidate(candidate,evidence,0,NULL);
 SELECT COALESCE((answer->>'result'='new' AND answer->>'revision'='1'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','ingest new candidate','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
answer:=public.zipon_ingest_candidate(candidate,evidence,1,NULL);
 SELECT COALESCE((answer->>'result'='unchanged' AND (SELECT count(*)=1 FROM public.development_updates WHERE project_id=pid)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','repeat candidate unchanged','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
candidate:=candidate||jsonb_build_object('address',tag||' changed address');
answer:=public.zipon_ingest_candidate(candidate,evidence,1,NULL);
 SELECT COALESCE((answer->>'result'='changed' AND answer->>'revision'='2'),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','normalized change with same source hash','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
evidence:=evidence||jsonb_build_object('content_hash',repeat('b',64),'raw_snapshot',jsonb_build_object('TEST',tag,'version',2));
answer:=public.zipon_ingest_candidate(candidate,evidence,2,NULL);
 SELECT COALESCE((answer->>'revision'='3' AND (SELECT count(*)=3 FROM public.development_updates WHERE project_id=pid) AND (SELECT count(*)=2 FROM public.development_project_sources WHERE project_id=pid)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','changed evidence history','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 rejected:=false;
 BEGIN
  PERFORM public.zipon_ingest_candidate(candidate||jsonb_build_object('sigungu','WRONG'),evidence,3,NULL);
 EXCEPTION WHEN SQLSTATE '22023' THEN rejected:=true; END;
 SELECT COALESCE((rejected),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','identity mismatch blocked','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 rejected:=false;
 BEGIN
  PERFORM public.zipon_ingest_candidate(candidate||jsonb_build_object('address',tag||' conflict'),evidence,1,NULL);
 EXCEPTION WHEN SQLSTATE '40001' THEN rejected:=true; END;
 SELECT COALESCE((rejected),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','revision conflict blocked','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 INSERT INTO public.development_project_sources(source_id,project_id,source_name,source_type,source_url,is_official,
 validation_status,verified_at,verified_by,content_hash,raw_snapshot)
 VALUES(sid,pid,tag,'OFFICIAL_NOTICE','https://cleanup.seoul.go.kr/TEST/'||tag,true,
 'VERIFIED',now(),tag,repeat('c',64),jsonb_build_object('TEST',tag));
 UPDATE public.development_projects SET status='ACTIVE',stage='TEST_APPROVED',stage_mapping_version='TEST',
 canonical_source_id=sid,last_verified_at=now(),validation_status='VERIFIED',
 geometry=extensions.ST_GeomFromText('POLYGON((127 37,127.01 37,127.01 37.01,127 37.01,127 37))',4326),
 geometry_source=tag,geometry_verified=true,geometry_verified_at=now()
 WHERE project_id=pid AND project_name=tag;
 evidence:=evidence||jsonb_build_object('content_hash',repeat('d',64),'raw_snapshot',jsonb_build_object('TEST',tag,'version',3));
 candidate:=candidate||jsonb_build_object('geometry_verified',false,'status','CANCELLED');
 answer:=public.zipon_ingest_candidate(candidate,evidence,3,NULL);
 SELECT COALESCE(((SELECT geometry_verified AND status='ACTIVE' AND stage='TEST_APPROVED'
 AND canonical_source_id=sid AND validation_status='VERIFIED' AND revision=4
 FROM public.development_projects WHERE project_id=pid)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','verified and canonical source protected','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT COALESCE(((SELECT relation='INSIDE' AND distance_m=0 FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=pid)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','verified polygon INSIDE','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 INSERT INTO public.development_projects(project_id,project_name,project_type,sigungu,geometry,geometry_source)
 VALUES(unverified_id,tag||'_unverified','OTHER',tag,
 extensions.ST_GeomFromText('POLYGON((127 37,127.01 37,127.01 37.01,127 37.01,127 37))',4326),tag);
 INSERT INTO public.development_projects(project_id,project_name,project_type,sigungu,location,location_source)
 VALUES(point_id,tag||'_point','OTHER',tag,extensions.ST_GeogFromText('SRID=4326;POINT(127.005 37.005)'),tag);
 INSERT INTO public.development_projects(project_id,project_name,project_type,sigungu)
 VALUES(empty_id,tag||'_empty','OTHER',tag);
 SELECT COALESCE(((SELECT relation='NEARBY' FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=unverified_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','unverified polygon never INSIDE','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT COALESCE(((SELECT relation='NEARBY' AND distance_m=0 FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=point_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','representative point only NEARBY','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT COALESCE(((SELECT relation='UNKNOWN' AND distance_m IS NULL FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=empty_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','no spatial UNKNOWN','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT COALESCE(((SELECT distance_m BETWEEN 110 AND 112 FROM public.zipon_development_search(127.005,37.006,tag,1000,100) WHERE project_id=point_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','geography distance meters','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT COALESCE(((SELECT relation='NEARBY' FROM public.zipon_development_search(127,37,tag,1000,100) WHERE project_id=pid)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','boundary is not INSIDE','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 rejected:=false;
 BEGIN
  PERFORM public.zipon_ingest_candidate(candidate||jsonb_build_object('project_id',failed_id,'project_name',tag||'_failed'),
    evidence||jsonb_build_object('collected_at','invalid timestamp'),0,NULL);
 EXCEPTION WHEN invalid_datetime_format THEN rejected:=true; END;
 SELECT COALESCE((rejected AND NOT EXISTS(SELECT 1 FROM public.development_projects WHERE project_id=failed_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','failed ingest has no partial master','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 RAISE EXCEPTION 'Rollback successful test fixtures' USING ERRCODE='ZP001';
 EXCEPTION
 WHEN SQLSTATE 'ZP001' THEN NULL;
 WHEN OTHERS THEN
 results:=results||jsonb_build_array(jsonb_build_object('check_item','execution SQLSTATE '||SQLSTATE,'passed',false));
 END;
 -- The inner subtransaction has rolled back, including SET LOCAL ROLE and every fixture.
 SELECT NOT EXISTS(SELECT 1 FROM public.development_projects WHERE project_id IN(pid,unverified_id,point_id,empty_id,failed_id))
 AND NOT EXISTS(SELECT 1 FROM public.development_project_sources WHERE project_id IN(pid,unverified_id,point_id,empty_id,failed_id))
 AND NOT EXISTS(SELECT 1 FROM public.development_updates WHERE project_id IN(pid,unverified_id,point_id,empty_id,failed_id)) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','TEST_FIXTURES_ROLLED_BACK','passed',ok));
 PERFORM set_config('zipon.rpc_postcheck',results::text,true);
END;
$test$;
WITH checks AS (
 SELECT ordinality AS n,value->>'check_item' AS check_item,(value->>'passed')::boolean AS passed
 FROM jsonb_array_elements(current_setting('zipon.rpc_postcheck')::jsonb) WITH ORDINALITY
), combined AS (
 SELECT n,check_item,CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS actual,'PASS'::text AS expected,passed FROM checks
 UNION ALL SELECT 9999,'ALL_CHECKS',CASE WHEN bool_and(passed) THEN 'PASS' ELSE 'FAIL' END,'PASS',bool_and(passed) FROM checks
)
SELECT check_item,actual,expected,passed FROM combined ORDER BY n;
ROLLBACK;

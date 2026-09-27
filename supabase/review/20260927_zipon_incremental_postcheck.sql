-- NEW zipon-realestate only. Run the ENTIRE file as Dashboard postgres.
-- Rollback-only functional test for zipon_ingest_candidate_v2 and
-- zipon_record_source_missing. NOT read-only: it writes inside a subtransaction
-- and rolls every write back, on success and on failure alike.
--
-- The test input is SELECTed from the database: the candidate and the official
-- source come from the target project's own latest development_updates snapshot,
-- so nobody copies a source_url, content_hash or external_id by hand.
-- Fixture rows use random TEST_ZIPON identifiers. No DELETE, no TRUNCATE, no DDL.
-- After the final ROLLBACK the existing 18 rows are byte-for-byte unchanged, and
-- the last checks prove it by comparing against values captured before the test.
BEGIN;
SET LOCAL statement_timeout='60s';
SET LOCAL lock_timeout='5s';
DO $test$
DECLARE target_id uuid:='0922ac26-1436-5158-853d-49d3c5aed7fb';
 fixture_id uuid:=gen_random_uuid(); verified_source uuid:=gen_random_uuid();
 tag text; before_row public.development_projects; after_row public.development_projects;
 base_candidate jsonb; base_source jsonb; candidate jsonb; answer jsonb; latest public.development_updates;
 before_updates bigint; before_projects bigint; before_all_updates bigint; before_sources bigint;
 rev bigint; updates_now bigint; results jsonb:='[]'; ok boolean; rejected boolean; blocked integer:=0;
BEGIN
 tag:='TEST_ZIPON_'||fixture_id::text;
 -- Captured as postgres, before anything is written, for the final comparison.
 SELECT * INTO before_row FROM public.development_projects WHERE project_id=target_id;
 SELECT count(*) INTO before_updates FROM public.development_updates WHERE project_id=target_id;
 SELECT count(*) INTO before_sources FROM public.development_project_sources WHERE project_id=target_id;
 SELECT count(*) INTO before_projects FROM public.development_projects;
 SELECT count(*) INTO before_all_updates FROM public.development_updates;
 BEGIN
 SELECT COALESCE((to_regprocedure('public.zipon_ingest_candidate_v2(jsonb,jsonb,bigint,jsonb,uuid)') IS NOT NULL
 AND to_regprocedure('public.zipon_record_source_missing(uuid,text,uuid)') IS NOT NULL
 AND to_regprocedure('public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid)') IS NOT NULL),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','v2 functions exist and v1 is still present','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE(((SELECT count(*)=2 AND bool_and(NOT p.prosecdef
 AND has_function_privilege('service_role',p.oid,'EXECUTE')
 AND NOT has_function_privilege('anon',p.oid,'EXECUTE')
 AND NOT has_function_privilege('authenticated',p.oid,'EXECUTE')
 AND NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE')
 AND EXISTS(SELECT 1 FROM unnest(p.proconfig) c WHERE replace(c,' ','')='search_path=pg_catalog,public,extensions,pg_temp'))
 FROM pg_proc p WHERE p.oid IN (
 to_regprocedure('public.zipon_ingest_candidate_v2(jsonb,jsonb,bigint,jsonb,uuid)'),
 to_regprocedure('public.zipon_record_source_missing(uuid,text,uuid)')))),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','invoker rights, fixed search_path, service_role only','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- Declared baseline: revision 1, NEEDS_REVIEW, exactly one history row.
 SELECT COALESCE((before_row.project_id=target_id AND before_row.revision=1
 AND before_row.validation_status='NEEDS_REVIEW' AND before_row.status='UNKNOWN'
 AND before_row.stage IS NULL AND before_updates=1 AND before_projects=18),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','baseline is the expected 18 rows and revision 1','passed',ok,
   'observed',jsonb_build_object('project_name',before_row.project_name,'revision',before_row.revision,
     'validation_status',before_row.validation_status,'update_count',before_updates,'projects',before_projects)));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- Test input is read from the database, never hand-written.
 SELECT * INTO latest FROM public.development_updates u
 WHERE u.project_id=target_id ORDER BY u.to_revision DESC LIMIT 1;
 base_candidate:=latest.new_snapshot->'candidate';
 base_source:=latest.new_snapshot->'source';
 SELECT COALESCE((jsonb_typeof(base_candidate)='object' AND jsonb_typeof(base_source)='object'
 AND base_candidate->>'project_id'=target_id::text
 AND base_source->>'source_url' ~ '^https://(cleanup\.seoul\.go\.kr|news\.seoul\.go\.kr)/'
 AND base_source->>'content_hash' ~ '^[0-9a-f]{64}$'
 AND base_source->>'external_id' IS NOT DISTINCT FROM base_candidate->>'external_id'
 AND (base_source->>'content_hash')=(SELECT s.content_hash FROM public.development_project_sources s
   WHERE s.source_id=latest.source_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','candidate and official source read from the stored snapshot','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SET LOCAL ROLE service_role;

 -- 1. The identical candidate is a no-op.
 answer:=public.zipon_ingest_candidate_v2(base_candidate,base_source,before_row.revision,'{}'::jsonb,NULL);
 SELECT COALESCE((answer->>'result'='unchanged'
 AND (SELECT revision=before_row.revision FROM public.development_projects WHERE project_id=target_id)
 AND (SELECT count(*)=before_updates FROM public.development_updates WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','identical candidate is unchanged with no new history','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 2. One controlled DETAIL change. The existing address must survive it.
 candidate:=base_candidate||jsonb_build_object('address',(base_candidate->>'address')||' '||tag);
 answer:=public.zipon_ingest_candidate_v2(candidate,base_source,before_row.revision,'{}'::jsonb,NULL);
 SELECT revision INTO rev FROM public.development_projects WHERE project_id=target_id;
 SELECT count(*) INTO updates_now FROM public.development_updates WHERE project_id=target_id;
 SELECT COALESCE((answer->>'result'='changed' AND answer->>'update_kind'='DETAIL'
 AND answer->'changed_fields'=jsonb_build_array('address')
 AND answer->'filled_fields'='[]'::jsonb
 AND rev=before_row.revision+1 AND updates_now=before_updates+1),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','DETAIL change: changed_fields exact, revision +1, history +1','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE(((SELECT address IS NOT DISTINCT FROM before_row.address
 AND project_name IS NOT DISTINCT FROM before_row.project_name
 AND stage_raw IS NOT DISTINCT FROM before_row.stage_raw
 FROM public.development_projects WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','existing values are never overwritten','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE(((SELECT update_kind='DETAIL' AND changed_fields=ARRAY['address']
 AND previous_stage IS NOT DISTINCT FROM before_row.stage_raw
 AND new_stage IS NOT DISTINCT FROM base_candidate->>'stage_raw'
 AND previous_status='UNKNOWN' AND new_status='UNKNOWN'
 AND from_revision=before_row.revision AND to_revision=before_row.revision+1
 FROM public.development_updates WHERE project_id=target_id ORDER BY to_revision DESC LIMIT 1)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','history row records the diff and the transition columns','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 3. A blank column may be filled; a populated one may not.
 candidate:=base_candidate||jsonb_build_object('planned_units',480,'dong',tag);
 answer:=public.zipon_ingest_candidate_v2(candidate,base_source,rev,'{}'::jsonb,NULL);
 SELECT COALESCE((answer->>'result'='changed'
 AND answer->'filled_fields'=jsonb_build_array('planned_units')
 AND answer->'changed_fields'=jsonb_build_array('dong','planned_units')
 AND (SELECT planned_units=480 AND dong IS NOT DISTINCT FROM before_row.dong
   FROM public.development_projects WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','FILL_BLANKS fills only the blank column','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT revision INTO rev FROM public.development_projects WHERE project_id=target_id;

 -- 4. A candidate can never promote status, stage or validation_status.
 FOREACH candidate IN ARRAY ARRAY[
   base_candidate||jsonb_build_object('status','ACTIVE'),
   base_candidate||jsonb_build_object('stage','ASSOCIATION_APPROVED'),
   base_candidate||jsonb_build_object('validation_status','VERIFIED')] LOOP
   rejected:=false;
   BEGIN
     PERFORM public.zipon_ingest_candidate_v2(candidate,base_source,rev,'{}'::jsonb,NULL);
   EXCEPTION WHEN SQLSTATE '22023' THEN rejected:=true; END;
   IF rejected THEN blocked:=blocked+1; END IF;
 END LOOP;
 SELECT COALESCE((blocked=3
 AND (SELECT revision=rev AND status='UNKNOWN' AND stage IS NULL AND validation_status='NEEDS_REVIEW'
   FROM public.development_projects WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','status, stage and validation_status promotion blocked','passed',ok,
   'observed',jsonb_build_object('rejected',blocked)));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 5. A flagged review records history but fills nothing.
 candidate:=base_candidate||jsonb_build_object('area_m2',1234.5,'address',(base_candidate->>'address')||' review '||tag);
 answer:=public.zipon_ingest_candidate_v2(candidate,base_source,rev,
   jsonb_build_object('kind','STAGE_CHANGE','review_required',true,
     'review_reasons',jsonb_build_array('STAGE_REGRESSION')),NULL);
 SELECT COALESCE((answer->>'result'='review_required' AND answer->'filled_fields'='[]'::jsonb
 AND answer->'review_reasons'=jsonb_build_array('STAGE_REGRESSION')
 AND (SELECT area_m2 IS NULL FROM public.development_projects WHERE project_id=target_id)
 AND (SELECT description LIKE 'REVIEW_REQUIRED:%' FROM public.development_updates
   WHERE project_id=target_id ORDER BY to_revision DESC LIMIT 1)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','review_required keeps the master row out of it','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
 SELECT revision INTO rev FROM public.development_projects WHERE project_id=target_id;

 -- 6. A VERIFIED master row is untouchable, tested on a TEST_ZIPON fixture.
 answer:=public.zipon_ingest_candidate_v2(
   jsonb_build_object('project_id',fixture_id,'project_name',tag,'project_type','OTHER',
     'sigungu',tag,'address',tag,'stage_raw',tag||'_stage'),
   jsonb_build_object('source_name',tag,'source_type','OFFICIAL_WEBSITE',
     'source_url','https://cleanup.seoul.go.kr/TEST/'||tag,'is_official',true,'collected_at',now(),
     'content_hash',repeat('a',64),'raw_snapshot',jsonb_build_object('TEST',tag)),0,'{}'::jsonb,NULL);
 SELECT COALESCE((answer->>'result'='new' AND answer->>'revision'='1'
 AND answer->>'update_kind'='INITIAL'
 AND answer->'changed_fields'=jsonb_build_array('candidate_evidence')),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','INITIAL ingest of a fixture project','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 INSERT INTO public.development_project_sources(source_id,project_id,source_name,source_type,source_url,
 is_official,validation_status,verified_at,verified_by,content_hash,raw_snapshot)
 VALUES(verified_source,fixture_id,tag,'OFFICIAL_NOTICE','https://cleanup.seoul.go.kr/TEST/verified/'||tag,
 true,'VERIFIED',now(),tag,repeat('c',64),jsonb_build_object('TEST',tag));
 UPDATE public.development_projects SET validation_status='VERIFIED',canonical_source_id=verified_source,
 last_verified_at=now() WHERE project_id=fixture_id;
 answer:=public.zipon_ingest_candidate_v2(
   jsonb_build_object('project_id',fixture_id,'project_name',tag,'project_type','OTHER',
     'sigungu',tag,'address',tag,'stage_raw',tag||'_stage','dong',tag||'_dong','planned_units',99),
   jsonb_build_object('source_name',tag,'source_type','OFFICIAL_WEBSITE',
     'source_url','https://cleanup.seoul.go.kr/TEST/'||tag,'is_official',true,'collected_at',now(),
     'content_hash',repeat('b',64),'raw_snapshot',jsonb_build_object('TEST',tag,'version',2)),1,'{}'::jsonb,NULL);
 SELECT COALESCE((answer->'filled_fields'='[]'::jsonb
 AND (SELECT validation_status='VERIFIED' AND dong IS NULL AND planned_units IS NULL AND revision=2
   FROM public.development_projects WHERE project_id=fixture_id)
 AND (SELECT count(*)=2 FROM public.development_updates WHERE project_id=fixture_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','VERIFIED master keeps its values and is never downgraded','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 7. Absence from a listing is recorded, and only recorded.
 SELECT count(*) INTO updates_now FROM public.development_updates WHERE project_id=target_id;
 answer:=public.zipon_record_source_missing(target_id,'ABSENT_FROM_OFFICIAL_LISTING postcheck '||tag,NULL);
 SELECT * INTO after_row FROM public.development_projects WHERE project_id=target_id;
 SELECT COALESCE((answer->>'result'='source_missing_recorded' AND answer->>'update_kind'='SOURCE_MISSING'
 AND after_row.revision=rev+1
 AND (SELECT count(*)=updates_now+1 FROM public.development_updates WHERE project_id=target_id)
 AND after_row.status='UNKNOWN' AND after_row.stage IS NULL
 AND after_row.validation_status=before_row.validation_status
 AND after_row.stage_raw IS NOT DISTINCT FROM before_row.stage_raw),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','SOURCE_MISSING recorded without touching status, stage or validation','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE(((SELECT update_kind='SOURCE_MISSING'
 AND previous_status IS NOT DISTINCT FROM new_status
 AND previous_stage IS NOT DISTINCT FROM new_stage
 AND changed_fields=ARRAY['source_presence']
 AND description LIKE 'ABSENCE_IS_NOT_CANCELLATION:%'
 FROM public.development_updates WHERE project_id=target_id ORDER BY to_revision DESC LIMIT 1)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','absence history states no status transition','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 8. Repeating the same absence must not grow revisions or history.
 SELECT revision INTO rev FROM public.development_projects WHERE project_id=target_id;
 SELECT count(*) INTO updates_now FROM public.development_updates WHERE project_id=target_id;
 answer:=public.zipon_record_source_missing(target_id,'ABSENT_FROM_OFFICIAL_LISTING repeat '||tag,NULL);
 SELECT COALESCE((answer->>'result'='unchanged'
 AND (SELECT revision=rev FROM public.development_projects WHERE project_id=target_id)
 AND (SELECT count(*)=updates_now FROM public.development_updates WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','repeated SOURCE_MISSING adds no revision and no history','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 RAISE EXCEPTION 'Rollback successful test fixtures' USING ERRCODE='ZP001';
 EXCEPTION
 WHEN SQLSTATE 'ZP001' THEN NULL;
 WHEN OTHERS THEN
 results:=results||jsonb_build_array(jsonb_build_object('check_item','execution SQLSTATE '||SQLSTATE,'passed',false));
 END;
 -- The inner subtransaction has rolled back: SET LOCAL ROLE, the fixture project
 -- and every write against the target project are gone.
 SELECT * INTO after_row FROM public.development_projects WHERE project_id=target_id;
 SELECT count(*) INTO updates_now FROM public.development_updates WHERE project_id=target_id;
 -- Compared as jsonb so every column counts, including the spatial ones.
 SELECT COALESCE((to_jsonb(after_row) IS NOT DISTINCT FROM to_jsonb(before_row) AND updates_now=before_updates
 AND (SELECT count(*)=before_sources FROM public.development_project_sources WHERE project_id=target_id)),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','TARGET_PROJECT_UNCHANGED','passed',ok,
   'observed',jsonb_build_object('revision',after_row.revision,'validation_status',after_row.validation_status,
     'status',after_row.status,'update_count',updates_now)));
 SELECT NOT EXISTS(SELECT 1 FROM public.development_projects WHERE project_id=fixture_id)
 AND NOT EXISTS(SELECT 1 FROM public.development_project_sources WHERE project_id=fixture_id)
 AND NOT EXISTS(SELECT 1 FROM public.development_updates WHERE project_id=fixture_id)
 AND NOT EXISTS(SELECT 1 FROM public.development_projects WHERE project_name LIKE 'TEST_ZIPON_%') INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','TEST_FIXTURES_ROLLED_BACK','passed',ok));
 SELECT (SELECT count(*)=before_projects FROM public.development_projects)
 AND (SELECT count(*)=before_all_updates FROM public.development_updates) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','EIGHTEEN_ROWS_AND_HISTORY_INTACT','passed',ok,
   'observed',jsonb_build_object('projects',before_projects,'updates',before_all_updates)));
 PERFORM set_config('zipon.incremental_postcheck',results::text,true);
END;
$test$;
WITH checks AS (
 SELECT ordinality AS n,value->>'check_item' AS check_item,(value->>'passed')::boolean AS passed,
 value->'observed' AS observed
 FROM jsonb_array_elements(current_setting('zipon.incremental_postcheck')::jsonb) WITH ORDINALITY
), combined AS (
 SELECT n,check_item,CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS actual,'PASS'::text AS expected,
 passed,observed FROM checks
 UNION ALL SELECT 9999,'ALL_CHECKS',CASE WHEN bool_and(passed) THEN 'PASS' ELSE 'FAIL' END,'PASS',
 bool_and(passed),NULL FROM checks
)
SELECT check_item,actual,expected,passed,observed FROM combined ORDER BY n;
ROLLBACK;

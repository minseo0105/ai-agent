from pathlib import Path
import json,re
R=Path(__file__).resolve().parents[1]
p=R/'supabase/migrations/20260927_zipon_candidate_ingest_rpc.sql';s=p.read_text(encoding='utf-8')
s=s.replace('BEGIN;\nCREATE', "BEGIN;\nSET LOCAL lock_timeout='5s';\nSET LOCAL statement_timeout='60s';\nCREATE",1)
s=s.replace(' BEGIN\n',' BEGIN\n')
s=s.replace(" pid:=(p_project->>'project_id')::uuid;", """ IF jsonb_typeof(p_project) IS DISTINCT FROM 'object' OR jsonb_typeof(p_source) IS DISTINCT FROM 'object'
 OR jsonb_typeof(p_source->'raw_snapshot') IS DISTINCT FROM 'object'
 OR NULLIF(btrim(p_source->>'source_name'),'') IS NULL
 OR NULLIF(p_source->>'collected_at','') IS NULL THEN
 RAISE EXCEPTION 'Invalid candidate document' USING ERRCODE='22023'; END IF;
 pid:=(p_project->>'project_id')::uuid;""")
s=s.replace(" IF FOUND THEN\n", """ IF FOUND THEN
   IF (oldrow.official_authority IS NOT NULL AND
       (oldrow.official_authority IS DISTINCT FROM p_project->>'official_authority'
        OR oldrow.external_id IS DISTINCT FROM p_project->>'external_id'))
   OR oldrow.project_type IS DISTINCT FROM p_project->>'project_type'
   OR oldrow.sigungu IS DISTINCT FROM p_project->>'sigungu' THEN
     RAISE EXCEPTION 'Candidate identity mismatch' USING ERRCODE='22023';
   END IF;
""",1)
s=s.replace("AND u.new_snapshot->'source'->>'source_url'=p_source->>'source_url'", "AND u.new_snapshot->'source'->>'source_url'=p_source->>'source_url'\n       AND u.new_snapshot->'candidate'=p_project")
# Check external source identifiers when present, without manufacturing them for list-only data.
s=s.replace(" -- Serialize first insert", """ IF NULLIF(p_source->>'external_id','') IS NOT NULL
 AND p_source->>'external_id' IS DISTINCT FROM p_project->>'external_id' THEN
 RAISE EXCEPTION 'Source identity mismatch' USING ERRCODE='22023'; END IF;
 -- Serialize first insert""")
p.write_text(s,encoding='utf-8')
# Explicit pg_temp last prevents implicit temporary schema precedence for relation/type lookup.
for name in ('20260927_zipon_candidate_ingest_rpc.sql','20260927_zipon_spatial_rpc.sql'):
 p=R/'supabase/migrations'/name;s=p.read_text(encoding='utf-8')
 s=s.replace('search_path=pg_catalog,public,extensions','search_path=pg_catalog,public,extensions,pg_temp')
 s=s.replace('search_path = pg_catalog, public, extensions','search_path = pg_catalog, public, extensions, pg_temp')
 p.write_text(s,encoding='utf-8')

checks=[]
def check(label,expr):
 checks.append(f""" SELECT COALESCE(({expr}),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','{label}','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;
""")
check('function signatures', "to_regprocedure('public.zipon_development_search(double precision,double precision,text,double precision,integer)') IS NOT NULL AND to_regprocedure('public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid)') IS NOT NULL")
check('security and execution privileges', """(SELECT count(*)=2 AND bool_and(NOT p.prosecdef
 AND has_function_privilege('service_role',p.oid,'EXECUTE')
 AND NOT has_function_privilege('anon',p.oid,'EXECUTE')
 AND NOT has_function_privilege('authenticated',p.oid,'EXECUTE')
 AND NOT EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE')
 AND EXISTS(SELECT 1 FROM unnest(p.proconfig) c WHERE replace(c,' ','')='search_path=pg_catalog,public,extensions,pg_temp'))
 FROM pg_proc p WHERE p.oid IN (
 to_regprocedure('public.zipon_development_search(double precision,double precision,text,double precision,integer)'),
 to_regprocedure('public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid)')))""")
metadata=''.join(checks);checks=[]
check('ingest new candidate', "answer->>'result'='new' AND answer->>'revision'='1'")
checks.append("answer:=public.zipon_ingest_candidate(candidate,evidence,1,NULL);\n")
check('repeat candidate unchanged', "answer->>'result'='unchanged' AND (SELECT count(*)=1 FROM public.development_updates WHERE project_id=pid)")
checks.append("candidate:=candidate||jsonb_build_object('address',tag||' changed address');\nanswer:=public.zipon_ingest_candidate(candidate,evidence,1,NULL);\n")
check('normalized change with same source hash', "answer->>'result'='changed' AND answer->>'revision'='2'")
checks.append("evidence:=evidence||jsonb_build_object('content_hash',repeat('b',64),'raw_snapshot',jsonb_build_object('TEST',tag,'version',2));\nanswer:=public.zipon_ingest_candidate(candidate,evidence,2,NULL);\n")
check('changed evidence history', "answer->>'revision'='3' AND (SELECT count(*)=3 FROM public.development_updates WHERE project_id=pid) AND (SELECT count(*)=2 FROM public.development_project_sources WHERE project_id=pid)")
checks.append(""" rejected:=false;
 BEGIN
  PERFORM public.zipon_ingest_candidate(candidate||jsonb_build_object('sigungu','WRONG'),evidence,3,NULL);
 EXCEPTION WHEN SQLSTATE '22023' THEN rejected:=true; END;
""")
check('identity mismatch blocked', 'rejected')
checks.append(""" rejected:=false;
 BEGIN
  PERFORM public.zipon_ingest_candidate(candidate||jsonb_build_object('address',tag||' conflict'),evidence,1,NULL);
 EXCEPTION WHEN SQLSTATE '40001' THEN rejected:=true; END;
""")
check('revision conflict blocked', 'rejected')
# Seed only UUID-scoped synthetic approved evidence; service_role has INSERT, not UPDATE sources.
checks.append("""
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
""")
check('verified and canonical source protected', """(SELECT geometry_verified AND status='ACTIVE' AND stage='TEST_APPROVED'
 AND canonical_source_id=sid AND validation_status='VERIFIED' AND revision=4
 FROM public.development_projects WHERE project_id=pid)""")
check('verified polygon INSIDE', """(SELECT relation='INSIDE' AND distance_m=0 FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=pid)""")
checks.append("""
 INSERT INTO public.development_projects(project_id,project_name,project_type,sigungu,geometry,geometry_source)
 VALUES(unverified_id,tag||'_unverified','OTHER',tag,
 extensions.ST_GeomFromText('POLYGON((127 37,127.01 37,127.01 37.01,127 37.01,127 37))',4326),tag);
 INSERT INTO public.development_projects(project_id,project_name,project_type,sigungu,location,location_source)
 VALUES(point_id,tag||'_point','OTHER',tag,extensions.ST_GeogFromText('SRID=4326;POINT(127.005 37.005)'),tag);
 INSERT INTO public.development_projects(project_id,project_name,project_type,sigungu)
 VALUES(empty_id,tag||'_empty','OTHER',tag);
""")
check('unverified polygon never INSIDE', "(SELECT relation='NEARBY' FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=unverified_id)")
check('representative point only NEARBY', "(SELECT relation='NEARBY' AND distance_m=0 FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=point_id)")
check('no spatial UNKNOWN', "(SELECT relation='UNKNOWN' AND distance_m IS NULL FROM public.zipon_development_search(127.005,37.005,tag,1000,100) WHERE project_id=empty_id)")
check('geography distance meters', "(SELECT distance_m BETWEEN 110 AND 112 FROM public.zipon_development_search(127.005,37.006,tag,1000,100) WHERE project_id=point_id)")
check('boundary is not INSIDE', "(SELECT relation='NEARBY' FROM public.zipon_development_search(127,37,tag,1000,100) WHERE project_id=pid)")
checks.append("""
 rejected:=false;
 BEGIN
  PERFORM public.zipon_ingest_candidate(candidate||jsonb_build_object('project_id',failed_id,'project_name',tag||'_failed'),
    evidence||jsonb_build_object('collected_at','invalid timestamp'),0,NULL);
 EXCEPTION WHEN invalid_datetime_format THEN rejected:=true; END;
""")
check('failed ingest has no partial master', "rejected AND NOT EXISTS(SELECT 1 FROM public.development_projects WHERE project_id=failed_id)")
functional=''.join(checks)
post="""-- NEW zipon-realestate only. Run ENTIRE file as Dashboard postgres.
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
"""+metadata+"""
 SET LOCAL ROLE service_role;
 candidate:=jsonb_build_object('project_id',pid,'project_name',tag,'project_type','OTHER','sigungu',tag,'address',tag);
 evidence:=jsonb_build_object('source_name',tag,'source_type','OFFICIAL_WEBSITE','source_url',
 'https://cleanup.seoul.go.kr/TEST/'||tag,'is_official',true,'collected_at',now(),
 'content_hash',repeat('a',64),'raw_snapshot',jsonb_build_object('TEST',tag));
 answer:=public.zipon_ingest_candidate(candidate,evidence,0,NULL);
"""+functional+"""
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
"""
(R/'supabase/review/20260927_zipon_spatial_postcheck.sql').write_text(post,encoding='utf-8')
# Choose a small, deterministic, coverage-oriented canary. Never connect to a database.
data=json.loads((R/'data/development/pilot_20260927.json').read_text(encoding='utf-8'))
chosen=[];seen=set()
def add(row):
 key=(row.get('official_authority'),row.get('external_id')) if row.get('external_id') else (row['sigungu'],re.sub(r'\s+','',row['project_name']))
 if key not in seen:chosen.append(row);seen.add(key)
for district in ('강동구','송파구','서초구'):
 for kind in ('RECONSTRUCTION','REDEVELOPMENT','SHINTONG'):
  rows=[r for r in data['records'] if r['sigungu']==district and r['project_type']==kind]
  if rows:add(sorted(rows,key=lambda r:r['project_id'])[0])
assert 5<=len(chosen)<=10
assert {r['sigungu'] for r in chosen}=={'강동구','송파구','서초구'}
assert {r['project_type'] for r in chosen}=={'RECONSTRUCTION','REDEVELOPMENT','SHINTONG'}
(R/'data/development/canary_20260927.json').write_text(json.dumps({'records':chosen,'policy':'CANARY ONLY; review identities before import'},ensure_ascii=False,indent=2),encoding='utf-8')
p=R/'scripts/import_zipon_candidates.py';s=p.read_text(encoding='utf-8').replace("    # Deliberately independent", "    if not 1 <= len(records) <= 10:\n        raise ValueError('Canary safety limit: at most 10 records; full pilot import blocked')\n    # Deliberately independent")
p.write_text(s,encoding='utf-8')
ids=','.join("'"+r['project_id']+"'::uuid" for r in chosen)
verify=f"""-- Read-only canary verification AFTER separately authorized import. No import here.
BEGIN READ ONLY;
SELECT p.project_id,p.project_name,p.project_type,p.sigungu,p.address,p.official_authority,p.external_id,
p.stage,p.stage_raw,p.status,p.validation_status,p.revision,
(SELECT count(*) FROM public.development_project_sources s WHERE s.project_id=p.project_id) AS source_count,
(SELECT count(*) FROM public.development_updates u WHERE u.project_id=p.project_id) AS history_count
FROM public.development_projects p WHERE p.project_id IN ({ids}) ORDER BY p.sigungu,p.project_type;
SELECT s.project_id,s.source_url,s.is_official,s.validation_status,s.content_hash
FROM public.development_project_sources s WHERE s.project_id IN ({ids});
SELECT p.official_authority,p.external_id,count(*) FROM public.development_projects p
WHERE p.external_id IS NOT NULL AND p.project_id IN ({ids}) GROUP BY 1,2 HAVING count(*)>1;
ROLLBACK;
"""
(R/'supabase/review/20260927_zipon_canary_check.sql').write_text(verify,encoding='utf-8')
(R/'docs/zipon_rpc_predeploy_20260927.md').write_text('''# RPC pre-deploy review

No DB SQL or import executed. Base migration unchanged.

Changes: fixed search_path includes pg_temp last; invoker rights; only service_role EXECUTE; static SQL only. Ingest rejects malformed documents and mismatched official identity/type/district. Candidate equality as well as source hash controls unchanged decisions; normalized changes are no longer lost. Canonical source, verified geometry, stage/status and existing business fields cannot be overwritten by candidate imports. Advisory lock and row lock serialize master/history writes. Failure rolls back function writes. Base FKs remain active. CREATE OR REPLACE preserves signature on reruns; no base objects dropped or altered.

SECURITY INVOKER does not grant RLS bypass; existing service_role BYPASSRLS is deliberate and remains server-only. SQL Editor postgres is also privileged. Caller-provided official URLs are provenance claims, not proof: collectors and human verification remain trusted backend responsibilities. No arbitrary table/column selection or dynamic SQL.

Execution on NEW zipon-realestate as Dashboard postgres:
1. supabase/migrations/20260927_zipon_spatial_rpc.sql
2. supabase/migrations/20260927_zipon_candidate_ingest_rpc.sql
3. supabase/review/20260927_zipon_spatial_postcheck.sql — run ENTIRE file. It temporarily writes TEST_ZIPON UUID fixtures under service_role, catches an intentional subtransaction rollback, verifies absence, returns one result table and ends ROLLBACK. It is no longer read-only. Existing rows are never targeted. If the Editor is interrupted, explicitly ROLLBACK the open transaction before continuing. ALL_CHECKS must be PASS.

Canary: data/development/canary_20260927.json spans all three districts and all three collected types. Inspect the file and source identities first. The importer now blocks >10 records for --apply-new-db. Default invocation remains local only. Do not import the 183-record pilot file.

After all new RPC checks pass and canary review is approved: run scripts/import_zipon_candidates.py data/development/canary_20260927.json --apply-new-db with existing isolated ZIPON_IMPORT_* process variables. This performs real candidate writes; it was not run here. Preserve the returned run_id. Run supabase/review/20260927_zipon_canary_check.sql in SQL Editor and verify IDs, address, source URL, UNKNOWN/NEEDS_REVIEW, revision=1, one initial history per new candidate. Repeating the same canary must yield unchanged and not increment project revisions/history. Collection run records may increase by design. No bulk DELETE cleanup: canary consists of real review candidates and is retained unless a separately reviewed rollback is authorized.

Static parser and mock checks cannot prove actual PostgreSQL function execution; the rollback-only postcheck provides that evidence after applying migrations. No HF/GitHub changes or deployment.
''',encoding='utf-8')
print('Updated RPC safeguards and rollback-only postcheck; canary records:',len(chosen))

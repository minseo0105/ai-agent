-- Reviewed installation required. Never applied by the refresh runner.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';

CREATE TABLE public.development_review_queue (
  review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_key text NOT NULL,
  project_id uuid REFERENCES public.development_projects(project_id) ON DELETE RESTRICT,
  source_hash text NOT NULL CHECK(source_hash ~ '^[0-9a-f]{64}$'),
  reason text NOT NULL,
  candidate jsonb NOT NULL CHECK(jsonb_typeof(candidate)='object'),
  source jsonb NOT NULL CHECK(jsonb_typeof(source)='object'),
  state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','APPROVED','REJECTED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT development_review_dedupe UNIQUE(candidate_key,source_hash,reason)
);
CREATE TABLE public.development_refresh_lease (
  name text PRIMARY KEY CHECK(name='zipon-development'),
  owner uuid NOT NULL,
  expires_at timestamptz NOT NULL
);
ALTER TABLE public.development_review_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.development_refresh_lease ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.development_review_queue,public.development_refresh_lease FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.development_review_queue TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.development_refresh_lease TO service_role;
CREATE INDEX development_review_pending_idx ON public.development_review_queue(state,created_at DESC);

CREATE FUNCTION public.zipon_refresh_lease(p_owner uuid,p_release boolean DEFAULT false)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE claimed uuid;
BEGIN
  IF p_owner IS NULL THEN RAISE EXCEPTION 'Owner required'; END IF;
  IF p_release THEN
    DELETE FROM public.development_refresh_lease WHERE name='zipon-development' AND owner=p_owner;
    RETURN FOUND;
  END IF;
  INSERT INTO public.development_refresh_lease(name,owner,expires_at)
  VALUES('zipon-development',p_owner,now()+interval '40 minutes')
  ON CONFLICT(name) DO UPDATE SET owner=EXCLUDED.owner,expires_at=EXCLUDED.expires_at
  WHERE development_refresh_lease.expires_at<now() OR development_refresh_lease.owner=p_owner
  RETURNING owner INTO claimed;
  RETURN claimed IS NOT NULL;
END $$;

CREATE FUNCTION public.zipon_refresh_stage(p_raw text)
RETURNS text LANGUAGE sql IMMUTABLE SECURITY INVOKER
SET search_path=pg_catalog AS $$
SELECT CASE regexp_replace(p_raw,'\s','','g')
 WHEN '후보지선정' THEN 'CANDIDATE'
 WHEN '안전진단' THEN 'SAFETY_DIAGNOSIS'
 WHEN '정비계획수립' THEN 'PLANNING' WHEN '기본계획수립' THEN 'PLANNING'
 WHEN '주민공람' THEN 'PLANNING' WHEN '재공람' THEN 'PLANNING'
 WHEN '정비계획제안' THEN 'PLANNING' WHEN '구의회의견청취' THEN 'PLANNING'
 WHEN '심의요청' THEN 'PLAN_DELIBERATION' WHEN '심의' THEN 'PLAN_DELIBERATION'
 WHEN '통합심의' THEN 'PLAN_DELIBERATION' WHEN '통심완료' THEN 'PLAN_DELIBERATION'
 WHEN '자문중' THEN 'PLAN_DELIBERATION'
 WHEN '정비계획고시' THEN 'PLAN_NOTICED'
 WHEN '구역지정' THEN 'DESIGNATED' WHEN '정비구역지정' THEN 'DESIGNATED'
 WHEN '정비구역지정고시' THEN 'DESIGNATED'
 WHEN '시행자지정' THEN 'IMPLEMENTER_DESIGNATED' WHEN '시행자지정(조합)' THEN 'IMPLEMENTER_DESIGNATED'
 WHEN '추진위원회승인' THEN 'COMMITTEE' WHEN '추진위승인' THEN 'COMMITTEE'
 WHEN '조합설립추진위원회승인' THEN 'COMMITTEE'
 WHEN '조합설립인가' THEN 'ASSOCIATION_APPROVED'
 WHEN '사업시행인가' THEN 'IMPLEMENTATION_APPROVED'
 WHEN '관리처분인가' THEN 'MANAGEMENT_DISPOSITION'
 WHEN '분양' THEN 'SALES' WHEN '일반분양승인' THEN 'SALES'
 WHEN '철거' THEN 'DEMOLITION' WHEN '철거신고' THEN 'DEMOLITION'
 WHEN '착공' THEN 'CONSTRUCTION' WHEN '착공신고' THEN 'CONSTRUCTION'
 WHEN '준공인가' THEN 'COMPLETED' WHEN '부분준공인가' THEN 'PARTIAL_COMPLETION'
 WHEN '이전고시' THEN 'TRANSFER_NOTICE'
 WHEN '조합해산' THEN 'ASSOCIATION_DISSOLVED' WHEN '조합청산' THEN 'ASSOCIATION_LIQUIDATION'
 ELSE 'UNKNOWN' END
$$;
CREATE FUNCTION public.zipon_refresh_rank(p_stage text)
RETURNS integer LANGUAGE sql IMMUTABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT (('{"CANDIDATE":10,"SAFETY_DIAGNOSIS":15,"PLANNING":20,"PLAN_DELIBERATION":25,
 "PLAN_NOTICED":30,"DESIGNATED":35,"IMPLEMENTER_DESIGNATED":38,"COMMITTEE":40,
 "ASSOCIATION_APPROVED":50,"IMPLEMENTATION_APPROVED":60,"MANAGEMENT_DISPOSITION":70,
 "SALES":75,"DEMOLITION":80,"CONSTRUCTION":85,"PARTIAL_COMPLETION":90,"COMPLETED":95,
 "TRANSFER_NOTICE":97}'::jsonb)->>p_stage)::integer
$$;

CREATE FUNCTION public.zipon_refresh_project(
 p_candidate jsonb,p_source jsonb,p_observation jsonb,p_expected_revision bigint,p_run_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $$
DECLARE oldrow public.development_projects; newrow public.development_projects;
 pid uuid; sid uuid; reason text; normalized text; before_rank integer; after_rank integer;
 delta text[]:='{}'; desired jsonb; latest jsonb; initial boolean; result jsonb;
 basis_date date; notice date; source_day date; source_time timestamptz; key text;
BEGIN
 IF jsonb_typeof(p_candidate) IS DISTINCT FROM 'object'
 OR jsonb_typeof(p_source) IS DISTINCT FROM 'object'
 OR jsonb_typeof(p_observation) IS DISTINCT FROM 'object'
 OR p_expected_revision IS NULL OR p_expected_revision<0
 OR COALESCE(p_source->>'source_url','') !~ '^https://(cleanup\.seoul\.go\.kr|news\.seoul\.go\.kr)/'
 OR p_source->'is_official' IS DISTINCT FROM 'true'::jsonb
 OR COALESCE(p_source->>'content_hash','') !~ '^[0-9a-f]{64}$'
 OR NULLIF(p_source->>'collected_at','') IS NULL
 OR jsonb_typeof(p_source->'raw_snapshot') IS DISTINCT FROM 'object'
 OR NULLIF(p_candidate->>'external_id','') IS NULL
 OR p_candidate->>'official_authority' IS DISTINCT FROM 'cleanup.seoul.go.kr'
 OR p_source->>'external_id' IS DISTINCT FROM p_candidate->>'external_id'
 OR p_candidate->>'status' IS DISTINCT FROM 'UNKNOWN'
 OR NULLIF(p_candidate->>'stage','') IS NOT NULL
 OR COALESCE(p_candidate->>'validation_status','NEEDS_REVIEW') NOT IN ('NEEDS_REVIEW','UNVERIFIED')
 OR p_candidate ? 'geometry' OR p_candidate ? 'location' THEN
   RAISE EXCEPTION 'Invalid refresh provenance' USING ERRCODE='22023';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.development_collection_runs WHERE run_id=p_run_id
   AND NOT dry_run AND status='RUNNING') OR NOT EXISTS(
   SELECT 1 FROM public.development_refresh_lease WHERE owner=p_run_id AND expires_at>now())
   THEN RAISE EXCEPTION 'Active leased run required'; END IF;
 pid:=(p_candidate->>'project_id')::uuid;
 IF pid IS NULL THEN RAISE EXCEPTION 'Project required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(pid::text,0));
 SELECT * INTO oldrow FROM public.development_projects WHERE project_id=pid FOR UPDATE;
 initial:=NOT FOUND;
 IF initial AND p_expected_revision<>0 THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
 key:=pid::text;
 IF NOT initial AND (oldrow.external_id IS DISTINCT FROM p_candidate->>'external_id'
   OR oldrow.official_authority IS DISTINCT FROM p_candidate->>'official_authority'
   OR oldrow.sigungu IS DISTINCT FROM p_candidate->>'sigungu'
   OR oldrow.project_type IS DISTINCT FROM p_candidate->>'project_type'
   OR regexp_replace(oldrow.project_name,'\s','','g') IS DISTINCT FROM regexp_replace(p_candidate->>'project_name','\s','','g')) THEN
   reason:='OFFICIAL_IDENTITY_CONFLICT';
 END IF;
 IF initial AND EXISTS(SELECT 1 FROM public.development_projects WHERE
   (official_authority=p_candidate->>'official_authority' AND external_id=p_candidate->>'external_id')
   OR (sigungu=p_candidate->>'sigungu' AND
     (regexp_replace(project_name,'\s','','g')=regexp_replace(p_candidate->>'project_name','\s','','g')
      OR (length(regexp_replace(project_name,'\s','','g'))>=3 AND
        (strpos(regexp_replace(p_candidate->>'project_name','\s','','g'),regexp_replace(project_name,'\s','','g'))>0
         OR strpos(regexp_replace(project_name,'\s','','g'),regexp_replace(p_candidate->>'project_name','\s','','g'))>0))))) THEN
   reason:='DUPLICATE_SUSPECTED';
 END IF;
 normalized:=public.zipon_refresh_stage(p_observation->>'stage_raw');
 IF p_observation<>'{}'::jsonb THEN
   IF p_observation->>'stage' IS DISTINCT FROM normalized OR normalized='UNKNOWN'
   OR p_observation->>'stage_verified_level' IS DISTINCT FROM 'OFFICIAL_DETAIL_VERIFIED'
   OR COALESCE(p_observation->>'evidence_url','') !~ '^https://cleanup\.seoul\.go\.kr/'
   OR NULLIF(p_observation->>'cafe_id','') IS NULL
   OR substring(p_observation->>'evidence_url' from '[?&]cafeId=([^&#]+)') IS DISTINCT FROM p_observation->>'cafe_id'
   OR p_source->'raw_snapshot'->'detail'->>'current_stage' IS DISTINCT FROM p_observation->>'stage_raw'
   OR p_source->'raw_snapshot'->'detail'->>'cafe_id' IS DISTINCT FROM p_observation->>'cafe_id'
   OR p_observation->'detail_page_matched' IS DISTINCT FROM 'true'::jsonb
   OR p_observation->>'content_hash' IS DISTINCT FROM p_source->>'content_hash' THEN
     reason:=COALESCE(reason,'DETAIL_NOT_VERIFIED');
   END IF;
   before_rank:=public.zipon_refresh_rank(COALESCE(oldrow.stage,public.zipon_refresh_stage(oldrow.stage_raw)));
   after_rank:=public.zipon_refresh_rank(normalized);
   IF after_rank IS NULL OR (before_rank IS NOT NULL AND after_rank<before_rank) THEN
     reason:=COALESCE(reason,'STAGE_REGRESSION_OR_UNORDERED'); END IF;
   IF COALESCE(p_observation->>'status','') NOT IN ('UNKNOWN','COMPLETED')
   OR (p_observation->>'status'='COMPLETED' AND normalized NOT IN ('COMPLETED','TRANSFER_NOTICE')) THEN
     reason:=COALESCE(reason,'STATUS_REVIEW_REQUIRED'); END IF;
   FOREACH key IN ARRAY ARRAY['stage_date','notice_date','source_date','effective_date'] LOOP
     IF NULLIF(p_observation->>key,'') IS NOT NULL THEN
       IF (p_observation->>key) !~ '^\d{4}-\d{2}-\d{2}$'
       OR p_observation->'date_basis'->>key NOT IN ('OFFICIAL_LABEL','CURRENT_MILESTONE')
       OR p_observation->'date_basis'->>key IS NULL THEN
         reason:=COALESCE(reason,'AMBIGUOUS_DATE');
       ELSE
         BEGIN basis_date:=(p_observation->>key)::date;
         EXCEPTION WHEN others THEN reason:=COALESCE(reason,'INVALID_DATE'); END;
       END IF;
     END IF;
   END LOOP;
 END IF;
 key:=pid::text;
 desired:=jsonb_strip_nulls(jsonb_build_object(
   'stage',CASE WHEN p_observation<>'{}'::jsonb THEN normalized END,
   'stage_raw',CASE WHEN p_observation<>'{}'::jsonb THEN p_observation->>'stage_raw' END,
   'status',CASE WHEN p_observation->>'status'='COMPLETED' THEN 'COMPLETED' END,
   'notice_date',p_observation->>'notice_date','source_date',p_observation->>'source_date'));
 IF NOT initial THEN
   IF NULLIF(p_candidate->>'address','') IS NOT NULL AND oldrow.address IS NOT NULL
   AND oldrow.address IS DISTINCT FROM p_candidate->>'address' THEN reason:=COALESCE(reason,'ADDRESS_CHANGED'); END IF;
   IF (oldrow.area_m2 IS NOT NULL AND NULLIF(p_candidate->>'area_m2','') IS NOT NULL
       AND oldrow.area_m2<>(p_candidate->>'area_m2')::numeric)
   OR (oldrow.planned_units IS NOT NULL AND NULLIF(p_candidate->>'planned_units','') IS NOT NULL
       AND oldrow.planned_units<>(p_candidate->>'planned_units')::integer) THEN
     reason:=COALESCE(reason,'EXISTING_DETAIL_CHANGED'); END IF;
   SELECT COALESCE(array_agg(e.k),'{}') INTO delta FROM jsonb_each(desired) e(k,v)
   WHERE to_jsonb(oldrow)->e.k IS DISTINCT FROM e.v;
   IF oldrow.validation_status='VERIFIED' AND cardinality(delta)>0 THEN reason:=COALESCE(reason,'VERIFIED_PROTECTED'); END IF;
   IF oldrow.status IN ('CANCELLED','SUSPENDED','COMPLETED') AND
     COALESCE(desired->>'status',oldrow.status) IS DISTINCT FROM oldrow.status THEN reason:=COALESCE(reason,'STATUS_CONFLICT'); END IF;
   IF oldrow.status IN ('CANCELLED','SUSPENDED') AND cardinality(delta)>0 THEN
     reason:=COALESCE(reason,'STATUS_CONFLICT'); END IF;
   IF reason IS NULL THEN
   IF NULLIF(p_observation->>'source_date','') IS NOT NULL AND oldrow.source_date IS NOT NULL
     AND (p_observation->>'source_date')::date<oldrow.source_date THEN reason:=COALESCE(reason,'STALE_SOURCE'); END IF;
   IF NULLIF(p_observation->>'notice_date','') IS NOT NULL AND oldrow.notice_date IS NOT NULL
     AND (p_observation->>'notice_date')::date<oldrow.notice_date THEN reason:=COALESCE(reason,'NOTICE_DATE_REGRESSION'); END IF;
   END IF;
 END IF;
 IF reason IS NOT NULL THEN
   INSERT INTO public.development_review_queue(candidate_key,project_id,source_hash,reason,candidate,source)
   VALUES(pid::text,CASE WHEN initial THEN NULL ELSE pid END,p_source->>'content_hash',reason,
     jsonb_build_object('project',p_candidate,'observation',p_observation),p_source)
   ON CONFLICT ON CONSTRAINT development_review_dedupe DO NOTHING;
   RETURN jsonb_build_object('result','review_required','reason',reason,'project_id',pid);
 END IF;
 SELECT evidence INTO latest FROM public.development_project_sources
 WHERE project_id=pid AND content_hash=p_source->>'content_hash' AND source_url=p_source->>'source_url'
 AND validation_status='VERIFIED'
 ORDER BY collected_at DESC LIMIT 1;
 IF NOT initial AND latest->'observation' IS NOT DISTINCT FROM p_observation THEN
   RETURN jsonb_build_object('result','unchanged','project_id',pid,'revision',oldrow.revision); END IF;
 IF NOT initial AND oldrow.revision<>p_expected_revision THEN
   RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
 IF initial THEN
   result:=public.zipon_ingest_candidate_v2(p_candidate,p_source,0,'{}',p_run_id);
   SELECT * INTO oldrow FROM public.development_projects WHERE project_id=pid FOR UPDATE;
 END IF;
 -- A separately verified source is append-only; existing source rows are never rewritten.
 sid:=gen_random_uuid(); source_time:=(p_source->>'collected_at')::timestamptz;
 INSERT INTO public.development_project_sources(source_id,project_id,collection_run_id,
   source_name,source_type,source_url,is_official,external_id,collected_at,content_hash,
   raw_snapshot,validation_status,verified_at,verified_by,evidence,published_at,effective_at)
 VALUES(sid,pid,p_run_id,p_source->>'source_name','OFFICIAL_WEBSITE',p_source->>'source_url',true,
   p_candidate->>'external_id',source_time,p_source->>'content_hash',p_source->'raw_snapshot',
   'VERIFIED',now(),'zipon-refresh-policy-v1',jsonb_build_object('observation',p_observation),
   NULLIF(p_observation->>'notice_date','')::date,NULLIF(p_observation->>'effective_date','')::date);
 UPDATE public.development_projects SET
   stage=COALESCE(desired->>'stage',stage),stage_raw=COALESCE(desired->>'stage_raw',stage_raw),
   stage_mapping_version=CASE WHEN desired ? 'stage' THEN 'zipon-refresh-policy-v1' ELSE stage_mapping_version END,
   status=COALESCE(desired->>'status',status),
   notice_date=COALESCE(NULLIF(desired->>'notice_date','')::date,notice_date),
   source_date=COALESCE(NULLIF(desired->>'source_date','')::date,source_date),
   dong=CASE WHEN validation_status<>'VERIFIED' THEN COALESCE(dong,p_candidate->>'dong') ELSE dong END,
   address=CASE WHEN validation_status<>'VERIFIED' THEN COALESCE(address,p_candidate->>'address') ELSE address END,
   area_m2=CASE WHEN validation_status<>'VERIFIED' THEN COALESCE(area_m2,(p_candidate->>'area_m2')::numeric) ELSE area_m2 END,
   planned_units=CASE WHEN validation_status<>'VERIFIED' THEN COALESCE(planned_units,(p_candidate->>'planned_units')::integer) ELSE planned_units END,
   canonical_source_id=CASE WHEN validation_status<>'VERIFIED' THEN sid ELSE canonical_source_id END,
   last_verified_at=CASE WHEN validation_status<>'VERIFIED' THEN now() ELSE last_verified_at END,
   field_evidence=CASE WHEN validation_status='VERIFIED' OR p_observation='{}'::jsonb THEN field_evidence ELSE
     field_evidence||jsonb_build_object('official_stage',p_observation||jsonb_build_object('current_stage',p_observation->>'stage_raw','fetched_at',source_time)) END,
   revision=revision+1,updated_at=now()
 WHERE project_id=pid RETURNING * INTO newrow;
 SELECT COALESCE(array_agg(e.k),'{}') INTO delta FROM jsonb_each(to_jsonb(newrow)) e(k,v)
 WHERE e.k NOT IN ('revision','updated_at','last_verified_at','canonical_source_id','field_evidence')
   AND to_jsonb(oldrow)->e.k IS DISTINCT FROM e.v;
 INSERT INTO public.development_updates(project_id,source_id,collection_run_id,update_kind,
   previous_stage,new_stage,previous_status,new_status,from_revision,to_revision,title,
   previous_snapshot,new_snapshot,changed_fields,event_hash)
 VALUES(pid,sid,p_run_id,CASE WHEN 'stage'=ANY(delta) OR 'stage_raw'=ANY(delta) THEN 'STAGE'
   WHEN 'status'=ANY(delta) THEN 'STATUS' WHEN cardinality(delta)>0 THEN 'DETAIL' ELSE 'REVERIFICATION' END,
   oldrow.stage_raw,newrow.stage_raw,oldrow.status,newrow.status,oldrow.revision,newrow.revision,
   'Official refresh applied',to_jsonb(oldrow),jsonb_build_object('master',to_jsonb(newrow),'observation',p_observation),delta,
   encode(sha256(convert_to(pid::text||':'||newrow.revision::text||':'||(p_source->>'content_hash'),'UTF8')),'hex'));
 RETURN jsonb_build_object('result',CASE WHEN initial THEN 'new' WHEN cardinality(delta)>0 THEN 'changed' ELSE 'source_updated' END,
   'project_id',pid,'revision',newrow.revision,'changed_fields',to_jsonb(delta));
END $$;

-- Wrap the existing strict spatial RPCs and append history in the same transaction.
CREATE FUNCTION public.zipon_refresh_spatial(p_project_id uuid,p_kind text,p_payload jsonb,
 p_source jsonb,p_expected_revision bigint,p_run_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $$
DECLARE before_row public.development_projects; after_row public.development_projects;
 result jsonb; sid uuid; reason text;
BEGIN
 IF COALESCE(p_kind,'') NOT IN ('LOCATION','BOUNDARY') OR COALESCE(p_source->>'content_hash','') !~ '^[0-9a-f]{64}$'
 OR p_source->'is_official' IS DISTINCT FROM 'true'::jsonb
 OR COALESCE(p_source->>'source_url','') !~ '^https://(data\.seoul\.go\.kr|cleanup\.seoul\.go\.kr)/' THEN
   RAISE EXCEPTION 'Invalid spatial source'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.development_collection_runs WHERE run_id=p_run_id
   AND NOT dry_run AND status='RUNNING') OR NOT EXISTS(
   SELECT 1 FROM public.development_refresh_lease WHERE owner=p_run_id AND expires_at>now())
   THEN RAISE EXCEPTION 'Active leased run required'; END IF;
 SELECT * INTO before_row FROM public.development_projects WHERE project_id=p_project_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Project missing'; END IF;
 IF before_row.revision<>p_expected_revision THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
 IF p_kind='BOUNDARY' AND before_row.geometry IS NOT NULL AND
   extensions.ST_Equals(before_row.geometry,extensions.ST_SetSRID(extensions.ST_GeomFromGeoJSON((p_payload->'geometry')::text),4326)) THEN
   RETURN jsonb_build_object('result','unchanged','project_id',p_project_id,'revision',before_row.revision);
 END IF;
 IF before_row.validation_status='VERIFIED' OR (p_kind='LOCATION' AND before_row.location IS NOT NULL)
 OR (p_kind='BOUNDARY' AND before_row.geometry IS NOT NULL) THEN
   INSERT INTO public.development_review_queue(candidate_key,project_id,source_hash,reason,candidate,source)
   VALUES(p_project_id::text,p_project_id,p_source->>'content_hash',p_kind||'_EXISTING_OR_VERIFIED',p_payload,p_source)
   ON CONFLICT ON CONSTRAINT development_review_dedupe DO NOTHING;
   RETURN jsonb_build_object('result','review_required','project_id',p_project_id);
 END IF;
 IF p_kind='LOCATION' THEN
   result:=public.zipon_set_project_location(p_project_id,(p_payload->>'longitude')::float8,
     (p_payload->>'latitude')::float8,before_row.sigungu,p_payload->>'geocode_source',p_payload->>'confidence',
     p_expected_revision,p_payload->'evidence');
 ELSE
   result:=public.zipon_set_project_boundary(p_project_id,p_payload->'geometry',p_payload->>'geometry_source',
     p_source->>'source_url',before_row.sigungu,p_expected_revision,p_payload->'evidence');
 END IF;
 IF result->>'result' NOT IN ('location_set','boundary_set') THEN RETURN result; END IF;
 SELECT * INTO after_row FROM public.development_projects WHERE project_id=p_project_id;
 sid:=before_row.canonical_source_id;
 IF sid IS NULL THEN RAISE EXCEPTION 'Canonical source required'; END IF;
 INSERT INTO public.development_updates(project_id,source_id,collection_run_id,update_kind,
 from_revision,to_revision,title,previous_snapshot,new_snapshot,changed_fields,event_hash)
 VALUES(p_project_id,sid,p_run_id,CASE WHEN p_kind='BOUNDARY' THEN 'GEOMETRY' ELSE 'DETAIL' END,
 before_row.revision,after_row.revision,'Verified spatial evidence applied',to_jsonb(before_row),
 jsonb_build_object('master',to_jsonb(after_row),'source',p_source,'spatial',p_payload),
 ARRAY[CASE WHEN p_kind='BOUNDARY' THEN 'geometry' ELSE 'location' END],
 encode(sha256(convert_to(p_project_id::text||':'||after_row.revision::text||':'||(p_source->>'content_hash'),'UTF8')),'hex'));
 RETURN result;
END $$;

CREATE FUNCTION public.zipon_refresh_dashboard()
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER
SET search_path=pg_catalog,public,pg_temp AS $$
SELECT jsonb_build_object(
 'total',(SELECT count(*) FROM public.development_projects),
 'locations',(SELECT count(*) FROM public.development_projects WHERE location IS NOT NULL),
 'boundaries',(SELECT count(*) FROM public.development_projects WHERE geometry_verified AND geometry IS NOT NULL),
 'pending',(SELECT count(*) FROM public.development_review_queue WHERE state='PENDING'),
 'stale_running',(SELECT count(*) FROM public.development_collection_runs WHERE status='RUNNING'
   AND NOT dry_run AND collector_version='zipon-live-refresh-v1' AND started_at<now()-interval '40 minutes'),
 'source_date',(SELECT max(source_date) FROM public.development_projects),
 'new_30d',(SELECT count(*) FROM public.development_projects WHERE created_at>=now()-interval '30 days'),
 'changed_30d',(SELECT count(DISTINCT project_id) FROM public.development_updates
   WHERE recorded_at>=now()-interval '30 days' AND update_kind<>'INITIAL' AND cardinality(changed_fields)>0
   AND title IN ('Official refresh applied','Verified spatial evidence applied')),
 'auto_applied_30d',(SELECT count(*) FROM public.development_updates
   WHERE recorded_at>=now()-interval '30 days' AND cardinality(changed_fields)>0
   AND title IN ('Official refresh applied','Verified spatial evidence applied')),
 'last_success',(SELECT max(finished_at) FROM public.development_collection_runs
   WHERE NOT dry_run AND collector_version='zipon-live-refresh-v1' AND status='SUCCEEDED' AND source_complete),
 'last_attempt',(SELECT max(started_at) FROM public.development_collection_runs
   WHERE NOT dry_run AND collector_version='zipon-live-refresh-v1'),
 'runs',COALESCE((SELECT jsonb_agg(jsonb_build_object('run_id',r.run_id,'started_at',r.started_at,
   'finished_at',r.finished_at,'status',r.status,'new_count',r.new_count,'changed_count',r.changed_count,
   'unchanged_count',r.unchanged_count,'validation_failed_count',r.validation_failed_count,
   'sources',COALESCE((SELECT jsonb_agg(jsonb_build_object('source',s->>'source','status',s->>'status',
     'source_complete',s->'source_complete')) FROM jsonb_array_elements(COALESCE(r.scope->'sources','[]')) s),'[]'::jsonb)))
   FROM (SELECT * FROM public.development_collection_runs WHERE NOT dry_run AND collector_version='zipon-live-refresh-v1'
     ORDER BY started_at DESC LIMIT 20) r),'[]'::jsonb),
 'recent_projects',COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM (SELECT project_id,project_name,created_at
   FROM public.development_projects ORDER BY created_at DESC LIMIT 20) r),'[]'::jsonb),
 'recent_changes',COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM (SELECT u.update_id,p.project_name,u.update_kind,u.recorded_at
   FROM public.development_updates u JOIN public.development_projects p USING(project_id)
   WHERE u.title IN ('Official refresh applied','Verified spatial evidence applied') AND cardinality(u.changed_fields)>0
   ORDER BY u.recorded_at DESC LIMIT 20) r),'[]'::jsonb))
$$;
REVOKE ALL ON FUNCTION public.zipon_refresh_dashboard() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_refresh_dashboard() TO service_role;

REVOKE ALL ON FUNCTION public.zipon_refresh_lease(uuid,boolean),
 public.zipon_refresh_stage(text),public.zipon_refresh_rank(text),
 public.zipon_refresh_project(jsonb,jsonb,jsonb,bigint,uuid),
 public.zipon_refresh_spatial(uuid,text,jsonb,jsonb,bigint,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_refresh_lease(uuid,boolean),
 public.zipon_refresh_stage(text),public.zipon_refresh_rank(text),
 public.zipon_refresh_project(jsonb,jsonb,jsonb,bigint,uuid),
 public.zipon_refresh_spatial(uuid,text,jsonb,jsonb,bigint,uuid) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;

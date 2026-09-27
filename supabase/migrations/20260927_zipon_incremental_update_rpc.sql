-- REVIEW ONLY. New RPC version for incremental updates. The existing
-- public.zipon_ingest_candidate is NOT modified and stays available.
--
-- What this version adds over v1:
--   * the field diff is computed server-side and stored in changed_fields
--   * update_kind is classified (INITIAL / STAGE / STATUS / DETAIL / REVERIFICATION)
--     and the stage/status transition columns are filled
--   * a blank master column may be filled from an official candidate, but no
--     existing value is ever overwritten and a VERIFIED row is never touched
--   * an unresolved identity or a stage that runs backwards returns
--     review_required and leaves the master row alone
-- Disappearance from an official listing is handled by zipon_record_source_missing:
-- it appends evidence only. No row is deleted and no business status is inferred.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';

CREATE OR REPLACE FUNCTION public.zipon_ingest_candidate_v2(
  p_project jsonb, p_source jsonb, p_expected_revision bigint,
  p_change jsonb DEFAULT '{}'::jsonb, p_run_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $fn$
DECLARE oldrow public.development_projects; newrow public.development_projects;
 pid uuid; sid uuid; next_revision bigint; before_data jsonb;
 changed text[]:='{}'; kind text; review boolean:=false; reasons text[]:='{}';
 filled text[]:='{}'; latest public.development_updates;
BEGIN
 IF jsonb_typeof(p_project) IS DISTINCT FROM 'object' OR jsonb_typeof(p_source) IS DISTINCT FROM 'object'
 OR jsonb_typeof(p_source->'raw_snapshot') IS DISTINCT FROM 'object'
 OR NULLIF(btrim(p_source->>'source_name'),'') IS NULL
 OR NULLIF(p_source->>'collected_at','') IS NULL THEN
 RAISE EXCEPTION 'Invalid candidate document' USING ERRCODE='22023'; END IF;
 pid:=(p_project->>'project_id')::uuid;
 IF pid IS NULL OR p_expected_revision IS NULL OR p_expected_revision<0
 OR COALESCE(p_source->>'source_type','')<>'OFFICIAL_WEBSITE' OR (p_source->>'is_official')::boolean IS DISTINCT FROM true
 OR COALESCE(p_source->>'source_url','') !~ '^https://(cleanup\.seoul\.go\.kr|news\.seoul\.go\.kr)/'
 OR COALESCE(p_source->>'content_hash','') !~ '^[0-9a-f]{64}$' THEN
 RAISE EXCEPTION 'Invalid candidate provenance' USING ERRCODE='22023'; END IF;
 IF NULLIF(p_source->>'external_id','') IS NOT NULL
 AND p_source->>'external_id' IS DISTINCT FROM p_project->>'external_id' THEN
 RAISE EXCEPTION 'Source identity mismatch' USING ERRCODE='22023'; END IF;
 -- A candidate may never carry an approval decision into the master row.
 IF COALESCE(p_project->>'validation_status','NEEDS_REVIEW') NOT IN ('NEEDS_REVIEW','UNVERIFIED')
 OR COALESCE(p_project->>'status','UNKNOWN')<>'UNKNOWN'
 OR NULLIF(p_project->>'stage','') IS NOT NULL THEN
 RAISE EXCEPTION 'Candidate may not promote status, stage or validation' USING ERRCODE='22023'; END IF;

 PERFORM pg_advisory_xact_lock(hashtextextended(pid::text,0));
 SELECT * INTO oldrow FROM public.development_projects WHERE project_id=pid FOR UPDATE;

 IF FOUND THEN
   IF (oldrow.official_authority IS NOT NULL AND
       (oldrow.official_authority IS DISTINCT FROM p_project->>'official_authority'
        OR oldrow.external_id IS DISTINCT FROM p_project->>'external_id'))
   OR oldrow.project_type IS DISTINCT FROM p_project->>'project_type'
   OR oldrow.sigungu IS DISTINCT FROM p_project->>'sigungu' THEN
     RAISE EXCEPTION 'Candidate identity mismatch' USING ERRCODE='22023';
   END IF;
   SELECT * INTO latest FROM public.development_updates u
   WHERE u.project_id=pid ORDER BY u.to_revision DESC LIMIT 1;
   IF latest.new_snapshot->'source'->>'content_hash'=p_source->>'content_hash'
   AND latest.new_snapshot->'source'->>'source_url'=p_source->>'source_url'
   AND latest.new_snapshot->'candidate'=p_project THEN
     RETURN jsonb_build_object('result','unchanged','project_id',pid,'revision',oldrow.revision,
       'update_kind',latest.update_kind,'changed_fields','[]'::jsonb);
   END IF;
   IF oldrow.revision<>p_expected_revision THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
   -- Server-side diff; the caller's classification is advisory only.
   SELECT coalesce(array_agg(f.name ORDER BY f.name),'{}') INTO changed FROM (VALUES
     ('project_name',oldrow.project_name,p_project->>'project_name'),
     ('dong',oldrow.dong,p_project->>'dong'),
     ('address',oldrow.address,p_project->>'address'),
     ('stage_raw',oldrow.stage_raw,p_project->>'stage_raw'),
     ('sido',oldrow.sido,p_project->>'sido'),
     ('area_m2',oldrow.area_m2::text,p_project->>'area_m2'),
     ('planned_units',oldrow.planned_units::text,p_project->>'planned_units')
   ) AS f(name,before_value,after_value)
   WHERE NULLIF(f.after_value,'') IS NOT NULL AND f.before_value IS DISTINCT FROM f.after_value;
   kind:=CASE WHEN 'stage_raw'=ANY(changed) THEN 'STAGE'
              WHEN oldrow.status IS DISTINCT FROM COALESCE(p_project->>'status','UNKNOWN') THEN 'STATUS'
              WHEN array_length(changed,1)>0 THEN 'DETAIL' ELSE 'REVERIFICATION' END;
   IF (p_change->>'review_required')::boolean IS TRUE THEN
     review:=true;
     SELECT coalesce(array_agg(value),'{}') INTO reasons
     FROM jsonb_array_elements_text(COALESCE(p_change->'review_reasons','[]'::jsonb));
   END IF;
   before_data:=to_jsonb(oldrow); next_revision:=oldrow.revision+1;
 ELSE
   IF p_expected_revision<>0 THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
   next_revision:=1; kind:='INITIAL'; changed:=ARRAY['candidate_evidence'];
   INSERT INTO public.development_projects(project_id,project_name,project_type,sido,sigungu,dong,address,
     official_authority,external_id,stage_raw,validation_status,field_evidence,area_m2,planned_units,location,location_source)
   VALUES(pid,p_project->>'project_name',p_project->>'project_type',p_project->>'sido',p_project->>'sigungu',
     p_project->>'dong',p_project->>'address',p_project->>'official_authority',p_project->>'external_id',
     p_project->>'stage_raw','NEEDS_REVIEW',COALESCE(p_project->'field_evidence','{}'::jsonb),
     (p_project->>'area_m2')::numeric,(p_project->>'planned_units')::integer,
     (p_project->>'location')::extensions.geography,p_project->>'location_source');
 END IF;

 SELECT source_id INTO sid FROM public.development_project_sources
 WHERE project_id=pid AND source_url=p_source->>'source_url' AND content_hash=p_source->>'content_hash'
 AND is_official AND validation_status='UNVERIFIED';
 IF sid IS NULL THEN
   sid:=gen_random_uuid();
   INSERT INTO public.development_project_sources(source_id,project_id,collection_run_id,source_name,source_type,
     source_url,is_official,external_id,collected_at,content_hash,raw_snapshot,validation_status)
   VALUES(sid,pid,p_run_id,p_source->>'source_name','OFFICIAL_WEBSITE',p_source->>'source_url',true,
     p_source->>'external_id',(p_source->>'collected_at')::timestamptz,p_source->>'content_hash',
     p_source->'raw_snapshot','UNVERIFIED');
 END IF;

 -- Canonical update: fill blanks only. No existing value is replaced, a VERIFIED
 -- row is left untouched, and a flagged review never reaches the master row.
 IF before_data IS NOT NULL AND NOT review AND oldrow.validation_status<>'VERIFIED' THEN
   UPDATE public.development_projects SET
     dong=COALESCE(dong,NULLIF(p_project->>'dong','')),
     address=COALESCE(address,NULLIF(p_project->>'address','')),
     area_m2=COALESCE(area_m2,NULLIF(p_project->>'area_m2','')::numeric),
     planned_units=COALESCE(planned_units,NULLIF(p_project->>'planned_units','')::integer)
   WHERE project_id=pid;
   SELECT coalesce(array_agg(f.name ORDER BY f.name),'{}') INTO filled FROM (VALUES
     ('dong',oldrow.dong,p_project->>'dong'),
     ('address',oldrow.address,p_project->>'address'),
     ('area_m2',oldrow.area_m2::text,p_project->>'area_m2'),
     ('planned_units',oldrow.planned_units::text,p_project->>'planned_units')
   ) AS f(name,before_value,after_value)
   WHERE f.before_value IS NULL AND NULLIF(f.after_value,'') IS NOT NULL;
 END IF;

 UPDATE public.development_projects SET revision=next_revision,updated_at=now()
 WHERE project_id=pid RETURNING * INTO newrow;

 INSERT INTO public.development_updates(project_id,source_id,collection_run_id,update_kind,
   previous_stage,new_stage,previous_status,new_status,from_revision,to_revision,title,description,
   previous_snapshot,new_snapshot,changed_fields,event_hash)
 VALUES(pid,sid,p_run_id,kind,
   CASE WHEN before_data IS NULL THEN NULL ELSE oldrow.stage_raw END,
   NULLIF(p_project->>'stage_raw',''),
   CASE WHEN before_data IS NULL THEN NULL ELSE oldrow.status END,
   CASE WHEN before_data IS NULL THEN NULL ELSE newrow.status END,
   CASE WHEN before_data IS NULL THEN NULL ELSE oldrow.revision END, next_revision,
   CASE WHEN before_data IS NULL THEN 'Official candidate collected; review required'
        WHEN review THEN 'Official change quarantined for review'
        ELSE 'Official change recorded; master values unchanged except filled blanks' END,
   CASE WHEN review THEN 'REVIEW_REQUIRED: '||array_to_string(reasons,',') ELSE NULL END,
   before_data,
   jsonb_build_object('master',to_jsonb(newrow),'candidate',p_project,'source',p_source,
     'change',jsonb_build_object('pipeline_kind',COALESCE(p_change->>'kind',kind),
       'review_required',review,'review_reasons',to_jsonb(reasons),'filled_fields',to_jsonb(filled))),
   changed,
   encode(sha256(convert_to(pid::text||':'||next_revision::text||':'||(p_source->>'content_hash'),'UTF8')),'hex'));

 RETURN jsonb_build_object(
   'result',CASE WHEN before_data IS NULL THEN 'new' WHEN review THEN 'review_required' ELSE 'changed' END,
   'project_id',pid,'revision',next_revision,'update_kind',kind,
   'changed_fields',to_jsonb(changed),'filled_fields',to_jsonb(filled),
   'review_reasons',to_jsonb(reasons));
END;
$fn$;

-- Disappearance from an official listing is evidence, never a business outcome.
CREATE OR REPLACE FUNCTION public.zipon_record_source_missing(
  p_project_id uuid, p_reason text, p_run_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public,extensions,pg_temp AS $fn$
DECLARE oldrow public.development_projects; newrow public.development_projects;
 sid uuid; latest public.development_updates; next_revision bigint;
BEGIN
 IF p_project_id IS NULL OR NULLIF(btrim(COALESCE(p_reason,'')),'') IS NULL THEN
   RAISE EXCEPTION 'Missing observation needs a project and a reason' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(p_project_id::text,0));
 SELECT * INTO oldrow FROM public.development_projects WHERE project_id=p_project_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('result','unknown_project','project_id',p_project_id); END IF;
 SELECT * INTO latest FROM public.development_updates u
 WHERE u.project_id=p_project_id ORDER BY u.to_revision DESC LIMIT 1;
 IF latest.update_kind='SOURCE_MISSING' THEN
   -- Already recorded; repeating the observation must not grow history or revisions.
   RETURN jsonb_build_object('result','unchanged','project_id',p_project_id,
     'revision',oldrow.revision,'update_kind','SOURCE_MISSING');
 END IF;
 SELECT source_id INTO sid FROM public.development_project_sources
 WHERE project_id=p_project_id AND is_official ORDER BY collected_at DESC LIMIT 1;
 IF sid IS NULL THEN RETURN jsonb_build_object('result','no_official_source','project_id',p_project_id); END IF;
 next_revision:=oldrow.revision+1;
 -- Status, stage, validation_status and geometry are deliberately not touched.
 UPDATE public.development_projects SET revision=next_revision,updated_at=now()
 WHERE project_id=p_project_id RETURNING * INTO newrow;
 INSERT INTO public.development_updates(project_id,source_id,collection_run_id,update_kind,
   previous_stage,new_stage,previous_status,new_status,from_revision,to_revision,title,description,
   previous_snapshot,new_snapshot,changed_fields,event_hash)
 VALUES(p_project_id,sid,p_run_id,'SOURCE_MISSING',oldrow.stage_raw,oldrow.stage_raw,
   oldrow.status,oldrow.status,oldrow.revision,next_revision,
   'Project absent from the official listing',
   'ABSENCE_IS_NOT_CANCELLATION: '||p_reason,
   to_jsonb(oldrow),jsonb_build_object('master',to_jsonb(newrow),
     'change',jsonb_build_object('pipeline_kind','SOURCE_MISSING','reason',p_reason)),
   ARRAY['source_presence'],
   encode(sha256(convert_to(p_project_id::text||':'||next_revision::text||':SOURCE_MISSING','UTF8')),'hex'));
 RETURN jsonb_build_object('result','source_missing_recorded','project_id',p_project_id,
   'revision',next_revision,'update_kind','SOURCE_MISSING');
END;
$fn$;

REVOKE ALL ON FUNCTION public.zipon_ingest_candidate_v2(jsonb,jsonb,bigint,jsonb,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_ingest_candidate_v2(jsonb,jsonb,bigint,jsonb,uuid) TO service_role;
REVOKE ALL ON FUNCTION public.zipon_record_source_missing(uuid,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_record_source_missing(uuid,text,uuid) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;

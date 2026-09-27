-- REVIEW ONLY. Candidate imports preserve approved facts and atomically append history.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
CREATE OR REPLACE FUNCTION public.zipon_ingest_candidate(p_project jsonb,p_source jsonb,p_expected_revision bigint,p_run_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,extensions,pg_temp AS $fn$
DECLARE oldrow public.development_projects; newrow public.development_projects;
 pid uuid; sid uuid; next_revision bigint; before_data jsonb;
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
 -- Serialize first insert as well as updates. Hash collision only serializes unrelated work.
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
   IF (SELECT u.new_snapshot->'source'->>'content_hash'=p_source->>'content_hash'
       AND u.new_snapshot->'source'->>'source_url'=p_source->>'source_url'
       AND u.new_snapshot->'candidate'=p_project
       FROM public.development_updates u WHERE u.project_id=pid ORDER BY u.to_revision DESC LIMIT 1) THEN
     RETURN jsonb_build_object('result','unchanged','project_id',pid,'revision',oldrow.revision);
   END IF;
   IF oldrow.revision<>p_expected_revision THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
   before_data:=to_jsonb(oldrow);next_revision:=oldrow.revision+1;
 ELSE
   IF p_expected_revision<>0 THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='40001'; END IF;
   next_revision:=1;
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
 INSERT INTO public.development_project_sources(source_id,project_id,collection_run_id,source_name,source_type,source_url,
 is_official,external_id,collected_at,content_hash,raw_snapshot,validation_status)
 VALUES(sid,pid,p_run_id,p_source->>'source_name','OFFICIAL_WEBSITE',p_source->>'source_url',true,p_source->>'external_id',
 (p_source->>'collected_at')::timestamptz,p_source->>'content_hash',p_source->'raw_snapshot','UNVERIFIED');
 END IF;
 -- Existing approved master values are never overwritten by an unreviewed collection.
 UPDATE public.development_projects SET revision=next_revision,updated_at=now() WHERE project_id=pid RETURNING * INTO newrow;
 INSERT INTO public.development_updates(project_id,source_id,collection_run_id,update_kind,from_revision,to_revision,title,
 previous_snapshot,new_snapshot,changed_fields,event_hash)
 VALUES(pid,sid,p_run_id,CASE WHEN before_data IS NULL THEN 'INITIAL' ELSE 'REVERIFICATION' END,
 CASE WHEN before_data IS NULL THEN NULL ELSE oldrow.revision END,next_revision,
 'Official candidate collected; review required',before_data,
 jsonb_build_object('master',to_jsonb(newrow),'candidate',p_project,'source',p_source),
 ARRAY['candidate_evidence'],encode(sha256(convert_to(pid::text||':'||next_revision::text||':'||(p_source->>'content_hash'),'UTF8')),'hex'));
 RETURN jsonb_build_object('result',CASE WHEN before_data IS NULL THEN 'new' ELSE 'changed' END,
 'project_id',pid,'revision',next_revision);
END;
$fn$;
REVOKE ALL ON FUNCTION public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.zipon_ingest_candidate(jsonb,jsonb,bigint,uuid) TO service_role;
NOTIFY pgrst,'reload schema';
COMMIT;

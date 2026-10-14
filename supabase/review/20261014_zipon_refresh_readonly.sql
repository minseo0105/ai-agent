-- SELECT-only. Does not invoke ingest/spatial/lease RPCs or rollback-only fixtures.
BEGIN TRANSACTION READ ONLY;
SELECT extname FROM pg_extension WHERE extname='postgis';
SELECT p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,
 p.prosecdef AS security_definer
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.proname IN (
 'zipon_ingest_candidate_v2','zipon_set_project_location','zipon_set_project_boundary',
 'zipon_refresh_project','zipon_refresh_spatial','zipon_refresh_lease','zipon_refresh_dashboard');
SELECT count(*) AS projects,count(*) FILTER(WHERE location IS NOT NULL) AS locations,
 count(*) FILTER(WHERE geometry_verified) AS verified_boundaries,
 count(*) FILTER(WHERE validation_status='VERIFIED') AS verified_projects
FROM public.development_projects;
SELECT run_id,collector_version,started_at,finished_at,status,dry_run,source_complete,
 new_count,changed_count,unchanged_count,validation_failed_count
FROM public.development_collection_runs ORDER BY started_at DESC LIMIT 30;
SELECT project_id,count(*) FROM public.development_projects GROUP BY project_id HAVING count(*)>1;
SELECT official_authority,external_id,count(*) FROM public.development_projects
WHERE external_id IS NOT NULL GROUP BY official_authority,external_id HAVING count(*)>1;
SELECT schemaname,tablename,rowsecurity FROM pg_tables WHERE schemaname='public'
 AND tablename IN ('development_review_queue','development_refresh_lease');
SELECT grantee,table_name,privilege_type FROM information_schema.role_table_grants
WHERE table_schema='public' AND table_name IN ('development_review_queue','development_refresh_lease')
 AND grantee IN ('anon','authenticated','PUBLIC');
ROLLBACK;

-- Read-only catalog inspection. Also usable BEFORE installation to distinguish
-- missing function, wrong signature, and missing privileges. Never invokes the RPC.
-- Run in zipon-realestate SQL Editor as postgres. No test data is created.
WITH target AS (
 SELECT to_regprocedure('public.zipon_set_project_location(uuid,double precision,double precision,text,text,text,bigint,jsonb)')::oid AS oid
), fn AS (
 SELECT p.* FROM pg_proc p JOIN target t ON p.oid=t.oid
), checks AS (
 SELECT 1 AS ord,'exact_signature_exists'::text AS check_item,
        (oid IS NOT NULL)::text AS actual,'true'::text AS expected,oid IS NOT NULL AS passed FROM target
 UNION ALL
 SELECT 2,'same_name_overload_count',count(*)::text,'1',count(*)=1
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='zipon_set_project_location'
 UNION ALL
 SELECT 3,'parameter_names',COALESCE((SELECT array_to_string(proargnames,',') FROM fn),'MISSING'),
 'p_project_id,p_longitude,p_latitude,p_expected_sigungu,p_geocode_source,p_confidence,p_expected_revision,p_evidence',
 COALESCE((SELECT proargnames=ARRAY['p_project_id','p_longitude','p_latitude','p_expected_sigungu','p_geocode_source','p_confidence','p_expected_revision','p_evidence']::text[] FROM fn),false)
 UNION ALL
 SELECT 4,'return_type',COALESCE((SELECT pg_get_function_result(oid) FROM fn),'MISSING'),'jsonb',
 COALESCE((SELECT prorettype='jsonb'::regtype FROM fn),false)
 UNION ALL
 SELECT 5,'security_invoker',COALESCE((SELECT (NOT prosecdef)::text FROM fn),'MISSING'),'true',
 COALESCE((SELECT NOT prosecdef FROM fn),false)
 UNION ALL
 SELECT 6,'search_path',COALESCE((SELECT array_to_string(proconfig,',') FROM fn),'MISSING'),
 'search_path=pg_catalog, public, extensions, pg_temp',
 COALESCE((SELECT EXISTS(SELECT 1 FROM unnest(proconfig) c WHERE replace(c,' ','')='search_path=pg_catalog,public,extensions,pg_temp') FROM fn),false)
 UNION ALL
 SELECT 7,'service_role_execute',COALESCE(has_function_privilege('service_role',oid,'EXECUTE'),false)::text,
 'true',COALESCE(has_function_privilege('service_role',oid,'EXECUTE'),false) FROM target
 UNION ALL
 SELECT 8,'anon_execute',COALESCE(has_function_privilege('anon',oid,'EXECUTE'),false)::text,
 'false',oid IS NOT NULL AND NOT COALESCE(has_function_privilege('anon',oid,'EXECUTE'),false) FROM target
 UNION ALL
 SELECT 9,'authenticated_execute',COALESCE(has_function_privilege('authenticated',oid,'EXECUTE'),false)::text,
 'false',oid IS NOT NULL AND NOT COALESCE(has_function_privilege('authenticated',oid,'EXECUTE'),false) FROM target
 UNION ALL
 SELECT 10,'public_execute',EXISTS(SELECT 1 FROM fn,LATERAL aclexplode(COALESCE(proacl,acldefault('f',proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE')::text,
 'false',EXISTS(SELECT 1 FROM fn) AND NOT EXISTS(SELECT 1 FROM fn,LATERAL aclexplode(COALESCE(proacl,acldefault('f',proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE')
 UNION ALL
 SELECT 11,'service_role_public_usage',has_schema_privilege('service_role','public','USAGE')::text,'true',has_schema_privilege('service_role','public','USAGE')
 UNION ALL
 SELECT 12,'service_role_extensions_usage',has_schema_privilege('service_role','extensions','USAGE')::text,'true',has_schema_privilege('service_role','extensions','USAGE')
 UNION ALL
 SELECT 13,'service_role_table_select_update',
 (has_table_privilege('service_role','public.development_projects','SELECT') AND has_table_privilege('service_role','public.development_projects','UPDATE'))::text,'true',
 has_table_privilege('service_role','public.development_projects','SELECT') AND has_table_privilege('service_role','public.development_projects','UPDATE')
 UNION ALL
 SELECT 14,'rls_enabled',COALESCE((SELECT relrowsecurity::text FROM pg_class WHERE oid='public.development_projects'::regclass),'MISSING'),'true',
 COALESCE((SELECT relrowsecurity FROM pg_class WHERE oid='public.development_projects'::regclass),false)
 UNION ALL
 SELECT 15,'postgis_extensions_schema',COALESCE((SELECT n.nspname::text FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='postgis'),'MISSING'),'extensions',
 EXISTS(SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='postgis' AND n.nspname='extensions')
 UNION ALL
 SELECT 16,'accepted_evidence_guard',COALESCE((SELECT position('ACCEPTED_EVIDENCE_REQUIRED' IN prosrc)>0 FROM fn),false)::text,'true',
 COALESCE((SELECT position('ACCEPTED_EVIDENCE_REQUIRED' IN prosrc)>0 FROM fn),false)
 UNION ALL
 SELECT 17,'verified_boundary_guard',COALESCE((SELECT position('VERIFIED_BOUNDARY_PRESENT' IN prosrc)>0 FROM fn),false)::text,'true',
 COALESCE((SELECT position('VERIFIED_BOUNDARY_PRESENT' IN prosrc)>0 FROM fn),false)
 UNION ALL
 SELECT 18,'pending_project_still_unmodified',
 COALESCE((SELECT (location IS NULL AND revision=1 AND geometry_verified=false)::text FROM public.development_projects WHERE project_id='0922ac26-1436-5158-853d-49d3c5aed7fb'),'MISSING'),
 'true',COALESCE((SELECT location IS NULL AND revision=1 AND geometry_verified=false FROM public.development_projects WHERE project_id='0922ac26-1436-5158-853d-49d3c5aed7fb'),false)
)
SELECT check_item,actual,expected,passed FROM (
 SELECT * FROM checks
 UNION ALL SELECT 999,'ALL_CHECKS',CASE WHEN bool_and(passed) THEN 'PASS' ELSE 'FAIL' END,'PASS',bool_and(passed) FROM checks
) AS report ORDER BY ord;
-- A PASS checks SQL catalogs, not PostgREST's live schema cache. Follow with
-- run_zipon_verified_coordinates.ps1 -ReconcileFirst (GET only), never bulk apply.

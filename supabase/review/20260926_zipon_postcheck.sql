-- READ ONLY. Run only after the reviewed migration is applied to zipon-realestate.
BEGIN READ ONLY;

SELECT e.extname, e.extversion, n.nspname AS extension_schema
FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
WHERE e.extname='postgis';

SELECT table_name,column_name,data_type,udt_schema,udt_name,is_nullable,column_default
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN
('alert_rules','notifications','source_snapshots','app_settings','development_projects',
 'development_project_sources','development_updates','development_collection_runs','geocode_cache')
ORDER BY table_name,ordinal_position;

SELECT c.relname AS table_name,c.relrowsecurity AS rls_enabled,
 has_table_privilege('anon',c.oid,'SELECT') AS anon_select,
 has_table_privilege('authenticated',c.oid,'SELECT') AS authenticated_select,
 has_table_privilege('service_role',c.oid,'SELECT') AS service_select,
 has_table_privilege('service_role',c.oid,'INSERT') AS service_insert,
 has_table_privilege('service_role',c.oid,'UPDATE') AS service_update,
 has_table_privilege('service_role',c.oid,'DELETE') AS service_delete
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r' AND c.relname IN
('alert_rules','notifications','source_snapshots','app_settings','development_projects',
 'development_project_sources','development_updates','development_collection_runs','geocode_cache')
ORDER BY c.relname;

SELECT tablename,indexname,indexdef FROM pg_catalog.pg_indexes
WHERE schemaname='public' AND (tablename LIKE 'development_%' OR tablename='geocode_cache'
 OR tablename IN ('alert_rules','notifications','source_snapshots','app_settings'))
ORDER BY tablename,indexname;

SELECT c.conname, c.conrelid::regclass AS table_name, pg_catalog.pg_get_constraintdef(c.oid) AS definition
FROM pg_catalog.pg_constraint c
WHERE c.connamespace='public'::regnamespace AND c.contype='f'
ORDER BY c.conrelid,c.conname;

SELECT 'alert_rules' AS table_name,count(*) AS row_count FROM public.alert_rules
UNION ALL SELECT 'notifications',count(*) FROM public.notifications
UNION ALL SELECT 'source_snapshots',count(*) FROM public.source_snapshots
UNION ALL SELECT 'app_settings',count(*) FROM public.app_settings
UNION ALL SELECT 'development_projects',count(*) FROM public.development_projects
UNION ALL SELECT 'development_project_sources',count(*) FROM public.development_project_sources
UNION ALL SELECT 'development_updates',count(*) FROM public.development_updates
UNION ALL SELECT 'development_collection_runs',count(*) FROM public.development_collection_runs
UNION ALL SELECT 'geocode_cache',count(*) FROM public.geocode_cache;

-- Synthetic in-memory examples, not business data. NO table INSERT.
-- Strict interior uses ST_Contains; an exact boundary is NEARBY at 0m.
-- Polygon distance can be used for NEARBY even when unverified, but cannot prove INSIDE.
WITH sample AS (
 SELECT extensions.ST_GeomFromText('POLYGON((127 37,127.01 37,127.01 37.01,127 37.01,127 37))',4326) AS boundary,
        extensions.ST_SetSRID(extensions.ST_MakePoint(127.005,37.005),4326) AS point
), cases AS (
 SELECT 'verified_polygon' AS label, boundary, true AS verified, point, NULL::extensions.geography AS location, 'INSIDE' AS expected FROM sample
 UNION ALL SELECT 'unverified_polygon',boundary,false,point,NULL::extensions.geography,'NEARBY' FROM sample
 UNION ALL SELECT 'representative_point_only',NULL::extensions.geometry,false,point,point::extensions.geography,'NEARBY' FROM sample
 UNION ALL SELECT 'no_spatial_data',NULL::extensions.geometry,false,point,NULL::extensions.geography,'UNKNOWN' FROM sample
 UNION ALL SELECT 'verified_multipolygon',extensions.ST_Multi(boundary),true,point,NULL::extensions.geography,'INSIDE' FROM sample
 UNION ALL SELECT 'exact_boundary',boundary,true,extensions.ST_SetSRID(extensions.ST_MakePoint(127,37),4326),NULL::extensions.geography,'NEARBY' FROM sample
), classified AS (
 SELECT label,expected,
 CASE
 WHEN verified AND boundary IS NOT NULL AND extensions.ST_Contains(boundary,point) THEN 'INSIDE'
 WHEN boundary IS NOT NULL AND extensions.ST_DWithin(boundary::extensions.geography,point::extensions.geography,1000) THEN 'NEARBY'
 WHEN location IS NOT NULL AND extensions.ST_DWithin(location,point::extensions.geography,1000) THEN 'NEARBY'
 ELSE 'UNKNOWN' END AS actual
 FROM cases
)
SELECT label,expected,actual,actual=expected AS passed FROM classified;

ROLLBACK;

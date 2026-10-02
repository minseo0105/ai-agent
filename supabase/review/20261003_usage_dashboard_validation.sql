-- Read-only. Run manually in the analytics project's SQL Editor.
SELECT p.proname, p.prosecdef, p.provolatile, p.proconfig
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.proname = 'usage_dashboard';
SELECT role_name,
       has_function_privilege(role_name, 'public.usage_dashboard(integer)', 'EXECUTE') AS can_execute,
       has_table_privilege(role_name, 'public.usage_events', 'SELECT') AS can_read_raw
FROM (VALUES ('anon'), ('authenticated'), ('service_role')) AS roles(role_name);
-- Expected: anon/authenticated false/false; service_role true/false.
SELECT relrowsecurity FROM pg_class WHERE oid = 'public.usage_events'::regclass;
SELECT * FROM pg_policies WHERE schemaname = 'public' AND tablename = 'usage_events';
SELECT public.usage_dashboard(1);
-- Optional: SELECT public.usage_dashboard(7); SELECT public.usage_dashboard(30);
-- Rollback review ONLY (never automatically run):
-- DROP FUNCTION public.usage_dashboard(integer);

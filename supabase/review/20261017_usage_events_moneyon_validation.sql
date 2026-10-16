-- Read-only. Run as the operator in the SAME Supabase project as usage_events.
-- 1) BEFORE applying 20261017_usage_events_moneyon.sql: confirm names/shapes match the migration's expectations.
SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint
WHERE conrelid = 'public.usage_events'::regclass AND contype = 'c' ORDER BY conname;
-- 2) Table protections must be unchanged (RLS on, zero policies, only service_role INSERT).
SELECT relrowsecurity FROM pg_class WHERE oid = 'public.usage_events'::regclass;
SELECT * FROM pg_policies WHERE schemaname = 'public' AND tablename = 'usage_events'; -- zero rows
SELECT grantee, privilege_type FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND table_name = 'usage_events' ORDER BY grantee, privilege_type;
-- 3) AFTER applying: all three constraints validated and MONEY:ON clicks (empty until the app deploys).
SELECT conname, convalidated FROM pg_constraint
WHERE conrelid = 'public.usage_events'::regclass AND contype = 'c' AND (pg_get_constraintdef(oid) LIKE '%service = ANY%' OR pg_get_constraintdef(oid) LIKE '%route = ANY%' OR pg_get_constraintdef(oid) LIKE '%official_source_click%') ORDER BY conname;
SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day, count(*) AS card_clicks
FROM public.usage_events WHERE service = 'moneyon' AND event_type = 'external_link_click'
GROUP BY 1 ORDER BY 1 DESC;

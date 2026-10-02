-- Read-only. Run as the operator in the shared AI LAB Supabase SQL Editor.
SELECT c.relname, c.relrowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'usage_events';
SELECT grantee, privilege_type FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND table_name = 'usage_events' ORDER BY grantee, privilege_type;
SELECT * FROM pg_policies WHERE schemaname = 'public' AND tablename = 'usage_events'; -- zero rows

-- KST calendar days, including today. Sessions = distinct browser-tab sessions, not people.
WITH bounds AS (
    SELECT date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul' AS today
)
SELECT count(*) FILTER (WHERE event_type = 'page_view' AND created_at >= today) AS today_page_views,
       count(DISTINCT session_id) FILTER (WHERE event_type = 'page_view' AND created_at >= today) AS today_sessions,
       count(*) FILTER (WHERE event_type = 'page_view') AS seven_day_page_views,
       count(*) FILTER (WHERE event_type = 'search' AND created_at >= today) AS today_searches,
       count(*) FILTER (WHERE event_type = 'api_error' AND created_at >= today) AS today_errors
FROM public.usage_events CROSS JOIN bounds WHERE created_at >= today - interval '6 days';

SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS day, service, event_type,
       metadata->>'action' AS action, count(*) AS event_count,
       count(DISTINCT session_id) AS sessions
FROM public.usage_events
WHERE created_at >= (date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul') - interval '6 days'
GROUP BY 1, 2, 3, 4 ORDER BY 1 DESC, 2, 3;

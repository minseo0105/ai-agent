-- MANUAL ONLY, shared AI LAB / dedicated analytics project.
-- Requires 20261002_usage_events.sql. No table grants, policies, or data change.
BEGIN;
CREATE FUNCTION public.usage_dashboard(p_days integer DEFAULT 1)
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    finish timestamptz := now();
    start_at timestamptz;
    row_count integer;
    result jsonb;
BEGIN
    IF p_days IS NULL OR p_days NOT IN (1, 7, 30) THEN
        RAISE EXCEPTION 'Unsupported analytics period';
    END IF;
    start_at := (date_trunc('day', finish AT TIME ZONE 'Asia/Seoul')
                 - (p_days - 1) * interval '1 day') AT TIME ZONE 'Asia/Seoul';
    -- Refuse rather than silently sampling/capping metrics. Bound later sorts/grouping.
    SELECT count(*) INTO row_count FROM (
        SELECT 1 FROM public.usage_events
        WHERE created_at >= start_at AND created_at <= finish LIMIT 100001
    ) limited;
    IF row_count > 100000 THEN
        RETURN jsonb_build_object('status', 'too_many_events');
    END IF;

    WITH events AS MATERIALIZED (
        SELECT id, created_at, (created_at AT TIME ZONE 'Asia/Seoul')::date AS day,
               session_id, service, route, event_type, metadata->>'action' AS action,
               (event_type = 'search' AND (
                   (service = 'realestate' AND route = '/realestate' AND metadata->>'action' IN
                       ('address_search','trade_search','subscription_search')) OR
                   (service = 'golf' AND route = '/golf' AND metadata->>'action' = 'golf_search')
               )) IS TRUE AS feature
        FROM public.usage_events WHERE created_at >= start_at AND created_at <= finish
    ), sessions AS (
        SELECT service, session_id, bool_or(event_type = 'page_view') AS visited,
               bool_or(feature) AS used
        FROM events WHERE session_id IS NOT NULL GROUP BY service, session_id
    ), ordered AS MATERIALIZED (
        SELECT *, row_number() OVER (PARTITION BY service, session_id ORDER BY created_at, id) AS seq
        FROM events WHERE session_id IS NOT NULL AND service IN ('realestate','golf')
    ), entered AS (
        SELECT service, session_id, min(seq) AS step FROM ordered
        WHERE event_type = 'page_view' GROUP BY service, session_id
    ), searched AS (
        SELECT e.service, e.session_id, min(o.seq) AS step
        FROM entered e JOIN ordered o USING (service, session_id)
        WHERE o.feature AND o.seq > e.step GROUP BY e.service, e.session_id
    ), engaged AS (
        SELECT s.service, s.session_id, min(o.seq) AS step
        FROM searched s JOIN ordered o USING (service, session_id)
        WHERE o.service = 'realestate' AND o.event_type IN ('map_click','project_click')
          AND o.seq > s.step GROUP BY s.service, s.session_id
    ), exited AS (
        SELECT e.service, e.session_id, min(o.seq) AS step
        FROM engaged e JOIN ordered o USING (service, session_id)
        WHERE o.event_type = 'external_link_click' AND o.action = 'naver_land_click'
          AND o.seq > e.step GROUP BY e.service, e.session_id
    ), service_counts AS (
        SELECT service,
            count(DISTINCT session_id) FILTER (WHERE event_type = 'page_view') AS visits,
            count(*) FILTER (WHERE event_type = 'page_view') AS page_views,
            count(*) FILTER (WHERE feature) AS features,
            count(*) FILTER (WHERE event_type = 'external_link_click') AS external,
            count(*) FILTER (WHERE event_type = 'api_error') AS errors,
            count(*) FILTER (WHERE event_type = 'map_click') AS map_clicks,
            count(*) FILTER (WHERE event_type = 'project_click') AS project_clicks,
            count(*) FILTER (WHERE event_type = 'external_link_click' AND action = 'naver_land_click') AS naver
        FROM events GROUP BY service
    ), service_metrics AS (
        SELECT c.*,
            (SELECT count(*) FROM sessions s WHERE s.service = c.service AND s.visited AND s.used) AS used_sessions,
            (SELECT count(*) FROM entered s WHERE s.service = c.service) AS funnel_entered,
            (SELECT count(*) FROM searched s WHERE s.service = c.service) AS funnel_searched,
            (SELECT count(*) FROM engaged s WHERE s.service = c.service) AS funnel_engaged,
            (SELECT count(*) FROM exited s WHERE s.service = c.service) AS funnel_external
        FROM service_counts c
    ), pages AS (
        SELECT service, route,
            count(DISTINCT session_id) FILTER (WHERE event_type = 'page_view') AS visits,
            count(*) FILTER (WHERE event_type = 'page_view') AS page_views,
            count(*) FILTER (WHERE feature) AS features
        FROM events WHERE event_type <> 'api_error' AND route NOT LIKE '/api/%'
        GROUP BY service, route
    ), daily AS (
        SELECT day, CASE WHEN grouping(service) = 1 THEN 'all' ELSE service END AS service,
            count(DISTINCT session_id) FILTER (WHERE event_type = 'page_view') AS visits,
            count(*) FILTER (WHERE event_type = 'page_view') AS page_views,
            count(*) FILTER (WHERE feature) AS features
        FROM events GROUP BY GROUPING SETS ((day), (day, service))
    ), recent AS (
        SELECT id, created_at, service, route, event_type, action
        FROM events ORDER BY created_at DESC, id DESC LIMIT 20
    )
    SELECT jsonb_build_object(
        'status', 'ok', 'start_at', start_at, 'end_at', finish,
        'totals', (SELECT jsonb_build_object(
            'visits', count(DISTINCT session_id) FILTER (WHERE event_type = 'page_view'),
            'page_views', count(*) FILTER (WHERE event_type = 'page_view'),
            'features', count(*) FILTER (WHERE feature),
            'external', count(*) FILTER (WHERE event_type = 'external_link_click'),
            'errors', count(*) FILTER (WHERE event_type = 'api_error')) FROM events),
        'pages', COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.page_views DESC, p.route) FROM pages p), '[]'::jsonb),
        'services', COALESCE((SELECT jsonb_agg(to_jsonb(s) ORDER BY s.service) FROM service_metrics s), '[]'::jsonb),
        'daily', COALESCE((SELECT jsonb_agg(to_jsonb(d) ORDER BY d.day, d.service) FROM daily d), '[]'::jsonb),
        'recent', COALESCE((SELECT jsonb_agg(to_jsonb(r) - 'id' ORDER BY r.created_at DESC, r.id DESC) FROM recent r), '[]'::jsonb)
    ) INTO result;
    RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION public.usage_dashboard(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.usage_dashboard(integer) TO service_role;
COMMENT ON FUNCTION public.usage_dashboard(integer) IS
    'Read-only bounded usage aggregates. Server-admin gate required; never grant to browser roles.';
COMMIT;

-- Apply manually in the shared AI LAB Supabase project (not the ZIP:ON project).
-- No core tables, functions, policies, or data are modified. Transactional, fail on conflict.
BEGIN;
CREATE TABLE public.usage_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    session_id uuid,
    service text NOT NULL CHECK (service IN ('home','realestate','golf','dreamcar','report','saju','car-selector','gif','other')),
    route text NOT NULL CHECK (route IN ('/','/realestate','/golf','/golf/club','/dreamcar','/report','/saju','/car-selector','/gif','/other',
        '/api/home','/api/realestate','/api/golf','/api/dreamcar','/api/report','/api/saju','/api/car-selector','/api/gif')),
    event_type text NOT NULL CHECK (event_type IN ('page_view','search','project_click','map_click','external_link_click','api_error')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (COALESCE((
        metadata = '{}'::jsonb OR
        (metadata - 'action' = '{}'::jsonb AND metadata->>'action' IN
            ('address_search','golf_search','trade_search','subscription_search','naver_land_click','official_source_click')) OR
        (event_type = 'api_error' AND metadata - 'status' = '{}'::jsonb AND
            jsonb_typeof(metadata->'status') = 'number' AND (metadata->>'status')::numeric BETWEEN 400 AND 599)
    ), false)),
    request_id text CHECK (request_id ~ '^[0-9a-f]{16}$'),
    CHECK (event_type = 'api_error' OR session_id IS NOT NULL)
);
CREATE INDEX usage_events_created_at_idx ON public.usage_events (created_at);
ALTER TABLE public.usage_events ENABLE ROW LEVEL SECURITY;
-- No public policies: browsers cannot insert or read, including authenticated members.
REVOKE ALL ON public.usage_events FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.usage_events_id_seq FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.usage_events FROM service_role;
REVOKE ALL ON SEQUENCE public.usage_events_id_seq FROM service_role;
GRANT INSERT ON public.usage_events TO service_role;
GRANT USAGE ON SEQUENCE public.usage_events_id_seq TO service_role;
COMMENT ON TABLE public.usage_events IS 'Lossy anonymous usage; retain 30 days. Operator SQL only; no core dependency.';
COMMIT;

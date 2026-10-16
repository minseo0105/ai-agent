-- MANUAL ONLY, shared AI LAB / dedicated analytics project (same project that holds usage_events).
-- Requires 20261002_usage_events.sql. Widens three CHECK constraints so the AI LAB home can record
-- MONEY:ON card clicks (external app: service 'moneyon', route '/moneyon', external_link_click,
-- metadata.action = 'moneyon_card_click'). No table, column, grant, policy or row change.
-- Existing rows stay valid because every new allowed set is a superset of the old one.
-- Constraints are found by definition; the script fails and rolls back if any is missing, ambiguous
-- or already widened. Check supabase/review/20261017_usage_events_moneyon_validation.sql first.
BEGIN;
DO $$
DECLARE
    pats text[] := ARRAY['service = ANY', 'route = ANY', 'official_source_click'];
    names text[] := ARRAY[]::text[];
    cnt int; n text; d text;
BEGIN
    -- Find each constraint by its definition (auto-generated names can differ between projects).
    FOR i IN 1..3 LOOP
        SELECT count(*) INTO cnt FROM pg_constraint
        WHERE conrelid = 'public.usage_events'::regclass AND contype = 'c'
          AND position(pats[i] in pg_get_constraintdef(oid)) > 0;
        IF cnt <> 1 THEN RAISE EXCEPTION 'expected exactly one constraint matching %, found %; review manually', pats[i], cnt; END IF;
        SELECT conname, pg_get_constraintdef(oid) INTO n, d FROM pg_constraint
        WHERE conrelid = 'public.usage_events'::regclass AND contype = 'c'
          AND position(pats[i] in pg_get_constraintdef(oid)) > 0;
        IF NOT (position('moneyon' in d) = 0) THEN RAISE EXCEPTION 'constraint % already allows moneyon', n; END IF;
        names := names || n;
    END LOOP;
    PERFORM set_config('ailab.cons_service', names[1], true);
    PERFORM set_config('ailab.cons_route', names[2], true);
    PERFORM set_config('ailab.cons_meta', names[3], true);
END $$;

DO $$
DECLARE s text := current_setting('ailab.cons_service'); r text := current_setting('ailab.cons_route'); m text := current_setting('ailab.cons_meta');
BEGIN
    EXECUTE format('ALTER TABLE public.usage_events DROP CONSTRAINT %I, DROP CONSTRAINT %I, DROP CONSTRAINT %I', s, r, m);
    EXECUTE format($q$ALTER TABLE public.usage_events ADD CONSTRAINT %I CHECK (service IN ('home','realestate','golf','dreamcar','report','saju','car-selector','gif','moneyon','other')) NOT VALID$q$, s);
    EXECUTE format($q$ALTER TABLE public.usage_events ADD CONSTRAINT %I CHECK (route IN ('/','/realestate','/golf','/golf/club','/dreamcar','/report','/saju','/car-selector','/gif','/moneyon','/other',
         '/api/home','/api/realestate','/api/golf','/api/dreamcar','/api/report','/api/saju','/api/car-selector','/api/gif')) NOT VALID$q$, r);
    EXECUTE format($q$ALTER TABLE public.usage_events ADD CONSTRAINT %I CHECK (COALESCE((
        metadata = '{}'::jsonb OR
        (metadata - 'action' = '{}'::jsonb AND metadata->>'action' IN
            ('address_search','golf_search','trade_search','subscription_search','naver_land_click','official_source_click',
             'moneyon_card_click')) OR
        (event_type = 'api_error' AND metadata - 'status' = '{}'::jsonb AND
            jsonb_typeof(metadata->'status') = 'number' AND (metadata->>'status')::numeric BETWEEN 400 AND 599)
    ), false)) NOT VALID$q$, m);
END $$;

DO $$
DECLARE s text := current_setting('ailab.cons_service'); r text := current_setting('ailab.cons_route'); m text := current_setting('ailab.cons_meta');
BEGIN
    EXECUTE format('ALTER TABLE public.usage_events VALIDATE CONSTRAINT %I', s);
    EXECUTE format('ALTER TABLE public.usage_events VALIDATE CONSTRAINT %I', r);
    EXECUTE format('ALTER TABLE public.usage_events VALIDATE CONSTRAINT %I', m);
END $$;
COMMIT;

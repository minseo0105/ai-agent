-- Review only: every write is commented out. No automatic production execution.
-- Retention: run weekly as the operator (or configure a separately reviewed scheduled job).
SELECT count(*) AS expired_rows FROM public.usage_events WHERE created_at < now() - interval '30 days';
-- DELETE FROM public.usage_events WHERE created_at < now() - interval '30 days';

-- Rollback only if this sprint must be removed. Loses analytics history, no CASCADE.
-- BEGIN;
-- DROP TABLE public.usage_events;
-- COMMIT;

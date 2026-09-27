-- REVIEW ONLY: non-destructive containment rollback for THIS NEW DATABASE ONLY.
-- Retains all tables, indexes, RLS and rows. This is NOT a schema reversal.
-- Does not change HF/GitHub Secrets or the old production connection.
-- Run only after stopping new-database collectors; manual owner access remains.
-- Reapplying the reviewed forward migration restores its explicit API permissions.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $rollback$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['alert_rules','notifications','source_snapshots','app_settings','development_collection_runs','development_projects','development_project_sources','development_updates','geocode_cache'] LOOP
    IF to_regclass('public.' || target) IS NOT NULL THEN
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC, anon, authenticated, service_role', target);
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target);
    END IF;
  END LOOP;
  FOREACH target IN ARRAY ARRAY['alert_rules_id_seq','notifications_id_seq'] LOOP
    IF to_regclass('public.' || target) IS NOT NULL THEN
      EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM PUBLIC, anon, authenticated, service_role', target);
    END IF;
  END LOOP;
END
$rollback$;
NOTIFY pgrst, 'reload schema';
COMMIT;

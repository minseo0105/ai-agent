# ZIP:ON isolated REST compatibility test

Status: prepared, NOT EXECUTED. No runtime deployment, Secret, schema or RLS changes.

## Credentials to prepare (do not paste into chat or source files)

Select the NEW `zipon-realestate` in Supabase Dashboard first.

1. Project Settings > General: copy Project ID / reference into `ZIPON_TEST_PROJECT_REF`.
2. Project Settings > Data API (or Connect > API): Project URL -> `ZIPON_TEST_SUPABASE_URL`.
3. Project Settings > API Keys > Legacy anon, service_role API keys: reveal/copy **service_role** -> `ZIPON_TEST_SUPABASE_SERVICE_ROLE_KEY`. Use the legacy JWT service_role key to match the existing backend Authorization header; not anon/publishable keys.
4. Top bar Connect > Connection String > Session pooler: copy PostgreSQL URI -> `ZIPON_TEST_DATABASE_URL`. Use `postgres.<project-ref>`, port 5432, database postgres. Replace password placeholder with the NEW database password (not your Dashboard login password or service_role key). Percent-encode special characters in the password. Direct connection using `db.<ref>.supabase.co` and postgres also works if IPv6 is available. URI must have no query string; script sets SSL require and timeouts itself.

Why the additional SQL connection: the migration intentionally gives no DELETE privilege to service_role on notifications, snapshots, development tables. There is also no spatial REST RPC. The SQL connection is used only for read-only preflight/spatial assertions and exact-run cleanup. All inserts and compatibility updates go through the existing requests REST helper and service_role. No new grants/policies/functions are created. Do not change HF/GitHub/local production credentials.

The Dashboard display name cannot be authenticated from these credentials; ensure the selected project is zipon-realestate yourself. The script cross-checks the supplied ref against REST hostname and SQL host/username, refuses nonempty tables, then checks a REST-created row through SQL to confirm the two connections agree.

## Planned coverage

- All nine tables: SQL count zero and REST read before writes; missing grants/failed reads stop execution.
- Existing realestate_monitor functions: get_auto_monitor_enabled, get_alert_rules, save_alert_rules, toggle_alert_rule, _notify, _snapshot_new, get_notifications, delete_alert_rule.
- app_settings SELECT only; no global settings writes.
- Snapshot backend INSERT/PATCH plus explicit REST UPSERT using on_conflict=source,item_key, then payload and single-row verification.
- Development project INSERT through REST, EWKT geography Point and geometry Polygon, source FK, canonical verified source PATCH, immutable history INSERT, REST readbacks.
- Synthetic source is clearly TEST-marked with example.invalid URL. It temporarily uses official/VERIFIED values only to exercise the canonical FK; it is never real evidence.
- Actual stored spatial values verified via read-only PostgreSQL: verified polygon INSIDE; unverified polygon NEARBY; representative point alone NEARBY; no spatial data UNKNOWN. Last three are SELECT-derived variants, not extra stored projects. This does not claim that a spatial REST endpoint exists.
- No collector calls, external geocoding, scheduler or paid APIs.

## Cleanup and recovery

Every run uses TEST_ZIPON_<UUID>. Project/source/update UUIDs are deterministically derived from this run UUID. A local recovery journal in reports/zipon-rest-tests contains only those identifiers, no credentials or server payloads.

Normal completion, assertion failures and Ctrl+C use finally cleanup: exact run update -> remove canonical link on exact test project -> exact source -> exact project -> exact snapshot -> exact notification -> exact alert. Cleanup is one SQL transaction. It never truncates, removes other TEST runs, or resets identity sequences. The existing alert DELETE backend path is separately tested with the captured ID. app_settings, collection_runs and geocode_cache receive no test rows.

Network loss or forced process termination can prevent cleanup; an ambiguous timed-out REST request can also finish after cleanup. The script must not be considered passed unless it exits 0 with REST COMPATIBILITY: PASS; CLEANUP: PASS. Preserve the run UUID and rerun cleanup after outstanding requests have settled, then check postcheck again. This is a recovery operation, not permission to delete unrelated rows.

Failure reporting includes step, HTTP status and allowlisted SQLSTATE/PostgREST code with a fixed cause description. Raw response bodies, exception messages, headers, keys, connection strings and full URLs are never logged. Unknown error details require private Dashboard log inspection; the script does not invent a cause or loosen permissions.

## Commands (future execution only)

In PowerShell, from the copied active repo:

```powershell
Set-Location -LiteralPath 'C:\Users\user\Desktop\ai-agent - 복사본'
& .\venv\Scripts\python.exe -m venv .\reports\zipon-rest-venv
& .\reports\zipon-rest-venv\Scripts\python.exe -m pip install requests 'psycopg[binary]>=3.2,<4'
& .\scripts\run_zipon_rest_compatibility.ps1 -Execute
```

The wrapper asks for four values using hidden prompts, passes them only as process environment variables and restores prior values on exit. Values do not appear in shell command history. It never reads or changes production SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY, .env, secrets.toml, HF or GitHub. Do not commit the test venv or recovery journals.

If needed, cleanup-only recovery (same NEW credentials, no new inserts):

```powershell
& .\scripts\run_zipon_rest_compatibility.ps1 -CleanupRun 'UUID_FROM_TEST_RUN_ID'
```

No network tests have been run during preparation. Static Python compilation is not proof of runtime DB compatibility. After an authorized successful test, repeat the read-only postcheck. Sequence values may have advanced even though all table counts return to zero.

References: https://supabase.com/docs/guides/database/connecting-to-postgres and https://supabase.com/docs/guides/api/api-keys

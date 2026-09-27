# Location RPC install/visibility review

No DB connection, function execution, schema/RLS/Secret change, bulk retry, commit,
push or deploy was performed by this task.

## Existing definition

File: `supabase/migrations/20260927_zipon_geocode_location_rpc.sql` (updated in place;
no second migration/function or overload was introduced).

```sql
public.zipon_set_project_location(
  p_project_id uuid,
  p_longitude double precision,
  p_latitude double precision,
  p_expected_sigungu text,
  p_geocode_source text,
  p_confidence text,
  p_expected_revision bigint,
  p_evidence jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
```

PL/pgSQL, SECURITY INVOKER, fixed search_path=pg_catalog,public,extensions,pg_temp.
EXECUTE revoked from PUBLIC,anon,authenticated; granted only to service_role among
application roles (the function owner retains normal ownership privileges).
It relies on the existing service_role table privileges/BYPASSRLS and extension
schema access, not on new client grants or disabling RLS.

## Evidence and diagnostic limits

Live read-only reconciliation supplied by the user shows the first project still
has location=null, revision=1 and no verified polygon. GET OpenAPI did not advertise
the RPC to that role. This proves REST visibility is missing; it does not distinguish
an absent pg_proc entry from missing EXECUTE/schema access or a stale schema cache.

The repository's earlier geocode document explicitly says this location migration
was not applied. Missing migration is therefore the leading hypothesis, not a
confirmed catalog finding. The successful development_projects read makes a global
authentication failure or complete exclusion of public schema less likely.
The payload's8 argument names/types match the existing local SQL. No evidence
supports a project lookup or optimistic revision conflict for this failure.

Run the new read-only postcheck BEFORE install if you want the distinction:
- exact_signature_exists=false and overload_count=0: definition missing in public.
- exact signature false but overload count positive: different deployed signature.
- signature exists, service_role_execute=false: privilege missing.
- SQL catalog/security checks PASS but REST still not advertised: inspect schema
  cache/exposure; do not interpret that alone as absent SQL function.

## Review fixes

Existing SQL already locks the exact UUID row, checks revision, refuses an existing
location, compares district and bounds, stores longitude then latitude at4326,
and never changes geometry. However its previous evidence check required only
two nonempty addresses and it did not refuse a verified-boundary row inside the RPC.

Added explicit ACCEPTED status, boolean coordinate_verified, X_IS_LONGITUDE and
all8 successful evidence checks; missing/false/extra failed checks are refused.
NULL provider now fails closed. A verified-boundary row is refused after locking.
The Python payload now passes those existing acceptance fields without promoting
unaccepted records. Same SQL signature and RPC endpoint are retained.
Evidence is an assertion from the privileged reviewed backend, not an independent
provider revalidation or cryptographic proof. No geocoder is called in the RPC.

Install SQL is9 statements: transaction, local timeouts, CREATE OR REPLACE the same
function, restrictive REVOKE/GRANT, function comment, PostgREST cache notification,
commit. Defining the function does not invoke its UPDATE or modify any project row.
There is no extension/table/RLS change, DROP, DELETE, INSERT or bulk call.

## User SQL Editor order

Select the NEW zipon-realestate project, then SQL Editor, New query, role postgres.
1. Optional diagnosis before installation: run the new read-only postcheck below.
2. Paste and run the complete existing migration file
   `supabase/migrations/20260927_zipon_geocode_location_rpc.sql`.
3. Run `supabase/review/20260927_zipon_location_rpc_readonly_postcheck.sql`.
   Expected final ALL_CHECKS=PASS. This is a single SELECT and never calls the RPC.
   It checks identity/signature, invoker security, role privileges, extension schema,
   evidence/boundary guards and the pending project's unchanged baseline.
4. Run the command below to inspect current REST visibility and that single project.
   Even a PASS is not authorization to retry coordinate writes.

Do NOT run the old `20260927_zipon_geocode_location_postcheck.sql`: it is a write/
rollback test and is outside this task. Its fixture was kept compatible with the
stronger evidence contract, but it was not executed.

```powershell
& 'C:\Users\user\Desktop\ai-agent\.worktrees\zipon-geocode-review\scripts\run_zipon_verified_coordinates.ps1' -ReconcileFirst -Python 'C:\Users\user\Desktop\ai-agent - 복사본\venv\Scripts\python.exe'
```

## Validation

PostgreSQL parser (pglast8.4) SQL and PL/pgSQL syntax PASS. Postcheck parsed as exactly
one SelectStmt. This is static validation, not DB runtime verification.
ZIP:ON suite428 tests,0 failures,2 skips. Accepted122 payload contract checks PASS.
Stage catalog preserved:119 detail,11 list-only,114 with dates; Shinbanpo25
조합설립추진위원회승인. Original uncertain-write journal retained unchanged.

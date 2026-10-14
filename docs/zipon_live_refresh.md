# ZIP:ON live refresh — implementation and activation runbook

Implemented against origin/main `862b2e576e6e1feaef64a6382bc62994376e2a06` on 2026-10-14.
Production DB credentials were unavailable. No migration, production write, Secret change or collector activation was performed.

## What runs

`scripts/refresh_zipon_live.py` reads the CURRENT ZIP Supabase rows, collects official Seoul sources, preserves raw evidence, resolves exact official IDs to existing UUIDs, plans protected changes, and calls atomic refresh RPCs. It never reads a dated pilot/baseline as the operating database. The frozen `seoul-identity-v1` is unchanged. Suspected overlaps (including 마천2 and existing protected IDs) are reviewed, never merged.

The separate workflow `.github/workflows/zipon-development-refresh.yml` has UTC schedules corresponding to daily 07:17 KST, Monday 08:17 KST, and the first day of the month 09:17 KST. Daily/weekly currently recheck all 25 district listings and program sources; monthly additionally rechecks unchanged official details. Weekly/monthly check SHP publications. A changed official notice with an exact cafe alias can also trigger a detail read. HF is only the serving application; its sleep/restart does not control the runner.

Scheduled collector execution requires BOTH repository variables `ZIPON_REFRESH_ENABLED=true` and `ZIPON_CANARY_VERIFIED=true`. Any DB write additionally requires `ZIPON_REFRESH_WRITE_ENABLED=true`. Dispatch defaults to dry-run, canary and limit 1. The runner's normal limit is 10 project RPCs; allowed explicit limit is at most 100. A DB lease (40 minutes), Actions concurrency and a 35-minute job timeout prevent overlapping writers. Official HTTP requests have three attempts, 1/2-second backoff, bounded bytes and strict HTTPS/host/redirect checks. Access rejection is not retried or bypassed. Exhausted host failures open a per-run circuit.

## Accepted changes and review

- An exact official ID preserves the existing canonical UUID. Missing IDs, overlapping names, identity/name/type/district changes and protected IDs enter an append-only deduplicated review queue.
- New exact-ID candidates are registered as NEEDS_REVIEW/UNKNOWN. Verified official DETAIL observations can advance non-VERIFIED master stage fields. Only explicit terminal 준공인가/이전고시 evidence establishes COMPLETED. ACTIVE is not inferred from merely being listed.
- Four-digit dates with exact official labels retain their meanings. Stage milestone dates are not general notice dates. A dated 이전고시 milestone is a notice date; two-digit years and conflicting dates require review. Source date, notice date, effective/publication date, collection and verification remain distinct in columns/provenance.
- VERIFIED field replacement, backward/unordered stages, cancellation/suspension, existing addresses/details and existing coordinates/boundaries require review. Review is a successful observation outcome, not a reason to stop other projects.
- Candidate observations and applied master changes are distinct. RPCs check identity, revision, stage mapping/rank, detail cafe ID/source consistency, dates and protection on the server too. Accepted before/after snapshots and history commit atomically. Every successful project/spatial result is reread and checked for its revision, identity and matching history.
- Missing is inferred ONLY for a source that was fully collected within the selected districts and that previously supplied the project. It writes absence evidence, never deletes or cancels a project.

## Spatial and durable evidence

OA-22712 discovery reads the posted UQ120 filename, file sequence, hidden form fields and real `frmFile.action`; it does not construct a date-based URL. It accepts official downloads only, limits sizes/expansion, checks ZIP CRC and SHP/DBF/SHX/PRJ, and uses the existing analyzer against live DB projects. Each PRJ is inspected; schema/CRS drift blocks boundary writes. Source hashes, schema fingerprints, version and validation results are preserved. Reused versions avoid downloads when the archived bytes are available; monthly force-download catches replacement under an unchanged filename.

First coordinates reuse existing exact-address/provider checks and a durable address cache. Negative cache entries expire after 30 days; provider failures are not cached. Whole-city re-geocoding is not performed. First boundaries require EXACT, unique name/district match, valid real geometry and the representative point inside. Existing strict spatial RPCs are wrapped so history is stored in the same transaction. Existing verified boundaries are never overwritten. Only officially verified Polygon/MultiPolygon enables INSIDE.

The PRIVATE Supabase Storage bucket `zipon-official-raw` stores content-addressed public originals, archive versions, run reports, geocode cache and runner state. Credentials, authentication headers and cookies are not saved in reports. Storage failure prevents success. No original SHP ZIP or operational DB dump is committed to Git.

## UI and operations

The authenticated read-only `/admin/zipon-data` page uses existing admin login/token validation. It shows attempts/full successes, source outcomes, project/location/boundary counts, recent registrations/applied history, pending reviews and stale-success warnings. Query failure returns unavailable, never fabricated zero counts. The SQL summary is SECURITY INVOKER and is not executable by anon/authenticated. No approval/write endpoint was added.

Applied DB observations take precedence over the packaged stage catalog. Development metadata includes source/notice dates. The existing map/card/filter implementation is retained and refetches on return to the visible tab and every five visible minutes.

## Evidence and limitations

- Actual official 25-district collection: 1,203 raw candidates; all 25 directory sources plus both fast-track sources completed. 영등포구 required two pages (105 accepted rows). The prior accepted-row-count cutoff was fixed: pages can contain other business categories, so 85 accepted rows need not mean the end of a 100-row page.
- Main 모아타운 source returned an official errorAccess redirect. It is SOURCE_ACCESS_DENIED, not a success. An independently linked official information portal exposes cancellations; a supplemental collector saves those as review evidence, not as an active-town-list substitute.
- Actual OA-22712 ZIP: posted `202609`, 2,516,298 bytes, SHA-256 `7788af6b3a2815bcbf529b1e005c9fb6d9828288fbedeec586a13e706c301703`, 2,776 records, EPSG:5174, zero transformed records outside the analyzer's Seoul sanity bounds.
- Official notice board collection and one exact-ID official detail were read live. The sampled detail explicitly reported 조합해산, an unordered review outcome; it was not promoted to a business status.
- Python policy/runner/admin tests, disposable PostgreSQL refresh/permissions/rollback tests, frontend typecheck/build and actual local browser auth/error/mobile checks were performed. PostgreSQL WASM tests use spatial stand-ins and DO NOT establish PostGIS predicate correctness. Existing PostGIS RPC tests must also pass in staging before a spatial production canary.
- Full-suite main baseline and implementation share the same six assertion failures and five errors (including a missing Golf `naver_calls` field and subprocess mock leakage). The previously stated seven-failure baseline was not assumed. No new failure was found in the same-environment comparison. No Golf file/data was modified.
- No production counts, current installed RPCs, DB reconciliation, scheduled DB writes or HF deployment are inferred from these offline/live-source checks. Status remains CONFIG_REQUIRED + DB_MIGRATION_REQUIRED, not LIVE_VERIFIED.

## User steps (three)

1. **Supabase: verify and install in the ZIP project.** Open the ZIP Supabase Dashboard → SQL Editor. Run `supabase/review/20261014_zipon_refresh_readonly.sql` first and retain project/location/verified-boundary counts. In staging, verify PostGIS and the existing `zipon_ingest_candidate_v2`, `zipon_set_project_location`, `zipon_set_project_boundary`, `zipon_record_source_missing` dependencies; install any absent reviewed predecessor migration before `supabase/migrations/20261014_zipon_live_refresh.sql`. Validate staging, then install the reviewed new migration on the intended ZIP project. Storage → create PRIVATE bucket `zipon-official-raw`. Success: new RPCs/tables exist, anonymous permissions remain absent, old counts are unchanged. No runner applies migrations automatically.
2. **GitHub: configure ZIP-only access, keep automatic collection gated.** Repository → Settings → Secrets and variables → Actions. Add Secrets `ZIPON_IMPORT_SUPABASE_URL`, `ZIPON_IMPORT_SUPABASE_KEY` for the intended ZIP project; add the chosen geocoder credentials only if initial coordinate filling is enabled. Keep `ZIPON_REFRESH_ENABLED` and `ZIPON_CANARY_VERIFIED` unset/false. Leave `ZIPON_REFRESH_WRITE_ENABLED=false` until canary approval. HF Settings must already have ZIP read configuration (`ZIPON_SUPABASE_URL`, `ZIPON_SUPABASE_SERVICE_ROLE_KEY`) and the existing admin auth configuration; the collector does not need HF settings. Success: workflow dry-run can read current ZIP rows; `/admin/zipon-data` can read the installed summary. Do not paste Secret values into chat or reports.
3. **GitHub Actions: dry-run → one-row canary → gated activation.** Open Actions → ZIP development refresh → Run workflow, job `canary`, apply `false`, limit `1`. Inspect the artifact, source failures, reviews and proposed change. After staging/DB safety checks, set WRITE_ENABLED=true and dispatch apply=true/limit=1. A canary is verified ONLY if a real accepted master write has matching before/after counts, expected revision/history and successful reconciliation; a no-op is not a verified write. Review any PARTIAL source outcome separately. Only after that set CANARY_VERIFIED=true and REFRESH_ENABLED=true. Success: a later schedule event performs real collection and safe writes, records outcomes in Supabase, and the map/admin page show the new observation. Until this evidence exists, the system is not LIVE_VERIFIED.

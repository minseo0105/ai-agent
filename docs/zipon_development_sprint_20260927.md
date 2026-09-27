# ZIP:ON development sprint — 2026-09-27

## Applied locally, not deployed (superseded)

> 2026-09-27: migrations, both RPCs, the spatial postcheck and the 8-record canary import have since
> been applied and verified on the real `zipon-realestate` project. See
> `docs/zipon_rpc_predeploy_20260927.md` and `docs/zipon_development_verification_20260927.md`.


Shared server-only Supabase headers now support sb_secret_ via apikey only and legacy keys via apikey + Bearer. Monitor and access settings use the same helper. SQLite and access local-file fallback selection are unchanged. No production configuration was read or changed and no Supabase write was performed in this sprint. Completed migrations and REST compatibility tests were NOT rerun.

## Backend contracts

- POST /api/realestate/development/search: longitude + latitude, optional sigungu, radius_m 0..10000, limit 1..100. Alternatively sigungu without coordinates returns UNKNOWN candidates.
- Calls public.zipon_development_search via existing requests REST transport. No runtime psycopg.
- Response status=ok/unavailable, nearby_projects with project_id/name/type/stage/status/validation_status/relation/distance_m/official_source/source_url/verified_at.
- POST /api/realestate/trades accepts include_development=false by default. When true, adds development_context; no coordinates means needs_geocode/UNKNOWN. Existing MOLIT rows currently have no coordinates. No geographic centroid is substituted. At most 10 distinct coordinate lookups per request, repeated points share results.
- Failed development lookup does not remove trades or change price/area/count behavior. Existing UI unchanged.

## SQL review and future action

Only NEW zipon-realestate, after explicit review, apply in this order:

1. supabase/migrations/20260927_zipon_spatial_rpc.sql
2. supabase/migrations/20260927_zipon_candidate_ingest_rpc.sql
3. supabase/review/20260927_zipon_spatial_postcheck.sql (read-only)

Do not rerun base migration. Both RPCs are SECURITY INVOKER with fixed search_path and EXECUTE only for service_role (PUBLIC/anon/authenticated revoked). They do not alter RLS or grant browser access. SQL parser validation does not prove server execution; new RPC runtime verification remains after approval.

Spatial search uses verified geometry + ST_Contains only for INSIDE. Point-only data can only yield NEARBY. Exact polygon boundary yields NEARBY; missing spatial data yields UNKNOWN when district scope is supplied. Known distant features are excluded, not mislabeled UNKNOWN. Meter distances use geography; existing GiST indices are available. Official evidence may be returned even when unverified, but verified_at remains null and validation_status is explicit.

Candidate RPC obtains a per-project transaction advisory lock, checks expected revision, inserts source and history in the same transaction, and avoids duplicate unchanged observations. It preserves approved existing master fields. Changed unreviewed observations live in append-only source/history snapshots; collection never automatically promotes a stage/status or constructs a polygon. New candidates begin UNKNOWN/NEEDS_REVIEW. Historical return to previously observed content still creates a new revision. Explicit business-status approval workflow is not yet implemented.

## Pilot and provenance

Artifact: data/development/pilot_20260927.json. Official Seoul cleanup list adapters plus Moatown status adapter registered in services/development_collector.py.

Current pilot: Gangdong 59, Songpa 52, Seocho 72 = 183 source-specific candidates. All have official source URLs, collected_at, row snapshot and content hash. These are NOT 183 reviewed unique businesses: cross-source duplicates and renamed businesses need reconciliation. Directory cafe identifiers are retained where available; other source rows receive internal deterministic UUIDs without inventing official IDs.

Moatown status endpoint timed out; browser access also redirected to the Seoul error page. No Moatown count was invented. Source run failures are included. Directory pagination coverage is conservatively PARTIAL, not treated as full inventory. No missing-record deletion/cancellation occurs.

Confirmed coordinate count 0; verified boundary count 0. Geocoding has an injected provider + reusable cache contract, accepting only exact BUILDING/PARCEL results, but no live provider/credential has been configured. Stored geocode_cache integration and official boundary ingestion remain next steps. Raw source stage and observed dates are retained; observed event dates are not misrepresented as publication dates.

## Operator commands (not run against DB)

Collect to local artifact: python -B scripts/collect_zipon_pilot.py

Inspect candidate file without DB: python -B scripts/import_zipon_candidates.py data/development/pilot_20260927.json

Only after migration approval and candidate review, separate import can use --apply-new-db and ZIPON_IMPORT_SUPABASE_URL / ZIPON_IMPORT_SUPABASE_KEY process variables. The importer pins the NEW project ref, does not read production secrets, and uses the atomic ingest RPC. It creates development_collection_runs with counters and safe error types; an interrupted run remains RUNNING for review. The importer was NOT applied in this sprint.

## Deferred related issues

MOLIT 1000-row / subscription 100-row pagination, scheduler saved ON/OFF, multi-rule notification newness/duplicate handling and legacy source_snapshots history are unchanged. New development history uses its own atomic append-only path, avoiding reuse of legacy snapshots. These unrelated monitor fixes need separate focused regression coverage.

No commit/push/deployment, no HF/GitHub Secret changes, no existing or new Supabase mutation in this sprint.

# RPC pre-deploy review

> 상태 업데이트 (2026-09-27): 아래 pre-deploy 절차는 실제 `zipon-realestate`(ref
> `nnxtkvjpzqqhjlgnprzo`)에서 **이미 실행 완료**되었습니다. base migration 적용, PostGIS 검증,
> REST compatibility PASS, CLEANUP PASS, spatial RPC 적용, candidate ingest RPC 적용,
> spatial postcheck 실행, `ALL_CHECKS = PASS` 확인, Canary 8건 실제 import
> (new 8 / changed 0 / unchanged 0 / errors 없음, project_id·official source·is_official=true·
> content_hash·validation_status=UNVERIFIED 확인)까지 끝났습니다.
> 따라서 이 문서의 "No DB SQL or import executed"는 작성 시점 기록이며 현재 상태가 아닙니다.
> 재실행하지 마십시오. 이후 진행 상황은 `docs/zipon_development_verification_20260927.md`를 보십시오.

No DB SQL or import executed at the time this review was written. Base migration unchanged.

Changes: fixed search_path includes pg_temp last; invoker rights; only service_role EXECUTE; static SQL only. Ingest rejects malformed documents and mismatched official identity/type/district. Candidate equality as well as source hash controls unchanged decisions; normalized changes are no longer lost. Canonical source, verified geometry, stage/status and existing business fields cannot be overwritten by candidate imports. Advisory lock and row lock serialize master/history writes. Failure rolls back function writes. Base FKs remain active. CREATE OR REPLACE preserves signature on reruns; no base objects dropped or altered.

SECURITY INVOKER does not grant RLS bypass; existing service_role BYPASSRLS is deliberate and remains server-only. SQL Editor postgres is also privileged. Caller-provided official URLs are provenance claims, not proof: collectors and human verification remain trusted backend responsibilities. No arbitrary table/column selection or dynamic SQL.

Execution on NEW zipon-realestate as Dashboard postgres:
1. supabase/migrations/20260927_zipon_spatial_rpc.sql
2. supabase/migrations/20260927_zipon_candidate_ingest_rpc.sql
3. supabase/review/20260927_zipon_spatial_postcheck.sql — run ENTIRE file. It temporarily writes TEST_ZIPON UUID fixtures under service_role, catches an intentional subtransaction rollback, verifies absence, returns one result table and ends ROLLBACK. It is no longer read-only. Existing rows are never targeted. If the Editor is interrupted, explicitly ROLLBACK the open transaction before continuing. ALL_CHECKS must be PASS.

Canary: data/development/canary_20260927.json spans all three districts and all three collected types. Inspect the file and source identities first. The importer now blocks >10 records for --apply-new-db. Default invocation remains local only. Do not import the 183-record pilot file.

After all new RPC checks pass and canary review is approved: run scripts/import_zipon_candidates.py data/development/canary_20260927.json --apply-new-db with existing isolated ZIPON_IMPORT_* process variables. This performs real candidate writes; it was not run here. Preserve the returned run_id. Run supabase/review/20260927_zipon_canary_check.sql in SQL Editor and verify IDs, address, source URL, UNKNOWN/NEEDS_REVIEW, revision=1, one initial history per new candidate. Repeating the same canary must yield unchanged and not increment project revisions/history. Collection run records may increase by design. No bulk DELETE cleanup: canary consists of real review candidates and is retained unless a separately reviewed rollback is authorized.

Static parser and mock checks cannot prove actual PostgreSQL function execution; the rollback-only postcheck provides that evidence after applying migrations. No HF/GitHub changes or deployment.

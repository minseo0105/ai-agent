# ZIP:ON final validation — 2026-09-28

Coordinate writes are complete. Do not rerun geocoding or any apply command.
The successful final DB readback was checked through the current API presenters:

| Check | Result |
|---|---:|
| Canonical projects |130|
| Coordinates / map markers |122 /122|
| Official detail / list-only / unresolved stage |119 /11 /0|
| Projects with milestone dates |114|
| Verified polygons |0|
| INSIDE enabled |false|
| REVIEW_REQUIRED / FAILED excluded |5 /1|

Shinbanpo25 renders `조합설립추진위원회승인`; the official raw date remains
`15.12.16` without inferred century. Existing112 detailed observations were preserved.
Seven recovered official-detail matches have district/address/type/identifier evidence.
Project identity and the separation of project_type from program are unchanged.

The final user-run resume skipped42 validated projects and added80, with0 failures,
0 conflicts,0 remaining attempts, matching coordinates and unchanged protected fields.
No DB calls that write data were made during this final validation/publishing task.
Stage changes remain catalog/code-only. Points cannot establish INSIDE.

## Verification

- ZIP:ON Python suite including focused and product tests:448 tests,0 failures,
  2 existing skips. Run once for final regression.
- Frontend typecheck PASS; production build PASS (12 static pages).
- Successful DB readback replay through map/stage presenters PASS.
- Runtime journals and temporary recovery checkpoints are ignored by Git and kept locally.

## Recovery behavior retained

RPC success and local journal failures are separate. Applied points are compared
against ACCEPTED evidence; unattempted rows do not create coordinate mismatches.
Atomic journal writes use unique same-directory files, fsync and bounded file-lock
retries. Exhausted retries preserve the recovery checkpoint and stop subsequent writes.
Windows PowerShell explicitly reads UTF-8 journals. No safety gate was removed.
Read-only live reconciliation precedes a resume and excludes all already-applied IDs.

The location RPC definition keeps its original signature and service_role-only
application access, with row locking/revision checks, no point overwrite, verified
geometry protection, Seoul bounds and explicit ACCEPTED evidence checks. The new
postcheck is SELECT-only. This task does not reapply SQL or change RLS/Secrets.

## Publishing

Use the existing main-push workflow `.github/workflows/deploy-space.yml` without
altering its deployment structure. Deployment status is reported separately after push.
Older preparation/diagnostic documents record historical states and are not current
instructions to rerun writes.

## Remaining data work

Review the5 ambiguous geocode candidates manually and investigate the1 failed
address (길동진흥). Two other canonical projects have no addressable geocode target.
Continue official-detail research for11 list-only stages and date evidence for16
projects. Verified polygons remain a separate official-source task; do not generate
boundaries or INSIDE judgments from representative points.

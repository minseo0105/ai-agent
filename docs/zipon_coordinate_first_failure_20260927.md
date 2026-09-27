# First coordinate apply: read-only diagnosis

Target: `0922ac26-1436-5158-853d-49d3c5aed7fb`.
Original journal: `data/development/coordinate_apply_guarded_result.json`.
SHA256: `831aec98b27fd2abbe7bf83b1a3046b057f8db47f7891714972185f63e416b7f`.
The journal is preserved, not reset or overwritten by reconciliation.

## Established evidence

- The first POST to `rpc/zipon_set_project_location` raised `HTTPError` at
  `response.raise_for_status()`. It did not reach JSON response parsing.
- Original exception handling retained only the exception class. HTTP status,
  PostgREST/SQLSTATE code and response message are unavailable retrospectively.
  A precise RPC/auth/schema/payload server cause cannot honestly be recovered
  from this journal alone. No write is retried to reproduce it.
- The completed **post-failure live DB snapshot stored in that journal** contains
  the target with `location=null`, `revision=1`, exactly matching its before row.
  All selected columns of all130 rows also compare equal. This establishes no
  coordinate/revision change at that snapshot, not an assertion about a later state.
- Local SQL expects the8 named parameters produced by `payload_for`.
  Revision conflict and missing project return a JSON refusal under the local
  function contract, rather than an HTTP error. The deployed function is not yet inspected.
- `docs/zipon_naver_geocoding_2026-09-27.md` still says the location RPC is not
  applied. Missing/unexposed RPC is a **hypothesis**, not proof of the live cause.

## Minimal diagnostic changes

- Apply runner now retains allowlisted HTTP status / PostgREST or SQLSTATE code /
  failure category. Raw exception messages, response bodies, headers, keys and URLs
  are never included in its error report.
- `reconcile_zipon_coordinate.py` only permits GET. It reads this project by exact
  UUID and GETs the REST OpenAPI schema to compare the advertised RPC parameters.
  It never invokes the write RPC, even for a dry-run. Lack of OpenAPI visibility
  does not prove a missing DB function; it can also mean role/schema exposure.
- `run_zipon_verified_coordinates.ps1 -ReconcileFirst` is mutually exclusive with
  `-Apply`, uses existing isolated variables or a hidden input, and restores the
  process variables. No production credentials or settings are accessed.
- A separate `coordinate_first_readonly_reconciliation.json` receives safe results.
  The original uncertain-write journal continues to block automatic bulk retries.

## Execution and limits

Related automated tests:30 PASS; PowerShell parser PASS.
New direct live read: blocked before network by missing isolated import variables.
No DB writes, schema changes, RPC invocation, push, deployment or journal reset.
Stage catalog remains119 detail /11 list-only /114 with dates; Shinbanpo25 remains
조합설립추진위원회승인.

Run only this diagnostic command in an interactive PowerShell. If prompted, paste
the new project's server key into the hidden console input, never into chat.

```powershell
& 'C:\Users\user\Desktop\ai-agent\.worktrees\zipon-geocode-review\scripts\run_zipon_verified_coordinates.ps1' -ReconcileFirst -Python 'C:\Users\user\Desktop\ai-agent - 복사본\venv\Scripts\python.exe'
```

Even a read-only dry-run PASS does not authorize another write. Inspect the report
first. Do not delete the old journal or run bulk apply to diagnose the problem.

# ZIP:ON stage reconciliation / guarded coordinate apply

Historical preparation record. Coordinates are now complete; see
[final validation](zipon_completion_20260928.md). Do not rerun the apply command below.

Base: `cf6c243e`, branch `codex/zipon-geocode-review`.
Actual worktree: `C:\Users\user\Desktop\ai-agent\.worktrees\zipon-geocode-review`.
No deployment, push, schema/security changes, or DB writes in this run.

## Stage evidence

130 canonical IDs from the existing import/baseline artifacts match the 130 IDs in the
previous production API snapshot and the packaged catalog exactly. The new live
production API request returned HTTP 503; this is **not a fresh DB reconciliation**.

| Evidence | Count |
|---|---:|
| OFFICIAL_DETAIL_VERIFIED |119/130|
| OFFICIAL_LIST_MAPPED only |11/130|
| No usable stage at either level |0/130|
| At least one milestone date |114/130|
| Original detail observations preserved field-for-field |112/112|

11 projects remain unresolved **at detail level**. A list stage does not establish
their complete procedure or milestone dates. Three recovery leads did not pass all
identity checks: 현대연립 (district omitted / lot notation differs), 목화연립
(209 vs 209-0), 이화연립 (canonical 153 vs detail 146). These are retained for
review, not silently remapped or promoted. Eight other projects have no confirmed
alternate detail observation. Original canonical IDs/types/programs are unchanged.

Seven newly verified detail observations: 선화연립, 풍전연립, 서초중앙하이츠2,
신반포25차, 신성빌라, 반도아파트, 송파동100번지. Each passes district, dong,
lot, project type, numeric name identifiers, frame name, and official cafeId checks.
The original 112 detail observations were not downloaded again.

### Shinbanpo 25

Canonical ID: `0164b2b0-1b21-51e3-8b8d-f97bda852a18`.
The old `sinbanpo25` alias returned an error page without a frame. The old collector
only followed that alias, so it retained list-only evidence. The UUID entry was
present in the catalog, but lacked project-name metadata, making name searches fail.

Recovered official identifier: `650900000613q27`, distinct from the combined
19차/25차 project's identifier. Official summary confirms 서초구 잠원동61-1 and 재건축.

- Current stage: 조합설립추진위원회승인.
- Official detail: https://cleanup.seoul.go.kr/assc/scrin-bbs/execute.do?cafeId=650900000613q27
- Official summary: https://cleanup.seoul.go.kr/cafe/mastr-cleanup-bsnsSumry/execute.do?cafeId=650900000613q27&stepSeCode=103&div=sumry
- Milestone string: `15.12.16` preserved verbatim; no century inference.

Current stage and dated milestones have separate evidence selectors. The detail
page's actual procedure order is retained. This observation does not override the
official list's suspension/status evidence or assert the page is a current legal notice.

## Presentation and replay

Blank/UNKNOWN RPC placeholders no longer hide a known official-list fallback.
Replay of the prior production API payload for all130 returns119 detail stages,
11 list-only stages, and0 unknown labels. Names/addresses/types/programs were added
to catalog metadata without changing `seoul-identity-v1`.
Existing UI already displays procedure position, explanation, dated milestones,
and official links, using detail-specific ordering. No frontend rewrite was needed.

## Coordinates: preparation only

Frozen ACCEPTED122 artifacts pass ID, original-evidence equality, district/address
component, exact NAVER match, Seoul bounds and longitude/latitude orientation checks.
REVIEW_REQUIRED5 and FAILED1 remain unchanged. **No coordinates have been written.**

The current process has neither `ZIPON_IMPORT_SUPABASE_URL` nor
`ZIPON_IMPORT_SUPABASE_KEY`. Production secrets were not read. Thus live preflight,
revision checks and post-write reconciliation have not run and must not be reported PASS.
The last supplied map state is0/130 points and0 verified polygons; current API503
prevents independent refresh. Points never enable INSIDE; no spatial SQL was changed.

`scripts/apply_zipon_verified_coordinates.py` defaults to a read-only dry-run:

1. Validate the frozen122 acceptance records; never geocode again.
2. Read all130 canonical IDs, addresses, districts, revisions, coordinates and geometry.
3. Reject the entire write phase if any row has a mismatch, existing point or verified polygon.
4. Repeat the complete read/revision comparison before any writes.
5. Call only existing `zipon_set_project_location` with the expected revision.
6. Journal the pending project ID before each request; stop on first refusal or uncertainty.
7. Read back all130; verify coordinates/revision increments, untouched other rows and
   protected fields (including the original geometry), counts and conflicts.

The122 individual RPC transactions are not an all-or-nothing bulk transaction. An
interruption can leave a partial run. `coordinate_apply_guarded_result.json` retains
safe project IDs/results and blocks automatic reruns after any attempted write. Resolve
that journal with read-only DB reconciliation; never delete the journal merely to retry.
No Secret/header/password/connection string is recorded.

### Secure user step

After local checks, run the following in your interactive PowerShell. It requests only
the **new zipon-realestate server Secret key** with hidden input if not already present
in the explicitly named import process variables. It restores those variables afterward.
Do not paste a key into chat. The URL is pinned to the reviewed new project.

```powershell
& 'C:\Users\user\Desktop\ai-agent\.worktrees\zipon-geocode-review\scripts\run_zipon_verified_coordinates.ps1' -Apply -Python 'C:\Users\user\Desktop\ai-agent - 복사본\venv\Scripts\python.exe'
```

This runs a read-only dry-run first and applies only if the whole gate passes.
Inspect its safe report before claiming122 successes. A blocked preflight leaves DB unchanged.
No main push/deploy is part of this command.

## Validation

Python ZIP:ON suite:417 tests,0 failures/errors,2 intentional skips (includes product tests).
Frontend typecheck PASS. Production build PASS (12 static pages).
PowerShell parser PASS. Original112 detail observations preservation PASS.
Live API replay unavailable (HTTP503); prior real API snapshot replay PASS.
Live DB preflight/apply/reconciliation: NOT RUN (missing isolated credentials).
Commit is deferred until the requested live DB gates can also be checked; base remains cf6c243e.

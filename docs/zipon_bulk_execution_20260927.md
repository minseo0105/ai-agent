# ZIP:ON production bulk geocode result

Deployment commit: `397230a68cc7987ef18cf4e942443fb8cd94fe03`.
GitHub → HF workflow succeeded: https://github.com/minseo0105/ai-agent/actions/runs/36315173238
The production aggregate endpoint returned HTTP 200 and `zipon-bulk-geocode-v1`.

## Actual execution

Four sequential slices (offset 0/32/64/96, size 32), 128 NAVER provider calls.
Aggregate used the cache only (zero additional provider calls).

| Outcome | Count |
|---|---:|
| ACCEPTED | 122 |
| REVIEW_REQUIRED | 5 |
| FAILED | 1 |
| PENDING_PROVIDER | 0 |

All 128 IDs exactly match the frozen canonical target list. No identity was changed.
The accepted-only apply artifact contains exactly 122 unique IDs, excluding every
review/failed row. Provider address elements and checks are preserved.

Checks on the 122 accepted rows passed: Seoul bounds, district, coordinate axis,
all recorded address checks, duplicate coordinates and district spread.
An additional exhaustive pairwise haversine check found zero pairs within 11 m.
District counts: Gangdong 37, Seocho 55, Songpa 30. These are representative
address points, not verified project boundaries; INSIDE remains prohibited.

## Not ready to apply

- 둔촌주공아파트 주택재건축정비사업조합 — ambiguous provider candidates.
- 신반포5차아파트 주택재건축정비사업 조합 — ambiguous provider candidates.
- 이화연립 주택재건축정비사업조합 — ambiguous provider candidates.
- 마천4재정비촉진구역 주택재개발정비사업조합 — ambiguous provider candidates.
- 마천3재정비촉진구역 주택재개발정비사업조합 — ambiguous provider candidates.
- 길동진흥아파트 주택재건축정비사업 조합 — provider returned NO_MATCH for the canonical address.

Do not select the first candidate or rewrite canonical addresses to force a match.

## Saved outputs

- `data/development/bulk_geocode_result_20260927.json`
- `data/development/bulk_geocode_review_20260927.json`
- `data/development/geocode_apply_ready_20260927.json`

Full slice/aggregate responses and the offline audit are additionally stored locally
under `C:/Users/user/Desktop/ai-agent/reports/zipon-production-bulk-397230a6/`.

## Validation / boundary

Initial ZIP:ON suite: 392 tests, no errors/failures, 2 skips.
After corrections: product suite 206 tests passed (including two new regressions).
Frontend production build and Docker-equivalent STATIC_EXPORT build passed.
Work began from a clean isolated checkpoint worktree; existing modified checkouts
were preserved. Golf code/data, Supabase RLS/schema, identity and secrets were untouched.

DB writes: **0**. Migrations: **0**. The development map does not gain these 122
pins until the user explicitly authorizes coordinate application. Before applying,
use the existing runner's read-only preflight to protect existing coordinates,
verified boundaries and revisions. Do not run `--apply` without that approval.

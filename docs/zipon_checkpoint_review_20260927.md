# ZIP:ON checkpoint deployment review — 2026-09-27

Reviewed checkpoint: `82c03c3` on `claude/keen-clarke-m73n6h`.
It descends directly from the reviewed remote main `fcb42975`.
Review worktree: `C:/Users/user/Desktop/ai-agent/.worktrees/zipon-geocode-review`.
Other checkouts and their uncommitted changes were preserved.

## Corrections

- Preserve address elements from the evaluated candidate when reconstructing cached or disambiguated results.
- Aggregate cached failed provider attempts as FAILED, not PENDING_PROVIDER. Keep only the exception type, never its message.
- Use the shared Supabase authentication helper in the future apply runner: server secret uses apikey; legacy credentials retain Bearer authentication.
- Regression tests cover cached evidence, failure counts without provider calls, and both authentication formats.

## Deployment and subsequent operation

Use the existing main push → GitHub Actions → Hugging Face workflow.
No migration, Supabase write, secret update, identity change or golf change is included.
Frontend was built with `STATIC_EXPORT=1`, matching the Docker build.

After deployment, run these requests sequentially, waiting for each JSON response:

1. `/api/realestate/geocode/bulk?offset=0&size=32`
2. `/api/realestate/geocode/bulk?offset=32&size=32`
3. `/api/realestate/geocode/bulk?offset=64&size=32`
4. `/api/realestate/geocode/bulk?offset=96&size=32`
5. `/api/realestate/geocode/bulk?aggregate=true`

Host: `https://minseo2-digital-ai-lab.hf.space`.
Aggregate uses cached results only. Save the aggregate JSON before a Space restart;
the local cache is not guaranteed to survive redeployment. Aggregate HTTP responses
can be cached for 60 seconds. Avoid reading aggregate midway through the slices.

Review all 128 outcomes, district matching, coordinate orientation, exact duplicate
coordinates, approximately 11 m coordinate clusters and district spread before
preparing the accepted-only artifact. REVIEW_REQUIRED must not be applied.
The approximate cluster check is a rounded coordinate grid, not an exhaustive
pairwise distance test. Review nearby pairs across grid boundaries as needed.
Database application remains blocked until explicit user approval.

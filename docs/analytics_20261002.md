# AI LAB anonymous usage events

## Sync and scope

Laptop main was fast-forwarded from `85bd6e01a24ea9993f10696743a2a7630a296bd4`
to the fetched origin/main `ad24960278a1591f08e051def00af07e6ef100a2`.
Existing `.worktrees/`, `reports/`, the geocode worktree, and stashes were preserved.
No reset, stash apply/pop, production SQL, or data migration was run.

History/source checks include reliability/health/ready and Golf request cancellation
(`33505eb9`), origin sorting (`c997775c`, `caae001e`), map/card linking, buyer stage
guides and deployment version reporting (`b0d1257c`), and Npay links (`d9ec4e59`).

The active web app is Next.js App Router (`web/src/app`), with home, realestate,
golf/club, dreamcar, report, saju, car-selector, gif and admin routes. FastAPI
`api/main.py` serves APIs and the static export. Existing access control,
request context, readiness checks, service APIs and Supabase helpers remain in use.
Only new analytics structures are added; no ZIP:ON schema, RLS, coordinates,
identity, polygon, stage, or Golf data changes.

## Collection and isolation

Browser → `POST /api/analytics/events` → bounded memory queue → one asynchronous
HTTP writer → shared AI LAB Supabase `public.usage_events`.

The writer uses `services.config.get_secret` and `services.supabase_auth.supabase_headers`.
Default credentials are the existing server-only `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY`. To choose a dedicated analytics project, supply both
`ANALYTICS_SUPABASE_URL` and `ANALYTICS_SUPABASE_SERVICE_ROLE_KEY` on the server.
Never put these in NEXT_PUBLIC variables. ZIPON_SUPABASE credentials are never used.
If credentials are absent/invalid, telemetry is discarded and startup still succeeds.

Browser transmission starts after a 1.5 second timer and an idle callback (up to
2 more seconds). Maximum 64 queued events, 20 per request, one active request,
1.5 second request timeout, no retry and no unload/beacon duplication. It sends
no cookies, Authorization header or referrer. Plain-text JSON avoids a cross-origin
preflight. No service client is imported and no core request is added or repeated.

The server accepts at most 16 KiB / 20 events per request, with a 1 second body-read
deadline and a process-wide token bucket (burst 120, refill 30/s; both requests
and events consume budget). The writer queue holds at most 256 events; one worker
writes batches of up to 20 with an 0.8 second HTTP timeout and 1 second total
deadline. Failure drops the batch and backlog and suppresses collection for 60s.
There are no per-session/IP maps, retries, or unbounded background tasks.
Shutdown cancels the worker instead of waiting for analytics to flush.

This is lossy operational counting, not audited billing or bot-proof analytics.
Short visits, shutdowns, overload, blocked transport and outages can lose events.
Public ingestion can receive forged visits; no public analytics read API exists.

## Privacy and event meaning

Session: random UUIDv4 in sessionStorage; unchanged on reload in the same tab.
Storage denial falls back to memory. A fresh independent tab gets a new session;
browsers may copy sessionStorage when duplicating an existing tab. No fingerprint
or long-lived localStorage tracking is used. Counts are sessions, not unique people.

Only fixed routes/services/event names and enumerated action values are accepted.
Unknown paths become `/other`; query strings/fragments and admin visits are excluded.
No names, email, phone, raw searches, addresses, coordinates, project IDs, IP,
User-Agent, tokens, cookies, request bodies or arbitrary exception text are stored.
`created_at` is the server ingestion time in UTC (not a client-supplied timestamp).

| Surface | Event | Metadata |
| --- | --- | --- |
| Home and other public routes | page_view | none |
| ZIP:ON | page_view | none |
| ZIP:ON filter input on changed, nonempty blur | search | action=address_search |
| ZIP:ON trade / subscription submission | search | action=trade_search / subscription_search |
| ZIP:ON card selection | project_click | none |
| ZIP:ON marker / verified boundary selection | map_click | none |
| ZIP:ON Npay / official source links | external_link_click | action=naver_land_click / official_source_click |
| Golf search, including sort-driven searches | search | action=golf_search |
| Completed service HTTP error responses | api_error | numeric status |

ZIP:ON currently has a local project/address filter, not a separate geocoding search
form. Its search event does not call a geocoder. Button/link clicks inside a card
do not also count as project selection. API errors are recorded server-side after
response completion, without reading the body; session_id is null. The existing
server-generated request ID is retained; caller-supplied IDs are omitted. Health,
ready, admin, access and analytics endpoints are excluded. Network failures before
the server and errors embedded in a successful streaming response are not counted.

A module-level route guard survives React effect replay/remounts. Rerendering the
same route does not create a new page_view. A → B → A does; reloading also does.
Visits include entering a route whose existing access gate is shown.

## Database and operator steps

Apply **only `supabase/migrations/20261002_usage_events.sql`** in the shared AI LAB
Supabase project's SQL Editor (or the explicit dedicated analytics project).
It is transactional and fails rather than silently reusing a conflicting table.
RLS is enabled with zero public policies. PUBLIC/anon/authenticated have no table
or sequence privileges; service_role gets INSERT and sequence USAGE only.
There is no foreign key to a core table. Indexes: primary key and created_at only.

After deploying and applying the migration, allow an existing failure cooldown
to expire (60 seconds), visit home/ZIP:ON/Golf, then run the read-only
`supabase/review/20261002_usage_events_validation.sql`. It checks privileges/RLS
and reports KST today views, sessions, searches, errors, seven-day views and
day/service/event/action counts. No administrator UI or public view is created.

Retention target is 30 days. Review and run the commented deletion statement in
`supabase/review/20261002_usage_events_maintenance.sql` weekly as an operator;
no retention job has been installed. The same file contains a commented rollback
that drops only usage_events without CASCADE. Neither statement is auto-executed.

## Performance evidence

Headless Chrome loaded actual production static builds of origin/main and this
change with identical local API fixtures; all external requests were blocked.
These are browser integration measurements, not a live production load test.

| Initial /realestate request | Before | After |
| --- | ---: | ---: |
| /api/access/status | 1 | 1 |
| /api/realestate/options | 1 | 1 |
| /api/realestate/notifications | 1 | 1 |
| /api/realestate/map/config | 1 | 1 |
| /api/realestate/development/map | 1 | 1 |
| Total core requests | 5 | 5 |
| Analytics requests | 0 | 1 |

Analytics uses no Naver/Golf/development API. Under a mocked analytics 503, Golf
search and the ZIP:ON UI remain usable. The timing/transport unit test also verifies
no synchronous fetch on a UI event and one bounded request at a time.

Existing duplicate-load observation:

- ROOT CAUSE: `tab === "개발지도" && <DevelopmentTab ...>` unmounts the map tab.
- CURRENT CALL COUNT: initial development request 1; after leaving/returning, 2
  cumulative in both builds (map config is also reloaded).
- EXPECTED CALL COUNT: 1 initial; a retained/cached tab could avoid the second.
- RECOMMENDED FIX: separately review tab retention or a request cache with clear
  region/completion invalidation. No loading architecture changes in this sprint.

## Verification commands and limits

- `python -X utf8 -B -m unittest tests.test_analytics -v`: mock Supabase transport,
  missing table, DB failure, total timeout, bounded queue, invalid/forbidden input,
  error privacy, startup failure, actual health route and mocked dependency readiness.
- `node tests/test_analytics_frontend.cjs`: delayed transport, storage denial,
  reload/new-session behavior, route dedup, privacy, overload and failed transmission.
- `node tests/test_analytics_browser.cjs`: real static pages and React development
  hydration/StrictMode/remounts; requires Playwright in reports/analytics-browser and
  the origin/main static export in reports/analytics-baseline/web/out.
- `node tests/test_estate_batches.cjs`: existing batching/price/area/sort behavior.
- `npm run typecheck`; `STATIC_EXPORT=1 NEXT_PUBLIC_API_URL='' npm run build`.
- SQL parsed with pglast locally; production PostgreSQL execution is intentionally
  not performed. Supabase RLS/privileges must be checked with the validation SQL.

The existing coordinate/boundary test scripts used URL.pathname as a filesystem
path, yielding `C:\\C:\\...` on Windows. They now use fileURLToPath; product
coordinate/boundary helpers are unchanged. Python tests run in UTF-8 mode on Windows.

Known pre-existing test failures reproduced against untouched origin/main:
three freshness assertions and one missing naver_calls field in test_golf_freshness;
two old data/Streamlit source assumptions in test_golf_master_adapter; one old
Streamlit route assertion in test_golf_service_pool. These seven failures are
outside analytics and were not hidden by changing product data or assertions.

Final Python result: 1,007 tests, 998 passed, 7 pre-existing failures/errors, 2 skipped
because optional official polygon review artifacts are absent. The 18 new analytics
tests passed. Reliability, Golf latest-request-wins/distance transitions, all 122
coordinate preservation cases and available polygon safety checks passed. Typecheck,
production static build, frontend transport tests and SQL parsing passed.

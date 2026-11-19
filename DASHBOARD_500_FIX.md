# AMORAP /api/admin/data — isolated dashboard recovery

Apply these files to the project root containing `server.py`, preserving `.env`, `.git`, the deployed Vercel entry point and existing database. The source archive does not include that entry point, so verify the production route actually imports this server implementation. Do not reset the database or replace saved settings. No new SQL is needed for this code change. The earlier additive repair SQL remains separate if the logs specifically show missing tables or settings.

## What changed
- Dashboard reads each setting, reservation list and message list inside its own SQL savepoint. A failed query or malformed stored data cannot abort subsequent reads on a functioning connection. The failed section is omitted, not replaced by an empty list; the response includes a `sectionErrors` object and section reference. A failed database connection still returns an error rather than pretending the data loaded.
- The UI shows a dedicated error for an unavailable section, keeps the other tabs accessible, and does not offer save controls for the unavailable data. Rendering failures are isolated too. Authentication, server-side sessions, CSRF checks, existing revision checks and the public booking API are retained.
- The endpoint and admin responses include `X-AMORAP-Dashboard-Release: 20261119-dashboard-isolation-1`. The data response includes `release` with the same value. The asset URL is cache-busted. The session protocol version is intentionally unchanged, so existing cookies remain valid.
- Runtime logs include a reference, section, exception class, SQLSTATE (when provided by PostgreSQL), and safe stack frame locations. No raw exception text, credentials or guest records are logged by this new diagnostic code.

## Verify deployment
1. `git add .`, commit, `git pull --rebase origin main`, `git push origin main`.
2. Confirm Vercel production deployment uses that commit and the actual API runtime is updated; reload admin.
3. In browser DevTools > Network > `/api/admin/data`, check status, Response and `X-AMORAP-Dashboard-Release`. A 200 with nonempty `sectionErrors` is a partial recovery, not a complete fix. Do not send customer data or cookie values.
4. If the response still returns 500, go to Vercel project Logs, reproduce the failure, filter `/api/admin/data`, and inspect the exception/stack. Search `AMORAP dashboard` or `AMORAP error`. A missing release header is a clue (not proof) that an older/different backend is handling the request. Send the error class, SQLSTATE, safe stack locations and reference only.

## QA
- `python -m py_compile server.py`; `node --check public/assets/admin.js`: passed.
- `python tests/qa_dashboard_recovery.py`: passed, including missing settings, invalid JSON, missing messages table, invalid message payload, recovery and saves to healthy settings.
- `python tests/qa_admin.py --browser`: passed local HTTP tests with SQLite adapter and actual Chromium DOM controls via a fetch bridge; includes healthy-tab navigation during failed service load, save controls absent for failed section, recovered tab, room/service/extra/bank changes, bookings and public catalog.
- `python tests/qa_sessions.py --tls`: passed HTTP and HTTPS cookie jar tests.
- No live PostgreSQL, authenticated production request, Vercel runtime or GitHub repository access was available. Savepoint SQL and the error isolation were tested on the SQLite adapter, not a real PostgreSQL connection. This is a defensive fix for the supplied source, not a confirmed root-cause diagnosis of the deployed 500.

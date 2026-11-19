# AMORAP — admin quality assurance
19 November 2026 | Admin reliability update

## Findings and corrections
- Previously, a successful login followed by an unsuccessful dashboard request returned the user to the sign-in screen. Startup session checks also treated all errors as signed-out. The updated dashboard makes loading, authenticated, retry, and expired-session states distinct.
- Overlapping UI requests and a second read after saving could make edits appear unsaved or lose their display state. Save handlers now use the committed response, serialize operations, preserve drafts on failure and detect stale settings revisions.
- The session cookie has a unique AMORAP name, a restricted admin API path, HttpOnly and SameSite=Lax. Sessions remain database-backed with a fixed 24-hour lifetime. Secure mode is required on production HTTPS. Existing staff need to sign in once after applying this update.
- Bank fields may all be cleared to disable new payments. Partial bank account settings are rejected. Previous booking payment instructions are immutable snapshots.
- Restaurant cards are updated/hidden consistently when a service is changed between event and dining types. Guest scripts and admin scripts use an updated version query to avoid stale cached code.

## Results on the isolated test environment
| Area | Result |
|---|---|
| Login, wrong credentials, session recovery, expiry and logout | Pass — HTTP integration and offline Chromium DOM |
| Simulated database outage, dashboard retry after login, save retry and unsaved draft recovery | Pass — HTTP / DOM |
| Villa fields, new villa, delete, rate, capacity, inventory, visibility and review | Pass — HTTP / DOM |
| Photo upload, public serving, cover selection, removal and invalid upload | Pass — HTTP / DOM |
| Extras and event/dining catalog CRUD | Pass — HTTP / DOM |
| Bank save/clear, incomplete account rejection, historic account snapshot | Pass — HTTP / DOM |
| Reservation and transfer reference, confirm, cancel, invalid transitions and conflict check | Pass — HTTP / DOM |
| Contact inbox and reservation filtering | Pass — HTTP / DOM |
| Concurrent stale settings edit, unauthorized access and missing CSRF | Pass — HTTP |
| Public villa, event and dining names and booking buttons after admin edits | Pass — offline DOM with local API bridge |
| Ten page routes, source file access denied | Pass — HTTP |
| Python compilation and JS syntax | Pass |
| Real Supabase, hosted browser cookie transport, live deployment, actual payment | Not tested |

The test suite uses the actual Python HTTP application with a disposable SQLite adapter. It does not run the PostgreSQL startup migration or PostgreSQL advisory lock implementation. Browser navigation was blocked by the environment. Chromium executed the actual dashboard and public page scripts using a fetch bridge into the HTTP application and emulated cookie handling. No live customer records or real bank data were used. No live deployment was made. Tests do not establish that the client's DNS, Supabase credentials, hosting or HTTPS proxy are working. There is no automatic bank payment verification. Uploaded photos removed from a catalog are no longer displayed; the underlying photo record is retained (not garbage-collected) so edits do not destroy stored data unexpectedly.

## Live acceptance checklist (on the deployed site)
1. Keep one canonical HTTPS domain; sign in once, refresh, switch tabs and open admin again. Verify the same session is retained. Sign out, refresh and verify that sign-in is required. Check the cookie is present and Secure on HTTPS.
2. Change one villa price/description and save. Refresh the admin and public villa page, verify the change, then restore the original values. Test a room photo upload and its public display.
3. Edit an event and dining service, an extra and the bank instructions; save and refresh each. Approve real rates and capacity only after owner review. Do not substitute QA bank details into production.
4. With owner-approved test data or a staging database, complete checkout, submit a test payment reference, verify it in admin, confirm and cancel the test booking. Confirm that availability is released. Production transfers must be verified independently by the resort.
5. If a request fails, capture the HTTP status in DevTools and server logs without passwords or cookies. 401 means session invalid; 503 indicates a database/backend availability issue, not an incorrect admin password. 403 may indicate a CSRF or forwarded-host problem. Check environment variables and Supabase connection before changing SQL or credentials.

Run `python tests/qa_admin.py` for a repeatable local HTTP QA pass. Use `--browser` for the offline interaction tests when Playwright and Chromium are installed. Set QA_CHROMIUM to the local Chromium executable if needed.

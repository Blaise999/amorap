# AMORAP Easy Admin — Local QA

- Redesigned primary navigation: Rooms & prices, Bookings, Payment options; Events & dining / Extras / Messages under More.
- Room editor opens from a list showing its nightly price. Essential name, rate, inventory, capacity and photos are first; advanced details are collapsed.
- New room and nightly price can be created and saved using Save room.
- Room photos still use the existing Supabase-backed upload endpoint. Deletion, cover photo and room deletion controls are preserved.
- Payment admin has separate local-bank and GCash cards. Guest checkout offers both when configured; no dummy bank or GCash details are supplied.
- The version string for the Python backend and admin JavaScript is synchronized to prevent mixing releases.

## Test evidence (isolated database / mocked browser API)

- `python tests/qa_admin.py`: PASSED — authentication, sessions, edit/add/delete villas, uploads, extras/events, reservations, bank settings, invoice states and access protection.
- `python tests/qa_sessions.py`: PASSED — HTTP cookies, session refresh, invalid origin and logout.
- `python tests/qa_dashboard_recovery.py`: PASSED — database section failures and safe recovery.
- `python tests/qa_photo_uploads.py`: PASSED — upload and serving, invalid URL validation, size limits.
- `python tests/qa_delete_now.py`: PASSED — delete room, image, service and extra without overwriting reservations.
- `python tests/qa_easy_admin_ui.py`: PASSED — browser edit/save price, add/save room, bank and GCash setup, advanced tabs and no JS errors.
- `python tests/qa_payment_flow.py --browser`: PASSED — browser date-first booking and both selectable payment methods with their own instructions.

**Not checked:** actual Supabase connection, production Vercel deployment, actual payment receipts, mobile-device browser compatibility on the customer's phone. These require validation on the deployed site.

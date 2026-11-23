# Easy Admin update — 20 November 2026

The AMORAP dashboard now has three main actions: **Rooms & prices**, **Bookings**, and **Payment options**. Other features (Events & dining, Extras, Messages) are under **More sections**.

**Adding a room:** Admin → Rooms & prices → **+ Add room** → enter name, nightly price in PHP, number of rooms and guest capacity → optionally upload photos → tick **Price and availability checked** when correct → **Save room**. Use the same screen to change prices. **More room details** includes policies, descriptions and amenities. The **Save room** action also saves any other pending room edits visible in the list.

**Accepting two payment methods:** Admin → Payment options. Enter the local bank name, account holder and account number, plus GCash account holder and mobile number. Click **Save payment options**. The guest checkout lists **Local bank transfer** and **GCash** separately. Each option becomes selectable only when its respective real account details are complete. Never enter placeholder account numbers to simulate payment availability.

**Installation:** Copy this update into the existing `amorap_repaired` folder. Keep `.env` and `.git` untouched. You must deploy the updated `server.py`, `public/admin/index.html`, `public/assets/admin.js` and `public/assets/styles/booking.css` **together**, since the new UI checks the server release version. No Supabase migration is required. Redeploy Vercel and refresh the admin page.

**Tests:** `python tests/qa_admin.py` for backend regressions; `python tests/qa_easy_admin_ui.py` for the new admin browser interface; `python tests/qa_payment_flow.py --browser` for guest checkout. Tests use isolated test data and do not update live Supabase.

**Limitations:** No production login, payment transfer or live Supabase/Vercel end-to-end connection was tested in this environment. These are manual transfer methods, not instant payment processing. The owner must configure real payment accounts before both can accept bookings.

---

# AMORAP — connected direct-booking website

A cleaned, connected version of the uploaded project. Python 3.10+ / Supabase PostgreSQL; no original Next.js application or third-party booking integration is needed. All public pages live in `public/`; the private backend, SQL, seed data and environment configuration remain outside this web root.

## 1. Start locally (Windows PowerShell)

Extract this ZIP into a **new, empty folder**. Open PowerShell in `amorap_repaired` (where `server.py` is located).

```powershell
python -m pip install -r requirements.txt
python server.py --preview
```

Open http://127.0.0.1:8000/. Preview serves the existing content and starter villa catalog; it deliberately disables reservation creation, payment, contact submission and admin actions. Stop it with Ctrl+C before starting the connected version. Illustrative starter rates are displayed; no demo funds or fake reservations are created.

## 2. Connect your existing Supabase project

1. In the project dashboard, open **SQL Editor → New query**. Paste `supabase_setup.sql` and run it. It creates or reuses only the `amorap_booking` schema and does not overwrite existing hotel settings or touch other schemas.
2. Click **Connect → Session pooler** and copy the actual connection string. Replace its password placeholder with your database password; percent-encode any reserved URL characters in the password. Do not use `postgres.xxxxx` or the example host.
3. From the project directory:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `AMORAP_DATABASE_URL` to the copied URL, set `AMORA_ADMIN_USER` and a unique `AMORA_ADMIN_PASSWORD` of at least 12 characters (20+ recommended). Save the file. Keep it private. Then:

```powershell
python server.py
```

The server reports connection and setup problems without printing your password. It fails closed if there is no valid database configuration. No SQLite is used in the production application.

## 3. Configure the resort

Go to http://127.0.0.1:8000/admin/ and sign in with the credentials you chose.

- **Villas:** set the real nightly rate (PHP), inventory, capacity, name, category, photos, bed, size, amenities, description, policy and visibility for each villa. Save all villas. Add or remove room types as needed. The four supplied room variants have example rates, capacity and inventory. Verify each villa, check its review checkbox and save before it can accept reservations.
- **Extras:** add the approved meals, activities or other add-ons, pricing per stay or night, and visibility. Save.
- **Bank transfer:** enter the verified resort-authorized bank, account holder, account number and payment instructions. Save. Guests receive the details after creating a reservation. Updated details apply only to new bookings.
- **Reservations:** review submissions and payment references; only confirm a reservation after independent verification of the transfer in the authorized resort bank account. Cancellation releases the held inventory.
- **Messages:** view messages from the contact and careers forms. No external messaging/email provider is configured.

## 4. Connected pages

| Route | Function |
|---|---|
| `/` | Home, supplied hero video, immediate booking modal |
| `/villas/` | Live admin-managed villa catalog |
| `/restaurant/` | Restaurant information and direct dining reservations |
| `/events/` | Event information and direct event reservations |
| `/contact/` | Contact and topic-prefilled inquiry form |
| `/about/` | Park overview, links to villas, dining and events |
| `/careers/` | Internal careers inquiry; no invented vacancies |
| `/booking/` | Direct booking entry and live catalog |
| `/checkout/` | Checkout drawer and last reservation access |
| `/admin/` | Staff login and administration |

The shared header, footer, mobile menu and booking drawer are consistent on public routes. The guest selects dates, quantity and guests, adds rooms and optional extras, and goes to checkout using the right-side bag icon. Cart data is retained during same-tab navigation. The backend recalculates prices and checks availability rather than trusting browser totals. A created reservation holds inventory for 24 hours; payment references move it to manual review. No external booking or checkout links remain. Unverified room photos/prices must be supplied by management. The original supplied hero video is served locally with a poster image and pause control.

## 5. GitHub and hosting

The archive excludes `.env`, old `.git` history, external widget captures, long filenames and temporary data. `.env.example` contains placeholders only. If the GitHub repository is empty, initialize and push:

```powershell
git init
git add .
git commit -m "Connect AMORAP pages and direct booking"
git branch -M main
git remote add origin https://github.com/Blaise999/amorap.git
git push -u origin main
```

If the repository already contains a commit, clone it first, replace its tracked application files with this project's files (keep the clone's `.git` directory), then commit and push normally. Do not force-push or merge this archive into the old captured site. Never commit `.env`. If a password has already been published, rotate it and coordinate the update with other websites that share it.

The server requires a Python-capable persistent host. It is not a static-only deployment or a drop-in Vercel application. For production, use HTTPS through a properly configured reverse proxy, secure cookies (`AMORA_SECURE_COOKIE=1`), environment secrets, rate limits, backups and a review of the resort's real payment, inventory and privacy policies. Do not expose Python's basic HTTP server directly to the internet. The default host is local-only. Shared-project schema isolation prevents naming collisions but is not the same as security isolation; use a restricted database role where possible. Do not expose the `amorap_booking` schema via the public Supabase APIs. Keep the project's owner database connection secret.

## Verification and limitations

All 10 page URLs and runtime assets returned HTTP 200 in a local server test. Local href/src/poster references, Python and JavaScript syntax passed checks. A temporary test database adapter (not part of the delivered app) was used to exercise admin settings, quote totals, inventory enforcement, reservation creation, transfer reference, confirmation, cancellation and contact messages. Preview correctly rejects booking writes and private source paths are not served. Actual Supabase connectivity was not verified: the uploaded `.env` had an example URL, not a usable connection string. Chromium navigation was blocked by the execution environment, so visual rendering and client-side interactions need local desktop/mobile verification. The supplied About and Careers files were broken captures; they have been rebuilt with available park information and contact actions, not invented business details. Real prices, availability and authorized bank details remain for management to configure.

## Catalog restoration update

- Replace the old project files with this version, keeping your real `.env` locally. The schema stays `amorap_booking`.
- On startup, a one-time migration adds bundled resort imagery to the four original room IDs only if they have no photos. Existing rates, descriptions, reservations, bank details and other edits are preserved. The same migration is available as `villa_catalog_upgrade.sql`; running it again is harmless. If you have never run the initial SQL, run `supabase_setup.sql` instead.
- Villa content is rendered immediately from a built-in catalog, then replaced with the live admin-saved catalog when the API responds. If offline, the original starter content remains visible and guests can build draft carts only: no fake availability or payment.
- The original ZIP has the two villa descriptions and Single/Double labels, but its old site fetched exact room photos, rates, inventory and other details from a database that was not supplied. Included category photos are the resort grounds capture and an ocean-villa exterior frame extracted from the supplied hero video, explicitly labeled as resort setting, not verified individual room photographs. Replace with the exact room photos in the dashboard when available.
- Keep the Supabase database URL private. A static-only host cannot run the Python booking API. Use the Python server for live edits and reservations.

## Starter pricing update

Example nightly rates: Inland Single PHP 4,500; Inland Double PHP 6,500; Ocean Single PHP 7,500; Ocean Double PHP 9,500. All amounts in the database are integer centavos. Example capacities are 2/4 and inventory is one per villa type. All example villas require explicit admin verification before booking. Sample extras are disabled. Existing non-null rates and existing nonempty extras are retained, and bank details and reservations are never changed. `starter_catalog_upgrade.sql` runs once automatically on server startup (or run it manually in Supabase SQL Editor after initial setup). Keep the `.env` and `.git` in your existing project.

## Unified direct booking update

Villas (Single/Double), dining and event packages now use the same reservation cart and bank-transfer checkout. Dining and events may be booked without a villa; they use a separate requested date, time and guest count. The existing `amorap_booking` schema and reservation table are unchanged. Restart the Python server with your real `.env`; initialization inserts the `services` setting only if absent, so existing rates, bank details and reservations are preserved. For a new database, run `supabase_setup.sql` as usual.

The Events & dining tab in admin includes starter rates and capacities (private event package PHP 25,000, maximum 50 guests; each dining venue PHP 380/person, daily capacity 20). These capacities and event rates are examples, not confirmed facts. The admin must review the packages, operating hours, prices, capacities and bank details before enabling live bookings. The model reserves one event across the resort per date, and a conservative shared daily seat capacity for each dining venue; requested times are confirmed by staff. Room availability is still checked per night. Assumed prices and unverified options support draft carts and estimates only: the server will not accept a reservation until the selected products are verified. No payment is requested during offline preview.

Tests: backend quote/validation unit tests with in-memory settings and reservation records; Chromium offline DOM tests with mock catalog for villa selection, event/dining forms and mixed cart; Python/JS syntax and internal file links. The environment prevented browser navigation to localhost; the actual hosted site and Supabase connection were not tested.


## Admin reliability and QA update — 2026-11-19

Apply the patch over the existing project root (the folder containing `server.py`). Keep `.env`, `.git`, the existing schema and customer records. Restart/redeploy the Python backend and public files together because the admin now expects revision-aware save responses. No migration or database reset is required if the original schema was already installed. Sign in once after deployment: the session cookie has a new AMORAP-specific name, is host-only and is scoped to `/`. Sessions have a rolling 24-hour window while the dashboard is open and connected, and still expire server-side. Use one canonical HTTPS hostname in production, set `AMORA_SECURE_COOKIE=1`, and configure your reverse proxy to forward the original public Host header. For localhost HTTP only, leave the secure-cookie setting at 0. Never mix local and hosted URLs when testing session continuity.

A database/API outage no longer sends the administrator back to login. The dashboard provides a retry action; unsaved edits are kept in the open page, including when a genuine expiry requires signing in again. Do not close/reload the page with unsaved changes. Concurrent save requests are blocked in the UI, and obsolete revisions are rejected rather than overwriting another editor's newer data. Saving settings updates the public catalog on the next catalog load, not a push to already-open pages. Bank fields can be cleared together to pause new payments; existing reservations retain the account details that were recorded when they were created. Actual transfers still require independent staff verification.

Run the isolated QA suite with `python tests/qa_admin.py`. It uses a disposable SQLite test adapter, not the real Supabase database. Optional offline Chromium DOM tests: install Playwright and Chromium locally, point `QA_CHROMIUM` to the Chromium executable and run `python tests/qa_admin.py --browser`. The test harness replaces browser fetch with a bridge to the real local Python HTTP handlers and emulates cookie transport because browser navigation was blocked in this environment. See `QA_REPORT.md` for results and hosted-site acceptance checks.


## Admin session reliability update — session3

Apply this patch to the project root, preserving `.env`, `.git`, and the existing Supabase schema. Restart/redeploy the Python backend and `public/` files together. The new cookie name is `amorap_admin_v3`; existing staff must sign in once. No new SQL or password reset.

- Login verifies that the browser returns the HttpOnly session cookie before revealing the dashboard. A structured message distinguishes missing cookies, revoked/expired sessions, upstream errors, and outdated backend versions.
- A visible dashboard checks the session every five minutes and on focus return. A successful check renews the database expiry and cookie when at least one hour has elapsed. The session remains valid for up to 24 hours after its last renewal; inactivity beyond that still requires login. It is not an unlimited login.
- All admin API responses and the admin script are non-cacheable. A proxy 401 or temporary database failure alone does not sign out staff. State-changing actions are retried only after explicit pre-mutation auth/CSRF rejection and successful session validation. No access token is placed in localStorage.
- For HTTPS production set `AMORA_SECURE_COOKIE=1` and optionally `AMORA_PUBLIC_ORIGIN=https://your-actual-website.example` (the exact canonical public origin, no path; replace the example). Leave `AMORA_PUBLIC_ORIGIN` unset and `AMORA_SECURE_COOKIE=0` for localhost HTTP. The proxy should forward the original Host, `X-Forwarded-Proto`, `Cookie`, `Set-Cookie`, `Origin` and `Sec-Fetch-Site`; do not cache `/api/admin/*` or the admin page. Use the same hostname throughout, not mixed www/non-www, HTTP/HTTPS or a separate static frontend.
- If login is accepted but the session cookie isn't returned, check the browser's Network panel for a `Set-Cookie` on POST `/api/admin/login` and the matching Cookie on GET `/api/admin/session`. Do not share cookie or CSRF values. If the API reports an outdated backend, redeploy both server and assets.

QA: `python tests/qa_admin.py` and `python tests/qa_sessions.py`. Optional `python tests/qa_sessions.py --tls` uses OpenSSL to generate a disposable local certificate. Optional `python tests/qa_admin.py --browser` runs offline Chromium DOM coverage. See `SESSION_QA.md` for the scope and limitations.

## Date-first booking and two payment choices — 2026-11-20

The booking journey now asks for **check-in and check-out dates first**, before showing villa choices. Direct Book buttons on the villas page also request dates before opening that villa's quantity and guest form. The dates are shared across all villas in the cart and can be changed before checkout. Event/dining reservations continue to use their own date, time and party-size forms.

At checkout the guest chooses **Local bank transfer** or **GCash**. The resort administrator configures each independently under **Admin → Payments**. Both options are visibly listed; an option is disabled until its verified account details have been saved. Existing bank settings remain intact. No dummy account numbers or automatic payment verification have been added. Customers receive the instructions and account for only their selected method after placing a reservation and enter a transaction reference for staff to review. Past reservations retain the payment account and method saved when booked. Manual payment confirmation is still required.

This upgrade adds optional keys (`gcashName`, `gcashNumber`, `gcashInstructions`) to the existing `amorap_booking.settings` payment JSON. **No new SQL migration or schema changes** are required, and previous settings are preserved. Old clients may keep using bank-only reservations while only the bank option is configured. Ensure the deployed Python backend and `public/` assets are redeployed together, then open the admin Payments tab to enter the resort's real GCash mobile number and name. Keep `.env` outside Git.

Isolated QA commands:

```powershell
python tests/qa_admin.py --browser
python tests/qa_dashboard_recovery.py
python tests/qa_payment_flow.py --browser
```

The suites use disposable SQLite test adapters and Chromium DOM tests, never production Supabase credentials or real financial transactions. Production database, hosting/cookie behavior and actual bank/GCash payments still require owner verification.


## Admin photo upload (Villas / Events & Dining)

In `/admin/`, open **Villas** or **Events & dining**, expand an item, and use its **Upload pictures** input. Choose one or more images from a phone or computer (JPG, PNG, WebP, or browser-supported HEIC). The browser optimizes each photo before uploading it (up to 1.5 MB stored image); **Save all villas** or **Save all services** to publish the new gallery. The first photo is the public cover; choose **Make cover** to change it. Remove a picture and save to unpublish it. Other edits and reservations are preserved.

Uploads go through authenticated `/api/admin/upload` and are stored in the existing private `amorap_booking.photos` table; the catalog stores URL references. `/api/photo/<name>` serves new uploads via the same `/api` backend that supports bookings; legacy `/uploads/<name>` links remain supported when routed to Python. The database schema must have been initialized with `supabase_setup.sql`, including the `photos` table. Existing installations with that table need **no new SQL**. Do not deploy only `public` to Vercel; its `/api` and `/uploads/` routes must reach the Python backend. If the deployment routes `/api/*` to Python, new photo URLs require no separate `/uploads` rewrite.

## Deleting rooms, events, extras and pictures

The Admin dashboard displays **Delete villa**, **Delete service**, and **Delete extra** buttons directly on each saved row. These are immediate, confirmed server-side deletions and do not require another **Save all** click. Individual gallery images have **Delete photo** buttons. Uploaded image bytes are removed from Supabase only when no other saved catalog item uses them. For unsaved content the button says **Discard draft**. Save or discard any other pending edits before an immediate deletion. Reservation history remains intact.

For deletion API, photo upload and browser regression checks see `DELETE_AND_UPLOAD_QA.md` and `tests/qa_delete_now.py`. Existing tables are reused; no new SQL required.


## November 2026 deployment and security fixes

- Never commit `.env`. A previous version was tracked publicly and credentials stored in it must be rotated. Deleting the file from the current branch does not erase the historical commit.
- Vercel routes `/api/*` through `api/index.py`. Use `GET /api/health` to verify that the connected Supabase schema is accessible without exposing its credentials.
- Original villas with no saved price receive a one-time illustrative rate from `seed.json`. This is not published as a bookable room until a resort administrator has verified the rate, guest capacity and room inventory in the dashboard.
- Existing admin-edited rates, bank details, reservations, and uploaded photos are not replaced by the migration.
- The guest booking flow remains unavailable for rooms marked unreviewed, and manual payments must be configured by the hotel owner.


### Payment receipts and first-come booking policy (November 2026)

- Guest chooses a 50% deposit or 100% payment, transfers to the chosen local bank or GCash account, and uploads a JPG/PNG/WebP receipt image. Amounts are in PHP centavos. No transaction-reference field is requested for new bookings.
- Receipt bytes are held in the existing `amorap_booking.photos` table with a separate `receipt-` prefix. They are **not** served via the public photo endpoint; only a signed-in admin can access `/api/admin/receipt/<reservation-id>`.
- Unpaid requests don't hold inventory and don't have a promised 24-hour reservation hold. The admin must verify the receipt amount and current availability before confirming.
- The exact booking policy is shown at checkout and the payment step: "Bookings are strictly first-come, first-served. A 50% or 100% payment is required to secure your reservation. Unpaid bookings are not confirmed and remain subject to availability".
- Existing historical transfer references remain visible to admins; previously confirmed bookings are preserved. No new Supabase table or migration is needed.


### Live room availability per villa type (November 2026)

- **Admin → Rooms & prices → Total rooms of this type (inventory)** controls stock for each villa type independently. Setting 0 prevents new bookings. No SQL migration is required.
- Public villa pages display total rooms per type (not a misleading date-independent availability claim). After the guest selects check-in/check-out, the booking cards and room editor display the **remaining number available across every night of that stay**.
- `GET /api/availability?checkin=YYYY-MM-DD&checkout=YYYY-MM-DD` computes date-specific remaining quantities by subtracting only **confirmed** overlapping reservations. Unpaid/receipt-review requests do not reserve inventory, consistent with the first-come booking policy. The counts are informational and not a guarantee; the server recalculates availability at checkout and admin confirmation.
- A sold-out room type is visibly marked and its booking action disabled for those dates; the quantity selector never allows more than the last verified count. Availability errors are not silently replaced by invented room counts.


## Editable contact details and guest-to-admin live chat (2026-11-23)

- **Admin → Customer care** is the source of truth for the phone number as displayed, a separate tap-to-call number, support email, resort address, optional head-office address, opening hours and greeting. Saving publishes the values on the public Contacts page and footer. Clearing a phone number/address removes the corresponding public contact information.
- The old large fixed **Call customer care** button has been removed. Regular phone links remain available on Contact and in the footer when an administrator supplies a valid number.
- A small **💬 Live Chat** button appears on guest pages. Opening it displays a compact, collapsible conversation. It is hidden while the reservation modal is open, so it cannot cover date fields, pricing or checkout actions.
- **Admin → Live chat** receives guest conversations and can send replies, close/reopen threads and view optional guest email. Both guest and admin clients poll for updates approximately every 8 seconds; this is near-real-time chat, not a guarantee of instant human response or WebSocket push notifications.
- Guest conversations use random 256-bit browser-held bearer tokens, stored only as a SHA-256 hash server-side; the guest token is required for reading or sending messages and never returned in the public catalog. Admin routes require the existing signed-in session and CSRF token to reply or change chat status.
- Chat messages are stored in the existing amorap_booking.messages table as distinct kind: chat payloads; traditional Contact form submissions remain separate. Existing messages and bookings are preserved. No SQL migration or database reset is required.
- Safeguards include server-side limits for message length and conversation length, basic creation rate limiting, HTML escaping in both UIs, and no-store responses. For exceptionally high traffic a shared edge rate limiter may still be useful.

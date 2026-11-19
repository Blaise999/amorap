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

Apply the patch over the existing project root (the folder containing `server.py`). Keep `.env`, `.git`, the existing schema and customer records. Restart/redeploy the Python backend and public files together because the admin now expects revision-aware save responses. No migration or database reset is required if the original schema was already installed. Sign in once after deployment: the session cookie has a new AMORAP-specific name and is scoped to `/api/admin/`. Sessions last 24 hours and still expire server-side. Use one canonical HTTPS hostname in production, set `AMORA_SECURE_COOKIE=1`, and configure your reverse proxy to forward the original public Host header. For localhost HTTP only, leave the secure-cookie setting at 0. Never mix local and hosted URLs when testing session continuity.

A database/API outage no longer sends the administrator back to login. The dashboard provides a retry action; unsaved edits are kept in the open page, including when a genuine expiry requires signing in again. Do not close/reload the page with unsaved changes. Concurrent save requests are blocked in the UI, and obsolete revisions are rejected rather than overwriting another editor's newer data. Saving settings updates the public catalog on the next catalog load, not a push to already-open pages. Bank fields can be cleared together to pause new payments; existing reservations retain the account details that were recorded when they were created. Actual transfers still require independent staff verification.

Run the isolated QA suite with `python tests/qa_admin.py`. It uses a disposable SQLite test adapter, not the real Supabase database. Optional offline Chromium DOM tests: install Playwright and Chromium locally, point `QA_CHROMIUM` to the Chromium executable and run `python tests/qa_admin.py --browser`. The test harness replaces browser fetch with a bridge to the real local Python HTTP handlers and emulates cookie transport because browser navigation was blocked in this environment. See `QA_REPORT.md` for results and hosted-site acceptance checks.

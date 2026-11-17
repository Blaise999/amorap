# AMORAP — connected direct-booking website

A cleaned, connected version of the uploaded project. Python 3.10+ / Supabase PostgreSQL; no original Next.js application or third-party booking integration is needed. All public pages live in `public/`; the private backend, SQL, seed data and environment configuration remain outside this web root.

## 1. Start locally (Windows PowerShell)

Extract this ZIP into a **new, empty folder**. Open PowerShell in `amorap_repaired` (where `server.py` is located).

```powershell
python -m pip install -r requirements.txt
python server.py --preview
```

Open http://127.0.0.1:8000/. Preview serves the existing content and starter villa catalog; it deliberately disables reservation creation, payment, contact submission and admin actions. Stop it with Ctrl+C before starting the connected version. No demo funds, room rates or fake reservations are used in the delivered site.

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

- **Villas:** set the real nightly rate (PHP), inventory, capacity, name, category, photos, bed, size, amenities, description, policy and visibility for each villa. Save all villas. Add or remove room types as needed. The four supplied room categories have no verified pricing or inventory; these must be entered before they can accept reservations.
- **Extras:** add the approved meals, activities or other add-ons, pricing per stay or night, and visibility. Save.
- **Bank transfer:** enter the verified resort-authorized bank, account holder, account number and payment instructions. Save. Guests receive the details after creating a reservation. Updated details apply only to new bookings.
- **Reservations:** review submissions and payment references; only confirm a reservation after independent verification of the transfer in the authorized resort bank account. Cancellation releases the held inventory.
- **Messages:** view contact, event, dining and careers inquiries. No external messaging/email provider is configured.

## 4. Connected pages

| Route | Function |
|---|---|
| `/` | Home, supplied hero video, immediate booking modal |
| `/villas/` | Live admin-managed villa catalog |
| `/restaurant/` | Restaurant information and internal dining inquiry |
| `/events/` | Event information and internal event inquiry |
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

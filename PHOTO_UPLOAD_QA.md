# AMORAP — Admin Photo Upload QA

## Changes

- Admin can choose multiple photographs from phone or desktop in Villas and Events & dining.
- Browser resizes/optimizes images for serverless upload size limits; JPG, PNG, WebP, and browser-supported iPhone photos accepted as source.
- Authenticated POST `/api/admin/upload` stores JPEG or WebP images in the existing `amorap_booking.photos` PostgreSQL table, not Vercel's ephemeral filesystem.
- Uploaded photos use `/api/photo/<generated-id>` so images resolve through the same `/api` backend as reservations; old `/uploads/<generated-id>` image links still work when those requests reach Python.
- Gallery supports cover selection, removal, thumbnails and save to publish.
- Event cards, bookable dining cards and the original three restaurant cards use the chosen images if configured.
- Existing villa images and saved services (including those without an `images` field) are preserved. No new database structure is needed if `amorap_booking.photos` exists.

## Tests performed locally

- Python source compiled, admin and guest JS pass `node --check`.
- Full admin isolated API + Chromium UI suite passes, including upload picker, duplicate and invalid photo handling, villa/service edits and publishing.
- Photo-specific API test passes: upload, retrieve through `/api/photo`, save to event and dining, publish and remove, reject foreign URLs, invalid auth, oversized images.
- Existing booking/payment/session QA passed before packing.

## Not tested on live infrastructure

- Actual production Supabase credentials, admin login, Vercel deployment routing and customer devices were not accessible. Check image GET request returns 200 after upload and save in production.
- If the `photos` table is missing, apply `photo_storage_check.sql` once in the correct Supabase project.
- A brand-new admin/backend version may require the owner to sign in again after the deployment.

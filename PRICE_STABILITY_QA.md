# AMORAP: Stable room prices and admin price saves

## What was changed

- **Guest booking:** Shows the selected villa's nightly rate on the dates step, the room/guest form and total during the cart and checkout loading transitions. Rates no longer disappear behind an empty loading state.
- **Rate integrity:** The booking selection waits for the API's live catalog before displaying bookable choices, rather than briefly flashing sample/default prices and then replacing them. When a previously loaded live catalog has a network interruption, the page marks rates as stale and disables final payment instead of silently replacing them with sample prices.
- **Change detection:** The cart uses the server's real quote for the verified total and explicitly warns when it differs from the on-page estimate. The booking endpoint still refuses a stale `expectedTotal`.
- **Admin:** The nightly price preview updates as the admin types. Saving a room keeps the editor open, shows the saved price, and reports success, instead of collapsing the entire editing section.
- **Cache:** New asset query strings on all public pages and synchronized admin/backend release IDs so stale JavaScript will not be silently mixed with new backend output.
- **Payments:** Existing separate GCash and local-bank choices are unchanged.

## Test results (isolated local environment; no production writes)

- `python tests/qa_price_stability.py` — PASS: real Chromium UI for date-first booking, room selection, cart loading, checkout, direct villa booking and admin price save without collapse.
- `python tests/qa_price_api.py` — PASS: admin saves PHP 8,175.00, a different client receives it from the public catalog, two-night server quote returns PHP 16,350.00.
- `python tests/qa_admin.py` — PASS: backend authentication, editing rooms, admin/photo operations, reservation controls.
- `python tests/qa_sessions.py` — PASS: session cookies and renewal.
- `python tests/qa_dashboard_recovery.py` — PASS: section-by-section dashboard error recovery.
- `python tests/qa_delete_now.py` — PASS: immediate deletion of rooms, photos, services and extras.
- `python tests/qa_photo_uploads.py` — PASS: uploading and serving photos.
- `python tests/qa_easy_admin_ui.py` — PASS: browser admin edit/save/add room and payment details.
- `python tests/qa_payment_flow.py --browser` — PASS: date-first booking and two payment methods.

## Deployment

For the **patch ZIP**, extract into the **existing Git project root** (the folder containing `server.py`), overwriting the corresponding files; don't overwrite `.git` or `.env`.

```powershell
git add .
git commit -m "Keep room prices visible through booking and admin saves"
git pull --rebase origin main
git push origin main
```

Redeploy the Python backend and static assets together. No SQL migration is required. After deployment, hard-refresh both `/villas/` and `/admin/`, change one nightly price, save, refresh, and verify the public listing and checkout. Real Supabase/Vercel tests were **not** possible here without production access. Production booking remains subject to actual inventory and successful API connection.

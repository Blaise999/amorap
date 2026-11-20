# AMORAP — Room, gallery and catalog deletion QA

## Owner workflow

1. Open **Admin → Villas**, select **Add villa**, enter the name, price, capacity and inventory, upload photos, then **Save all villas**. The public Villas page reads the saved catalog.
2. Every saved villa has a visible **Delete villa** action on its row, without needing to expand the editor. Confirm to delete immediately. There is no subsequent Save step. Historical reservation records are retained.
3. Open a villa or event/dining editor to view its picture gallery. **Delete photo** removes a saved photo immediately from that public listing. **Make cover** changes the photo order only after **Save all**.
4. **Events & dining** and **Extras** also show immediate **Delete service** and **Delete extra** actions. New, unsaved items instead show **Discard draft**.
5. A newly uploaded photo can be discarded before the entire villa/service is saved. Unreferenced uploaded image bytes are deleted from `amorap_booking.photos`.

## Safety behavior

- Each delete requires user confirmation.
- Deletions use a database revision (`If-Match`); concurrent changes return 409 and are not overwritten.
- Editing a saved item while other unsaved changes exist requires saving or discarding those changes before immediate deletion. No silent loss of form drafts.
- Confirmed and historical reservations cannot be deleted from the catalog editor. Reservation status remains managed through the existing Confirm/Cancel buttons.
- Uploaded image bytes are deleted when no longer used in any saved room, event or dining gallery; shared uploads are retained until the final reference is removed.
- Bundled resort photographs are not deleted from disk, only unlinked from the public catalog.
- DELETE requests require an authenticated admin session, matching CSRF token and same-site request origin.
- No SQL migration is required if the existing `amorap_booking.settings` and `amorap_booking.photos` tables already exist.

## Local tests run

- `python tests/qa_delete_now.py` — actual HTTP routes: add/publish a villa and upload, delete saved room, delete saved image, shared-photo lifecycle, invalid/expired revision, CSRF/authentication, deleting services/extras, photo discard.
- `python tests/qa_admin.py --browser` — admin Chromium DOM: sign in, save, image upload, persisted photo delete, immediate villa/service/extra delete, reservation management, public catalog, failure recovery.
- `python tests/qa_dashboard_recovery.py`, `python tests/qa_payment_flow.py`, `python tests/qa_sessions.py`, `python tests/qa_photo_uploads.py` — existing regression coverage.
- `node --check public/assets/admin.js`, `python -m py_compile server.py` — syntax validation.

These tests use an isolated SQLite adapter and a local HTTP handler for QA. Production Supabase and live Vercel routing, cookies, and images were not accessible from the test environment and have not been verified here.

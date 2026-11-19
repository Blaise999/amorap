-- Optional, safe repair: only the AMORAP private photos table.
-- Use in Supabase SQL Editor only if uploads report a missing photos table.
-- Existing images, villas and reservations are not changed.
BEGIN;
CREATE SCHEMA IF NOT EXISTS amorap_booking;
CREATE TABLE IF NOT EXISTS amorap_booking.photos (
 name text PRIMARY KEY,
 mime text NOT NULL CHECK (mime IN ('image/jpeg','image/png','image/webp')),
 content bytea NOT NULL CHECK (octet_length(content) <= 6000000)
);
REVOKE ALL ON SCHEMA amorap_booking FROM PUBLIC, anon, authenticated;
REVOKE ALL ON amorap_booking.photos FROM PUBLIC, anon, authenticated;
ALTER TABLE amorap_booking.photos ENABLE ROW LEVEL SECURITY;
COMMIT;

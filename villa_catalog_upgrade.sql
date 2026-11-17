-- Apply once to existing AMORAP installs. No other schema or room fields are modified.
BEGIN;
SELECT pg_advisory_xact_lock(1095585618, 20261117);
WITH claimed AS (
 INSERT INTO amorap_booking.settings(key,value) VALUES ('villa_photo_seed_v2','true')
 ON CONFLICT (key) DO NOTHING RETURNING key
), defaults(id,photo) AS (VALUES
('inland-single','/assets/villas/inland-resort.webp'),
('inland-double','/assets/villas/inland-resort.webp'),
('ocean-single','/assets/villas/ocean-resort.webp'),
('ocean-double','/assets/villas/ocean-resort.webp')), restored AS (
 SELECT jsonb_agg(CASE WHEN d.id IS NOT NULL AND COALESCE(r.room->'images','[]'::jsonb) = '[]'::jsonb
                      THEN jsonb_set(r.room,'{images}',jsonb_build_array(d.photo),true)
                      ELSE r.room END ORDER BY r.ord) AS catalog
 FROM amorap_booking.settings s CROSS JOIN LATERAL jsonb_array_elements(s.value::jsonb) WITH ORDINALITY AS r(room,ord)
 LEFT JOIN defaults d ON d.id=r.room->>'id'
 WHERE s.key='rooms'
)
UPDATE amorap_booking.settings SET value=restored.catalog::text FROM restored
WHERE key='rooms' AND restored.catalog IS NOT NULL AND EXISTS(SELECT 1 FROM claimed);
COMMIT;

-- AMORAP only. Fill missing villa rates once; preserve saved rates and all reservations.
-- Starter prices require admin review; sample extras are disabled.
BEGIN;
SELECT pg_advisory_xact_lock(1095585618, 20261117);
CREATE TEMP TABLE IF NOT EXISTS amorap_starter_claim (claimed boolean) ON COMMIT DROP;
WITH claim AS (
 INSERT INTO amorap_booking.settings(key,value) VALUES ('starter_rates_v1','true')
 ON CONFLICT (key) DO NOTHING RETURNING key
)
INSERT INTO amorap_starter_claim SELECT true FROM claim;
WITH defaults(id,price,capacity,inventory) AS (VALUES
('inland-single',450000,2,1),
('inland-double',650000,4,1),
('ocean-single',750000,2,1),
('ocean-double',950000,4,1)
), filled AS (
 SELECT jsonb_agg(CASE WHEN d.id IS NOT NULL AND (r.room->>'price') IS NULL THEN
 r.room || jsonb_build_object('price',d.price,
 'capacity',CASE WHEN COALESCE((r.room->>'capacity')::int,0)=0 THEN d.capacity ELSE (r.room->>'capacity')::int END,
 'inventory',CASE WHEN COALESCE((r.room->>'inventory')::int,0)=0 THEN d.inventory ELSE (r.room->>'inventory')::int END,
 'reviewed',false) ELSE r.room END ORDER BY r.ord) catalog
 FROM amorap_booking.settings s CROSS JOIN LATERAL jsonb_array_elements(s.value::jsonb) WITH ORDINALITY AS r(room,ord)
 LEFT JOIN defaults d ON d.id=r.room->>'id' WHERE s.key='rooms'
)
UPDATE amorap_booking.settings SET value=filled.catalog::text FROM filled
WHERE key='rooms' AND filled.catalog IS NOT NULL AND EXISTS(SELECT 1 FROM amorap_starter_claim);
UPDATE amorap_booking.settings SET value='[{"id": "starter-breakfast", "name": "Breakfast", "description": "Example extra — confirm service and inclusions before enabling.", "price": 45000, "basis": "night", "active": false}, {"id": "starter-airport-transfer", "name": "Airport transfer", "description": "Example extra — confirm route and availability before enabling.", "price": 150000, "basis": "stay", "active": false}, {"id": "starter-room-decoration", "name": "Room decoration", "description": "Example extra — confirm package before enabling.", "price": 120000, "basis": "stay", "active": false}]'
WHERE key='addons' AND value::jsonb='[]'::jsonb AND EXISTS(SELECT 1 FROM amorap_starter_claim);
DROP TABLE amorap_starter_claim;
COMMIT;

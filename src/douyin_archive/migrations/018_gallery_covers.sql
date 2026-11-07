-- Gallery works were recorded without a cover. Scan those creators again so the
-- catalog picks up one; rows and saved covers stay as they are.
UPDATE creators SET catalog_scanned_at=NULL
WHERE catalog_scanned_at IS NOT NULL AND remote_id IN (
    SELECT creator_id FROM creator_catalog_items
    WHERE item_type='gallery' AND cover_url IS NULL
);

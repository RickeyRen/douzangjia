-- 0 pending, 1 saved, 2 given up until a newer cover URL arrives.
ALTER TABLE creator_catalog_items ADD COLUMN cover_state INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS creator_catalog_items_cover_pending
ON creator_catalog_items(item_id) WHERE cover_state=0;

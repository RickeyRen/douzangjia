-- Library scope checks look items up by id across sources; the primary key
-- leads with source_id, so give the reverse direction its own index.
CREATE INDEX IF NOT EXISTS source_items_item
ON source_items(item_id, source_id);

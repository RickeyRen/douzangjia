-- Home shelves count each list's items and its latest sighting; covering both
-- columns keeps that to an index-only read instead of visiting every row.
CREATE INDEX IF NOT EXISTS source_items_recency
ON source_items(source_id, last_seen_at);

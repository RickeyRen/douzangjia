-- Lets the home page totals count items by type and week from the index alone,
-- without reading each item's large metadata JSON from disk.
CREATE INDEX IF NOT EXISTS items_library_counts
ON items(remote_id, item_type, first_seen_at, creator_id);

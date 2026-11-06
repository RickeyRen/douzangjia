-- Every public work of the creators the library holds, kept apart from items:
-- there can be many times more of them, and the library feeds scan items.
-- A creator's rows move into items once Douyin removes the creator.
CREATE TABLE IF NOT EXISTS creator_catalog_items (
    item_id TEXT PRIMARY KEY,
    creator_id TEXT NOT NULL REFERENCES creators(remote_id) ON DELETE CASCADE,
    author_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    item_type TEXT NOT NULL,
    published_at INTEGER,
    duration_ms INTEGER,
    cover_url TEXT,
    source_url TEXT,
    statistics_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS creator_catalog_items_creator
ON creator_catalog_items(creator_id, published_at DESC);

ALTER TABLE creators ADD COLUMN catalog_scanned_at INTEGER;
ALTER TABLE creators ADD COLUMN catalog_item_count INTEGER NOT NULL DEFAULT 0;

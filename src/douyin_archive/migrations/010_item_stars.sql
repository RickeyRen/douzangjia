CREATE TABLE IF NOT EXISTS item_stars (
    item_id TEXT PRIMARY KEY REFERENCES items(remote_id),
    starred_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS item_stars_recent
ON item_stars(starred_at DESC, item_id DESC);

CREATE INDEX IF NOT EXISTS items_published_feed
ON items(COALESCE(published_at, first_seen_at) DESC, remote_id DESC);

CREATE INDEX IF NOT EXISTS items_archived_feed
ON items(first_seen_at DESC, remote_id DESC);

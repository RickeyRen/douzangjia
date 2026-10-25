CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    position INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS album_items (
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    added_at INTEGER NOT NULL,
    PRIMARY KEY(album_id, item_id)
);

CREATE INDEX IF NOT EXISTS album_items_recent ON album_items(album_id, added_at DESC, item_id DESC);
CREATE INDEX IF NOT EXISTS album_items_by_item ON album_items(item_id);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    tag TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(item_id, tag)
);

CREATE INDEX IF NOT EXISTS item_tags_by_tag ON item_tags(tag, item_id);

CREATE TABLE IF NOT EXISTS item_notes (
    item_id TEXT PRIMARY KEY REFERENCES items(remote_id),
    note TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

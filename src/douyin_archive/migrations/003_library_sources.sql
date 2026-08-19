CREATE TABLE creators (
    remote_id TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    unique_id TEXT,
    avatar_url TEXT,
    follower_count INTEGER,
    post_count INTEGER,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL
);

ALTER TABLE items ADD COLUMN creator_id TEXT REFERENCES creators(remote_id);
ALTER TABLE items ADD COLUMN cover_url TEXT;
ALTER TABLE items ADD COLUMN duration_ms INTEGER;
ALTER TABLE items ADD COLUMN statistics_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE items ADD COLUMN visibility TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE items ADD COLUMN source_url TEXT;

CREATE INDEX items_creator_published
ON items(creator_id, published_at DESC, remote_id DESC);

CREATE TABLE library_sources (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN (
        'post',
        'like',
        'favorite_collection',
        'favorite_video',
        'favorite_music',
        'favorite_series',
        'favorite_drama',
        'watch_history',
        'watch_later',
        'reservation',
        'following'
    )),
    remote_id TEXT NOT NULL,
    name TEXT NOT NULL,
    declared_count INTEGER,
    sync_cursor TEXT,
    sync_status TEXT NOT NULL DEFAULT 'never' CHECK(sync_status IN (
        'never', 'running', 'complete', 'incomplete', 'failed'
    )),
    last_full_scan_at INTEGER,
    last_incremental_scan_at INTEGER,
    error_code TEXT,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    UNIQUE(kind, remote_id)
);

CREATE INDEX library_sources_kind_status
ON library_sources(kind, sync_status, name);

CREATE TABLE source_items (
    source_id TEXT NOT NULL REFERENCES library_sources(id),
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    remote_order TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY(source_id, item_id)
);

CREATE INDEX source_items_feed
ON source_items(source_id, remote_order DESC, item_id DESC);

CREATE TABLE sync_checkpoints (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES library_sources(id),
    cursor TEXT,
    page_index INTEGER NOT NULL,
    discovered_count INTEGER NOT NULL,
    response_digest TEXT,
    stop_reason TEXT,
    created_at INTEGER NOT NULL,
    UNIQUE(source_id, page_index, cursor)
);

CREATE INDEX sync_checkpoints_source_created
ON sync_checkpoints(source_id, created_at DESC, id DESC);


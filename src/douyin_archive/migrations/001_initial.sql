CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE auth_sessions (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL UNIQUE,
    encrypted_cookies BLOB NOT NULL,
    status TEXT NOT NULL,
    last_verified_at INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE TABLE collections (
    remote_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_history_json TEXT NOT NULL,
    sync_cursor TEXT,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL
);

CREATE TABLE items (
    remote_id TEXT PRIMARY KEY,
    author_name TEXT NOT NULL,
    description TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('video', 'gallery')),
    published_at INTEGER,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    metadata_digest TEXT
);

CREATE TABLE collection_items (
    collection_id TEXT NOT NULL REFERENCES collections(remote_id),
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY(collection_id, item_id)
);

CREATE TABLE media_files (
    id INTEGER PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    asset_index INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    relative_path TEXT,
    byte_size INTEGER,
    checksum_sha256 TEXT,
    mime_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(item_id, asset_index)
);

CREATE TABLE download_jobs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    remote_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at INTEGER NOT NULL,
    claimed_by TEXT,
    claimed_at INTEGER,
    last_error_code TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(kind, remote_id)
);

CREATE INDEX download_jobs_claimable
ON download_jobs(status, next_attempt_at, id);

CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    enqueued_count INTEGER NOT NULL DEFAULT 0,
    cursor_json TEXT,
    error_code TEXT,
    started_at INTEGER NOT NULL,
    finished_at INTEGER
);

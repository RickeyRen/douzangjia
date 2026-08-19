PRAGMA foreign_keys=OFF;

BEGIN IMMEDIATE;

CREATE TABLE library_sources_new (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN (
        'post',
        'recommend',
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

INSERT INTO library_sources_new (
    id, kind, remote_id, name, declared_count, sync_cursor, sync_status,
    last_full_scan_at, last_incremental_scan_at, error_code,
    first_seen_at, last_seen_at
)
SELECT
    id, kind, remote_id, name, declared_count, sync_cursor, sync_status,
    last_full_scan_at, last_incremental_scan_at, error_code,
    first_seen_at, last_seen_at
FROM library_sources;

DROP TABLE library_sources;
ALTER TABLE library_sources_new RENAME TO library_sources;

CREATE INDEX library_sources_kind_status
ON library_sources(kind, sync_status, name);

COMMIT;

PRAGMA foreign_keys=ON;

-- SQLite cannot widen a CHECK constraint in place; rebuild the table so
-- hand-picked selections and "everything missing" runs get their own kinds.
PRAGMA foreign_keys=OFF;

CREATE TABLE archive_batches_new (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('item', 'source', 'creator', 'selection', 'missing')),
    target_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN (
        'queued', 'discovering', 'running', 'paused',
        'completed', 'failed', 'cancelled'
    )),
    discovered_count INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER,
    error_code TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    finished_at INTEGER
);

INSERT INTO archive_batches_new SELECT * FROM archive_batches;
DROP TABLE archive_batches;
ALTER TABLE archive_batches_new RENAME TO archive_batches;

CREATE INDEX IF NOT EXISTS archive_batches_target_status
ON archive_batches(kind, target_id, status, id DESC);

PRAGMA foreign_keys=ON;

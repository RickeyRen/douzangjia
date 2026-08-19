CREATE TABLE archive_batches (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('item', 'source', 'creator')),
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

CREATE INDEX archive_batches_target_status
ON archive_batches(kind, target_id, status, id DESC);

ALTER TABLE download_jobs ADD COLUMN batch_id INTEGER REFERENCES archive_batches(id);
ALTER TABLE download_jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;
ALTER TABLE download_jobs ADD COLUMN paused_at INTEGER;
ALTER TABLE download_jobs ADD COLUMN cancel_requested_at INTEGER;

CREATE INDEX download_jobs_batch_status
ON download_jobs(batch_id, status, id);

CREATE TABLE archive_batch_items (
    batch_id INTEGER NOT NULL REFERENCES archive_batches(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    job_id INTEGER REFERENCES download_jobs(id),
    created_at INTEGER NOT NULL,
    PRIMARY KEY(batch_id, item_id)
);

CREATE INDEX archive_batch_items_job
ON archive_batch_items(job_id, batch_id);

CREATE TABLE creator_subscriptions (
    creator_id TEXT PRIMARY KEY REFERENCES creators(remote_id),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
    scan_interval_seconds INTEGER NOT NULL DEFAULT 21600
        CHECK(scan_interval_seconds >= 900),
    archive_new_items INTEGER NOT NULL DEFAULT 1 CHECK(archive_new_items IN (0, 1)),
    last_scan_at INTEGER,
    next_scan_at INTEGER,
    last_error_code TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX creator_subscriptions_due
ON creator_subscriptions(enabled, next_scan_at, creator_id);

CREATE TABLE job_events (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES download_jobs(id),
    batch_id INTEGER REFERENCES archive_batches(id),
    event_type TEXT NOT NULL,
    error_code TEXT,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    CHECK(job_id IS NOT NULL OR batch_id IS NOT NULL)
);

CREATE INDEX job_events_batch_created
ON job_events(batch_id, created_at DESC, id DESC);

CREATE INDEX job_events_job_created
ON job_events(job_id, created_at DESC, id DESC);

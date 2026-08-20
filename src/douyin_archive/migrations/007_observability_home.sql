ALTER TABLE library_sources
ADD COLUMN auto_download_enabled INTEGER NOT NULL DEFAULT 0
CHECK(auto_download_enabled IN (0, 1));

ALTER TABLE library_sources
ADD COLUMN download_policy_updated_at INTEGER;

UPDATE library_sources
SET auto_download_enabled=1
WHERE kind='favorite_collection';

CREATE TABLE download_intents (
    item_id TEXT NOT NULL REFERENCES items(remote_id),
    origin_type TEXT NOT NULL CHECK(origin_type IN ('source', 'manual', 'creator')),
    origin_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(item_id, origin_type, origin_id)
);

CREATE INDEX download_intents_active_item
ON download_intents(item_id, active, origin_type);

CREATE INDEX download_intents_origin
ON download_intents(origin_type, origin_id, active, item_id);

CREATE TABLE douyin_account (
    provider TEXT PRIMARY KEY CHECK(provider='douyin'),
    remote_id TEXT,
    nickname TEXT,
    unique_id TEXT,
    avatar_url TEXT,
    health_status TEXT NOT NULL DEFAULT 'unknown' CHECK(health_status IN (
        'healthy', 'degraded', 'expired', 'checking', 'unknown'
    )),
    last_verified_at INTEGER,
    last_sync_at INTEGER,
    last_failure_at INTEGER,
    last_error_code TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    profile_updated_at INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE TABLE metric_samples (
    id INTEGER PRIMARY KEY,
    resolution TEXT NOT NULL DEFAULT 'raw' CHECK(resolution IN ('raw', 'minute', 'hour')),
    sampled_at INTEGER NOT NULL,
    download_speed_bps REAL NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    queue_pending INTEGER NOT NULL DEFAULT 0,
    queue_running INTEGER NOT NULL DEFAULT 0,
    queue_retry INTEGER NOT NULL DEFAULT 0,
    queue_failed INTEGER NOT NULL DEFAULT 0,
    cpu_load_percent REAL NOT NULL DEFAULT 0,
    memory_used_bytes INTEGER NOT NULL DEFAULT 0,
    process_memory_bytes INTEGER NOT NULL DEFAULT 0,
    disk_used_bytes INTEGER NOT NULL DEFAULT 0,
    disk_free_bytes INTEGER NOT NULL DEFAULT 0,
    archive_bytes INTEGER NOT NULL DEFAULT 0,
    recent_errors INTEGER NOT NULL DEFAULT 0,
    UNIQUE(resolution, sampled_at)
);

CREATE INDEX metric_samples_window
ON metric_samples(resolution, sampled_at DESC);

CREATE TABLE remote_checks (
    item_id TEXT PRIMARY KEY REFERENCES items(remote_id),
    status TEXT NOT NULL DEFAULT 'unknown' CHECK(status IN (
        'available', 'deleted', 'private', 'restricted',
        'auth_required', 'rate_limited', 'unknown'
    )),
    checked_at INTEGER,
    evidence_code TEXT,
    consecutive_matches INTEGER NOT NULL DEFAULT 0,
    last_available_at INTEGER,
    updated_at INTEGER NOT NULL
);

CREATE INDEX remote_checks_stale
ON remote_checks(status, checked_at, item_id);

ALTER TABLE media_files ADD COLUMN width INTEGER;
ALTER TABLE media_files ADD COLUMN height INTEGER;
ALTER TABLE media_files ADD COLUMN codec TEXT;
ALTER TABLE media_files ADD COLUMN fps REAL;
ALTER TABLE media_files ADD COLUMN bit_rate INTEGER;
ALTER TABLE media_files ADD COLUMN duration_ms INTEGER;
ALTER TABLE media_files ADD COLUMN probe_status TEXT NOT NULL DEFAULT 'pending'
CHECK(probe_status IN ('pending', 'ready', 'unavailable', 'failed'));
ALTER TABLE media_files ADD COLUMN probed_at INTEGER;
ALTER TABLE media_files ADD COLUMN completed_at INTEGER;

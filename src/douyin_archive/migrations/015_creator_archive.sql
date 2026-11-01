-- Douyin rewrites a banned or deactivated creator's profile in place (the
-- nickname becomes the numeric 抖音号, the avatar the default one), so every
-- identity we ever saw is kept as its own snapshot instead of overwritten.
ALTER TABLE creators ADD COLUMN signature TEXT;
ALTER TABLE creators ADD COLUMN following_count INTEGER;
ALTER TABLE creators ADD COLUMN total_favorited INTEGER;
ALTER TABLE creators ADD COLUMN ip_location TEXT;
ALTER TABLE creators ADD COLUMN cover_url TEXT;
-- active | reset | deactivated | banned | vanished
ALTER TABLE creators ADD COLUMN archive_status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE creators ADD COLUMN archive_status_since INTEGER;
ALTER TABLE creators ADD COLUMN archive_evidence TEXT;
ALTER TABLE creators ADD COLUMN archive_checked_at INTEGER;
-- A softer verdict waits for a second matching check before it is applied.
ALTER TABLE creators ADD COLUMN archive_pending_status TEXT;
ALTER TABLE creators ADD COLUMN archive_pending_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS creator_snapshots (
    id INTEGER PRIMARY KEY,
    creator_id TEXT NOT NULL REFERENCES creators(remote_id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    nickname TEXT NOT NULL,
    unique_id TEXT,
    signature TEXT,
    avatar_url TEXT,
    avatar_key TEXT,
    avatar_path TEXT,
    cover_url TEXT,
    cover_path TEXT,
    follower_count INTEGER,
    following_count INTEGER,
    total_favorited INTEGER,
    post_count INTEGER,
    ip_location TEXT,
    -- 1 when the identity is Douyin's placeholder for a reset or closed account.
    degraded INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    media_attempts INTEGER NOT NULL DEFAULT 0,
    media_attempted_at INTEGER,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    UNIQUE(creator_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS creator_snapshots_history
ON creator_snapshots(creator_id, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS creators_archive_status
ON creators(archive_status, archive_status_since DESC);

-- Names queued for download kept the author as it was then; that is often the
-- only record of a creator renamed before snapshots existed.
INSERT OR IGNORE INTO creator_snapshots
    (creator_id, fingerprint, nickname, source, first_seen_at, last_seen_at)
SELECT i.creator_id,
       'job:' || TRIM(json_extract(d.payload_json, '$.author_name')),
       TRIM(json_extract(d.payload_json, '$.author_name')),
       'download_job', MIN(d.created_at), MAX(d.created_at)
FROM download_jobs d
JOIN items i ON i.remote_id = d.remote_id
JOIN creators c ON c.remote_id = i.creator_id
WHERE d.kind = 'download'
  AND json_valid(d.payload_json)
  AND TRIM(COALESCE(json_extract(d.payload_json, '$.author_name'), '')) <> ''
  AND TRIM(json_extract(d.payload_json, '$.author_name')) <> c.nickname
GROUP BY i.creator_id, TRIM(json_extract(d.payload_json, '$.author_name'));

-- Where the owner stopped in a long video, so any device resumes there.
CREATE TABLE IF NOT EXISTS item_playback (
    item_id TEXT PRIMARY KEY REFERENCES items(remote_id),
    position_ms INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

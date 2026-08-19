CREATE TABLE source_entities (
    source_id TEXT NOT NULL REFERENCES library_sources(id) ON DELETE CASCADE,
    remote_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    subtitle TEXT,
    cover_url TEXT,
    source_url TEXT,
    remote_order TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY(source_id, remote_id)
);

CREATE INDEX source_entities_browse
ON source_entities(source_id, remote_order DESC, remote_id DESC);

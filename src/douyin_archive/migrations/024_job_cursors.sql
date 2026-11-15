-- Where slow background walks over big tables left off, so a restart resumes
-- instead of starting over. Walking by primary key needs no new index on
-- media_files (see 022 for what an extra index there once did).
CREATE TABLE IF NOT EXISTS job_cursors (
    name TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    started_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

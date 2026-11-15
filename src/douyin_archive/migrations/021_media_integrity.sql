-- Backup self-check: when each saved file was last confirmed intact, and what
-- was wrong with it the last time it was not.
ALTER TABLE media_files ADD COLUMN verified_at INTEGER;
ALTER TABLE media_files ADD COLUMN verify_status TEXT;
ALTER TABLE media_files ADD COLUMN verify_failed_at INTEGER;
CREATE INDEX IF NOT EXISTS media_files_verify_queue ON media_files(status, verified_at);

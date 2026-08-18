ALTER TABLE media_files
ADD COLUMN downloaded_bytes INTEGER NOT NULL DEFAULT 0;

ALTER TABLE media_files
ADD COLUMN total_bytes INTEGER;

ALTER TABLE media_files
ADD COLUMN speed_bps REAL NOT NULL DEFAULT 0;

ALTER TABLE media_files
ADD COLUMN progress_updated_at INTEGER;


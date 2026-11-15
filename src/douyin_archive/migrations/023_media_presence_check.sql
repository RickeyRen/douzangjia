-- Backup self-check, fast pass: when each saved file was last seen on disk with
-- the right size. Hashing everything takes weeks; this pass takes minutes.
-- No index on purpose: an index led by media_files.status hijacked the hot
-- per-item "has a ready file" probe (see 022).
ALTER TABLE media_files ADD COLUMN present_at INTEGER;

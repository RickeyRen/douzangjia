-- 021 briefly added an index on media_files(status, verified_at). SQLite then
-- used it for the hot "does this item have a ready file" probe instead of the
-- item_id index, scanning every ready file per item: queries of seconds took
-- minutes and the whole server stalled. The self-check scans without it.
DROP INDEX IF EXISTS media_files_verify_queue;

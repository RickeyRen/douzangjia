BEGIN IMMEDIATE;

INSERT INTO library_sources (
    id, kind, remote_id, name, declared_count, sync_cursor, sync_status,
    last_full_scan_at, last_incremental_scan_at, error_code,
    first_seen_at, last_seen_at, auto_download_enabled,
    download_policy_updated_at
)
SELECT
    'account:favorite_videos', 'favorite_video', 'self', '抖音全部收藏',
    declared_count, sync_cursor, sync_status, last_full_scan_at,
    last_incremental_scan_at, error_code, first_seen_at, last_seen_at,
    auto_download_enabled, download_policy_updated_at
FROM library_sources
WHERE id='favorite_collection:__douyin_all_favorites__'
  AND NOT EXISTS (
      SELECT 1 FROM library_sources WHERE id='account:favorite_videos'
  );

UPDATE library_sources
SET name='抖音全部收藏',
    auto_download_enabled=MAX(
        auto_download_enabled,
        COALESCE((
            SELECT CASE
                WHEN download_policy_updated_at IS NOT NULL
                THEN auto_download_enabled
                ELSE 0
            END
            FROM library_sources legacy
            WHERE legacy.id='favorite_collection:__douyin_all_favorites__'
        ), 0)
    ),
    download_policy_updated_at=CASE
        WHEN download_policy_updated_at IS NULL THEN (
            SELECT download_policy_updated_at
            FROM library_sources legacy
            WHERE legacy.id='favorite_collection:__douyin_all_favorites__'
        )
        WHEN COALESCE((
            SELECT download_policy_updated_at
            FROM library_sources legacy
            WHERE legacy.id='favorite_collection:__douyin_all_favorites__'
        ), download_policy_updated_at) > download_policy_updated_at THEN (
            SELECT download_policy_updated_at
            FROM library_sources legacy
            WHERE legacy.id='favorite_collection:__douyin_all_favorites__'
        )
        ELSE download_policy_updated_at
    END
WHERE id='account:favorite_videos';

INSERT INTO source_items (
    source_id, item_id, remote_order, metadata_json, first_seen_at, last_seen_at
)
SELECT
    'account:favorite_videos', item_id, remote_order, metadata_json,
    first_seen_at, last_seen_at
FROM source_items
WHERE source_id='favorite_collection:__douyin_all_favorites__'
ON CONFLICT(source_id, item_id) DO UPDATE SET
    remote_order=COALESCE(source_items.remote_order, excluded.remote_order),
    metadata_json=CASE
        WHEN source_items.metadata_json='{}' THEN excluded.metadata_json
        ELSE source_items.metadata_json
    END,
    first_seen_at=MIN(source_items.first_seen_at, excluded.first_seen_at),
    last_seen_at=MAX(source_items.last_seen_at, excluded.last_seen_at);

INSERT INTO source_entities (
    source_id, remote_id, entity_type, title, subtitle, cover_url, source_url,
    remote_order, metadata_json, first_seen_at, last_seen_at
)
SELECT
    'account:favorite_videos', remote_id, entity_type, title, subtitle,
    cover_url, source_url, remote_order, metadata_json, first_seen_at, last_seen_at
FROM source_entities
WHERE source_id='favorite_collection:__douyin_all_favorites__'
ON CONFLICT(source_id, remote_id) DO UPDATE SET
    last_seen_at=MAX(source_entities.last_seen_at, excluded.last_seen_at);

INSERT INTO download_intents (
    item_id, origin_type, origin_id, active, payload_json, created_at, updated_at
)
SELECT
    item_id, origin_type, 'account:favorite_videos', active, payload_json,
    created_at, updated_at
FROM download_intents
WHERE origin_type='source'
  AND origin_id='favorite_collection:__douyin_all_favorites__'
ON CONFLICT(item_id, origin_type, origin_id) DO UPDATE SET
    active=MAX(download_intents.active, excluded.active),
    payload_json=CASE
        WHEN download_intents.payload_json='{}' THEN excluded.payload_json
        ELSE download_intents.payload_json
    END,
    created_at=MIN(download_intents.created_at, excluded.created_at),
    updated_at=MAX(download_intents.updated_at, excluded.updated_at);

UPDATE archive_batches
SET target_id='account:favorite_videos'
WHERE kind='source'
  AND target_id='favorite_collection:__douyin_all_favorites__';

DELETE FROM download_intents
WHERE origin_type='source'
  AND origin_id='favorite_collection:__douyin_all_favorites__';
DELETE FROM sync_checkpoints
WHERE source_id='favorite_collection:__douyin_all_favorites__';
DELETE FROM source_entities
WHERE source_id='favorite_collection:__douyin_all_favorites__';
DELETE FROM source_items
WHERE source_id='favorite_collection:__douyin_all_favorites__';
DELETE FROM library_sources
WHERE id='favorite_collection:__douyin_all_favorites__';
DELETE FROM collection_items
WHERE collection_id='__douyin_all_favorites__';
DELETE FROM collections
WHERE remote_id='__douyin_all_favorites__';

CREATE TABLE creator_identity_refresh (
    creator_id TEXT PRIMARY KEY REFERENCES creators(remote_id) ON DELETE CASCADE,
    attempted_at INTEGER NOT NULL,
    error_code TEXT
);

CREATE INDEX creator_identity_refresh_retry
ON creator_identity_refresh(attempted_at, creator_id);

COMMIT;

from __future__ import annotations

import json
import time

from .db import Database
from .library_models import (
    CreatorRecord,
    LibrarySource,
    LibrarySyncStatus,
    SourceEntityRecord,
    SourceIntegrity,
)


class LibraryRepository:
    ACCOUNT_SOURCES = (
        ("account:posts", "post", "作品"),
        ("account:recommendations", "recommend", "推荐"),
        ("account:likes", "like", "喜欢"),
        ("account:favorite_videos", "favorite_video", "收藏视频"),
        ("account:favorite_music", "favorite_music", "收藏音乐"),
        ("account:favorite_series", "favorite_series", "收藏合集"),
        ("account:favorite_drama", "favorite_drama", "收藏短剧"),
        ("account:watch_history", "watch_history", "观看历史"),
        ("account:watch_later", "watch_later", "稍后再看"),
        ("account:reservations", "reservation", "我的预约"),
        ("account:following", "following", "关注"),
    )

    def __init__(self, database: Database) -> None:
        self.db = database

    @staticmethod
    def favorite_collection_source_id(remote_id: str) -> str:
        return f"favorite_collection:{remote_id}"

    async def backfill_legacy_collections(self) -> None:
        await self.db.execute(
            "INSERT INTO library_sources "
            "(id, kind, remote_id, name, declared_count, sync_status, "
            "first_seen_at, last_seen_at, auto_download_enabled) "
            "SELECT 'favorite_collection:' || remote_id, 'favorite_collection', "
            "remote_id, name, NULL, 'incomplete', first_seen_at, last_seen_at, 1 "
            "FROM collections WHERE true "
            "ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, last_seen_at=MAX(library_sources.last_seen_at, excluded.last_seen_at)"
        )
        await self.db.execute(
            "INSERT INTO source_items "
            "(source_id, item_id, remote_order, metadata_json, first_seen_at, last_seen_at) "
            "SELECT 'favorite_collection:' || collection_id, item_id, "
            "printf('%020d', first_seen_at), '{}', first_seen_at, last_seen_at "
            "FROM collection_items WHERE true "
            "ON CONFLICT(source_id, item_id) DO UPDATE SET "
            "last_seen_at=MAX(source_items.last_seen_at, excluded.last_seen_at)"
        )

    async def ensure_account_sources(self) -> None:
        now = int(time.time())
        for source_id, kind, name in self.ACCOUNT_SOURCES:
            await self.db.execute(
                "INSERT INTO library_sources "
                "(id, kind, remote_id, name, sync_status, first_seen_at, last_seen_at) "
                "VALUES (?, ?, 'self', ?, 'never', ?, ?) "
                "ON CONFLICT(kind, remote_id) DO UPDATE SET name=excluded.name, "
                "last_seen_at=excluded.last_seen_at",
                (source_id, kind, name, now, now),
            )

    async def upsert_source(self, source: LibrarySource) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO library_sources "
            "(id, kind, remote_id, name, declared_count, sync_cursor, sync_status, "
            "last_full_scan_at, last_incremental_scan_at, error_code, "
            "first_seen_at, last_seen_at, auto_download_enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "kind=excluded.kind, remote_id=excluded.remote_id, name=excluded.name, "
            "declared_count=excluded.declared_count, sync_cursor=excluded.sync_cursor, "
            "sync_status=excluded.sync_status, last_full_scan_at=excluded.last_full_scan_at, "
            "last_incremental_scan_at=excluded.last_incremental_scan_at, "
            "error_code=excluded.error_code, last_seen_at=excluded.last_seen_at",
            (
                source.id,
                source.kind.value,
                source.remote_id,
                source.name,
                source.declared_count,
                source.sync_cursor,
                source.sync_status.value,
                source.last_full_scan_at,
                source.last_incremental_scan_at,
                source.error_code,
                now,
                now,
                int(source.kind.value == "favorite_collection"),
            ),
        )

    async def upsert_creator(self, creator: CreatorRecord) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO creators "
            "(remote_id, nickname, unique_id, avatar_url, follower_count, post_count, "
            "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(remote_id) DO UPDATE SET "
            "nickname=excluded.nickname, "
            "unique_id=COALESCE(excluded.unique_id, creators.unique_id), "
            "avatar_url=COALESCE(excluded.avatar_url, creators.avatar_url), "
            "follower_count=COALESCE(excluded.follower_count, creators.follower_count), "
            "post_count=COALESCE(excluded.post_count, creators.post_count), "
            "last_seen_at=excluded.last_seen_at",
            (
                creator.remote_id,
                creator.nickname,
                creator.unique_id,
                creator.avatar_url,
                creator.follower_count,
                creator.post_count,
                now,
                now,
            ),
        )

    async def link_source_item(
        self,
        source_id: str,
        item_id: str,
        remote_order: str | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = int(time.time())
        metadata_json = json.dumps(
            metadata or {}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        await self.db.execute(
            "INSERT INTO source_items "
            "(source_id, item_id, remote_order, metadata_json, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id, item_id) DO UPDATE SET "
            "remote_order=excluded.remote_order, metadata_json=excluded.metadata_json, "
            "last_seen_at=excluded.last_seen_at",
            (source_id, item_id, remote_order, metadata_json, now, now),
        )

    async def reconcile_source_items(
        self, source_id: str, current_item_ids: set[str]
    ) -> int:
        if not current_item_ids:
            cursor = await self.db.execute(
                "DELETE FROM source_items WHERE source_id=?", (source_id,)
            )
            return cursor.rowcount
        placeholders = ",".join("?" for _ in current_item_ids)
        cursor = await self.db.execute(
            f"DELETE FROM source_items WHERE source_id=? "
            f"AND item_id NOT IN ({placeholders})",
            (source_id, *sorted(current_item_ids)),
        )
        return cursor.rowcount

    async def upsert_source_entity(self, entity: SourceEntityRecord) -> None:
        now = int(time.time())
        metadata_json = json.dumps(
            entity.metadata or {},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        await self.db.execute(
            "INSERT INTO source_entities "
            "(source_id, remote_id, entity_type, title, subtitle, cover_url, "
            "source_url, remote_order, metadata_json, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id, remote_id) DO UPDATE SET "
            "entity_type=excluded.entity_type, title=excluded.title, "
            "subtitle=excluded.subtitle, cover_url=excluded.cover_url, "
            "source_url=excluded.source_url, remote_order=excluded.remote_order, "
            "metadata_json=excluded.metadata_json, last_seen_at=excluded.last_seen_at",
            (
                entity.source_id,
                entity.remote_id,
                entity.entity_type,
                entity.title,
                entity.subtitle,
                entity.cover_url,
                entity.source_url,
                entity.remote_order,
                metadata_json,
                now,
                now,
            ),
        )

    async def reconcile_source_entities(
        self, source_id: str, current_entity_ids: set[str]
    ) -> int:
        if not current_entity_ids:
            cursor = await self.db.execute(
                "DELETE FROM source_entities WHERE source_id=?", (source_id,)
            )
            return cursor.rowcount
        placeholders = ",".join("?" for _ in current_entity_ids)
        cursor = await self.db.execute(
            f"DELETE FROM source_entities WHERE source_id=? "
            f"AND remote_id NOT IN ({placeholders})",
            (source_id, *sorted(current_entity_ids)),
        )
        return cursor.rowcount

    async def source_integrity(self, source_id: str) -> SourceIntegrity | None:
        row = await self.db.fetchone(
            "SELECT s.id, s.declared_count, s.sync_status, "
            "(SELECT COUNT(*) FROM source_items si_count "
            "WHERE si_count.source_id=s.id) + "
            "(SELECT COUNT(*) FROM source_entities se_count "
            "WHERE se_count.source_id=s.id) AS discovered_count, "
            "COALESCE((SELECT SUM(CASE WHEN EXISTS ("
            "SELECT 1 FROM media_files mf_ready "
            "WHERE mf_ready.item_id=si_archive.item_id AND mf_ready.status='ready'"
            ") AND NOT EXISTS ("
            "SELECT 1 FROM media_files mf_pending "
            "WHERE mf_pending.item_id=si_archive.item_id AND mf_pending.status!='ready'"
            ") THEN 1 ELSE 0 END) FROM source_items si_archive "
            "WHERE si_archive.source_id=s.id), 0) AS archived_count "
            "FROM library_sources s "
            "WHERE s.id=?",
            (source_id,),
        )
        if row is None:
            return None
        declared_count = (
            int(row["declared_count"]) if row["declared_count"] is not None else None
        )
        discovered_count = int(row["discovered_count"])
        archived_count = int(row["archived_count"])
        missing_count = (
            max(declared_count - discovered_count, 0)
            if declared_count is not None
            else 0
        )
        sync_status = LibrarySyncStatus(str(row["sync_status"]))
        return SourceIntegrity(
            source_id=str(row["id"]),
            declared_count=declared_count,
            discovered_count=discovered_count,
            archived_count=archived_count,
            missing_count=missing_count,
            sync_status=sync_status,
            complete=(
                sync_status is LibrarySyncStatus.COMPLETE
                and declared_count is not None
                and declared_count == discovered_count
            ),
        )

    async def save_checkpoint(
        self,
        source_id: str,
        *,
        cursor: str | None,
        page_index: int,
        discovered_count: int,
        response_digest: str | None = None,
        stop_reason: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO sync_checkpoints "
            "(source_id, cursor, page_index, discovered_count, response_digest, "
            "stop_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id, page_index, cursor) DO UPDATE SET "
            "discovered_count=excluded.discovered_count, "
            "response_digest=excluded.response_digest, "
            "stop_reason=excluded.stop_reason, created_at=excluded.created_at",
            (
                source_id,
                cursor,
                page_index,
                max(0, discovered_count),
                response_digest,
                stop_reason,
                int(time.time()),
            ),
        )

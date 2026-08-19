from __future__ import annotations

import json
import time

from .db import Database
from .library_models import (
    CreatorRecord,
    LibrarySource,
    LibrarySyncStatus,
    SourceIntegrity,
)


class LibraryRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    @staticmethod
    def favorite_collection_source_id(remote_id: str) -> str:
        return f"favorite_collection:{remote_id}"

    async def backfill_legacy_collections(self) -> None:
        await self.db.execute(
            "INSERT INTO library_sources "
            "(id, kind, remote_id, name, declared_count, sync_status, "
            "first_seen_at, last_seen_at) "
            "SELECT 'favorite_collection:' || remote_id, 'favorite_collection', "
            "remote_id, name, NULL, 'incomplete', first_seen_at, last_seen_at "
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

    async def upsert_source(self, source: LibrarySource) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO library_sources "
            "(id, kind, remote_id, name, declared_count, sync_cursor, sync_status, "
            "last_full_scan_at, last_incremental_scan_at, error_code, "
            "first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
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
            ),
        )

    async def upsert_creator(self, creator: CreatorRecord) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO creators "
            "(remote_id, nickname, unique_id, avatar_url, follower_count, post_count, "
            "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(remote_id) DO UPDATE SET "
            "nickname=excluded.nickname, unique_id=excluded.unique_id, "
            "avatar_url=excluded.avatar_url, follower_count=excluded.follower_count, "
            "post_count=excluded.post_count, last_seen_at=excluded.last_seen_at",
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

    async def source_integrity(self, source_id: str) -> SourceIntegrity | None:
        row = await self.db.fetchone(
            "SELECT s.id, s.declared_count, s.sync_status, "
            "COUNT(si.item_id) AS discovered_count, "
            "COALESCE(SUM(CASE WHEN EXISTS ("
            "SELECT 1 FROM media_files mf_ready "
            "WHERE mf_ready.item_id=si.item_id AND mf_ready.status='ready'"
            ") AND NOT EXISTS ("
            "SELECT 1 FROM media_files mf_pending "
            "WHERE mf_pending.item_id=si.item_id AND mf_pending.status!='ready'"
            ") THEN 1 ELSE 0 END), 0) AS archived_count "
            "FROM library_sources s "
            "LEFT JOIN source_items si ON si.source_id=s.id "
            "WHERE s.id=? GROUP BY s.id",
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

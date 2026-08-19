from __future__ import annotations

import json
import time
from typing import Any

from .db import Database
from .models import Collection, DownloadJob, MediaAsset, MediaProgress, RemoteItem
from .paths import asset_filename
from .storage import ObjectStore


class ArchiveRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def upsert_collection(self, remote_id: str, name: str) -> Collection:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            existing = await self.db.fetchone(
                "SELECT * FROM collections WHERE remote_id=?", (remote_id,)
            )
            if existing is None:
                history = [name]
                await self.db.execute(
                    "INSERT INTO collections "
                    "(remote_id, name, name_history_json, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (remote_id, name, json.dumps(history, ensure_ascii=False), now, now),
                )
            else:
                history = json.loads(existing["name_history_json"])
                if not history or history[-1] != name:
                    history.append(name)
                await self.db.execute(
                    "UPDATE collections SET name=?, name_history_json=?, last_seen_at=? "
                    "WHERE remote_id=?",
                    (name, json.dumps(history, ensure_ascii=False), now, remote_id),
                )
            row = await self.db.fetchone(
                "SELECT * FROM collections WHERE remote_id=?", (remote_id,)
            )
        if row is None:
            raise RuntimeError("collection upsert did not return a row")
        return Collection.from_row(row)

    async def get_collection(self, remote_id: str) -> Collection | None:
        row = await self.db.fetchone(
            "SELECT * FROM collections WHERE remote_id=?", (remote_id,)
        )
        return Collection.from_row(row) if row is not None else None

    async def upsert_item(
        self,
        *,
        remote_id: str,
        author_name: str,
        description: str,
        item_type: str,
        published_at: int | None = None,
        metadata_digest: str | None = None,
    ) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, published_at, "
            "first_seen_at, last_seen_at, metadata_digest) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(remote_id) DO UPDATE SET "
            "author_name=excluded.author_name, description=excluded.description, "
            "item_type=excluded.item_type, published_at=excluded.published_at, "
            "last_seen_at=excluded.last_seen_at, metadata_digest=excluded.metadata_digest",
            (
                remote_id,
                author_name,
                description,
                item_type,
                published_at,
                now,
                now,
                metadata_digest,
            ),
        )

    async def link_collection_item(self, collection_id: str, item_id: str) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO collection_items "
            "(collection_id, item_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(collection_id, item_id) DO UPDATE SET "
            "last_seen_at=excluded.last_seen_at",
            (collection_id, item_id, now, now),
        )

    async def count_collection_items(self, collection_id: str) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS total FROM collection_items WHERE collection_id=?",
            (collection_id,),
        )
        return int(row["total"]) if row is not None else 0

    async def save_discovery_page(
        self, collection_id: str, items: tuple[RemoteItem, ...]
    ) -> None:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            for item in items:
                await self.db.execute(
                    "INSERT INTO items "
                    "(remote_id, author_name, description, item_type, published_at, "
                    "first_seen_at, last_seen_at, metadata_digest) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, NULL) "
                    "ON CONFLICT(remote_id) DO UPDATE SET "
                    "author_name=excluded.author_name, description=excluded.description, "
                    "item_type=excluded.item_type, published_at=excluded.published_at, "
                    "last_seen_at=excluded.last_seen_at",
                    (
                        item.remote_id,
                        item.author_name,
                        item.description,
                        item.item_type,
                        item.published_at,
                        now,
                        now,
                    ),
                )
                await self.db.execute(
                    "INSERT INTO collection_items "
                    "(collection_id, item_id, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(collection_id, item_id) DO UPDATE SET "
                    "last_seen_at=excluded.last_seen_at",
                    (collection_id, item.remote_id, now, now),
                )

    async def list_known_item_ids(self) -> set[str]:
        rows = await self.db.fetchall("SELECT remote_id FROM items")
        return {str(row["remote_id"]) for row in rows}


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def enqueue_unique(
        self, kind: str, remote_id: str, payload: dict[str, Any]
    ) -> DownloadJob:
        now = int(time.time())
        row = await self.db.fetchone(
            "INSERT INTO download_jobs "
            "(kind, remote_id, payload_json, status, attempts, next_attempt_at, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?) "
            "ON CONFLICT(kind, remote_id) DO UPDATE SET "
            "payload_json=excluded.payload_json, "
            "status=CASE WHEN download_jobs.status IN ('completed', 'failed') "
            "THEN 'pending' ELSE download_jobs.status END, "
            "attempts=CASE WHEN download_jobs.status IN ('completed', 'failed') "
            "THEN 0 ELSE download_jobs.attempts END, "
            "next_attempt_at=CASE WHEN download_jobs.status IN ('completed', 'failed') "
            "THEN excluded.next_attempt_at ELSE download_jobs.next_attempt_at END, "
            "last_error_code=CASE WHEN download_jobs.status IN ('completed', 'failed') "
            "THEN NULL ELSE download_jobs.last_error_code END, "
            "updated_at=excluded.updated_at "
            "RETURNING *",
            (kind, remote_id, json.dumps(payload, separators=(",", ":")), now, now, now),
        )
        if row is None:
            raise RuntimeError("job enqueue did not return a row")
        return DownloadJob.from_row(row)

    async def claim_next(self, *, worker_id: str) -> DownloadJob | None:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            candidate = await self.db.fetchone(
                "SELECT id FROM download_jobs "
                "WHERE status IN ('pending', 'retry') AND next_attempt_at <= ? "
                "ORDER BY next_attempt_at, id LIMIT 1",
                (now,),
            )
            if candidate is None:
                return None
            row = await self.db.fetchone(
                "UPDATE download_jobs SET status='running', attempts=attempts+1, "
                "claimed_by=?, claimed_at=?, updated_at=? WHERE id=? RETURNING *",
                (worker_id, now, now, candidate["id"]),
            )
        return DownloadJob.from_row(row) if row is not None else None

    async def get_by_key(self, kind: str, remote_id: str) -> DownloadJob | None:
        row = await self.db.fetchone(
            "SELECT * FROM download_jobs WHERE kind=? AND remote_id=?",
            (kind, remote_id),
        )
        return DownloadJob.from_row(row) if row is not None else None

    async def complete(self, job_id: int) -> None:
        await self.db.execute(
            "UPDATE download_jobs SET status='completed', claimed_by=NULL, "
            "updated_at=? WHERE id=?",
            (int(time.time()), job_id),
        )

    async def fail(
        self, job_id: int, error_code: str, *, retry_after_seconds: int
    ) -> None:
        now = int(time.time())
        await self.db.execute(
            "UPDATE download_jobs SET status='retry', claimed_by=NULL, "
            "last_error_code=?, next_attempt_at=?, updated_at=? WHERE id=?",
            (error_code, now + retry_after_seconds, now, job_id),
        )

    async def fail_terminal(self, job_id: int, error_code: str) -> None:
        await self.db.execute(
            "UPDATE download_jobs SET status='failed', claimed_by=NULL, "
            "last_error_code=?, updated_at=? WHERE id=?",
            (error_code, int(time.time()), job_id),
        )

    async def recover_stale_running(self, *, older_than_seconds: int) -> int:
        cutoff = int(time.time()) - older_than_seconds
        cursor = await self.db.execute(
            "UPDATE download_jobs SET status='retry', claimed_by=NULL, "
            "last_error_code='WORKER_RESTARTED', next_attempt_at=?, updated_at=? "
            "WHERE status='running' AND claimed_at <= ?",
            (int(time.time()), int(time.time()), cutoff),
        )
        return cursor.rowcount

    async def get(self, job_id: int) -> DownloadJob | None:
        row = await self.db.fetchone("SELECT * FROM download_jobs WHERE id=?", (job_id,))
        return DownloadJob.from_row(row) if row is not None else None

    async def count(self) -> int:
        row = await self.db.fetchone("SELECT COUNT(*) AS total FROM download_jobs")
        return int(row["total"]) if row is not None else 0


class DownloadProgressRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def prepare_asset(
        self, asset: MediaAsset, *, downloaded_bytes: int = 0
    ) -> MediaProgress:
        now = int(time.time())
        row = await self.db.fetchone(
            "INSERT INTO media_files "
            "(item_id, asset_index, media_type, relative_path, byte_size, "
            "checksum_sha256, mime_type, status, created_at, updated_at, "
            "downloaded_bytes, total_bytes, speed_bps, progress_updated_at) "
            "VALUES (?, ?, ?, NULL, NULL, NULL, ?, 'pending', ?, ?, ?, ?, 0, ?) "
            "ON CONFLICT(item_id, asset_index) DO UPDATE SET "
            "media_type=excluded.media_type, mime_type=excluded.mime_type, "
            "status=CASE WHEN media_files.status='ready' THEN 'ready' ELSE 'pending' END, "
            "downloaded_bytes=CASE WHEN media_files.status='ready' "
            "THEN COALESCE(media_files.byte_size, media_files.downloaded_bytes) "
            "ELSE MAX(media_files.downloaded_bytes, excluded.downloaded_bytes) END, "
            "total_bytes=CASE WHEN media_files.status='ready' "
            "THEN COALESCE(media_files.byte_size, media_files.total_bytes, excluded.total_bytes) "
            "ELSE COALESCE(media_files.total_bytes, excluded.total_bytes) END, "
            "speed_bps=0, progress_updated_at=excluded.progress_updated_at, "
            "updated_at=excluded.updated_at RETURNING *",
            (
                asset.remote_id,
                asset.asset_index,
                asset.media_type,
                asset.mime_type,
                now,
                now,
                max(0, downloaded_bytes),
                asset.expected_size,
                now,
            ),
        )
        if row is None:
            raise RuntimeError("media progress prepare did not return a row")
        return MediaProgress.from_row(row)

    async def update(
        self,
        item_id: str,
        asset_index: int,
        *,
        status: str,
        downloaded_bytes: int,
        total_bytes: int | None,
        speed_bps: float,
    ) -> MediaProgress:
        now = int(time.time())
        row = await self.db.fetchone(
            "UPDATE media_files SET status=?, downloaded_bytes=?, total_bytes=?, "
            "speed_bps=?, progress_updated_at=?, updated_at=? "
            "WHERE item_id=? AND asset_index=? RETURNING *",
            (
                status,
                max(0, downloaded_bytes),
                total_bytes,
                max(0.0, speed_bps),
                now,
                now,
                item_id,
                asset_index,
            ),
        )
        if row is None:
            raise RuntimeError("media progress asset is not prepared")
        return MediaProgress.from_row(row)

    async def get_for_item(self, item_id: str) -> list[MediaProgress]:
        rows = await self.db.fetchall(
            "SELECT * FROM media_files WHERE item_id=? ORDER BY asset_index", (item_id,)
        )
        return [MediaProgress.from_row(row) for row in rows]

    async def backfill_parts(self, store: ObjectStore) -> int:
        """Restore visible progress from durable files before workers resume."""
        rows = await self.db.fetchall(
            "SELECT payload_json FROM download_jobs "
            "WHERE kind='download' AND status != 'completed'"
        )
        restored = 0
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                assets = payload.get("assets", ())
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
            for value in assets:
                try:
                    expected_size = value.get("expected_size")
                    asset = MediaAsset(
                        remote_id=str(value["remote_id"]),
                        asset_index=int(value["asset_index"]),
                        media_type=str(value["media_type"]),
                        url=str(value["url"]),
                        mime_type=(
                            str(value["mime_type"])
                            if value.get("mime_type")
                            else None
                        ),
                        expected_size=(
                            int(expected_size) if expected_size is not None else None
                        ),
                    )
                except (AttributeError, KeyError, TypeError, ValueError):
                    continue
                filename = asset_filename(
                    asset.asset_index, asset.media_type, asset.mime_type
                )
                object_file = store.object_path(asset.remote_id, filename)
                part_file = store.part_path(asset.remote_id, filename)
                downloaded_bytes = (
                    object_file.stat().st_size
                    if object_file.is_file()
                    else part_file.stat().st_size
                    if part_file.is_file()
                    else 0
                )
                await self.prepare_asset(asset, downloaded_bytes=downloaded_bytes)
                restored += 1
        return restored

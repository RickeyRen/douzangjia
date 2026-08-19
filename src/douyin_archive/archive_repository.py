from __future__ import annotations

import time
from dataclasses import dataclass

from .db import Database


@dataclass(frozen=True, slots=True)
class ArchiveBatch:
    id: int
    kind: str
    target_id: str
    status: str
    discovered_count: int
    completed_count: int
    failed_count: int
    downloaded_bytes: int
    total_bytes: int | None
    error_code: str | None
    total_items: int
    created_at: int
    updated_at: int
    finished_at: int | None


@dataclass(frozen=True, slots=True)
class CreatorSubscription:
    creator_id: str
    enabled: bool
    scan_interval_seconds: int
    archive_new_items: bool
    last_scan_at: int | None
    next_scan_at: int | None
    last_error_code: str | None


class ArchiveBatchRepository:
    ACTIVE_STATUSES = ("queued", "discovering", "running", "paused")

    def __init__(self, database: Database) -> None:
        self.db = database

    async def create_batch(self, kind: str, target_id: str) -> ArchiveBatch:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            existing = await self.db.fetchone(
                "SELECT id FROM archive_batches WHERE kind=? AND target_id=? "
                "AND status IN ('queued', 'discovering', 'running', 'paused') "
                "ORDER BY id DESC LIMIT 1",
                (kind, target_id),
            )
            if existing is not None:
                batch_id = int(existing["id"])
            else:
                row = await self.db.fetchone(
                    "INSERT INTO archive_batches "
                    "(kind, target_id, status, created_at, updated_at) "
                    "VALUES (?, ?, 'queued', ?, ?) RETURNING id",
                    (kind, target_id, now, now),
                )
                if row is None:
                    raise RuntimeError("archive batch creation failed")
                batch_id = int(row["id"])
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise RuntimeError("archive batch disappeared after creation")
        return batch

    async def add_item(
        self, batch_id: int, item_id: str, *, job_id: int | None = None
    ) -> None:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            await self.db.execute(
                "INSERT INTO archive_batch_items (batch_id, item_id, job_id, created_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(batch_id, item_id) DO UPDATE SET "
                "job_id=COALESCE(excluded.job_id, archive_batch_items.job_id)",
                (batch_id, item_id, job_id, now),
            )
            await self.db.execute(
                "UPDATE archive_batches SET discovered_count=("
                "SELECT COUNT(*) FROM archive_batch_items WHERE batch_id=?"
                "), updated_at=? WHERE id=?",
                (batch_id, now, batch_id),
            )

    async def set_status(
        self, batch_id: int, status: str, *, error_code: str | None = None
    ) -> None:
        now = int(time.time())
        finished_at = now if status in {"completed", "failed", "cancelled"} else None
        await self.db.execute(
            "UPDATE archive_batches SET status=?, error_code=?, updated_at=?, "
            "finished_at=? WHERE id=?",
            (status, error_code, now, finished_at, batch_id),
        )

    async def get_batch(self, batch_id: int) -> ArchiveBatch | None:
        row = await self.db.fetchone(
            "SELECT b.*, COUNT(bi.item_id) AS total_items "
            "FROM archive_batches b LEFT JOIN archive_batch_items bi ON bi.batch_id=b.id "
            "WHERE b.id=? GROUP BY b.id",
            (batch_id,),
        )
        return self._batch(row) if row is not None else None

    async def count_batches(self) -> int:
        row = await self.db.fetchone("SELECT COUNT(*) AS total FROM archive_batches")
        return int(row["total"]) if row is not None else 0

    async def list_batches(self, *, limit: int = 50) -> list[ArchiveBatch]:
        active_rows = await self.db.fetchall(
            "SELECT id FROM archive_batches "
            "WHERE status IN ('queued', 'discovering', 'running') "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        for row in active_rows:
            await self.refresh_batch(int(row["id"]))
        rows = await self.db.fetchall(
            "SELECT b.*, COUNT(bi.item_id) AS total_items "
            "FROM archive_batches b LEFT JOIN archive_batch_items bi ON bi.batch_id=b.id "
            "GROUP BY b.id ORDER BY b.id DESC LIMIT ?",
            (limit,),
        )
        return [self._batch(row) for row in rows]

    async def control_batch(self, batch_id: int, action: str) -> ArchiveBatch | None:
        batch = await self.get_batch(batch_id)
        if batch is None:
            return None
        now = int(time.time())
        if action == "pause":
            if batch.status not in {"queued", "discovering", "running"}:
                raise ValueError("batch cannot be paused")
            await self.db.execute(
                "UPDATE download_jobs SET status='paused', paused_at=?, updated_at=? "
                "WHERE id IN (SELECT job_id FROM archive_batch_items WHERE batch_id=?) "
                "AND status IN ('pending', 'retry')",
                (now, now, batch_id),
            )
            await self.set_status(batch_id, "paused")
        elif action == "resume":
            if batch.status != "paused":
                raise ValueError("batch is not paused")
            await self.db.execute(
                "UPDATE download_jobs SET status='pending', paused_at=NULL, "
                "next_attempt_at=?, updated_at=? WHERE id IN "
                "(SELECT job_id FROM archive_batch_items WHERE batch_id=?) "
                "AND status='paused'",
                (now, now, batch_id),
            )
            await self.set_status(batch_id, "running")
        elif action == "cancel":
            if batch.status in {"completed", "failed", "cancelled"}:
                raise ValueError("batch cannot be cancelled")
            await self.db.execute(
                "UPDATE download_jobs SET status='cancelled', cancel_requested_at=?, "
                "updated_at=? WHERE id IN "
                "(SELECT job_id FROM archive_batch_items WHERE batch_id=?) "
                "AND status IN ('pending', 'retry', 'paused')",
                (now, now, batch_id),
            )
            await self.set_status(batch_id, "cancelled")
        else:
            raise ValueError("unknown batch action")
        return await self.refresh_batch(batch_id)

    async def refresh_batch(self, batch_id: int) -> ArchiveBatch | None:
        batch = await self.get_batch(batch_id)
        if batch is None:
            return None
        rows = await self.db.fetchall(
            "SELECT bi.item_id, j.status AS job_status, "
            "COALESCE((SELECT SUM(CASE WHEN mf.status='ready' "
            "THEN COALESCE(mf.byte_size, mf.downloaded_bytes) "
            "ELSE mf.downloaded_bytes END) FROM media_files mf "
            "WHERE mf.item_id=bi.item_id), 0) AS downloaded_bytes, "
            "EXISTS(SELECT 1 FROM media_files ready WHERE ready.item_id=bi.item_id "
            "AND ready.status='ready') AS has_ready_media "
            "FROM archive_batch_items bi LEFT JOIN download_jobs j ON j.id=bi.job_id "
            "WHERE bi.batch_id=?",
            (batch_id,),
        )
        completed = sum(
            1
            for row in rows
            if row["job_status"] == "completed" or bool(row["has_ready_media"])
        )
        failed = sum(1 for row in rows if row["job_status"] == "failed")
        downloaded_bytes = sum(int(row["downloaded_bytes"]) for row in rows)
        if batch.status in {"paused", "cancelled"}:
            status = batch.status
        elif not rows or completed == len(rows):
            status = "completed"
        elif failed == len(rows):
            status = "failed"
        else:
            status = "running"
        now = int(time.time())
        finished_at = now if status in {"completed", "failed", "cancelled"} else None
        await self.db.execute(
            "UPDATE archive_batches SET status=?, discovered_count=?, "
            "completed_count=?, failed_count=?, downloaded_bytes=?, "
            "updated_at=?, finished_at=? WHERE id=?",
            (
                status,
                len(rows),
                completed,
                failed,
                downloaded_bytes,
                now,
                finished_at,
                batch_id,
            ),
        )
        return await self.get_batch(batch_id)

    async def upsert_subscription(
        self,
        creator_id: str,
        *,
        enabled: bool,
        scan_interval_seconds: int,
        archive_new_items: bool,
    ) -> CreatorSubscription:
        now = int(time.time())
        next_scan_at = now if enabled else None
        await self.db.execute(
            "INSERT INTO creator_subscriptions "
            "(creator_id, enabled, scan_interval_seconds, archive_new_items, "
            "next_scan_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(creator_id) DO UPDATE SET "
            "enabled=excluded.enabled, "
            "scan_interval_seconds=excluded.scan_interval_seconds, "
            "archive_new_items=excluded.archive_new_items, "
            "next_scan_at=CASE WHEN excluded.enabled=1 THEN "
            "COALESCE(creator_subscriptions.next_scan_at, excluded.next_scan_at) "
            "ELSE NULL END, updated_at=excluded.updated_at",
            (
                creator_id,
                int(enabled),
                scan_interval_seconds,
                int(archive_new_items),
                next_scan_at,
                now,
                now,
            ),
        )
        subscription = await self.get_subscription(creator_id)
        if subscription is None:
            raise RuntimeError("creator subscription upsert failed")
        return subscription

    async def get_subscription(self, creator_id: str) -> CreatorSubscription | None:
        row = await self.db.fetchone(
            "SELECT * FROM creator_subscriptions WHERE creator_id=?", (creator_id,)
        )
        if row is None:
            return None
        return CreatorSubscription(
            creator_id=str(row["creator_id"]),
            enabled=bool(row["enabled"]),
            scan_interval_seconds=int(row["scan_interval_seconds"]),
            archive_new_items=bool(row["archive_new_items"]),
            last_scan_at=(
                int(row["last_scan_at"]) if row["last_scan_at"] is not None else None
            ),
            next_scan_at=(
                int(row["next_scan_at"]) if row["next_scan_at"] is not None else None
            ),
            last_error_code=(
                str(row["last_error_code"])
                if row["last_error_code"] is not None
                else None
            ),
        )

    async def list_due_subscriptions(
        self, *, now: int | None = None, limit: int = 20
    ) -> list[CreatorSubscription]:
        due_at = int(time.time()) if now is None else now
        rows = await self.db.fetchall(
            "SELECT creator_id FROM creator_subscriptions "
            "WHERE enabled=1 AND next_scan_at IS NOT NULL AND next_scan_at<=? "
            "ORDER BY next_scan_at, creator_id LIMIT ?",
            (due_at, limit),
        )
        result: list[CreatorSubscription] = []
        for row in rows:
            subscription = await self.get_subscription(str(row["creator_id"]))
            if subscription is not None:
                result.append(subscription)
        return result

    async def finish_subscription_scan(
        self, creator_id: str, *, error_code: str | None = None
    ) -> CreatorSubscription | None:
        now = int(time.time())
        await self.db.execute(
            "UPDATE creator_subscriptions SET last_scan_at=?, "
            "next_scan_at=CASE WHEN enabled=1 THEN ? + scan_interval_seconds ELSE NULL END, "
            "last_error_code=?, updated_at=? WHERE creator_id=?",
            (now, now, error_code, now, creator_id),
        )
        return await self.get_subscription(creator_id)

    @staticmethod
    def _batch(row) -> ArchiveBatch:
        return ArchiveBatch(
            id=int(row["id"]),
            kind=str(row["kind"]),
            target_id=str(row["target_id"]),
            status=str(row["status"]),
            discovered_count=int(row["discovered_count"]),
            completed_count=int(row["completed_count"]),
            failed_count=int(row["failed_count"]),
            downloaded_bytes=int(row["downloaded_bytes"]),
            total_bytes=(int(row["total_bytes"]) if row["total_bytes"] is not None else None),
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
            total_items=int(row["total_items"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            finished_at=(int(row["finished_at"]) if row["finished_at"] is not None else None),
        )

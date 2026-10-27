from __future__ import annotations

import time
from collections.abc import Callable
from math import ceil
from typing import Any

from .archive_repository import ArchiveBatch, ArchiveBatchRepository
from .db import Database

ACTIVE_BATCH_STATUSES = ("queued", "discovering", "running", "paused")
# Throughput is averaged over this window so the ETA does not jump with every chunk.
RATE_WINDOW_SECONDS = 300
MIN_RATE_WINDOW_SECONDS = 30
CURRENT_LIMIT = 4
FAILURE_LIMIT = 20


async def batch_label(database: Database, batch: ArchiveBatch) -> str:
    """A name a person recognises instead of the raw target id."""
    if batch.kind == "missing":
        return "全部未存作品"
    if batch.kind == "selection":
        return f"手动选择的 {batch.total_items} 个作品"
    if batch.kind == "source":
        row = await database.fetchone(
            "SELECT name FROM library_sources WHERE id=?", (batch.target_id,)
        )
        return f"来源：{row['name']}" if row is not None else "来源"
    if batch.kind == "creator":
        row = await database.fetchone(
            "SELECT nickname FROM creators WHERE remote_id=?", (batch.target_id,)
        )
        return f"博主：{row['nickname']}" if row is not None else "博主"
    row = await database.fetchone(
        "SELECT description, author_name FROM items WHERE remote_id=?", (batch.target_id,)
    )
    if row is None:
        return "单个作品"
    return str(row["description"] or "").strip()[:40] or f"@{row['author_name']} 的作品"


class ArchiveProgressService:
    def __init__(self, database: Database, *, clock: Callable[[], float] = time.time) -> None:
        self.db = database
        self.clock = clock
        self.batches = ArchiveBatchRepository(database)

    async def snapshot(self) -> dict[str, Any]:
        now = int(self.clock())
        placeholders = ",".join("?" for _ in ACTIVE_BATCH_STATUSES)
        batch_rows = await self.db.fetchall(
            f"SELECT id FROM archive_batches WHERE status IN ({placeholders}) ORDER BY id",
            ACTIVE_BATCH_STATUSES,
        )
        active: list[ArchiveBatch] = []
        for row in batch_rows:
            batch = await self.batches.refresh_batch(int(row["id"]))
            if batch is not None and batch.status in ACTIVE_BATCH_STATUSES:
                active.append(batch)
        failures = await self._failures()
        return {
            "active": await self._active(active, now) if active else None,
            "failures": failures["items"],
            "failedTotal": failures["total"],
        }

    async def retry_failed(self) -> int:
        now = int(self.clock())
        cursor = await self.db.execute(
            "UPDATE download_jobs SET status='pending', attempts=0, last_error_code=NULL, "
            "next_attempt_at=?, claimed_by=NULL, updated_at=? "
            "WHERE kind='download' AND status='failed'",
            (now, now),
        )
        # A paused batch stays paused: its retried jobs wait with the rest of it.
        await self.db.execute(
            "UPDATE download_jobs SET status='paused', paused_at=? "
            "WHERE status='pending' AND id IN (SELECT bi.job_id FROM archive_batch_items bi "
            "JOIN archive_batches b ON b.id=bi.batch_id WHERE b.status='paused')",
            (now,),
        )
        # Batches that ended because of these failures are running again.
        rows = await self.db.fetchall(
            "SELECT id FROM archive_batches WHERE status='failed' OR "
            "(status='completed' AND failed_count > 0)"
        )
        for row in rows:
            await self.db.execute(
                "UPDATE archive_batches SET status='running', finished_at=NULL WHERE id=?",
                (int(row["id"]),),
            )
            await self.batches.refresh_batch(int(row["id"]))
        return int(cursor.rowcount or 0)

    async def _active(self, batches: list[ArchiveBatch], now: int) -> dict[str, Any]:
        ids = [batch.id for batch in batches]
        placeholders = ",".join("?" for _ in ids)
        rows = await self.db.fetchall(
            "SELECT bi.item_id, MAX(j.status) AS job_status, "
            "EXISTS(SELECT 1 FROM media_files r WHERE r.item_id=bi.item_id "
            "AND r.status='ready') AS ready, "
            "COALESCE((SELECT SUM(CASE WHEN mf.status='ready' "
            "THEN COALESCE(mf.byte_size, mf.downloaded_bytes) ELSE mf.downloaded_bytes END) "
            "FROM media_files mf WHERE mf.item_id=bi.item_id), 0) AS bytes "
            "FROM archive_batch_items bi LEFT JOIN download_jobs j ON j.id=bi.job_id "
            f"WHERE bi.batch_id IN ({placeholders}) GROUP BY bi.item_id",
            tuple(ids),
        )
        total = len(rows)
        completed = sum(1 for row in rows if row["ready"] or row["job_status"] == "completed")
        failed = sum(
            1 for row in rows if not row["ready"] and row["job_status"] == "failed"
        )
        running = sum(1 for row in rows if not row["ready"] and row["job_status"] == "running")
        waiting = max(0, total - completed - failed - running)
        completed_bytes = sum(int(row["bytes"]) for row in rows if row["ready"])
        downloaded_bytes = sum(int(row["bytes"]) for row in rows)

        average = await self.db.fetchone(
            "SELECT COUNT(DISTINCT item_id) AS items, COALESCE(SUM(byte_size), 0) AS bytes "
            "FROM media_files WHERE status='ready'"
        )
        average_bytes = (
            int(average["bytes"]) / int(average["items"])
            if average is not None and int(average["items"])
            else None
        )
        remaining_items = total - completed - failed
        estimated_total = (
            int(completed_bytes + average_bytes * (total - completed))
            if average_bytes is not None
            else None
        )

        started_at = min(batch.created_at for batch in batches)
        window = max(MIN_RATE_WINDOW_SECONDS, min(RATE_WINDOW_SECONDS, now - started_at))
        recent = await self.db.fetchone(
            "SELECT COALESCE(SUM(byte_size), 0) AS bytes, COUNT(DISTINCT item_id) AS items "
            "FROM media_files WHERE status='ready' AND updated_at >= ?",
            (now - window,),
        )
        rate_bps = int(recent["bytes"]) / window if recent is not None else 0.0
        items_per_minute = int(recent["items"]) * 60 / window if recent is not None else 0.0
        live = await self.db.fetchone(
            "SELECT COALESCE(SUM(speed_bps), 0) AS speed FROM media_files "
            "WHERE status='running' AND progress_updated_at >= ?",
            (now - 5,),
        )
        speed_bps = max(float(live["speed"]) if live is not None else 0.0, rate_bps)
        eta_seconds: int | None = None
        if remaining_items <= 0:
            eta_seconds = 0
        elif items_per_minute > 0:
            eta_seconds = ceil(remaining_items / items_per_minute * 60)
        elif estimated_total is not None and speed_bps > 0:
            eta_seconds = ceil(max(0, estimated_total - downloaded_bytes) / speed_bps)

        return {
            "status": "paused" if all(b.status == "paused" for b in batches) else "running",
            "batches": [
                {
                    "id": batch.id,
                    "kind": batch.kind,
                    "label": await batch_label(self.db, batch),
                    "status": batch.status,
                    "totalItems": batch.total_items,
                    "completedCount": batch.completed_count,
                    "failedCount": batch.failed_count,
                    "createdAt": batch.created_at,
                }
                for batch in batches
            ],
            "totalItems": total,
            "completedItems": completed,
            "failedItems": failed,
            "runningItems": running,
            "waitingItems": waiting,
            "downloadedBytes": downloaded_bytes,
            "estimatedTotalBytes": estimated_total,
            "speedBps": speed_bps,
            "itemsPerMinute": round(items_per_minute, 2),
            "etaSeconds": eta_seconds,
            "startedAt": started_at,
            "current": await self._current(ids),
        }

    async def _current(self, batch_ids: list[int]) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in batch_ids)
        rows = await self.db.fetchall(
            "SELECT DISTINCT j.remote_id, i.description, i.author_name, i.cover_url, "
            "COALESCE((SELECT SUM(mf.downloaded_bytes) FROM media_files mf "
            "WHERE mf.item_id=j.remote_id), 0) AS downloaded_bytes, "
            "(SELECT SUM(mf.total_bytes) FROM media_files mf "
            "WHERE mf.item_id=j.remote_id) AS total_bytes "
            "FROM download_jobs j JOIN archive_batch_items bi ON bi.job_id=j.id "
            "LEFT JOIN items i ON i.remote_id=j.remote_id "
            f"WHERE bi.batch_id IN ({placeholders}) AND j.status='running' "
            "ORDER BY j.updated_at DESC LIMIT ?",
            (*batch_ids, CURRENT_LIMIT),
        )
        return [
            {
                "remoteId": str(row["remote_id"]),
                "description": str(row["description"] or ""),
                "author": str(row["author_name"] or ""),
                "coverUrl": row["cover_url"],
                "downloadedBytes": int(row["downloaded_bytes"]),
                "totalBytes": int(row["total_bytes"]) if row["total_bytes"] is not None else None,
            }
            for row in rows
        ]

    async def _failures(self) -> dict[str, Any]:
        total = await self.db.fetchone(
            "SELECT COUNT(*) AS total FROM download_jobs "
            "WHERE kind='download' AND status='failed'"
        )
        rows = await self.db.fetchall(
            "SELECT j.remote_id, j.last_error_code, j.attempts, j.updated_at, "
            "i.description, i.author_name, i.cover_url FROM download_jobs j "
            "LEFT JOIN items i ON i.remote_id=j.remote_id "
            "WHERE j.kind='download' AND j.status='failed' "
            "ORDER BY j.updated_at DESC, j.id DESC LIMIT ?",
            (FAILURE_LIMIT,),
        )
        return {
            "total": int(total["total"]) if total is not None else 0,
            "items": [
                {
                    "remoteId": str(row["remote_id"]),
                    "description": str(row["description"] or ""),
                    "author": str(row["author_name"] or ""),
                    "coverUrl": row["cover_url"],
                    "errorCode": row["last_error_code"],
                    "attempts": int(row["attempts"]),
                    "failedAt": int(row["updated_at"]),
                }
                for row in rows
            ],
        }

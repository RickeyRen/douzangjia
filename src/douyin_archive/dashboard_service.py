from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .account_health import AccountHealthService
from .db import Database
from .download_monitor import DownloadMonitor
from .telemetry import system_snapshot

WINDOW_SECONDS = {"15m": 15 * 60, "24h": 24 * 60 * 60, "7d": 7 * 24 * 60 * 60}
DAY_SECONDS = 24 * 60 * 60
SHANGHAI = ZoneInfo("Asia/Shanghai")


class DashboardService:
    def __init__(
        self,
        database: Database,
        archive_root: Path,
        *,
        clock: Callable[[], int | float] = time.time,
        started_at: int | None = None,
    ) -> None:
        self.db = database
        self.archive_root = archive_root
        self.clock = clock
        self.started_at = int(clock()) if started_at is None else started_at

    async def source_progress(self) -> list[dict[str, object]]:
        rows = await self.db.fetchall(
            "SELECT ls.*, "
            "(SELECT COUNT(*) FROM source_items si WHERE si.source_id=ls.id) AS discovered, "
            "(SELECT COUNT(*) FROM source_items si WHERE si.source_id=ls.id "
            "AND EXISTS(SELECT 1 FROM media_files mf WHERE mf.item_id=si.item_id "
            "AND mf.status='ready')) AS archived, "
            "(SELECT COALESCE(SUM((SELECT COALESCE(SUM(mf.byte_size), 0) "
            "FROM media_files mf WHERE mf.item_id=si.item_id AND mf.status='ready')), 0) "
            "FROM source_items si WHERE si.source_id=ls.id) AS archived_bytes, "
            "(SELECT COUNT(*) FROM source_items si JOIN download_jobs j "
            "ON j.kind='download' AND j.remote_id=si.item_id "
            "WHERE si.source_id=ls.id AND j.status='pending') AS pending, "
            "(SELECT COUNT(*) FROM source_items si JOIN download_jobs j "
            "ON j.kind='download' AND j.remote_id=si.item_id "
            "WHERE si.source_id=ls.id AND j.status='running') AS running, "
            "(SELECT COUNT(*) FROM source_items si JOIN download_jobs j "
            "ON j.kind='download' AND j.remote_id=si.item_id "
            "WHERE si.source_id=ls.id AND j.status='retry') AS retry, "
            "(SELECT COUNT(*) FROM source_items si JOIN download_jobs j "
            "ON j.kind='download' AND j.remote_id=si.item_id "
            "WHERE si.source_id=ls.id AND j.status='failed') AS failed "
            "FROM library_sources ls ORDER BY CASE ls.kind "
            "WHEN 'post' THEN 0 WHEN 'recommend' THEN 1 WHEN 'like' THEN 2 "
            "WHEN 'favorite_video' THEN 3 WHEN 'favorite_collection' THEN 4 "
            "ELSE 10 END, ls.name, ls.id"
        )
        result: list[dict[str, object]] = []
        for row in rows:
            discovered = int(row["discovered"])
            archived = int(row["archived"])
            remote_total = (
                int(row["declared_count"])
                if row["declared_count"] is not None
                else None
            )
            result.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "autoDownloadEnabled": bool(row["auto_download_enabled"]),
                    "downloadPolicyUpdatedAt": row["download_policy_updated_at"],
                    "discovered": discovered,
                    "archived": archived,
                    "pending": int(row["pending"]),
                    "running": int(row["running"]),
                    "retry": int(row["retry"]),
                    "failed": int(row["failed"]),
                    "archivedBytes": int(row["archived_bytes"]),
                    "knownTotalBytes": int(row["archived_bytes"]),
                    "remoteTotal": remote_total,
                    "remoteComplete": bool(
                        remote_total is not None
                        and discovered == remote_total
                        and row["sync_status"] == "complete"
                    ),
                    "coveragePercent": (
                        round(archived / discovered * 100, 1) if discovered else 0.0
                    ),
                    "syncStatus": row["sync_status"],
                    "lastSyncAt": row["last_incremental_scan_at"]
                    or row["last_full_scan_at"],
                    "errorCode": row["error_code"],
                }
            )
        return result

    async def throughput(self, archive_bytes: int) -> dict[str, object]:
        now = int(self.clock())
        local_now = datetime.fromtimestamp(now, tz=SHANGHAI)
        today_start = int(
            local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        )
        history = await self.db.fetchone(
            "SELECT MIN(completed_at) AS started_at FROM media_files "
            "WHERE status='ready' AND completed_at IS NOT NULL"
        )
        history_started = (
            int(history["started_at"])
            if history is not None and history["started_at"] is not None
            else None
        )

        async def window(current_start: int, previous_start: int) -> dict[str, object]:
            row = await self.db.fetchone(
                "SELECT "
                "COALESCE(SUM(CASE WHEN completed_at>=? AND completed_at<? "
                "THEN byte_size ELSE 0 END), 0) AS current_bytes, "
                "COALESCE(SUM(CASE WHEN completed_at>=? AND completed_at<? "
                "THEN byte_size ELSE 0 END), 0) AS previous_bytes "
                "FROM media_files WHERE status='ready' AND byte_size IS NOT NULL",
                (current_start, now, previous_start, current_start),
            )
            current = int(row["current_bytes"]) if row is not None else 0
            previous = int(row["previous_bytes"]) if row is not None else 0
            return {
                "bytes": current,
                "previousBytes": previous,
                "deltaBytes": current - previous,
                "comparisonAvailable": bool(
                    history_started is not None and history_started <= previous_start
                ),
            }

        return {
            "today": await window(today_start, today_start - DAY_SECONDS),
            "sevenDays": await window(now - 7 * DAY_SECONDS, now - 14 * DAY_SECONDS),
            "thirtyDays": await window(
                now - 30 * DAY_SECONDS, now - 60 * DAY_SECONDS
            ),
            "lifetime": {"bytes": archive_bytes},
            "historyStartedAt": history_started,
        }

    async def snapshot(self) -> dict[str, object]:
        disk = shutil.disk_usage(self.archive_root)
        library = await self.db.fetchone(
            "SELECT (SELECT COUNT(*) FROM items) AS items, "
            "(SELECT COUNT(DISTINCT item_id) FROM media_files WHERE status='ready') "
            "AS archived_items, (SELECT COUNT(*) FROM media_files WHERE status='ready') "
            "AS media_files, (SELECT COUNT(*) FROM creators) AS creators, "
            "(SELECT COUNT(*) FROM library_sources) AS sources, "
            "(SELECT COUNT(*) FROM library_sources WHERE sync_status='complete') "
            "AS complete_sources, "
            "(SELECT COUNT(*) FROM library_sources WHERE sync_status IN "
            "('incomplete', 'failed')) AS incomplete_sources, "
            "(SELECT COUNT(*) FROM library_sources WHERE sync_status='never') "
            "AS never_sources, "
            "(SELECT COUNT(*) FROM source_items) + "
            "(SELECT COUNT(*) FROM source_entities) AS discovered_links, "
            "(SELECT COALESCE(SUM(byte_size), 0) FROM media_files WHERE status='ready') "
            "AS archived_bytes"
        )
        queue = (await DownloadMonitor(self.db).snapshot(limit=0))["summary"]
        recent_errors = await self.db.fetchone(
            "SELECT "
            "(SELECT COUNT(*) FROM download_jobs WHERE status IN ('failed', 'retry') "
            "AND last_error_code IS NOT NULL) + "
            "(SELECT COUNT(*) FROM sync_runs WHERE status='failed' "
            "AND started_at >= ?) AS total",
            (int(self.clock()) - 86_400,),
        )
        latest_sync = await self.db.fetchone(
            "SELECT id, mode, phase, status, discovered_count, enqueued_count, "
            "error_code, started_at, finished_at FROM sync_runs ORDER BY id DESC LIMIT 1"
        )
        archive_bytes = int(library["archived_bytes"]) if library is not None else 0
        generated_at = int(self.clock())
        return {
            "storage": {
                "totalBytes": disk.total,
                "usedBytes": disk.used,
                "freeBytes": disk.free,
                "archiveBytes": archive_bytes,
                "usedPercent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
            },
            "system": system_snapshot(),
            "library": {
                "items": int(library["items"]) if library is not None else 0,
                "archivedItems": (
                    int(library["archived_items"]) if library is not None else 0
                ),
                "mediaFiles": int(library["media_files"]) if library is not None else 0,
                "creators": int(library["creators"]) if library is not None else 0,
                "sources": int(library["sources"]) if library is not None else 0,
                "completeSources": (
                    int(library["complete_sources"]) if library is not None else 0
                ),
                "incompleteSources": (
                    int(library["incomplete_sources"]) if library is not None else 0
                ),
                "neverSyncedSources": (
                    int(library["never_sources"]) if library is not None else 0
                ),
                "discoveredLinks": (
                    int(library["discovered_links"]) if library is not None else 0
                ),
                "archivedBytes": archive_bytes,
            },
            "throughput": await self.throughput(archive_bytes),
            "queue": queue,
            "health": {
                "recentErrors": int(recent_errors["total"]) if recent_errors else 0,
                "uptimeSeconds": max(generated_at - self.started_at, 0),
                "latestSync": (
                    {
                        "id": latest_sync["id"],
                        "mode": latest_sync["mode"],
                        "phase": latest_sync["phase"],
                        "status": latest_sync["status"],
                        "discovered": latest_sync["discovered_count"],
                        "enqueued": latest_sync["enqueued_count"],
                        "errorCode": latest_sync["error_code"],
                        "startedAt": latest_sync["started_at"],
                        "finishedAt": latest_sync["finished_at"],
                    }
                    if latest_sync is not None
                    else None
                ),
            },
            "account": await AccountHealthService(self.db).snapshot(),
            "sources": await self.source_progress(),
            "generatedAt": generated_at,
        }

    async def series(self, window: str) -> list[dict[str, object]]:
        seconds = WINDOW_SECONDS.get(window)
        if seconds is None:
            raise ValueError("unsupported dashboard window")
        rows = await self.db.fetchall(
            "SELECT * FROM metric_samples WHERE sampled_at>=? "
            "ORDER BY sampled_at, id",
            (int(self.clock()) - seconds,),
        )
        return [
            {
                "sampledAt": int(row["sampled_at"]),
                "downloadSpeedBps": float(row["download_speed_bps"]),
                "downloadedBytes": int(row["downloaded_bytes"]),
                "cpuLoadPercent": float(row["cpu_load_percent"]),
                "memoryUsedBytes": int(row["memory_used_bytes"]),
                "processMemoryBytes": int(row["process_memory_bytes"]),
                "diskUsedBytes": int(row["disk_used_bytes"]),
                "diskFreeBytes": int(row["disk_free_bytes"]),
                "archiveBytes": int(row["archive_bytes"]),
            }
            for row in rows
        ]

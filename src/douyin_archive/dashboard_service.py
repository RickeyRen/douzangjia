from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

from .account_health import AccountHealthService
from .db import Database
from .download_monitor import DownloadMonitor
from .telemetry import system_snapshot

WINDOW_SECONDS = {"15m": 15 * 60, "24h": 24 * 60 * 60, "7d": 7 * 24 * 60 * 60}


class DashboardService:
    def __init__(
        self,
        database: Database,
        archive_root: Path,
        *,
        clock: Callable[[], int | float] = time.time,
    ) -> None:
        self.db = database
        self.archive_root = archive_root
        self.clock = clock

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

    async def snapshot(self) -> dict[str, object]:
        disk = shutil.disk_usage(self.archive_root)
        library = await self.db.fetchone(
            "SELECT (SELECT COUNT(*) FROM items) AS items, "
            "(SELECT COUNT(DISTINCT item_id) FROM media_files WHERE status='ready') "
            "AS archived_items, (SELECT COUNT(*) FROM media_files WHERE status='ready') "
            "AS media_files, (SELECT COUNT(*) FROM creators) AS creators, "
            "(SELECT COUNT(*) FROM library_sources) AS sources, "
            "(SELECT COALESCE(SUM(byte_size), 0) FROM media_files WHERE status='ready') "
            "AS archived_bytes"
        )
        queue = (await DownloadMonitor(self.db).snapshot(limit=0))["summary"]
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
                "archivedBytes": archive_bytes,
            },
            "queue": queue,
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

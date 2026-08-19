from __future__ import annotations

import os
import resource
import shutil
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Request

from ..download_monitor import DownloadMonitor

router = APIRouter(prefix="/api")


def _proc_memory_bytes() -> int:
    status = Path("/proc/self/status")
    if status.is_file():
        try:
            for line in status.read_text(encoding="utf-8").splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass
    maximum = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return maximum if sys.platform == "darwin" else maximum * 1024


def _system_memory() -> tuple[int, int]:
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        values: dict[str, int] = {}
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
        except (OSError, ValueError, IndexError):
            values = {}
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
        return total, max(total - available, 0)
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total = int(os.sysconf("SC_PHYS_PAGES")) * page_size
        available = int(os.sysconf("SC_AVPHYS_PAGES")) * page_size
        return total, max(total - available, 0)
    except (OSError, ValueError):
        return 0, 0


def _system_snapshot() -> dict[str, object]:
    cpu_count = os.cpu_count() or 1
    try:
        load_1, load_5, load_15 = os.getloadavg()
    except OSError:
        load_1 = load_5 = load_15 = 0.0
    memory_total, memory_used = _system_memory()
    return {
        "cpuCount": cpu_count,
        "cpuLoadPercent": round(min(max(load_1 / cpu_count * 100, 0), 100), 1),
        "loadAverage1m": round(load_1, 2),
        "loadAverage5m": round(load_5, 2),
        "loadAverage15m": round(load_15, 2),
        "memoryTotalBytes": memory_total,
        "memoryUsedBytes": memory_used,
        "processMemoryBytes": _proc_memory_bytes(),
    }


@router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, object]:
    database = request.app.state.database
    settings = request.app.state.settings
    disk = shutil.disk_usage(settings.archive_root)
    library = await database.fetchone(
        "SELECT "
        "(SELECT COUNT(*) FROM items) AS items, "
        "(SELECT COUNT(DISTINCT item_id) FROM media_files WHERE status='ready') "
        "AS archived_items, "
        "(SELECT COUNT(*) FROM creators) AS creators, "
        "(SELECT COUNT(*) FROM library_sources) AS sources, "
        "(SELECT COUNT(*) FROM library_sources WHERE sync_status='complete') "
        "AS complete_sources, "
        "(SELECT COUNT(*) FROM library_sources WHERE sync_status IN ('incomplete', 'failed')) "
        "AS incomplete_sources, "
        "(SELECT COUNT(*) FROM library_sources WHERE sync_status='never') "
        "AS never_sources, "
        "(SELECT COUNT(*) FROM source_items) + "
        "(SELECT COUNT(*) FROM source_entities) AS discovered_links, "
        "(SELECT COALESCE(SUM(byte_size), 0) FROM media_files WHERE status='ready') "
        "AS archived_bytes"
    )
    queue = (await DownloadMonitor(database).snapshot(limit=0))["summary"]
    recent_errors = await database.fetchone(
        "SELECT "
        "(SELECT COUNT(*) FROM download_jobs WHERE status IN ('failed', 'retry') "
        "AND last_error_code IS NOT NULL) + "
        "(SELECT COUNT(*) FROM sync_runs WHERE status='failed' "
        "AND started_at >= ?) AS total",
        (int(time.time()) - 86_400,),
    )
    latest_sync = await database.fetchone(
        "SELECT id, mode, phase, status, discovered_count, enqueued_count, "
        "error_code, started_at, finished_at FROM sync_runs ORDER BY id DESC LIMIT 1"
    )
    archived_bytes = int(library["archived_bytes"]) if library is not None else 0
    generated_at = int(time.time())
    return {
        "storage": {
            "totalBytes": disk.total,
            "usedBytes": disk.used,
            "freeBytes": disk.free,
            "archiveBytes": archived_bytes,
            "usedPercent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
        },
        "system": _system_snapshot(),
        "library": {
            "items": int(library["items"]) if library is not None else 0,
            "archivedItems": int(library["archived_items"]) if library is not None else 0,
            "creators": int(library["creators"]) if library is not None else 0,
            "sources": int(library["sources"]) if library is not None else 0,
            "completeSources": int(library["complete_sources"]) if library is not None else 0,
            "incompleteSources": int(library["incomplete_sources"]) if library is not None else 0,
            "neverSyncedSources": int(library["never_sources"]) if library is not None else 0,
            "discoveredLinks": int(library["discovered_links"]) if library is not None else 0,
            "archivedBytes": archived_bytes,
        },
        "queue": queue,
        "health": {
            "recentErrors": int(recent_errors["total"]) if recent_errors else 0,
            "uptimeSeconds": max(
                generated_at - int(getattr(request.app.state, "started_at", generated_at)),
                0,
            ),
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
        "generatedAt": generated_at,
    }

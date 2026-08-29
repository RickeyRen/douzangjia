from __future__ import annotations

import os
import resource
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .db import Database
from .download_monitor import DownloadMonitor


@dataclass(frozen=True, slots=True)
class MetricSample:
    sampled_at: int
    download_speed_bps: float = 0
    downloaded_bytes: int = 0
    queue_pending: int = 0
    queue_running: int = 0
    queue_retry: int = 0
    queue_failed: int = 0
    cpu_load_percent: float = 0
    memory_used_bytes: int = 0
    process_memory_bytes: int = 0
    disk_used_bytes: int = 0
    disk_free_bytes: int = 0
    archive_bytes: int = 0
    recent_errors: int = 0
    resolution: str = "raw"


def process_memory_bytes() -> int:
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


def _process_rss_bytes(pid: int, proc_root: Path) -> int:
    try:
        lines = (proc_root / str(pid) / "status").read_text(
            encoding="utf-8"
        ).splitlines()
    except OSError:
        return 0
    for line in lines:
        if line.startswith("VmRSS:"):
            try:
                return int(line.split()[1]) * 1024
            except (ValueError, IndexError):
                return 0
    return 0


def process_tree_snapshot(
    *,
    root_pid: int | None = None,
    proc_root: Path = Path("/proc"),
) -> dict[str, int]:
    """Return RSS for actual Chromium descendants of the application process."""
    root = os.getpid() if root_pid is None else root_pid
    pending = [root]
    visited: set[int] = set()
    browser_count = 0
    browser_memory = 0
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        try:
            children = (
                proc_root / str(pid) / "task" / str(pid) / "children"
            ).read_text(encoding="utf-8")
            pending.extend(int(value) for value in children.split())
        except (OSError, ValueError):
            pass
        if pid == root:
            continue
        try:
            command = (proc_root / str(pid) / "cmdline").read_bytes().replace(
                b"\0", b" "
            ).decode("utf-8", errors="ignore").lower()
        except OSError:
            continue
        if "chromium" not in command and "chrome" not in command:
            continue
        browser_count += 1
        browser_memory += _process_rss_bytes(pid, proc_root)
    return {
        "browserProcessCount": browser_count,
        "browserMemoryBytes": browser_memory,
    }


def system_memory() -> tuple[int, int]:
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


def system_snapshot() -> dict[str, object]:
    cpu_count = os.cpu_count() or 1
    try:
        load_1, load_5, load_15 = os.getloadavg()
    except OSError:
        load_1 = load_5 = load_15 = 0.0
    memory_total, memory_used = system_memory()
    return {
        "cpuCount": cpu_count,
        "cpuLoadPercent": round(min(max(load_1 / cpu_count * 100, 0), 100), 1),
        "loadAverage1m": round(load_1, 2),
        "loadAverage5m": round(load_5, 2),
        "loadAverage15m": round(load_15, 2),
        "memoryTotalBytes": memory_total,
        "memoryUsedBytes": memory_used,
        "processMemoryBytes": process_memory_bytes(),
        **process_tree_snapshot(),
    }


class TelemetrySampler:
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

    async def record(self, sample: MetricSample) -> None:
        await self.db.execute(
            "INSERT INTO metric_samples "
            "(resolution, sampled_at, download_speed_bps, downloaded_bytes, "
            "queue_pending, queue_running, queue_retry, queue_failed, cpu_load_percent, "
            "memory_used_bytes, process_memory_bytes, disk_used_bytes, disk_free_bytes, "
            "archive_bytes, recent_errors) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(resolution, sampled_at) DO UPDATE SET "
            "download_speed_bps=excluded.download_speed_bps, "
            "downloaded_bytes=excluded.downloaded_bytes, "
            "queue_pending=excluded.queue_pending, queue_running=excluded.queue_running, "
            "queue_retry=excluded.queue_retry, queue_failed=excluded.queue_failed, "
            "cpu_load_percent=excluded.cpu_load_percent, "
            "memory_used_bytes=excluded.memory_used_bytes, "
            "process_memory_bytes=excluded.process_memory_bytes, "
            "disk_used_bytes=excluded.disk_used_bytes, "
            "disk_free_bytes=excluded.disk_free_bytes, "
            "archive_bytes=excluded.archive_bytes, recent_errors=excluded.recent_errors",
            (
                sample.resolution,
                sample.sampled_at,
                sample.download_speed_bps,
                sample.downloaded_bytes,
                sample.queue_pending,
                sample.queue_running,
                sample.queue_retry,
                sample.queue_failed,
                sample.cpu_load_percent,
                sample.memory_used_bytes,
                sample.process_memory_bytes,
                sample.disk_used_bytes,
                sample.disk_free_bytes,
                sample.archive_bytes,
                sample.recent_errors,
            ),
        )

    async def sample(self) -> MetricSample:
        sampled_at = int(self.clock())
        queue = (await DownloadMonitor(self.db).snapshot(limit=0))["summary"]
        archive = await self.db.fetchone(
            "SELECT COALESCE(SUM(byte_size), 0) AS total "
            "FROM media_files WHERE status='ready'"
        )
        errors = await self.db.fetchone(
            "SELECT COUNT(*) AS total FROM download_jobs "
            "WHERE status IN ('failed', 'retry') AND last_error_code IS NOT NULL"
        )
        disk = shutil.disk_usage(self.archive_root)
        system = system_snapshot()
        result = MetricSample(
            sampled_at=sampled_at,
            download_speed_bps=float(queue["speedBps"]),
            downloaded_bytes=int(queue["downloadedBytes"]),
            queue_pending=int(queue["pending"]),
            queue_running=int(queue["running"]),
            queue_retry=int(queue["retry"]),
            queue_failed=int(queue["failed"]),
            cpu_load_percent=float(system["cpuLoadPercent"]),
            memory_used_bytes=int(system["memoryUsedBytes"]),
            process_memory_bytes=int(system["processMemoryBytes"]),
            disk_used_bytes=disk.used,
            disk_free_bytes=disk.free,
            archive_bytes=int(archive["total"]) if archive is not None else 0,
            recent_errors=int(errors["total"]) if errors is not None else 0,
        )
        await self.record(result)
        return result

    async def prune(self) -> None:
        now = int(self.clock())
        raw_cutoff = now - 24 * 60 * 60
        await self.db.execute(
            "INSERT INTO metric_samples "
            "(resolution, sampled_at, download_speed_bps, downloaded_bytes, "
            "queue_pending, queue_running, queue_retry, queue_failed, cpu_load_percent, "
            "memory_used_bytes, process_memory_bytes, disk_used_bytes, disk_free_bytes, "
            "archive_bytes, recent_errors) "
            "SELECT 'minute', CAST(sampled_at / 60 AS INTEGER) * 60, "
            "AVG(download_speed_bps), MAX(downloaded_bytes), MAX(queue_pending), "
            "MAX(queue_running), MAX(queue_retry), MAX(queue_failed), "
            "AVG(cpu_load_percent), CAST(AVG(memory_used_bytes) AS INTEGER), "
            "CAST(AVG(process_memory_bytes) AS INTEGER), MAX(disk_used_bytes), "
            "MIN(disk_free_bytes), MAX(archive_bytes), MAX(recent_errors) "
            "FROM metric_samples WHERE resolution='raw' AND sampled_at<? "
            "GROUP BY CAST(sampled_at / 60 AS INTEGER) "
            "ON CONFLICT(resolution, sampled_at) DO UPDATE SET "
            "download_speed_bps=excluded.download_speed_bps, "
            "downloaded_bytes=excluded.downloaded_bytes, "
            "queue_pending=excluded.queue_pending, queue_running=excluded.queue_running, "
            "queue_retry=excluded.queue_retry, queue_failed=excluded.queue_failed, "
            "cpu_load_percent=excluded.cpu_load_percent, "
            "memory_used_bytes=excluded.memory_used_bytes, "
            "process_memory_bytes=excluded.process_memory_bytes, "
            "disk_used_bytes=excluded.disk_used_bytes, "
            "disk_free_bytes=excluded.disk_free_bytes, "
            "archive_bytes=excluded.archive_bytes, recent_errors=excluded.recent_errors",
            (raw_cutoff,),
        )
        await self.db.execute(
            "DELETE FROM metric_samples WHERE resolution='raw' AND sampled_at<?",
            (raw_cutoff,),
        )
        minute_cutoff = now - 30 * 24 * 60 * 60
        await self.db.execute(
            "INSERT INTO metric_samples "
            "(resolution, sampled_at, download_speed_bps, downloaded_bytes, "
            "queue_pending, queue_running, queue_retry, queue_failed, cpu_load_percent, "
            "memory_used_bytes, process_memory_bytes, disk_used_bytes, disk_free_bytes, "
            "archive_bytes, recent_errors) "
            "SELECT 'hour', CAST(sampled_at / 3600 AS INTEGER) * 3600, "
            "AVG(download_speed_bps), MAX(downloaded_bytes), MAX(queue_pending), "
            "MAX(queue_running), MAX(queue_retry), MAX(queue_failed), "
            "AVG(cpu_load_percent), CAST(AVG(memory_used_bytes) AS INTEGER), "
            "CAST(AVG(process_memory_bytes) AS INTEGER), MAX(disk_used_bytes), "
            "MIN(disk_free_bytes), MAX(archive_bytes), MAX(recent_errors) "
            "FROM metric_samples WHERE resolution='minute' AND sampled_at<? "
            "GROUP BY CAST(sampled_at / 3600 AS INTEGER) "
            "ON CONFLICT(resolution, sampled_at) DO UPDATE SET "
            "download_speed_bps=excluded.download_speed_bps, "
            "downloaded_bytes=excluded.downloaded_bytes, "
            "queue_pending=excluded.queue_pending, queue_running=excluded.queue_running, "
            "queue_retry=excluded.queue_retry, queue_failed=excluded.queue_failed, "
            "cpu_load_percent=excluded.cpu_load_percent, "
            "memory_used_bytes=excluded.memory_used_bytes, "
            "process_memory_bytes=excluded.process_memory_bytes, "
            "disk_used_bytes=excluded.disk_used_bytes, "
            "disk_free_bytes=excluded.disk_free_bytes, "
            "archive_bytes=excluded.archive_bytes, recent_errors=excluded.recent_errors",
            (minute_cutoff,),
        )
        await self.db.execute(
            "DELETE FROM metric_samples WHERE resolution='minute' AND sampled_at<?",
            (minute_cutoff,),
        )

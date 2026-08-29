from __future__ import annotations

import os
import resource
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..dashboard_events import dashboard_event_stream
from ..dashboard_service import DashboardService

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
    runtime_owner = getattr(request.app.state, "runtime", None)
    runtime = runtime_owner.dashboard_runtime() if runtime_owner is not None else None
    return await DashboardService(
        request.app.state.database,
        request.app.state.settings.archive_root,
        started_at=int(getattr(request.app.state, "started_at", time.time())),
    ).snapshot(runtime=runtime)


@router.get("/dashboard/series")
async def dashboard_series(
    request: Request,
    window: str = Query(default="24h", pattern="^(15m|24h|7d)$"),
) -> dict[str, object]:
    service = DashboardService(
        request.app.state.database,
        request.app.state.settings.archive_root,
        started_at=int(getattr(request.app.state, "started_at", time.time())),
    )
    return {"window": window, "items": await service.series(window)}


@router.get("/events")
async def dashboard_events(request: Request) -> StreamingResponse:
    service = DashboardService(
        request.app.state.database,
        request.app.state.settings.archive_root,
        started_at=int(getattr(request.app.state, "started_at", time.time())),
    )

    async def load_snapshot() -> dict[str, object]:
        runtime_owner = getattr(request.app.state, "runtime", None)
        runtime = (
            runtime_owner.dashboard_runtime() if runtime_owner is not None else None
        )
        return await service.snapshot(runtime=runtime)

    return StreamingResponse(
        dashboard_event_stream(
            load_snapshot, request.app.state.dashboard_events, refresh_seconds=1.0
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )

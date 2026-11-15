from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api")


def _snapshot(source: Path, target: Path) -> None:
    """Consistent copy via the SQLite backup API; safe while the app writes."""
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as origin, sqlite3.connect(target) as copy:
        origin.backup(copy)


def _backups(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    backups = getattr(runtime, "database_backups", None)
    if backups is None:
        from ..db_backup import DatabaseBackups

        root: Path = request.app.state.settings.archive_root
        backups = DatabaseBackups(root / "data" / "archive.sqlite3", root / "data" / "backups")
    return backups


def _tree_size(path: Path) -> tuple[int, int]:
    total = files = 0
    if not path.is_dir():
        return 0, 0
    for folder, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += (Path(folder) / name).stat().st_size
                files += 1
            except OSError:
                continue
    return total, files


def _disk_and_files(root: Path) -> dict:
    from ..notifier import DISK_LOW_FREE_BYTES, DISK_LOW_FREE_PERCENT

    try:
        usage = shutil.disk_usage(root)
        percent = usage.free / usage.total * 100 if usage.total else 100.0
        disk = {
            "totalBytes": usage.total,
            "freeBytes": usage.free,
            "usedBytes": usage.used,
            "low": usage.free < DISK_LOW_FREE_BYTES or percent < DISK_LOW_FREE_PERCENT,
        }
    except OSError:
        disk = None
    data = root / "data"
    database = sum(
        (data / name).stat().st_size
        for name in ("archive.sqlite3", "archive.sqlite3-wal")
        if (data / name).is_file()
    )
    backups, backup_count = _tree_size(data / "backups")
    quarantine, quarantine_files = _tree_size(root / "quarantine")
    return {
        "disk": disk,
        "database": {"bytes": database},
        "backups": {"bytes": backups, "count": backup_count},
        "quarantine": {"bytes": quarantine, "files": quarantine_files},
    }


@router.get("/storage")
async def storage_usage(request: Request):
    """Where the NAS space goes: saved media, the database, its backups, quarantine."""
    root: Path = request.app.state.settings.archive_root
    row = await request.app.state.database.fetchone(
        "SELECT COUNT(*) AS files, COALESCE(SUM(byte_size), 0) AS total, "
        "COALESCE(SUM(CASE WHEN media_type='video' THEN byte_size END), 0) AS videos, "
        "COALESCE(SUM(CASE WHEN media_type='image' THEN byte_size END), 0) AS images "
        "FROM media_files WHERE status='ready'"
    )
    files = await asyncio.to_thread(_disk_and_files, root)
    total = int(row["total"]) if row else 0
    videos = int(row["videos"]) if row else 0
    images = int(row["images"]) if row else 0
    return {
        "media": {
            "files": int(row["files"]) if row else 0,
            "bytes": total,
            "videoBytes": videos,
            "imageBytes": images,
            "otherBytes": max(0, total - videos - images),
        },
        **files,
    }


@router.get("/backup/status")
async def backup_status(request: Request):
    return await asyncio.to_thread(_backups(request).summary)


@router.post("/backup/now")
async def backup_now(request: Request):
    backups = _backups(request)
    created = await backups.backup_now()
    if created is None:
        return JSONResponse(
            status_code=500,
            content={"code": "BACKUP_FAILED", "message": backups.last_error or "备份没有完成"},
        )
    return await asyncio.to_thread(backups.summary)


@router.get("/backup/database")
async def download_database(request: Request, background: BackgroundTasks):
    root: Path = request.app.state.settings.archive_root
    source = root / "data" / "archive.sqlite3"
    if not source.is_file():
        return JSONResponse(status_code=404, content={"code": "DATABASE_MISSING", "message": "还没有数据库"})
    stamp = time.strftime("%Y%m%d-%H%M%S")
    temporary = root / "tmp" / f"backup-{stamp}.sqlite3"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_snapshot, source, temporary)
    background.add_task(temporary.unlink, missing_ok=True)
    return FileResponse(
        temporary,
        media_type="application/vnd.sqlite3",
        filename=f"douzangjia-{stamp}.sqlite3",
        headers={"Cache-Control": "no-store"},
    )

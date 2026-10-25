from __future__ import annotations

import asyncio
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

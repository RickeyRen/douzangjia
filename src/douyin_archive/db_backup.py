from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

import anyio

logger = logging.getLogger(__name__)

RUN_EVERY_SECONDS = 3600
BACKUP_EVERY_SECONDS = 24 * 3600
KEEP_BACKUPS = 7
PREFIX = "auto-"
# Copy in slices so the app's own writers are never blocked for long.
PAGES_PER_STEP = 4096


def _copy(source: Path, target: Path) -> None:
    partial = target.with_name(target.name + ".part")
    partial.unlink(missing_ok=True)
    # closing(): a sqlite3 connection used as a context manager only commits, it
    # stays open. The copy also inherits the source's WAL mode, so renaming it
    # while open left .part-wal / .part-shm files behind every day.
    with (
        closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as origin,
        closing(sqlite3.connect(partial)) as copy,
    ):
        origin.backup(copy, pages=PAGES_PER_STEP, sleep=0.02)
        # One self-contained file that can be copied off the NAS as it is.
        copy.execute("PRAGMA journal_mode=DELETE")
        # A backup nobody can open is worse than none: prove it reads back.
        verdict = copy.execute("PRAGMA quick_check").fetchone()[0]
    if verdict != "ok":
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"database backup failed its check: {verdict}")
    partial.rename(target)


def _clear_litter(backup_dir: Path) -> None:
    """Remove half-written copies and SQLite sidecars of our own copies (never other files)."""
    for path in backup_dir.glob(f"{PREFIX}*"):
        if path.name.endswith((".part", ".part-wal", ".part-shm", ".part-journal")):
            path.unlink(missing_ok=True)


def created_at(path: Path) -> int:
    """When a copy was made, from its name (file times change when NAS tools copy it)."""
    try:
        return int(time.mktime(time.strptime(path.stem[len(PREFIX):], "%Y%m%d-%H%M%S")))
    except ValueError:
        return int(path.stat().st_mtime)


class DatabaseBackups:
    """A daily, self-checked copy of the library database, the last week kept.

    Media files can be downloaded again from Douyin; albums, tags, notes, stars
    and the record of vanished works live only in this database.
    """

    def __init__(
        self,
        database_path: Path,
        backup_dir: Path,
        *,
        keep: int = KEEP_BACKUPS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database_path = database_path
        self.backup_dir = backup_dir
        self.keep = keep
        self.clock = clock
        self.last_error: str | None = None

    def backups(self) -> list[Path]:
        """Our own daily copies, newest first (manual and pre-deploy ones are left alone)."""
        if not self.backup_dir.is_dir():
            return []
        return sorted(self.backup_dir.glob(f"{PREFIX}*.sqlite3"), key=lambda path: path.name, reverse=True)

    async def run_tick(self) -> Path | None:
        newest = self.backups()
        if newest and self.clock() - created_at(newest[0]) < BACKUP_EVERY_SECONDS:
            return None
        return await self.backup_now()

    async def backup_now(self) -> Path | None:
        if not self.database_path.is_file():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.clock()))
        target = self.backup_dir / f"{PREFIX}{stamp}.sqlite3"
        try:
            await anyio.to_thread.run_sync(_copy, self.database_path, target)
        except Exception as error:  # a failed backup must not take the worker down
            self.last_error = str(error)
            logger.warning("database backup failed", exc_info=True)
            return None
        self.last_error = None
        _clear_litter(self.backup_dir)
        for stale in self.backups()[self.keep :]:
            stale.unlink(missing_ok=True)
        logger.info("database backed up to %s", target.name)
        return target

    def summary(self) -> dict[str, Any]:
        copies = self.backups()
        return {
            "directory": "data/backups",
            "keep": self.keep,
            "lastError": self.last_error,
            "backups": [
                {"name": path.name, "bytes": path.stat().st_size, "createdAt": created_at(path)}
                for path in copies
            ],
        }

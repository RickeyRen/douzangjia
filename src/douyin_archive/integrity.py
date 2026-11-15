from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio

from .db import Database
from .worker import MEDIA_URL_EXPIRED

logger = logging.getLogger(__name__)

RUN_EVERY_SECONDS = 60
# Hashing reads every byte, and the NAS disk is shared with downloads and other
# services: a quarter GB a minute walks a 300 GB archive in under a day.
MAX_FILES_PER_RUN = 40
MAX_BYTES_PER_RUN = 256 * 1024 * 1024
# A full re-check of everything this often; new files are checked first.
RECHECK_AFTER_SECONDS = 30 * 24 * 3600
# Fast pass: only "is it there, is the size right". Stats are cheap, so the
# whole archive is covered within the first hour, then again every day.
PRESENCE_FILES_PER_RUN = 2000
PRESENCE_RECHECK_SECONDS = 24 * 3600
QUARANTINE_DIR = "quarantine"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ArchiveVerifier:
    """Slowly confirm every saved file is still on disk and unchanged.

    A file that went missing or no longer matches its checksum is moved aside
    (never deleted), marked unsaved and its download is queued again; the link
    refresher fetches a fresh URL for it like any other expired download.
    """

    def __init__(
        self,
        database: Database,
        archive_root: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = database
        self.archive_root = archive_root.resolve()
        self.clock = clock

    async def run_batch(self) -> int:
        await self.run_presence_pass()
        return await self.run_checksum_pass()

    async def run_presence_pass(self) -> int:
        now = int(self.clock())
        rows = await self.db.fetchall(
            "SELECT id, item_id, relative_path, byte_size FROM media_files "
            "WHERE status='ready' AND relative_path IS NOT NULL "
            "AND (present_at IS NULL OR present_at < ?) "
            "ORDER BY present_at IS NOT NULL, present_at, id LIMIT ?",
            (now - PRESENCE_RECHECK_SECONDS, PRESENCE_FILES_PER_RUN),
        )
        if not rows:
            return 0
        results = await anyio.to_thread.run_sync(self._check_presence, [dict(row) for row in rows])
        stamp = int(self.clock())
        async with self.db.transaction(immediate=True):
            for row, problem in results:
                if problem is None:
                    await self.db.execute(
                        "UPDATE media_files SET present_at=? WHERE id=?", (stamp, row["id"])
                    )
                else:
                    await self._mark_for_repair(row, problem, stamp)
        return len(results)

    def _check_presence(self, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str | None]]:
        results: list[tuple[dict[str, Any], str | None]] = []
        for row in rows:
            problem = self._check(row, hash_contents=False)
            if problem == "corrupt":
                self._quarantine(row)
            results.append((row, problem))
        return results

    async def run_checksum_pass(self) -> int:
        now = int(self.clock())
        rows = await self.db.fetchall(
            "SELECT id, item_id, relative_path, byte_size, checksum_sha256 FROM media_files "
            "WHERE status='ready' AND relative_path IS NOT NULL "
            "AND (verified_at IS NULL OR verified_at < ?) "
            "ORDER BY verified_at IS NOT NULL, verified_at, id LIMIT ?",
            (now - RECHECK_AFTER_SECONDS, MAX_FILES_PER_RUN),
        )
        if not rows:
            return 0
        # All disk work happens off the event loop: on a busy NAS a single stat
        # can stall for seconds, and every request would wait behind it.
        results = await anyio.to_thread.run_sync(self._check_files, [dict(row) for row in rows])
        stamp = int(self.clock())
        async with self.db.transaction(immediate=True):
            for row, problem in results:
                if problem is None:
                    await self.db.execute(
                        "UPDATE media_files SET verified_at=?, present_at=?, verify_status='ok' "
                        "WHERE id=?",
                        (stamp, stamp, row["id"]),
                    )
                else:
                    await self._mark_for_repair(row, problem, stamp)
        return len(results)

    def _check_files(self, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str | None]]:
        results: list[tuple[dict[str, Any], str | None]] = []
        budget = MAX_BYTES_PER_RUN
        for row in rows:
            if budget <= 0:
                break
            problem = self._check(row)
            budget -= int(row["byte_size"] or 0)
            if problem == "corrupt":
                self._quarantine(row)
            results.append((row, problem))
        return results

    def _check(self, row: dict[str, Any], *, hash_contents: bool = True) -> str | None:
        path = self.archive_root / str(row["relative_path"])
        if not path.is_file():
            return "missing"
        if row["byte_size"] is not None and path.stat().st_size != int(row["byte_size"]):
            return "corrupt"
        if hash_contents and row["checksum_sha256"] and _sha256(path) != row["checksum_sha256"]:
            return "corrupt"
        return None

    def _quarantine(self, row: dict[str, Any]) -> None:
        # Keep the damaged copy for the owner to inspect; the downloader would
        # otherwise take the existing file as already saved.
        path = self.archive_root / str(row["relative_path"])
        if path.is_file():
            target = self.archive_root / QUARANTINE_DIR / f"{row['relative_path']}.{int(self.clock())}"
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)

    async def _mark_for_repair(self, row: dict[str, Any], problem: str, now: int) -> None:
        logger.warning(
            "saved file %s for item %s is %s; downloading it again",
            row["relative_path"],
            row["item_id"],
            problem,
        )
        await self.db.execute(
            # verified_at is cleared so the fresh copy is checked as soon as it lands.
            "UPDATE media_files SET status='pending', verify_status=?, verify_failed_at=?, "
            "verified_at=NULL, present_at=NULL, downloaded_bytes=0, updated_at=? WHERE id=?",
            (problem, now, now, row["id"]),
        )
        # The old link has long expired; queue it as one so a fresh URL is fetched.
        await self.db.execute(
            "UPDATE download_jobs SET status='retry', attempts=0, claimed_by=NULL, "
            "last_error_code=?, next_attempt_at=?, updated_at=? "
            "WHERE kind='download' AND remote_id=? AND status IN ('completed', 'failed')",
            (MEDIA_URL_EXPIRED, now, now, row["item_id"]),
        )

    async def summary(self) -> dict[str, Any]:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(verified_at IS NOT NULL), 0) AS verified, "
            "COALESCE(SUM(present_at IS NOT NULL OR verified_at IS NOT NULL), 0) AS present, "
            "MIN(COALESCE(present_at, verified_at)) AS oldest_present, "
            "MIN(verified_at) AS oldest, MAX(verified_at) AS latest, "
            "COALESCE(SUM(verify_failed_at IS NOT NULL), 0) AS repaired "
            "FROM media_files WHERE status='ready' AND relative_path IS NOT NULL"
        )
        broken = await self.db.fetchone(
            "SELECT COUNT(*) AS broken FROM media_files "
            "WHERE status!='ready' AND verify_status IN ('missing', 'corrupt')"
        )
        total = int(row["total"]) if row else 0
        verified = int(row["verified"]) if row else 0
        return {
            "totalFiles": total,
            "verifiedFiles": verified,
            # Fast pass: seen on disk with the right size, contents not yet hashed.
            "presentFiles": int(row["present"]) if row else 0,
            "allPresentSince": int(row["oldest_present"])
            if row and total and int(row["present"]) == total and row["oldest_present"] is not None
            else None,
            # Only meaningful once every file has been looked at once.
            "allCheckedSince": int(row["oldest"]) if row and verified == total and total else None,
            "lastCheckedAt": int(row["latest"]) if row and row["latest"] is not None else None,
            "repairingFiles": int(broken["broken"]) if broken else 0,
            "repairedFiles": int(row["repaired"]) if row else 0,
        }

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict
from typing import Any

from .archive_repository import ArchiveBatchRepository
from .db import Database
from .provider.normalizers import normalize_page
from .worker import MEDIA_URL_EXPIRED

logger = logging.getLogger(__name__)

# Older builds recorded expired signatures as a generic HTTP error.
REFRESHABLE_CODES = (MEDIA_URL_EXPIRED, "MEDIA_HTTP_ERROR")
# Douyin answers the detail API sparsely under load, so ask little and often.
BATCH_SIZE = 10
MAX_BATCHES_PER_RUN = 3
RUN_EVERY_SECONDS = 30
# An item missing from a detail answer is usually throttling, not deletion;
# back off instead of deciding it is gone (remote checks decide that).
UNAVAILABLE_BACKOFF_SECONDS = 600
MAX_UNAVAILABLE_BACKOFF_SECONDS = 6 * 3600
# After this many tries Douyin is not going to hand out a link; stop retrying so
# the batch can finish and the item shows up under failures with a retry button.
MAX_UNAVAILABLE_ATTEMPTS = 24
# When Douyin hands back nothing at all it is refusing us, not missing a few
# items. Stop asking for a while, then try one small batch; asking on every
# tick only keeps the throttle going and burns the items' retry budget.
DRY_RUNS_BEFORE_COOLDOWN = 2
COOLDOWN_SECONDS = (20 * 60, 40 * 60, 80 * 60, 120 * 60)

RecordFetcher = Callable[[list[str]], Awaitable[Sequence[dict[str, Any]]]]


class MediaUrlRefresher:
    """Re-sign play URLs of downloads that failed because the captured link expired.

    Play URLs from list responses are only valid for a short while, so anything
    queued long after its sync (a bulk "save everything") needs fresh ones.
    """

    def __init__(
        self,
        database: Database,
        fetch_records: RecordFetcher,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = database
        self.fetch_records = fetch_records
        self.clock = clock
        self.dry_runs = 0
        self.cooldowns = 0
        self.cooldown_until = 0
        self.refused_since: int | None = None

    def status(self) -> dict[str, Any] | None:
        """What the download screens show while Douyin refuses fresh links."""
        if self.refused_since is None:
            return None
        return {
            "refusedSince": self.refused_since,
            "retryAt": self.cooldown_until or None,
        }

    async def run_batch(self) -> int:
        now = int(self.clock())
        if now < self.cooldown_until:
            await self._hold_dead_links()
            return 0
        probing = self.cooldown_until > 0
        refreshed = 0
        asked = 0
        answered = 0
        failed = False
        for _ in range(1 if probing else MAX_BATCHES_PER_RUN):
            placeholders = ",".join("?" for _ in REFRESHABLE_CODES)
            rows = await self.db.fetchall(
                "SELECT id, remote_id, attempts FROM download_jobs "
                f"WHERE kind='download' AND status='retry' AND last_error_code IN ({placeholders}) "
                "ORDER BY next_attempt_at, id LIMIT ?",
                (*REFRESHABLE_CODES, BATCH_SIZE),
            )
            if not rows:
                break
            ids = [str(row["remote_id"]) for row in rows]
            asked += len(ids)
            try:
                records = await self.fetch_records(ids)
            except Exception:
                logger.warning("media URL refresh failed for %s items", len(ids), exc_info=True)
                failed = True
                break
            fresh = {
                item.remote_id: item
                for item in normalize_page({"aweme_list": list(records)}).items
                if item.assets
            }
            answered += len(fresh)
            if not fresh:
                # Nothing at all came back: a refusal, not a verdict on these
                # items. Leave them untouched so they keep their retry budget.
                break
            now = int(self.clock())
            for row in rows:
                item = fresh.get(str(row["remote_id"]))
                if item is not None:
                    # Fresh signatures expire within hours; put them at the front of
                    # the queue. Scheduled "now", they waited behind thousands of
                    # stale first tries and expired again before a worker got there.
                    await self.db.execute(
                        "UPDATE download_jobs SET payload_json=?, status='pending', "
                        "next_attempt_at=0, last_error_code=NULL, updated_at=? "
                        "WHERE id=? AND status='retry'",
                        (json.dumps(asdict(item), separators=(",", ":")), now, row["id"]),
                    )
                    refreshed += 1
                elif int(row["attempts"]) >= MAX_UNAVAILABLE_ATTEMPTS:
                    await self.db.execute(
                        "UPDATE download_jobs SET status='failed', claimed_by=NULL, "
                        "last_error_code=?, updated_at=? WHERE id=? AND status='retry'",
                        ("MEDIA_URL_UNAVAILABLE", now, row["id"]),
                    )
                    await self._refresh_batch(row["id"])
                else:
                    delay = min(
                        MAX_UNAVAILABLE_BACKOFF_SECONDS,
                        UNAVAILABLE_BACKOFF_SECONDS * 2 ** min(int(row["attempts"]), 6),
                    )
                    await self.db.execute(
                        "UPDATE download_jobs SET last_error_code=?, next_attempt_at=?, "
                        "updated_at=? WHERE id=?",
                        ("MEDIA_URL_UNAVAILABLE", now + delay, now, row["id"]),
                    )
            logger.info("media URL refresh returned %s of %s items", len(fresh), len(ids))
            if len(rows) < BATCH_SIZE:
                break
        if refreshed:
            logger.info("re-signed %s expired media URLs", refreshed)
        await self._track_refusals(asked=asked, answered=answered, failed=failed)
        return refreshed

    async def _track_refusals(self, *, asked: int, answered: int, failed: bool) -> None:
        now = int(self.clock())
        if answered:
            if self.refused_since is not None:
                logger.info("Douyin hands out media links again; resuming refresh")
            self.dry_runs = 0
            self.cooldowns = 0
            self.cooldown_until = 0
            self.refused_since = None
            return
        if not asked and not failed:
            return  # nothing waiting, nothing learned
        self.dry_runs += 1
        if self.refused_since is None:
            self.refused_since = now
        if self.cooldown_until or self.dry_runs >= DRY_RUNS_BEFORE_COOLDOWN:
            pause = COOLDOWN_SECONDS[min(self.cooldowns, len(COOLDOWN_SECONDS) - 1)]
            self.cooldowns += 1
            self.cooldown_until = now + pause
            logger.warning(
                "Douyin refused fresh media links %s times; pausing refresh for %s minutes",
                self.dry_runs,
                pause // 60,
            )
            await self._hold_dead_links()

    async def _hold_dead_links(self) -> None:
        # Workers would otherwise keep retrying links known to be dead, and each
        # try spends one of the item's attempts.
        placeholders = ",".join("?" for _ in REFRESHABLE_CODES)
        await self.db.execute(
            "UPDATE download_jobs SET next_attempt_at=? "
            f"WHERE kind='download' AND status='retry' AND last_error_code IN ({placeholders}) "
            "AND next_attempt_at < ?",
            (self.cooldown_until, *REFRESHABLE_CODES, self.cooldown_until),
        )

    async def _refresh_batch(self, job_id: int) -> None:
        row = await self.db.fetchone("SELECT batch_id FROM download_jobs WHERE id=?", (job_id,))
        if row is not None and row["batch_id"] is not None:
            await ArchiveBatchRepository(self.db).refresh_batch(int(row["batch_id"]))

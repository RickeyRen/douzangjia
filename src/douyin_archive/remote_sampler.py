from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from .db import Database
from .remote_availability import RemoteAvailabilityService, status_for_evidence

logger = logging.getLogger(__name__)

RECHECK_AFTER_SECONDS = 7 * 86_400
RUN_EVERY_SECONDS = 30 * 60
STOP_ON = {"rate_limited", "auth_required"}


class RemoteCheckSampler:
    """Spread remote availability checks over the day so "gone" items surface on their own."""

    def __init__(
        self,
        database: Database,
        checker: Callable[[str], Awaitable[str]],
        *,
        per_day: int,
        run_every_seconds: int = RUN_EVERY_SECONDS,
    ) -> None:
        self.db = database
        self.checker = checker
        self.per_day = per_day
        self.run_every_seconds = run_every_seconds
        self.availability = RemoteAvailabilityService(database)

    def budget(self) -> int:
        if self.per_day <= 0:
            return 0
        return max(1, round(self.per_day * self.run_every_seconds / 86_400))

    async def pick(self, limit: int, *, now: int | None = None) -> list[str]:
        now = int(time.time()) if now is None else now
        rows = await self.db.fetchall(
            "SELECT i.remote_id FROM items i LEFT JOIN remote_checks rc ON rc.item_id=i.remote_id "
            "WHERE rc.item_id IS NULL OR rc.checked_at IS NULL OR rc.checked_at < ? "
            "ORDER BY rc.checked_at IS NOT NULL, rc.checked_at, i.first_seen_at DESC LIMIT ?",
            (now - RECHECK_AFTER_SECONDS, limit),
        )
        return [str(row["remote_id"]) for row in rows]

    async def run_batch(self, *, now: int | None = None) -> int:
        budget = self.budget()
        if budget == 0:
            return 0
        checked = 0
        for remote_id in await self.pick(budget, now=now):
            try:
                evidence = await self.checker(remote_id)
            except Exception:
                logger.warning("remote check failed for %s", remote_id, exc_info=True)
                continue
            await self.availability.record(remote_id, evidence, checked_at=now)
            checked += 1
            if status_for_evidence(evidence) in STOP_ON:
                logger.info("remote sampling paused after %s", evidence)
                break
        return checked

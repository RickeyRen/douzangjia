from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict
from typing import Any

from .db import Database
from .provider.normalizers import normalize_page
from .worker import MEDIA_URL_EXPIRED

logger = logging.getLogger(__name__)

# Older builds recorded expired signatures as a generic HTTP error.
REFRESHABLE_CODES = (MEDIA_URL_EXPIRED, "MEDIA_HTTP_ERROR")
BATCH_SIZE = 20
MAX_BATCHES_PER_RUN = 10
RUN_EVERY_SECONDS = 30
# Douyin no longer returning an item after this many refreshes means it is gone.
GIVE_UP_AFTER_ATTEMPTS = 6

RecordFetcher = Callable[[list[str]], Awaitable[Sequence[dict[str, Any]]]]


class MediaUrlRefresher:
    """Re-sign play URLs of downloads that failed because the captured link expired.

    Play URLs from list responses are only valid for a short while, so anything
    queued long after its sync (a bulk "save everything") needs fresh ones.
    """

    def __init__(self, database: Database, fetch_records: RecordFetcher) -> None:
        self.db = database
        self.fetch_records = fetch_records

    async def run_batch(self) -> int:
        refreshed = 0
        for _ in range(MAX_BATCHES_PER_RUN):
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
            try:
                records = await self.fetch_records(ids)
            except Exception:
                logger.warning("media URL refresh failed for %s items", len(ids), exc_info=True)
                break
            fresh = {
                item.remote_id: item
                for item in normalize_page({"aweme_list": list(records)}).items
                if item.assets
            }
            now = int(time.time())
            for row in rows:
                item = fresh.get(str(row["remote_id"]))
                if item is not None:
                    await self.db.execute(
                        "UPDATE download_jobs SET payload_json=?, status='pending', "
                        "next_attempt_at=?, last_error_code=NULL, updated_at=? "
                        "WHERE id=? AND status='retry'",
                        (json.dumps(asdict(item), separators=(",", ":")), now, now, row["id"]),
                    )
                    refreshed += 1
                elif int(row["attempts"]) >= GIVE_UP_AFTER_ATTEMPTS:
                    await self.db.execute(
                        "UPDATE download_jobs SET status='failed', last_error_code='MEDIA_GONE', "
                        "updated_at=? WHERE id=? AND status='retry'",
                        (now, row["id"]),
                    )
                else:
                    # Not returned this time; keep it out of the next pick for a while.
                    await self.db.execute(
                        "UPDATE download_jobs SET last_error_code=?, updated_at=? WHERE id=?",
                        ("MEDIA_URL_UNAVAILABLE", now, row["id"]),
                    )
            if len(rows) < BATCH_SIZE:
                break
        if refreshed:
            logger.info("re-signed %s expired media URLs", refreshed)
        return refreshed

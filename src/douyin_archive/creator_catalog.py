"""Record every public work of a creator while their Douyin page still lists them.

Nothing here downloads media. The scan opens the creator's page like a person
scrolling through it and keeps what the page itself loaded, one creator per tick.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from .db import Database
from .provider.base import ProviderError
from .provider.normalizers import normalize_page
from .repositories import ArchiveRepository

logger = logging.getLogger(__name__)

SCAN_EVERY_SECONDS = 180
RESCAN_AFTER_SECONDS = 30 * 86_400
CANDIDATE_REFRESH_SECONDS = 30 * 60
PROMOTE_BATCH_SIZE = 500
# Pages that load nothing although the creator has works suggest Douyin is
# pushing back, so the scan backs off instead of pressing on.
EMPTY_SCANS_BEFORE_PAUSE = 3
PAUSE_SECONDS = 6 * 3_600


class CreatorCatalogScanner:
    def __init__(
        self,
        database: Database,
        scan: Callable[[str], AsyncIterator[list[dict[str, Any]]]],
    ) -> None:
        self.database = database
        self.scan = scan
        self.archive = ArchiveRepository(database)
        self._candidates: list[str] = []
        self._candidates_at = 0
        self._empty_scans = 0
        self.paused_until = 0

    async def run_tick(self) -> str | None:
        await self.promote_removed_creators()
        now = int(time.time())
        if now < self.paused_until:
            return None
        creator_id = await self._next_candidate(now)
        if creator_id is None:
            return None
        try:
            await self.scan_creator(creator_id)
        except ProviderError as error:
            logger.warning("creator catalog scan skipped for %s: %s", creator_id, error.code)
            self.paused_until = now + PAUSE_SECONDS
            return None
        except Exception:
            logger.exception("creator catalog scan failed for %s", creator_id)
            return None
        return creator_id

    async def _next_candidate(self, now: int) -> str | None:
        if not self._candidates or now - self._candidates_at > CANDIDATE_REFRESH_SECONDS:
            rows = await self.database.fetchall(
                "SELECT c.remote_id, COUNT(DISTINCT i.remote_id) AS saved FROM creators c "
                "JOIN items i ON i.creator_id=c.remote_id "
                "JOIN media_files mf ON mf.item_id=i.remote_id AND mf.status='ready' "
                "WHERE c.archive_status<>'banned' "
                "AND (c.catalog_scanned_at IS NULL OR c.catalog_scanned_at <= ?) "
                # A reset creator's works are the ones about to disappear.
                "GROUP BY c.remote_id ORDER BY c.archive_status='reset' DESC, "
                "c.catalog_scanned_at IS NOT NULL, saved DESC, c.remote_id LIMIT 200",
                (now - RESCAN_AFTER_SECONDS,),
            )
            self._candidates = [str(row["remote_id"]) for row in rows]
            self._candidates.reverse()
            self._candidates_at = now
        return self._candidates.pop() if self._candidates else None

    async def scan_creator(self, creator_id: str) -> int:
        now = int(time.time())
        seen = 0
        async for records in self.scan(creator_id):
            for item in normalize_page({"status_code": 0, "aweme_list": records}).items:
                if item.creator_id != creator_id:
                    continue
                await self.database.execute(
                    "INSERT INTO creator_catalog_items "
                    "(item_id, creator_id, author_name, description, item_type, published_at, "
                    "duration_ms, cover_url, source_url, statistics_json, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(item_id) DO UPDATE SET "
                    "description=excluded.description, cover_url=excluded.cover_url, "
                    "statistics_json=excluded.statistics_json, last_seen_at=excluded.last_seen_at",
                    (
                        item.remote_id,
                        creator_id,
                        item.author_name,
                        item.description,
                        item.item_type,
                        item.published_at,
                        item.duration_ms,
                        item.cover_url,
                        item.source_url,
                        json.dumps(item.statistics or {}, separators=(",", ":"), sort_keys=True),
                        now,
                        now,
                    ),
                )
                seen += 1
        await self._after_scan(creator_id, seen, now)
        return seen

    async def _after_scan(self, creator_id: str, seen: int, now: int) -> None:
        creator = await self.database.fetchone(
            "SELECT post_count, archive_status FROM creators WHERE remote_id=?", (creator_id,)
        )
        expected = creator is not None and creator["archive_status"] == "active" and (creator["post_count"] or 0) > 0
        if seen == 0 and expected:
            self._empty_scans += 1
            if self._empty_scans >= EMPTY_SCANS_BEFORE_PAUSE:
                logger.warning(
                    "creator catalog scan paused: %d pages in a row loaded no works", self._empty_scans
                )
                self.paused_until = now + PAUSE_SECONDS
                self._empty_scans = 0
                self._candidates = []
            # Left unmarked, so the creator is tried again on a later pass.
            return
        self._empty_scans = 0
        await self.database.execute(
            "UPDATE creators SET catalog_scanned_at=?, catalog_item_count=("
            "SELECT COUNT(*) FROM creator_catalog_items cc WHERE cc.creator_id=?) WHERE remote_id=?",
            (now, creator_id, creator_id),
        )

    async def promote_removed_creators(self) -> int:
        """Show a removed creator's recorded works on their archive page."""
        rows = await self.database.fetchall(
            "SELECT cc.* FROM creator_catalog_items cc JOIN creators c ON c.remote_id=cc.creator_id "
            "WHERE c.archive_status<>'active' AND NOT EXISTS ("
            "SELECT 1 FROM items i WHERE i.remote_id=cc.item_id) LIMIT ?",
            (PROMOTE_BATCH_SIZE,),
        )
        for row in rows:
            await self.archive.upsert_item(
                remote_id=str(row["item_id"]),
                author_name=str(row["author_name"]),
                description=str(row["description"]),
                item_type=str(row["item_type"]),
                published_at=row["published_at"],
                creator_id=str(row["creator_id"]),
                cover_url=row["cover_url"],
                duration_ms=row["duration_ms"],
                statistics=json.loads(row["statistics_json"]),
                source_url=row["source_url"],
            )
        return len(rows)

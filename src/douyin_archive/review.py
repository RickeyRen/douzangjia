"""收藏回顾: what the owner collected, month by month, and what Douyin lost since.

One pass over every collected work feeds every figure. On the NAS that pass
takes about a minute (source_items rows are wide), so it runs in the
background at most once a day and the page reads the stored snapshot.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import Database
from .library_scope import TRANSIENT_SOURCE_KINDS

logger = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 30 * 60
# The pass reads every collected work; on the busy NAS it can slow a sync
# running at the same time, so daily rebuilds wait for the small hours.
REBUILD_AFTER_SECONDS = 20 * 3600
QUIET_HOURS = range(3, 6)  # Shanghai time
TOP_CREATORS = 12
SHANGHAI = timezone(timedelta(hours=8))
# Followed accounts are people, not works the owner chose to keep.
NOT_COLLECTED = (*TRANSIENT_SOURCE_KINDS, "following")
VANISHED = ("deleted", "private")


def _month(stamp: int | None) -> str | None:
    return datetime.fromtimestamp(stamp, SHANGHAI).strftime("%Y-%m") if stamp else None


class CollectionReview:
    def __init__(self, database: Database, *, clock: Callable[[], float] = time.time) -> None:
        self.db = database
        self.clock = clock

    async def snapshot(self) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT body_json, built_at FROM review_snapshots WHERE id=1")
        if row is None:
            return None
        return {**json.loads(str(row["body_json"])), "builtAt": int(row["built_at"])}

    async def run_tick(self) -> bool:
        """Build the first snapshot at once; refresh it nightly after that."""
        row = await self.db.fetchone("SELECT built_at FROM review_snapshots WHERE id=1")
        if row is not None:
            now = self.clock()
            if now - int(row["built_at"]) < REBUILD_AFTER_SECONDS:
                return False
            if datetime.fromtimestamp(now, SHANGHAI).hour not in QUIET_HOURS:
                return False
        await self.rebuild()
        return True

    async def rebuild(self) -> dict[str, Any]:
        started = time.monotonic()
        body = await self.build()
        await self.db.execute(
            "INSERT INTO review_snapshots (id, body_json, built_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET body_json=excluded.body_json, built_at=excluded.built_at",
            (json.dumps(body, ensure_ascii=False), int(self.clock())),
        )
        logger.info("collection review rebuilt in %.1fs", time.monotonic() - started)
        return body

    async def build(self) -> dict[str, Any]:
        excluded = ",".join("?" * len(NOT_COLLECTED))
        rows = await self.db.fetchall(
            "SELECT m.item_id, m.added_at, i.published_at, i.creator_id, i.author_name, "
            "EXISTS (SELECT 1 FROM media_files mf WHERE mf.item_id=m.item_id AND mf.status='ready') AS saved, "
            "(SELECT rc.status FROM remote_checks rc WHERE rc.item_id=m.item_id) AS remote "
            "FROM (SELECT si.item_id, MIN(si.first_seen_at) AS added_at FROM source_items si "
            "JOIN library_sources ls ON ls.id=si.source_id "
            f"WHERE ls.kind NOT IN ({excluded}) GROUP BY si.item_id) m "
            "JOIN items i ON i.remote_id=m.item_id",
            NOT_COLLECTED,
        )
        months: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        years: Counter[str] = Counter()
        creators: dict[str, dict[str, Any]] = {}
        vanished = {"total": 0, "saved": 0}
        saved_total = 0
        first_added: int | None = None
        for row in rows:
            added = int(row["added_at"]) if row["added_at"] is not None else None
            saved = bool(row["saved"])
            gone = row["remote"] in VANISHED
            saved_total += saved
            if added is not None:
                first_added = added if first_added is None else min(first_added, added)
                bucket = months[_month(added) or ""]
                bucket[0] += 1
                bucket[1] += saved
            if row["published_at"]:
                years[datetime.fromtimestamp(int(row["published_at"]), SHANGHAI).strftime("%Y")] += 1
            if gone:
                vanished["total"] += 1
                vanished["saved"] += saved
            if row["creator_id"]:
                entry = creators.setdefault(
                    str(row["creator_id"]),
                    {"id": str(row["creator_id"]), "name": str(row["author_name"] or ""), "count": 0, "vanished": 0},
                )
                entry["count"] += 1
                entry["vanished"] += gone
        top = sorted(creators.values(), key=lambda entry: (-entry["count"], entry["name"]))[:TOP_CREATORS]
        if top:
            marks = ",".join("?" * len(top))
            details = {
                str(row["remote_id"]): row
                for row in await self.db.fetchall(
                    f"SELECT remote_id, nickname, avatar_url FROM creators WHERE remote_id IN ({marks})",
                    [entry["id"] for entry in top],
                )
            }
            for entry in top:
                detail = details.get(entry["id"])
                if detail is not None:
                    entry["name"] = str(detail["nickname"] or entry["name"])
                    entry["avatarUrl"] = detail["avatar_url"]
        return {
            "totals": {"items": len(rows), "saved": saved_total, "since": first_added},
            # The first month holds everything that existed before the archive started.
            "firstMonth": _month(first_added),
            "months": [
                {"month": month, "added": counts[0], "saved": counts[1]}
                for month, counts in sorted(months.items())
                if month
            ],
            "publishedYears": [{"year": year, "count": count} for year, count in sorted(years.items())],
            "topCreators": top,
            "vanished": {**vanished, "lost": vanished["total"] - vanished["saved"]},
        }

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from ..avatars import avatar_route
from ..creator_archive import preserved_identity
from ..library_scope import library_item_ids_sql, library_item_sql
from ..sync_health import sync_health_snapshot
from .feed import _serialize_item, cover_store_for

router = APIRouter(prefix="/api")

HOME_SHELF_SIZE = 12
SQL_CHUNK = 500
# Library-wide counts scan every item; they barely move, so serve the last answer
# and recount in the background at most this often.
LIBRARY_TOTALS_TTL_SECONDS = 300
SHELF_SOURCE_KINDS = ("favorite_collection", "favorite_video", "like", "post", "watch_later")
ACTIVITY_DAYS = 70
SPEED_WINDOW_SECONDS = 24 * 60 * 60
SPEED_BUCKET_SECONDS = 600
WEEK_SECONDS = 7 * 24 * 60 * 60
# The charts move in day and 10-minute steps; recompute them at most this often.
ACTIVITY_TTL_SECONDS = 60
SHANGHAI = ZoneInfo("Asia/Shanghai")
# China keeps UTC+8 all year, so SQL can bucket days with a fixed offset.
SHANGHAI_OFFSET_SECONDS = 8 * 60 * 60


async def sync_health(request: Request, *, now: int | None = None) -> dict[str, Any]:
    store = getattr(request.app.state, "settings_store", None)
    interval = int(
        (await store.load()).sync_interval_seconds
        if store is not None
        else request.app.state.settings.sync_interval_seconds
    )
    return await sync_health_snapshot(
        request.app.state.database,
        interval_seconds=interval,
        coordinator=getattr(request.app.state, "browser_coordinator", None),
        now=now,
    )


async def _count_library(database: Any, *, now: int | None = None) -> dict[str, Any]:
    # Counted in Python from index-only scans: the SQL form ran the library
    # predicate per item and per creator, which took minutes on a busy NAS.
    week_ago = (int(time.time()) if now is None else now) - WEEK_SECONDS
    library_ids = {row[0] for row in await database.fetchall(library_item_ids_sql())}
    item_rows = await database.fetchall(
        "SELECT remote_id, item_type, first_seen_at, creator_id FROM items "
        "INDEXED BY items_library_counts"
    )
    items = videos = galleries = items_week = 0
    per_creator: dict[str, int] = {}
    for row in item_rows:
        if row[0] not in library_ids:
            continue
        items += 1
        if row[1] == "video":
            videos += 1
        elif row[1] == "gallery":
            galleries += 1
        if row[2] is not None and row[2] >= week_ago:
            items_week += 1
        if row[3] is not None:
            per_creator[row[3]] = per_creator.get(row[3], 0) + 1
    creator_ids = list(per_creator)
    creator_seen: dict[str, tuple[int, int]] = {}
    for offset in range(0, len(creator_ids), SQL_CHUNK):
        chunk = creator_ids[offset : offset + SQL_CHUNK]
        rows = await database.fetchall(
            "SELECT remote_id, first_seen_at, last_seen_at FROM creators "
            f"WHERE remote_id IN ({','.join('?' for _ in chunk)})",
            chunk,
        )
        for row in rows:
            creator_seen[row[0]] = (row[1] or 0, row[2] or 0)
    creators_week = sum(1 for first, _ in creator_seen.values() if first >= week_ago)
    top = sorted(
        creator_seen,
        key=lambda creator_id: (per_creator[creator_id], creator_seen[creator_id][1]),
        reverse=True,
    )[:HOME_SHELF_SIZE]
    details: dict[str, dict[str, Any]] = {}
    if top:
        rows = await database.fetchall(
            "SELECT remote_id, nickname, unique_id, avatar_url FROM creators "
            f"WHERE remote_id IN ({','.join('?' for _ in top)})",
            top,
        )
        details = {row["remote_id"]: dict(row) for row in rows}
    creator_rows = [
        {**details[creator_id], "items": per_creator[creator_id]}
        for creator_id in top
        if creator_id in details
    ]
    return {
        "items": items,
        "videos": videos,
        "galleries": galleries,
        "creators": len(creator_seen),
        "items_week": items_week,
        "creators_week": creators_week,
        "creator_rows": creator_rows,
    }


async def home_activity(
    database: Any, counts: dict[str, Any], *, now: int | None = None
) -> dict[str, Any]:
    """Per-day saves (Shanghai dates) and the last day's download speed for the home charts."""
    now = int(time.time()) if now is None else now
    today = datetime.fromtimestamp(now, tz=SHANGHAI).date()
    first_day = today - timedelta(days=ACTIVITY_DAYS - 1)
    start = int(datetime(first_day.year, first_day.month, first_day.day, tzinfo=SHANGHAI).timestamp())
    # An item counts on the day its first file landed, so re-downloads never count twice.
    offset = SHANGHAI_OFFSET_SECONDS
    saved_rows = await database.fetchall(
        "SELECT (first_done + ?) / 86400 AS day, COUNT(*) AS saved FROM ("
        "SELECT MIN(completed_at) AS first_done FROM media_files "
        "WHERE status='ready' AND completed_at IS NOT NULL GROUP BY item_id"
        ") WHERE first_done>=? AND first_done<=? GROUP BY day",
        (offset, start, now),
    )
    by_day = {int(row["day"]): int(row["saved"]) for row in saved_rows}
    epoch_day = (start + offset) // 86400
    daily = [
        {
            "date": (first_day + timedelta(days=index)).isoformat(),
            "count": by_day.get(epoch_day + index, 0),
        }
        for index in range(ACTIVITY_DAYS)
    ]
    speed_rows = await database.fetchall(
        "SELECT CAST(sampled_at / ? AS INTEGER) * ? AS bucket, "
        "AVG(download_speed_bps) AS bps FROM metric_samples "
        "WHERE resolution='raw' AND sampled_at>=? GROUP BY bucket ORDER BY bucket",
        (SPEED_BUCKET_SECONDS, SPEED_BUCKET_SECONDS, now - SPEED_WINDOW_SECONDS),
    )
    vanished_week = await database.fetchone(
        "SELECT COUNT(*) AS total FROM creators "
        "WHERE archive_status<>'active' AND archive_status_since>=?",
        (now - WEEK_SECONDS,),
    )
    return {
        "dailySaved": daily,
        "speed": [
            {"at": int(row["bucket"]), "bps": round(float(row["bps"]), 1)} for row in speed_rows
        ],
        "speedBucketSeconds": SPEED_BUCKET_SECONDS,
        "week": {
            "items": int(counts.get("items_week", 0)),
            "saved": sum(day["count"] for day in daily[-7:]),
            "creators": int(counts.get("creators_week", 0)),
            "vanished": int(vanished_week["total"]) if vanished_week is not None else 0,
        },
    }


async def warm_library_counts(app: Any) -> None:
    """Count once at startup so the first visit after a restart is not the slow one."""
    if getattr(app.state, "home_library_counts", None) is None:
        app.state.home_library_counts = (time.monotonic(), await _count_library(app.state.database))


async def library_counts(request: Request) -> dict[str, Any]:
    """Library-wide counts, recomputed in the background once they are stale."""
    state = request.app.state
    database = state.database
    cached = getattr(state, "home_library_counts", None)
    now = time.monotonic()
    if cached is None:
        counts = await _count_library(database)
        state.home_library_counts = (now, counts)
        return counts
    computed_at, counts = cached
    refreshing = getattr(state, "home_library_refresh", None)
    if now - computed_at > LIBRARY_TOTALS_TTL_SECONDS and (refreshing is None or refreshing.done()):

        async def refresh() -> None:
            state.home_library_counts = (time.monotonic(), await _count_library(database))

        state.home_library_refresh = asyncio.create_task(refresh())
    return counts


async def cached_activity(request: Request, counts: dict[str, Any]) -> dict[str, Any]:
    state = request.app.state
    cached = getattr(state, "home_activity", None)
    now = time.monotonic()
    if cached is not None and now - cached[0] < ACTIVITY_TTL_SECONDS:
        return cached[1]
    activity = await home_activity(state.database, counts)
    state.home_activity = (now, activity)
    return activity


@router.get("/home")
async def home(request: Request) -> dict[str, Any]:
    database = request.app.state.database
    counts = await library_counts(request)
    local = await database.fetchone(
        "SELECT COUNT(DISTINCT item_id) AS items, COALESCE(SUM(byte_size), 0) AS bytes "
        "FROM media_files WHERE status='ready'"
    )
    stars = await database.fetchone("SELECT COUNT(*) AS total FROM item_stars")
    gone = await database.fetchone(
        "SELECT COUNT(*) AS total FROM remote_checks WHERE status IN ('deleted', 'private')"
    )
    checked = await database.fetchone(
        "SELECT COUNT(*) AS total FROM remote_checks WHERE checked_at IS NOT NULL"
    )
    vanished = await database.fetchone(
        "SELECT COUNT(*) AS total FROM creators WHERE archive_status<>'active'"
    )
    vanished_rows = await database.fetchall(
        "SELECT c.remote_id, c.archive_status, c.archive_status_since, "
        "(SELECT COUNT(*) FROM items i WHERE i.creator_id=c.remote_id) AS items "
        "FROM creators c WHERE c.archive_status<>'active' "
        "ORDER BY COALESCE(c.archive_status_since, 0) DESC, c.remote_id DESC LIMIT ?",
        (HOME_SHELF_SIZE,),
    )
    vanished_creators = []
    for row in vanished_rows:
        kept = await preserved_identity(database, str(row["remote_id"]))
        vanished_creators.append(
            {
                "id": row["remote_id"],
                "nickname": kept["nickname"] if kept is not None else "原名未知",
                "uniqueId": kept["unique_id"] if kept is not None else None,
                "avatarUrl": f"/api/creators/{row['remote_id']}/avatar",
                "status": row["archive_status"],
                "since": row["archive_status_since"],
                "itemCount": row["items"],
            }
        )

    recent_rows = await database.fetchall(
        f"SELECT i.* FROM items i WHERE {library_item_sql('i')} "
        "ORDER BY i.first_seen_at DESC, i.remote_id DESC LIMIT ?",
        (HOME_SHELF_SIZE,),
    )
    gone_rows = await database.fetchall(
        "SELECT i.* FROM items i JOIN remote_checks rc ON rc.item_id=i.remote_id "
        "WHERE rc.status IN ('deleted', 'private') ORDER BY rc.checked_at DESC, i.remote_id DESC LIMIT ?",
        (HOME_SHELF_SIZE,),
    )
    starred_rows = await database.fetchall(
        "SELECT i.* FROM items i JOIN item_stars s ON s.item_id=i.remote_id "
        "ORDER BY s.starred_at DESC, i.remote_id DESC LIMIT ?",
        (HOME_SHELF_SIZE,),
    )
    placeholders = ",".join("?" for _ in SHELF_SOURCE_KINDS)
    source_rows = await database.fetchall(
        "SELECT ls.id, ls.kind, ls.name, COUNT(si.item_id) AS item_count, "
        "MAX(si.last_seen_at) AS last_seen_at "
        "FROM library_sources ls LEFT JOIN source_items si ON si.source_id=ls.id "
        f"WHERE ls.kind IN ({placeholders}) GROUP BY ls.id "
        "HAVING item_count > 0 ORDER BY ls.kind='favorite_collection' DESC, item_count DESC",
        SHELF_SOURCE_KINDS,
    )
    shelves = []
    for source in source_rows:
        covers = await database.fetchall(
            "SELECT i.cover_url, (SELECT mf.id FROM media_files mf "
            "WHERE mf.item_id=i.remote_id AND mf.status='ready' "
            "ORDER BY mf.asset_index LIMIT 1) AS media_id "
            "FROM source_items si JOIN items i ON i.remote_id=si.item_id "
            "WHERE si.source_id=? "
            "ORDER BY media_id IS NULL, COALESCE(si.remote_order, '') DESC LIMIT 4",
            (source["id"],),
        )
        shelves.append(
            {
                "id": source["id"],
                "kind": source["kind"],
                "name": source["name"],
                "itemCount": source["item_count"],
                "lastSeenAt": source["last_seen_at"],
                "covers": [
                    f"/api/media/{row['media_id']}/poster" if row["media_id"] else row["cover_url"]
                    for row in covers
                    if row["media_id"] or row["cover_url"]
                ],
            }
        )
    creator_rows = counts["creator_rows"]
    covers = cover_store_for(request)
    return {
        "stats": {
            "items": counts["items"],
            "videos": counts["videos"],
            "galleries": counts["galleries"],
            "downloadedItems": local["items"],
            "archivedBytes": local["bytes"],
            "creators": counts["creators"],
            "starred": stars["total"],
            "gone": gone["total"],
            "remoteChecked": checked["total"],
            "vanishedCreators": vanished["total"],
        },
        "vanishedCreators": vanished_creators,
        "activity": await cached_activity(request, counts),
        "health": await sync_health(request),
        "recent": [await _serialize_item(database, row, covers) for row in recent_rows],
        "starred": [await _serialize_item(database, row, covers) for row in starred_rows],
        "gone": [await _serialize_item(database, row, covers) for row in gone_rows],
        "shelves": shelves,
        "creators": [
            {
                "id": row["remote_id"],
                "nickname": row["nickname"],
                "uniqueId": row["unique_id"],
                "avatarUrl": avatar_route(str(row["remote_id"]), row["avatar_url"]),
                "itemCount": row["items"],
            }
            for row in creator_rows
        ],
    }


@router.get("/health/sync")
async def sync_health_route(request: Request) -> dict[str, Any]:
    return await sync_health(request)

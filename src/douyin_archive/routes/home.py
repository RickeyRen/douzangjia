from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Request

from ..avatars import avatar_route
from ..creator_archive import preserved_identity
from ..library_scope import library_item_sql
from ..sync_health import sync_health_snapshot
from .feed import _serialize_item, cover_store_for

router = APIRouter(prefix="/api")

HOME_SHELF_SIZE = 12
# Library-wide counts scan every item; they barely move, so serve the last answer
# and recount in the background at most this often.
LIBRARY_TOTALS_TTL_SECONDS = 300
SHELF_SOURCE_KINDS = ("favorite_collection", "favorite_video", "like", "post", "watch_later")


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


async def _count_library(database: Any) -> dict[str, Any]:
    in_library = library_item_sql("i")
    totals = await database.fetchone(
        "SELECT COUNT(*) AS items, "
        "COALESCE(SUM(CASE WHEN item_type='video' THEN 1 ELSE 0 END), 0) AS videos, "
        "COALESCE(SUM(CASE WHEN item_type='gallery' THEN 1 ELSE 0 END), 0) AS galleries "
        f"FROM items i WHERE {in_library}"
    )
    creators = await database.fetchone(
        "SELECT COUNT(*) AS total FROM creators c WHERE EXISTS "
        f"(SELECT 1 FROM items i WHERE i.creator_id=c.remote_id AND {in_library})"
    )
    creator_rows = await database.fetchall(
        "SELECT c.remote_id, c.nickname, c.unique_id, c.avatar_url, COUNT(i.remote_id) AS items "
        "FROM creators c JOIN items i ON i.creator_id=c.remote_id "
        f"WHERE {in_library} GROUP BY c.remote_id ORDER BY items DESC, c.last_seen_at DESC LIMIT ?",
        (HOME_SHELF_SIZE,),
    )
    return {
        "items": totals["items"],
        "videos": totals["videos"],
        "galleries": totals["galleries"],
        "creators": creators["total"],
        "creator_rows": [dict(row) for row in creator_rows],
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

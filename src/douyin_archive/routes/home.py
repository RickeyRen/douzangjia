from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..avatars import avatar_route
from ..sync_health import sync_health_snapshot
from .feed import _serialize_item

router = APIRouter(prefix="/api")

HOME_SHELF_SIZE = 12
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


@router.get("/home")
async def home(request: Request) -> dict[str, Any]:
    database = request.app.state.database
    totals = await database.fetchone(
        "SELECT COUNT(*) AS items, "
        "COALESCE(SUM(CASE WHEN item_type='video' THEN 1 ELSE 0 END), 0) AS videos, "
        "COALESCE(SUM(CASE WHEN item_type='gallery' THEN 1 ELSE 0 END), 0) AS galleries "
        "FROM items"
    )
    local = await database.fetchone(
        "SELECT COUNT(DISTINCT item_id) AS items, COALESCE(SUM(byte_size), 0) AS bytes "
        "FROM media_files WHERE status='ready'"
    )
    creators = await database.fetchone("SELECT COUNT(*) AS total FROM creators")
    stars = await database.fetchone("SELECT COUNT(*) AS total FROM item_stars")
    gone = await database.fetchone(
        "SELECT COUNT(*) AS total FROM remote_checks WHERE status IN ('deleted', 'private')"
    )
    checked = await database.fetchone(
        "SELECT COUNT(*) AS total FROM remote_checks WHERE checked_at IS NOT NULL"
    )

    recent_rows = await database.fetchall(
        "SELECT * FROM items ORDER BY first_seen_at DESC, remote_id DESC LIMIT ?",
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
    creator_rows = await database.fetchall(
        "SELECT c.remote_id, c.nickname, c.unique_id, c.avatar_url, COUNT(i.remote_id) AS items "
        "FROM creators c JOIN items i ON i.creator_id=c.remote_id "
        "GROUP BY c.remote_id ORDER BY items DESC, c.last_seen_at DESC LIMIT ?",
        (HOME_SHELF_SIZE,),
    )
    return {
        "stats": {
            "items": totals["items"],
            "videos": totals["videos"],
            "galleries": totals["galleries"],
            "downloadedItems": local["items"],
            "archivedBytes": local["bytes"],
            "creators": creators["total"],
            "starred": stars["total"],
            "gone": gone["total"],
            "remoteChecked": checked["total"],
        },
        "health": await sync_health(request),
        "recent": [await _serialize_item(database, row) for row in recent_rows],
        "starred": [await _serialize_item(database, row) for row in starred_rows],
        "gone": [await _serialize_item(database, row) for row in gone_rows],
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

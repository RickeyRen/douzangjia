from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request

from ..account_health import AccountHealthService
from .feed import _serialize_item

router = APIRouter(prefix="/api")

HOME_SHELF_SIZE = 12
STALE_MINIMUM_SECONDS = 30 * 60
FAILING_AFTER_CONSECUTIVE = 2
SHELF_SOURCE_KINDS = ("favorite_collection", "favorite_video", "like", "post", "watch_later")


async def sync_health(request: Request, *, now: int | None = None) -> dict[str, Any]:
    """Summarize whether discovery is actually keeping up, for the alert banner."""
    database = request.app.state.database
    now = int(time.time()) if now is None else now
    interval = int(request.app.state.settings.sync_interval_seconds)
    account = await AccountHealthService(database).snapshot()
    latest = await database.fetchone(
        "SELECT status, error_code, started_at, finished_at FROM sync_runs "
        "ORDER BY id DESC LIMIT 1"
    )
    last_success = await database.fetchone(
        "SELECT MAX(finished_at) AS finished_at FROM sync_runs WHERE status='completed'"
    )
    recent = await database.fetchall(
        "SELECT status FROM sync_runs WHERE status IN ('completed', 'failed') "
        "ORDER BY id DESC LIMIT 20"
    )
    consecutive_failures = 0
    for row in recent:
        if row["status"] != "failed":
            break
        consecutive_failures += 1
    last_success_at = last_success["finished_at"] if last_success is not None else None
    coordinator = getattr(request.app.state, "browser_coordinator", None)
    browser = await coordinator.probe() if coordinator is not None else "not_started"

    stale_after = max(interval * 3, STALE_MINIMUM_SECONDS)
    error_code = latest["error_code"] if latest is not None else None
    if account.get("status") == "expired" or not account.get("sessionStored"):
        state = "login_required"
        error_code = account.get("errorCode") or "DOUYIN_SESSION_EXPIRED"
    elif browser in {"disconnected", "unresponsive"}:
        state = "failing"
        error_code = "BROWSER_DISCONNECTED"
    elif latest is not None and latest["status"] in {"running", "queued"}:
        state = "syncing"
    elif last_success_at is None:
        state = "never"
    elif consecutive_failures >= FAILING_AFTER_CONSECUTIVE:
        state = "failing"
    elif now - int(last_success_at) > stale_after:
        # Catches the scheduler dying before it can even record a failed run.
        state = "stale"
        error_code = error_code or "SYNC_STALLED"
    else:
        state = "ok"
        error_code = None
    return {
        "state": state,
        "lastSuccessAt": last_success_at,
        "lastAttemptAt": latest["started_at"] if latest is not None else None,
        "lastErrorCode": error_code,
        "consecutiveFailures": consecutive_failures,
        "intervalSeconds": interval,
        "staleAfterSeconds": stale_after,
        "browser": browser,
    }


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

    recent_rows = await database.fetchall(
        "SELECT * FROM items ORDER BY first_seen_at DESC, remote_id DESC LIMIT ?",
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
        },
        "health": await sync_health(request),
        "recent": [await _serialize_item(database, row) for row in recent_rows],
        "starred": [await _serialize_item(database, row) for row in starred_rows],
        "shelves": shelves,
        "creators": [
            {
                "id": row["remote_id"],
                "nickname": row["nickname"],
                "uniqueId": row["unique_id"],
                "avatarUrl": row["avatar_url"],
                "itemCount": row["items"],
            }
            for row in creator_rows
        ],
    }


@router.get("/health/sync")
async def sync_health_route(request: Request) -> dict[str, Any]:
    return await sync_health(request)

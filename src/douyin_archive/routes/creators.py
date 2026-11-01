from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from ..avatars import AvatarCache, avatar_route
from ..creator_archive import (
    ARCHIVE_STATUSES,
    CreatorMediaStore,
    preserved_identity,
    serialize_snapshot,
)
from ..library_repository import LibraryRepository
from ..library_scope import library_item_sql
from ..provider.base import ProviderError

router = APIRouter(prefix="/api/creators")


def _encode_cursor(last_seen_at: int, remote_id: str) -> str:
    raw = json.dumps([last_seen_at, remote_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(decoded, list) or len(decoded) != 2:
            raise ValueError
        return int(decoded[0]), str(decoded[1])
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid creator cursor") from error


def _serialize_creator(row, preserved=None) -> dict[str, object]:
    subscription = None
    if row["subscription_enabled"] is not None:
        subscription = {
            "enabled": bool(row["subscription_enabled"]),
            "scanIntervalSeconds": int(row["scan_interval_seconds"]),
            "archiveNewItems": bool(row["archive_new_items"]),
            "lastScanAt": row["last_scan_at"],
            "nextScanAt": row["next_scan_at"],
            "lastErrorCode": row["subscription_error_code"],
        }
    status = row["archive_status"]
    archived = status != "active"
    current_avatar = avatar_route(str(row["remote_id"]), row["avatar_url"])
    kept = serialize_snapshot(preserved) if preserved is not None else None
    # Once Douyin has rewritten the profile, show the creator as they were.
    use_kept = archived and kept is not None
    return {
        "id": row["remote_id"],
        "nickname": kept["nickname"] if use_kept else row["nickname"],
        "uniqueId": (kept["uniqueId"] or row["unique_id"]) if use_kept else row["unique_id"],
        "avatarUrl": (kept["avatarUrl"] or current_avatar) if use_kept else current_avatar,
        "followerCount": row["follower_count"],
        "postCount": row["post_count"],
        "knownItemCount": int(row["known_item_count"]),
        "archivedItemCount": int(row["archived_item_count"]),
        "lastSeenAt": row["last_seen_at"],
        "subscription": subscription,
        "signature": row["signature"],
        "followingCount": row["following_count"],
        "totalFavorited": row["total_favorited"],
        "ipLocation": row["ip_location"],
        "archive": {
            "status": status,
            "since": row["archive_status_since"],
            "checkedAt": row["archive_checked_at"],
            "currentNickname": row["nickname"],
            "currentAvatarUrl": current_avatar,
            "preserved": kept,
        },
    }


def _select_sql(where: str) -> str:
    return (
        "SELECT c.*, COUNT(DISTINCT i.remote_id) AS known_item_count, "
        "COALESCE(SUM(CASE WHEN i.remote_id IS NOT NULL AND EXISTS("
        "SELECT 1 FROM media_files mf WHERE mf.item_id=i.remote_id "
        "AND mf.status='ready') THEN 1 ELSE 0 END), 0) AS archived_item_count, "
        "cs.enabled AS subscription_enabled, cs.scan_interval_seconds, "
        "cs.archive_new_items, cs.last_scan_at, cs.next_scan_at, "
        "cs.last_error_code AS subscription_error_code "
        "FROM creators c LEFT JOIN items i ON i.creator_id=c.remote_id "
        # An archived creator's page keeps every work we ever knew, not just kept ones.
        f"AND (c.archive_status<>'active' OR {library_item_sql('i')}) "
        "LEFT JOIN creator_subscriptions cs ON cs.creator_id=c.remote_id "
        f"{where} GROUP BY c.remote_id"
    )


@router.get("")
async def list_creators(
    request: Request,
    limit: int = Query(default=40, ge=1, le=100),
    cursor: str | None = None,
    search: str | None = None,
    sort: str = Query(default="recent", pattern="^(recent|items)$"),
):
    conditions: list[str] = []
    parameters: list[object] = []
    if search:
        conditions.append("(c.nickname LIKE ? OR c.unique_id LIKE ?)")
        term = f"%{search}%"
        parameters.extend((term, term))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    # The "items" order ranks creators by how much of them the archive holds.
    sort_key = "c.last_seen_at" if sort == "recent" else "known_item_count"
    # Creators met only in the recommend feed or watch history stay out of the list.
    having = " HAVING (known_item_count > 0 OR cs.creator_id IS NOT NULL)"
    if cursor:
        try:
            before_key, remote_id = _decode_cursor(cursor)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_CURSOR", "message": "分页游标无效"},
            )
        having += f" AND ({sort_key} < ? OR ({sort_key}=? AND c.remote_id < ?))"
        parameters.extend((before_key, before_key, remote_id))
    rows = await request.app.state.database.fetchall(
        _select_sql(where)
        + having
        + f" ORDER BY {sort_key} DESC, c.remote_id DESC LIMIT ?",
        (*parameters, limit + 1),
    )
    visible = rows[:limit]
    next_cursor = None
    if len(rows) > limit and visible:
        last = visible[-1]
        key = last["last_seen_at"] if sort == "recent" else last["known_item_count"]
        next_cursor = _encode_cursor(int(key), str(last["remote_id"]))
    return {
        "items": [await _with_preserved(request, row) for row in visible],
        "nextCursor": next_cursor,
    }


async def _with_preserved(request: Request, row) -> dict[str, object]:
    preserved = await preserved_identity(request.app.state.database, str(row["remote_id"]))
    return _serialize_creator(row, preserved)


@router.get("/vanished")
async def vanished_creators(
    request: Request,
    limit: int = Query(default=60, ge=1, le=200),
    cursor: str | None = None,
):
    """Creators Douyin has banned, reset, closed or emptied, newest first."""
    database = request.app.state.database
    placeholders = ",".join("?" for _ in ARCHIVE_STATUSES)
    parameters: list[object] = list(ARCHIVE_STATUSES)
    condition = ""
    if cursor:
        try:
            before, remote_id = _decode_cursor(cursor)
        except ValueError:
            return JSONResponse(status_code=400, content={"code": "INVALID_CURSOR", "message": "分页游标无效"})
        condition = (
            " AND (COALESCE(c.archive_status_since, 0) < ? OR "
            "(COALESCE(c.archive_status_since, 0) = ? AND c.remote_id < ?))"
        )
        parameters.extend((before, before, remote_id))
    rows = await database.fetchall(
        _select_sql(f"WHERE c.archive_status IN ({placeholders}){condition}")
        + " ORDER BY COALESCE(c.archive_status_since, 0) DESC, c.remote_id DESC LIMIT ?",
        (*parameters, limit + 1),
    )
    visible = rows[:limit]
    next_cursor = None
    if len(rows) > limit and visible:
        last = visible[-1]
        next_cursor = _encode_cursor(int(last["archive_status_since"] or 0), str(last["remote_id"]))
    counts = await database.fetchall(
        f"SELECT archive_status, COUNT(*) AS n FROM creators WHERE archive_status IN ({placeholders}) "
        "GROUP BY archive_status",
        ARCHIVE_STATUSES,
    )
    return {
        "items": [await _with_preserved(request, row) for row in visible],
        "nextCursor": next_cursor,
        "counts": {str(row["archive_status"]): int(row["n"]) for row in counts},
    }


@router.get("/{creator_id}/snapshots/{snapshot_id}/{kind}")
async def creator_snapshot_image(creator_id: str, snapshot_id: int, kind: str, request: Request):
    if kind not in ("avatar", "cover"):
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "message": "不存在"})
    row = await request.app.state.database.fetchone(
        f"SELECT {kind}_path AS path FROM creator_snapshots WHERE id=? AND creator_id=?",
        (snapshot_id, creator_id),
    )
    path = CreatorMediaStore(request.app.state.settings.archive_root).resolve(row["path"] if row else None)
    if path is None:
        return JSONResponse(status_code=404, content={"code": "IMAGE_UNAVAILABLE", "message": "图片没有存下来"})
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=2592000"})


@router.post("/{creator_id}/archive-check")
async def recheck_creator(creator_id: str, request: Request):
    runtime = request.app.state.runtime
    if runtime is None or not hasattr(runtime, "check_creator_status"):
        return JSONResponse(status_code=503, content={"code": "RUNTIME_UNAVAILABLE", "message": "抖音资料服务未启动"})
    exists = await request.app.state.database.fetchone("SELECT 1 FROM creators WHERE remote_id=?", (creator_id,))
    if exists is None:
        return JSONResponse(status_code=404, content={"code": "CREATOR_NOT_FOUND", "message": "创作者不存在"})
    await runtime.check_creator_status(creator_id)
    return await creator_detail(creator_id, request)


@router.get("/{creator_id}/avatar")
async def creator_avatar(creator_id: str, request: Request):
    row = await request.app.state.database.fetchone(
        "SELECT avatar_url, archive_status FROM creators WHERE remote_id=?", (creator_id,)
    )
    if row is None:
        return JSONResponse(status_code=404, content={"code": "CREATOR_NOT_FOUND", "message": "创作者不存在"})
    if row["archive_status"] != "active":
        preserved = await preserved_identity(request.app.state.database, creator_id)
        kept = CreatorMediaStore(request.app.state.settings.archive_root).resolve(
            preserved["avatar_path"] if preserved is not None else None
        )
        if kept is not None:
            return FileResponse(kept, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
    cache = getattr(request.app.state, "avatar_cache", None)
    if cache is None:
        cache = AvatarCache(request.app.state.settings.archive_root)
        request.app.state.avatar_cache = cache
    path = await cache.get(creator_id, row["avatar_url"])
    if path is None:
        return JSONResponse(status_code=404, content={"code": "AVATAR_UNAVAILABLE", "message": "头像暂不可用"})
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})


@router.get("/{creator_id}")
async def creator_detail(creator_id: str, request: Request):
    row = await request.app.state.database.fetchone(
        _select_sql("WHERE c.remote_id=?"), (creator_id,)
    )
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"code": "CREATOR_NOT_FOUND", "message": "创作者不存在"},
        )
    return await _detail_payload(request, row)


async def _detail_payload(request: Request, row) -> dict[str, object]:
    database = request.app.state.database
    payload = await _with_preserved(request, row)
    history = await database.fetchall(
        "SELECT * FROM creator_snapshots WHERE creator_id=? ORDER BY first_seen_at, id",
        (row["remote_id"],),
    )
    payload["archive"]["history"] = [serialize_snapshot(entry) for entry in history]
    return payload


@router.post("/{creator_id}/refresh")
async def refresh_creator_detail(creator_id: str, request: Request):
    existing = await request.app.state.database.fetchone(
        "SELECT remote_id FROM creators WHERE remote_id=?", (creator_id,)
    )
    if existing is None:
        return JSONResponse(
            status_code=404,
            content={"code": "CREATOR_NOT_FOUND", "message": "创作者不存在"},
        )
    runtime = request.app.state.runtime
    if runtime is None or not hasattr(runtime, "refresh_creator_profile"):
        return JSONResponse(
            status_code=503,
            content={"code": "RUNTIME_UNAVAILABLE", "message": "抖音资料服务未启动"},
        )
    try:
        profile = await runtime.refresh_creator_profile(creator_id)
    except ProviderError as error:
        return JSONResponse(
            status_code=409,
            content={"code": error.code, "message": "暂时无法从抖音更新博主资料"},
        )
    await LibraryRepository(request.app.state.database).upsert_creator(profile, source="profile")
    row = await request.app.state.database.fetchone(
        _select_sql("WHERE c.remote_id=?"), (creator_id,)
    )
    return await _detail_payload(request, row)

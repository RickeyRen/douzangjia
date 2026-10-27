from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from ..avatars import AvatarCache, avatar_route
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


def _serialize_creator(row) -> dict[str, object]:
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
    return {
        "id": row["remote_id"],
        "nickname": row["nickname"],
        "uniqueId": row["unique_id"],
        "avatarUrl": avatar_route(str(row["remote_id"]), row["avatar_url"]),
        "followerCount": row["follower_count"],
        "postCount": row["post_count"],
        "knownItemCount": int(row["known_item_count"]),
        "archivedItemCount": int(row["archived_item_count"]),
        "lastSeenAt": row["last_seen_at"],
        "subscription": subscription,
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
        f"AND {library_item_sql('i')} "
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
        "items": [_serialize_creator(row) for row in visible],
        "nextCursor": next_cursor,
    }


@router.get("/{creator_id}/avatar")
async def creator_avatar(creator_id: str, request: Request):
    row = await request.app.state.database.fetchone(
        "SELECT avatar_url FROM creators WHERE remote_id=?", (creator_id,)
    )
    if row is None:
        return JSONResponse(status_code=404, content={"code": "CREATOR_NOT_FOUND", "message": "创作者不存在"})
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
    return _serialize_creator(row)


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
    await LibraryRepository(request.app.state.database).upsert_creator(profile)
    row = await request.app.state.database.fetchone(
        _select_sql("WHERE c.remote_id=?"), (creator_id,)
    )
    return _serialize_creator(row)

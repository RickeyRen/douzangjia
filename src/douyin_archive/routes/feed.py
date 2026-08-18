from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api")


def _encode_cursor(first_seen_at: int, remote_id: str) -> str:
    payload = json.dumps([first_seen_at, remote_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        return int(payload[0]), str(payload[1])
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid feed cursor") from error


async def _serialize_item(database, row) -> dict[str, Any]:
    collections = await database.fetchall(
        "SELECT c.remote_id, c.name FROM collections c "
        "JOIN collection_items ci ON ci.collection_id=c.remote_id "
        "WHERE ci.item_id=? ORDER BY c.name",
        (row["remote_id"],),
    )
    media = await database.fetchall(
        "SELECT id, asset_index, media_type, byte_size, mime_type FROM media_files "
        "WHERE item_id=? AND status='ready' ORDER BY asset_index",
        (row["remote_id"],),
    )
    return {
        "awemeId": row["remote_id"],
        "author": row["author_name"],
        "description": row["description"],
        "type": row["item_type"],
        "publishedAt": row["published_at"],
        "archivedAt": row["first_seen_at"],
        "collections": [
            {"id": item["remote_id"], "name": item["name"]} for item in collections
        ],
        "media": [
            {
                "id": item["id"],
                "index": item["asset_index"],
                "type": item["media_type"],
                "byteSize": item["byte_size"],
                "mimeType": item["mime_type"],
                "url": f"/api/media/{item['id']}",
            }
            for item in media
        ],
    }


@router.get("/collections")
async def collections(request: Request) -> dict[str, object]:
    rows = await request.app.state.database.fetchall(
        "SELECT c.remote_id, c.name, c.last_seen_at, COUNT(ci.item_id) AS item_count "
        "FROM collections c LEFT JOIN collection_items ci ON ci.collection_id=c.remote_id "
        "GROUP BY c.remote_id ORDER BY c.name"
    )
    return {
        "items": [
            {
                "id": row["remote_id"],
                "name": row["name"],
                "itemCount": row["item_count"],
                "lastSeenAt": row["last_seen_at"],
            }
            for row in rows
        ]
    }


@router.get("/feed")
async def feed(
    request: Request,
    limit: int = Query(default=12, ge=1, le=50),
    cursor: str | None = None,
    collection_id: str | None = Query(default=None, alias="collectionId"),
    media_type: str | None = Query(default=None, alias="type"),
    search: str | None = None,
):
    conditions: list[str] = []
    parameters: list[object] = []
    if collection_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM collection_items ci "
            "WHERE ci.item_id=i.remote_id AND ci.collection_id=?)"
        )
        parameters.append(collection_id)
    if media_type:
        conditions.append("i.item_type=?")
        parameters.append(media_type)
    if search:
        conditions.append("(i.description LIKE ? OR i.author_name LIKE ? OR i.remote_id LIKE ?)")
        term = f"%{search}%"
        parameters.extend((term, term, term))
    if cursor:
        try:
            before_time, before_id = _decode_cursor(cursor)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_CURSOR", "message": "分页游标无效"},
            )
        conditions.append("(i.first_seen_at < ? OR (i.first_seen_at = ? AND i.remote_id < ?))")
        parameters.extend((before_time, before_time, before_id))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await request.app.state.database.fetchall(
        f"SELECT i.* FROM items i {where} "
        "ORDER BY i.first_seen_at DESC, i.remote_id DESC LIMIT ?",
        (*parameters, limit + 1),
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    items = [await _serialize_item(request.app.state.database, row) for row in visible]
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = _encode_cursor(last["first_seen_at"], last["remote_id"])
    return {"items": items, "nextCursor": next_cursor}


@router.get("/items/{remote_id}")
async def item_detail(remote_id: str, request: Request):
    row = await request.app.state.database.fetchone(
        "SELECT * FROM items WHERE remote_id=?", (remote_id,)
    )
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ITEM_NOT_FOUND", "message": "归档作品不存在"},
        )
    return await _serialize_item(request.app.state.database, row)

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


def _local_state(job_status: str | None, *, ready_assets: int, total_assets: int) -> str:
    if total_assets > 0 and ready_assets == total_assets:
        return "downloaded"
    return {
        "running": "downloading",
        "retry": "retry",
        "failed": "failed",
    }.get(job_status or "", "waiting")


def _payload_asset_summary(payload_json: str | None) -> tuple[int, int | None]:
    try:
        payload = json.loads(payload_json or "{}")
        assets = payload.get("assets", [])
    except (json.JSONDecodeError, TypeError, AttributeError):
        return 0, None
    if not isinstance(assets, list):
        return 0, None
    valid = [asset for asset in assets if isinstance(asset, dict)]
    expected_sizes = [asset.get("expected_size") for asset in valid]
    total_bytes = (
        sum(int(size) for size in expected_sizes)
        if valid and all(size is not None for size in expected_sizes)
        else None
    )
    return len(valid), total_bytes


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
    job = await database.fetchone(
        "SELECT status, payload_json FROM download_jobs WHERE kind='download' AND remote_id=?",
        (row["remote_id"],),
    )
    local = await database.fetchone(
        "SELECT COUNT(*) AS total_assets, "
        "COALESCE(SUM(CASE WHEN status='ready' THEN 1 ELSE 0 END), 0) AS ready_assets, "
        "COALESCE(SUM(CASE WHEN status='ready' THEN COALESCE(byte_size, downloaded_bytes) "
        "ELSE downloaded_bytes END), 0) AS downloaded_bytes, "
        "CASE WHEN COUNT(*)=0 OR SUM(CASE WHEN COALESCE(total_bytes, byte_size) IS NULL "
        "THEN 1 ELSE 0 END)>0 THEN NULL ELSE SUM(COALESCE(total_bytes, byte_size)) END "
        "AS total_bytes FROM media_files WHERE item_id=?",
        (row["remote_id"],),
    )
    payload_assets, payload_total_bytes = _payload_asset_summary(
        str(job["payload_json"]) if job is not None else None
    )
    total_assets = max(
        int(local["total_assets"]) if local is not None else 0, payload_assets
    )
    ready_assets = int(local["ready_assets"]) if local is not None else 0
    return {
        "awemeId": row["remote_id"],
        "creatorId": row["creator_id"],
        "author": row["author_name"],
        "description": row["description"],
        "type": row["item_type"],
        "publishedAt": row["published_at"],
        "archivedAt": row["first_seen_at"],
        "sourceUrl": row["source_url"],
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
        "local": {
            "state": _local_state(
                str(job["status"]) if job is not None else None,
                ready_assets=ready_assets,
                total_assets=total_assets,
            ),
            "readyAssets": ready_assets,
            "totalAssets": total_assets,
            "downloadedBytes": int(local["downloaded_bytes"]) if local is not None else 0,
            "totalBytes": (
                payload_total_bytes
                if payload_total_bytes is not None
                else int(local["total_bytes"])
                if local is not None and local["total_bytes"] is not None
                else None
            ),
        },
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
    author: str | None = None,
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
    if author:
        conditions.append("i.author_name=?")
        parameters.append(author)
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

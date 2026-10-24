from __future__ import annotations

import base64
import json
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..remote_availability import RemoteAvailabilityService

router = APIRouter(prefix="/api")


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


def _json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _serialize_item(database, row) -> dict[str, Any]:
    collections = await database.fetchall(
        "SELECT c.remote_id, c.name FROM collections c "
        "JOIN collection_items ci ON ci.collection_id=c.remote_id "
        "WHERE ci.item_id=? ORDER BY c.name",
        (row["remote_id"],),
    )
    media = await database.fetchall(
        "SELECT id, asset_index, media_type, relative_path, byte_size, "
        "checksum_sha256, mime_type, width, height, codec, fps, bit_rate, duration_ms, "
        "probe_status, probed_at, completed_at FROM media_files "
        "WHERE item_id=? AND status='ready' ORDER BY asset_index",
        (row["remote_id"],),
    )
    creator = None
    if row["creator_id"]:
        creator = await database.fetchone(
            "SELECT remote_id, nickname, unique_id, avatar_url FROM creators WHERE remote_id=?",
            (row["creator_id"],),
        )
    star = await database.fetchone(
        "SELECT starred_at FROM item_stars WHERE item_id=?", (row["remote_id"],)
    )
    remote_check = await database.fetchone(
        "SELECT status, checked_at, evidence_code, last_available_at "
        "FROM remote_checks WHERE item_id=?",
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
    total_assets = max(int(local["total_assets"]) if local is not None else 0, payload_assets)
    ready_assets = int(local["ready_assets"]) if local is not None else 0
    statistics = _json_object(row["statistics_json"])
    metadata = _json_object(row["metadata_json"])
    return {
        "awemeId": row["remote_id"],
        "creatorId": row["creator_id"],
        "author": row["author_name"],
        "description": row["description"],
        "type": row["item_type"],
        "publishedAt": row["published_at"],
        "archivedAt": row["first_seen_at"],
        "sourceUrl": row["source_url"],
        "coverUrl": row["cover_url"],
        "thumbnailUrl": (
            f"/api/media/{media[0]['id']}/poster" if media else row["cover_url"] or None
        ),
        "starred": star is not None,
        "starredAt": star["starred_at"] if star is not None else None,
        "creator": (
            {
                "id": creator["remote_id"],
                "nickname": creator["nickname"],
                "uniqueId": creator["unique_id"],
                "avatarUrl": creator["avatar_url"],
            }
            if creator is not None
            else None
        ),
        "douyin": {
            "statistics": statistics,
            "durationMs": row["duration_ms"],
            "hashtags": metadata.get("hashtags", []),
            "music": metadata.get("music"),
            "visibility": row["visibility"],
        },
        "collections": [{"id": item["remote_id"], "name": item["name"]} for item in collections],
        "media": [
            {
                "id": item["id"],
                "index": item["asset_index"],
                "type": item["media_type"],
                "byteSize": item["byte_size"],
                "mimeType": item["mime_type"],
                "url": f"/api/media/{item['id']}",
                "posterUrl": f"/api/media/{item['id']}/poster",
                "relativePath": item["relative_path"],
                "checksumSha256": item["checksum_sha256"],
                "completedAt": item["completed_at"],
                "technical": {
                    "width": item["width"],
                    "height": item["height"],
                    "codec": item["codec"],
                    "fps": item["fps"],
                    "bitRate": item["bit_rate"],
                    "durationMs": item["duration_ms"],
                    "probeStatus": item["probe_status"],
                    "probedAt": item["probed_at"],
                },
            }
            for item in media
        ],
        "remoteAvailability": (
            {
                "status": remote_check["status"],
                "checkedAt": remote_check["checked_at"],
                "evidenceCode": remote_check["evidence_code"],
                "lastAvailableAt": remote_check["last_available_at"],
            }
            if remote_check is not None
            else {
                "status": "unknown",
                "checkedAt": None,
                "evidenceCode": None,
                "lastAvailableAt": None,
            }
        ),
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


FEED_SORTS = {"archived", "published", "source", "starred", "random"}


def _encode_feed_cursor(key: object, remote_id: str) -> str:
    payload = json.dumps([key, remote_id], separators=(",", ":"), ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_feed_cursor(value: str) -> tuple[object, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        key, remote_id = payload
        if not isinstance(key, (int, str)) or isinstance(key, bool):
            raise TypeError
        return key, str(remote_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid feed cursor") from error


def _invalid_feed_request(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": code, "message": message})


@router.get("/feed")
async def feed(
    request: Request,
    limit: int = Query(default=12, ge=1, le=50),
    cursor: str | None = None,
    collection_id: str | None = Query(default=None, alias="collectionId"),
    source_id: str | None = Query(default=None, alias="sourceId"),
    creator_id: str | None = Query(default=None, alias="creatorId"),
    media_type: str | None = Query(default=None, alias="type"),
    author: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    seed: int = Query(default=1, ge=1, le=2_147_483_646),
    downloaded: bool = False,
    starred: bool = False,
):
    sort = sort or ("source" if source_id else "starred" if starred else "archived")
    if sort not in FEED_SORTS:
        return _invalid_feed_request("INVALID_SORT", "不支持的排序方式")
    if sort == "source" and not source_id:
        return _invalid_feed_request("INVALID_SORT", "按来源顺序排序需要指定来源")
    if sort == "starred" and not starred:
        return _invalid_feed_request("INVALID_SORT", "按精选时间排序需要只看精选")

    joins: list[str] = []
    conditions: list[str] = []
    parameters: list[object] = []
    if source_id:
        joins.append("JOIN source_items si ON si.item_id=i.remote_id AND si.source_id=?")
        parameters.append(source_id)
    if starred:
        joins.append("JOIN item_stars st ON st.item_id=i.remote_id")
    if collection_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM collection_items ci "
            "WHERE ci.item_id=i.remote_id AND ci.collection_id=?)"
        )
        parameters.append(collection_id)
    if creator_id:
        conditions.append("i.creator_id=?")
        parameters.append(creator_id)
    if media_type:
        conditions.append("i.item_type=?")
        parameters.append(media_type)
    if author:
        conditions.append("i.author_name=?")
        parameters.append(author)
    if search:
        conditions.append(
            "(i.description LIKE ? OR i.author_name LIKE ? OR i.remote_id LIKE ? "
            "OR EXISTS (SELECT 1 FROM creators c WHERE c.remote_id=i.creator_id "
            "AND (c.nickname LIKE ? OR c.unique_id LIKE ?)))"
        )
        term = f"%{search}%"
        parameters.extend((term,) * 5)
    if downloaded:
        conditions.append(
            "EXISTS (SELECT 1 FROM media_files mf "
            "WHERE mf.item_id=i.remote_id AND mf.status='ready')"
        )

    sort_expression = {
        "archived": "i.first_seen_at",
        "published": "COALESCE(i.published_at, i.first_seen_at)",
        "source": "COALESCE(si.remote_order, '')",
        "starred": "st.starred_at",
        # Scatter ids with a large odd multiplier, then permute by a seed-derived
        # factor; both steps are bijections mod a prime, so pages stay stable.
        "random": (
            "(((CAST(substr(i.remote_id, -9) AS INTEGER) * 2654435761) % 4294967311)"
            f" * {seed % 65521 + 1}) % 4294967311"
        ),
    }[sort]
    expects_text_key = sort == "source"
    if cursor:
        try:
            before_key, before_id = _decode_feed_cursor(cursor)
            if isinstance(before_key, str) != expects_text_key:
                raise ValueError
        except ValueError:
            return _invalid_feed_request("INVALID_CURSOR", "分页游标无效")
        conditions.append(
            f"({sort_expression} < ? OR ({sort_expression} = ? AND i.remote_id < ?))"
        )
        parameters.extend((before_key, before_key, before_id))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await request.app.state.database.fetchall(
        f"SELECT i.*, {sort_expression} AS feed_sort_key FROM items i {' '.join(joins)} "
        f"{where} ORDER BY feed_sort_key DESC, i.remote_id DESC LIMIT ?",
        (*parameters, limit + 1),
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    items = [await _serialize_item(request.app.state.database, row) for row in visible]
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = _encode_feed_cursor(last["feed_sort_key"], str(last["remote_id"]))
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


@router.post("/items/{remote_id}/remote-check")
async def check_item_remote(remote_id: str, request: Request):
    row = await request.app.state.database.fetchone(
        "SELECT remote_id FROM items WHERE remote_id=?", (remote_id,)
    )
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ITEM_NOT_FOUND", "message": "归档作品不存在"},
        )
    runtime = request.app.state.runtime
    if runtime is None or not hasattr(runtime, "check_item_availability"):
        return JSONResponse(
            status_code=503,
            content={"code": "REMOTE_CHECK_UNAVAILABLE", "message": "远端检查暂不可用"},
        )
    evidence = await runtime.check_item_availability(remote_id)
    return await RemoteAvailabilityService(request.app.state.database).record(remote_id, evidence)


async def _item_exists(request: Request, remote_id: str) -> bool:
    row = await request.app.state.database.fetchone(
        "SELECT 1 FROM items WHERE remote_id=?", (remote_id,)
    )
    return row is not None


def _item_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"code": "ITEM_NOT_FOUND", "message": "归档作品不存在"},
    )


@router.put("/items/{remote_id}/star")
async def star_item(remote_id: str, request: Request):
    if not await _item_exists(request, remote_id):
        return _item_not_found()
    starred_at = int(time.time())
    await request.app.state.database.execute(
        "INSERT INTO item_stars (item_id, starred_at) VALUES (?, ?) "
        "ON CONFLICT(item_id) DO NOTHING",
        (remote_id, starred_at),
    )
    row = await request.app.state.database.fetchone(
        "SELECT starred_at FROM item_stars WHERE item_id=?", (remote_id,)
    )
    return {"starred": True, "starredAt": row["starred_at"] if row else starred_at}


@router.delete("/items/{remote_id}/star")
async def unstar_item(remote_id: str, request: Request):
    if not await _item_exists(request, remote_id):
        return _item_not_found()
    await request.app.state.database.execute(
        "DELETE FROM item_stars WHERE item_id=?", (remote_id,)
    )
    return {"starred": False, "starredAt": None}

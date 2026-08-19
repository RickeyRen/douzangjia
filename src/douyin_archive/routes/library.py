from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..library_repository import LibraryRepository
from .feed import _serialize_item

router = APIRouter(prefix="/api/library")


def _encode_library_cursor(sort_key: str | int, remote_id: str) -> str:
    payload = json.dumps([sort_key, remote_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_library_cursor(value: str) -> tuple[str | int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        sort_key = payload[0]
        if not isinstance(sort_key, (str, int)) or isinstance(sort_key, bool):
            raise TypeError
        return sort_key, str(payload[1])
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid library cursor") from error


@router.get("/sources")
async def sources(request: Request) -> dict[str, object]:
    rows = await request.app.state.database.fetchall(
        "SELECT * FROM library_sources ORDER BY kind, name, id"
    )
    repository = LibraryRepository(request.app.state.database)
    items: list[dict[str, Any]] = []
    for row in rows:
        integrity = await repository.source_integrity(str(row["id"]))
        if integrity is None:
            continue
        items.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "remoteId": row["remote_id"],
                "name": row["name"],
                "declaredCount": integrity.declared_count,
                "discoveredCount": integrity.discovered_count,
                "archivedCount": integrity.archived_count,
                "missingCount": integrity.missing_count,
                "syncStatus": integrity.sync_status.value,
                "complete": integrity.complete,
                "lastFullScanAt": row["last_full_scan_at"],
                "lastIncrementalScanAt": row["last_incremental_scan_at"],
                "errorCode": row["error_code"],
            }
        )
    return {"items": items}


@router.get("/feed")
async def library_feed(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
    source_id: str | None = Query(default=None, alias="sourceId"),
    creator_id: str | None = Query(default=None, alias="creatorId"),
):
    if source_id and creator_id:
        return JSONResponse(
            status_code=400,
            content={
                "code": "AMBIGUOUS_LIBRARY_FILTER",
                "message": "来源和创作者筛选不能同时使用",
            },
        )

    parameters: list[object] = []
    conditions: list[str] = []
    if source_id:
        from_clause = "items i JOIN source_items si ON si.item_id=i.remote_id"
        sort_expression = "COALESCE(si.remote_order, '')"
        conditions.append("si.source_id=?")
        parameters.append(source_id)
        cursor_kind = "text"
    else:
        from_clause = "items i"
        sort_expression = "COALESCE(i.published_at, i.first_seen_at)"
        cursor_kind = "integer"
        if creator_id:
            conditions.append("i.creator_id=?")
            parameters.append(creator_id)

    if cursor:
        try:
            before_key, before_id = _decode_library_cursor(cursor)
            if cursor_kind == "text" and not isinstance(before_key, str):
                raise ValueError
            if cursor_kind == "integer" and not isinstance(before_key, int):
                raise ValueError
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_CURSOR", "message": "分页游标无效"},
            )
        conditions.append(
            f"({sort_expression} < ? OR ({sort_expression} = ? AND i.remote_id < ?))"
        )
        parameters.extend((before_key, before_key, before_id))

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await request.app.state.database.fetchall(
        f"SELECT i.*, {sort_expression} AS library_sort_key "
        f"FROM {from_clause} {where} "
        f"ORDER BY {sort_expression} DESC, i.remote_id DESC LIMIT ?",
        (*parameters, limit + 1),
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    items = [await _serialize_item(request.app.state.database, row) for row in visible]
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = _encode_library_cursor(
            last["library_sort_key"], str(last["remote_id"])
        )
    return {"items": items, "nextCursor": next_cursor}


@router.get("/entities")
async def library_entities(
    request: Request,
    source_id: str = Query(alias="sourceId"),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
):
    parameters: list[object] = [source_id]
    conditions = ["source_id=?"]
    sort_expression = "COALESCE(remote_order, '')"
    if cursor:
        try:
            before_key, before_id = _decode_library_cursor(cursor)
            if not isinstance(before_key, str):
                raise TypeError
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_CURSOR", "message": "分页游标无效"},
            )
        conditions.append(
            f"({sort_expression} < ? OR "
            f"({sort_expression} = ? AND remote_id < ?))"
        )
        parameters.extend((before_key, before_key, before_id))
    rows = await request.app.state.database.fetchall(
        "SELECT *, "
        f"{sort_expression} AS entity_sort_key FROM source_entities "
        f"WHERE {' AND '.join(conditions)} "
        f"ORDER BY {sort_expression} DESC, remote_id DESC LIMIT ?",
        (*parameters, limit + 1),
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    items = []
    for row in visible:
        try:
            metadata = json.loads(str(row["metadata_json"]))
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        items.append(
            {
                "id": row["remote_id"],
                "type": row["entity_type"],
                "title": row["title"],
                "subtitle": row["subtitle"],
                "coverUrl": row["cover_url"],
                "sourceUrl": row["source_url"],
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = _encode_library_cursor(
            str(last["entity_sort_key"]), str(last["remote_id"])
        )
    return {"items": items, "nextCursor": next_cursor}

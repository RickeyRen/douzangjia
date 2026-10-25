from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..archive_repository import ArchiveBatch, ArchiveBatchRepository
from ..archive_service import (
    ArchivePayloadUnavailable,
    ArchiveService,
    ArchiveTargetNotFound,
)
from ..repositories import JobRepository

router = APIRouter(prefix="/api")


class SelectionRequest(BaseModel):
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=2000)


class BulkStarRequest(BaseModel):
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=2000)
    starred: bool = True


class SubscriptionRequest(BaseModel):
    enabled: bool
    scan_interval_seconds: int = Field(
        default=21_600, ge=900, le=2_592_000, alias="scanIntervalSeconds"
    )
    archive_new_items: bool = Field(default=True, alias="archiveNewItems")


def _serialize_batch(batch: ArchiveBatch) -> dict[str, object]:
    return {
        "id": batch.id,
        "kind": batch.kind,
        "targetId": batch.target_id,
        "status": batch.status,
        "discoveredCount": batch.discovered_count,
        "completedCount": batch.completed_count,
        "failedCount": batch.failed_count,
        "downloadedBytes": batch.downloaded_bytes,
        "totalBytes": batch.total_bytes,
        "errorCode": batch.error_code,
        "totalItems": batch.total_items,
        "createdAt": batch.created_at,
        "updatedAt": batch.updated_at,
        "finishedAt": batch.finished_at,
    }


def _service(request: Request) -> ArchiveService:
    database = request.app.state.database
    return ArchiveService(
        database,
        JobRepository(database),
        ArchiveBatchRepository(database),
    )


async def _archive_target(request: Request, kind: str, target_id: str):
    service = _service(request)
    try:
        if kind == "item":
            batch = await service.archive_item(target_id)
        elif kind == "source":
            batch = await service.archive_source(target_id)
        elif request.app.state.runtime is not None:
            creator = await request.app.state.database.fetchone(
                "SELECT remote_id FROM creators WHERE remote_id=?", (target_id,)
            )
            if creator is None:
                raise ArchiveTargetNotFound(target_id)
            batch = await request.app.state.runtime.trigger_creator_archive(target_id)
        else:
            batch = await service.archive_creator(target_id)
    except ArchiveTargetNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "code": "ARCHIVE_TARGET_NOT_FOUND",
                "message": "归档目标不存在",
            },
        )
    except ArchivePayloadUnavailable:
        return JSONResponse(
            status_code=409,
            content={
                "code": "ARCHIVE_PAYLOAD_UNAVAILABLE",
                "message": "作品媒体信息需要先同步",
            },
        )
    return _serialize_batch(batch)


@router.post("/archive/items/{remote_id}", status_code=202)
async def archive_item(remote_id: str, request: Request):
    return await _archive_target(request, "item", remote_id)


@router.post("/archive/sources/{source_id}", status_code=202)
async def archive_source(source_id: str, request: Request):
    return await _archive_target(request, "source", source_id)


@router.post("/archive/creators/{creator_id}", status_code=202)
async def archive_creator(creator_id: str, request: Request):
    return await _archive_target(request, "creator", creator_id)


@router.post("/archive/selection", status_code=202)
async def archive_selection(body: SelectionRequest, request: Request):
    try:
        batch, skipped = await _service(request).archive_selection(body.item_ids)
    except ArchiveTargetNotFound:
        return JSONResponse(
            status_code=404,
            content={"code": "ARCHIVE_TARGET_NOT_FOUND", "message": "所选作品不存在"},
        )
    return {"batch": _serialize_batch(batch), "skipped": skipped}


@router.get("/archive/missing")
async def missing_summary(request: Request):
    return await _service(request).missing_summary()


@router.post("/archive/missing", status_code=202)
async def archive_missing(request: Request):
    batch, skipped = await _service(request).archive_missing()
    return {"batch": _serialize_batch(batch), "skipped": skipped}


@router.post("/items/bulk-star")
async def bulk_star(body: BulkStarRequest, request: Request):
    database = request.app.state.database
    now = int(time.time())
    placeholders = ",".join("?" for _ in body.item_ids)
    async with database.transaction(immediate=True):
        if body.starred:
            await database.execute(
                f"INSERT OR IGNORE INTO item_stars (item_id, starred_at) "
                f"SELECT remote_id, ? FROM items WHERE remote_id IN ({placeholders})",
                (now, *body.item_ids),
            )
        else:
            await database.execute(
                f"DELETE FROM item_stars WHERE item_id IN ({placeholders})", tuple(body.item_ids)
            )
    rows = await database.fetchall(
        f"SELECT item_id FROM item_stars WHERE item_id IN ({placeholders})", tuple(body.item_ids)
    )
    return {"starred": sorted(str(row["item_id"]) for row in rows)}


@router.get("/archive/batches")
async def list_batches(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    repository = ArchiveBatchRepository(request.app.state.database)
    batches = await repository.list_batches(limit=limit)
    return {"items": [_serialize_batch(batch) for batch in batches]}


@router.get("/archive/batches/{batch_id}")
async def get_batch(batch_id: int, request: Request):
    batch = await ArchiveBatchRepository(request.app.state.database).refresh_batch(batch_id)
    if batch is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ARCHIVE_BATCH_NOT_FOUND", "message": "归档批次不存在"},
        )
    return _serialize_batch(batch)


@router.post("/archive/batches/{batch_id}/{action}")
async def control_batch(batch_id: int, action: str, request: Request):
    if action not in {"pause", "resume", "cancel"}:
        return JSONResponse(
            status_code=404,
            content={"code": "ARCHIVE_ACTION_NOT_FOUND", "message": "批次操作不存在"},
        )
    repository = ArchiveBatchRepository(request.app.state.database)
    try:
        batch = await repository.control_batch(batch_id, action)
    except ValueError:
        return JSONResponse(
            status_code=409,
            content={"code": "ARCHIVE_ACTION_CONFLICT", "message": "当前批次状态不支持该操作"},
        )
    if batch is None:
        return JSONResponse(
            status_code=404,
            content={"code": "ARCHIVE_BATCH_NOT_FOUND", "message": "归档批次不存在"},
        )
    return _serialize_batch(batch)


@router.put("/creator-subscriptions/{creator_id}")
async def put_creator_subscription(
    creator_id: str, payload: SubscriptionRequest, request: Request
):
    database = request.app.state.database
    creator = await database.fetchone(
        "SELECT remote_id FROM creators WHERE remote_id=?", (creator_id,)
    )
    if creator is None:
        return JSONResponse(
            status_code=404,
            content={"code": "CREATOR_NOT_FOUND", "message": "创作者不存在"},
        )
    subscription = await ArchiveBatchRepository(database).upsert_subscription(
        creator_id,
        enabled=payload.enabled,
        scan_interval_seconds=payload.scan_interval_seconds,
        archive_new_items=payload.archive_new_items,
    )
    data = asdict(subscription)
    return {
        "creatorId": data["creator_id"],
        "enabled": data["enabled"],
        "scanIntervalSeconds": data["scan_interval_seconds"],
        "archiveNewItems": data["archive_new_items"],
        "lastScanAt": data["last_scan_at"],
        "nextScanAt": data["next_scan_at"],
        "lastErrorCode": data["last_error_code"],
    }

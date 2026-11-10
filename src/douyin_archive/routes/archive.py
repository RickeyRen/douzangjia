from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..archive_progress import ArchiveProgressService, batch_label
from ..archive_repository import ArchiveBatch, ArchiveBatchRepository
from ..archive_service import (
    ArchivePayloadUnavailable,
    ArchiveService,
    ArchiveTargetNotFound,
)
from ..repositories import JobRepository

PROGRESS_SHARE_SECONDS = 2.5

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
# Queueing ten thousand items takes minutes; answer the request once the batch
# exists and keep adding items in the background.
MISSING_QUEUE_WAIT_SECONDS = 5


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
    request.app.state.archive_progress_cache = None
    return await _archive_target(request, "item", remote_id)


@router.post("/archive/sources/{source_id}", status_code=202)
async def archive_source(source_id: str, request: Request):
    request.app.state.archive_progress_cache = None
    return await _archive_target(request, "source", source_id)


@router.post("/archive/creators/{creator_id}", status_code=202)
async def archive_creator(creator_id: str, request: Request):
    request.app.state.archive_progress_cache = None
    return await _archive_target(request, "creator", creator_id)


@router.post("/archive/selection", status_code=202)
async def archive_selection(body: SelectionRequest, request: Request):
    request.app.state.archive_progress_cache = None
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
    request.app.state.archive_progress_cache = None
    state = request.app.state
    service = _service(request)
    task = await start_missing_queue(state, service)
    try:
        batch, skipped = await asyncio.wait_for(asyncio.shield(task), MISSING_QUEUE_WAIT_SECONDS)
    except TimeoutError:
        plan = getattr(state, "missing_archive_plan", None) or {}
        batch = await service.batches.get_batch(int(plan["batchId"])) if plan else None
        if batch is None:
            batch = await service.batches.create_batch("missing", "all")
        return {"batch": _serialize_batch(batch), "skipped": 0, "queueing": True}
    return {"batch": _serialize_batch(batch), "skipped": skipped, "queueing": False}


async def start_missing_queue(state: Any, service: ArchiveService) -> asyncio.Task:
    """Start (or join) queueing every unsaved library item into the bulk batch."""
    task = getattr(state, "missing_archive_task", None)
    if task is None or task.done():
        item_ids = await service.missing_item_ids()
        batch = await service.batches.create_batch("missing", "all")
        # The progress card shows the whole plan while items are still being queued.
        state.missing_archive_plan = {"batchId": batch.id, "planned": len(item_ids)}
        task = asyncio.create_task(service.archive_missing(item_ids))
        task.add_done_callback(_log_queue_failure)
        state.missing_archive_task = task
    return task


async def resume_missing_queue(app: Any) -> bool:
    """Finish queueing a "save everything" batch that a restart cut short.

    Queueing ten thousand items runs in the background for minutes; a deploy or
    reboot in that window left most of them never queued while the card showed
    the batch nearly done. Paused or stopped batches are the user's choice and
    stay as they are.
    """
    database = app.state.database
    active = await database.fetchone(
        "SELECT id FROM archive_batches WHERE kind='missing' AND target_id='all' "
        "AND status IN ('queued', 'running') ORDER BY id DESC LIMIT 1"
    )
    if active is None:
        return False
    service = ArchiveService(database, JobRepository(database), ArchiveBatchRepository(database))
    await start_missing_queue(app.state, service)
    return True


def queueing_plan(request: Request) -> dict[str, int] | None:
    """The bulk download still being queued, if any."""
    task = getattr(request.app.state, "missing_archive_task", None)
    plan = getattr(request.app.state, "missing_archive_plan", None)
    if task is None or task.done() or not plan:
        return None
    return plan


def _log_queue_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("queueing missing items failed", exc_info=task.exception())


@router.get("/archive/progress")
async def archive_progress(request: Request):
    state = request.app.state
    cached = getattr(state, "archive_progress_cache", None)
    now = time.monotonic()
    if cached is not None and now - cached[0] < PROGRESS_SHARE_SECONDS:
        # The web page and the app both poll every few seconds; with a large
        # batch each snapshot costs a second or more on a busy NAS.
        snapshot = copy.deepcopy(cached[1])
    else:
        snapshot = await ArchiveProgressService(state.database).snapshot()
        state.archive_progress_cache = (time.monotonic(), copy.deepcopy(snapshot))
    plan = queueing_plan(request)
    active = snapshot.get("active")
    if plan and active and any(batch["id"] == plan["batchId"] for batch in active["batches"]):
        active["plannedItems"] = max(int(active["totalItems"]), plan["planned"])
        active["queueing"] = True
    return snapshot


@router.post("/archive/retry-failed")
async def retry_failed(request: Request):
    request.app.state.archive_progress_cache = None
    retried = await ArchiveProgressService(request.app.state.database).retry_failed()
    return {"retried": retried}


@router.post("/items/bulk-star")
async def bulk_star(body: BulkStarRequest, request: Request):
    request.app.state.archive_progress_cache = None
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
    database = request.app.state.database
    return {
        "items": [
            {**_serialize_batch(batch), "label": await batch_label(database, batch)}
            for batch in batches
        ]
    }


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
    request.app.state.archive_progress_cache = None
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

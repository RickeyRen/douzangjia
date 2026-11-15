"""Resume long videos where they were left, on whichever device opens them next."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api")

# Douyin clips are mostly short; only longer videos are worth resuming.
MIN_DURATION_MS = 120_000
# A few seconds in is "just looked"; the last stretch is "finished".
MIN_POSITION_MS = 10_000
END_MARGIN_MS = 15_000


class PlaybackBody(BaseModel):
    position_ms: int = Field(alias="positionMs", ge=0)
    duration_ms: int = Field(alias="durationMs", gt=0)


def resumable(position_ms: int, duration_ms: int) -> bool:
    return (
        duration_ms >= MIN_DURATION_MS
        and MIN_POSITION_MS <= position_ms <= duration_ms - END_MARGIN_MS
    )


@router.get("/items/{remote_id}/playback")
async def get_playback(remote_id: str, request: Request):
    row = await request.app.state.database.fetchone(
        "SELECT position_ms, duration_ms, updated_at FROM item_playback WHERE item_id=?", (remote_id,)
    )
    if row is None:
        return {"positionMs": None}
    return {
        "positionMs": int(row["position_ms"]),
        "durationMs": int(row["duration_ms"]),
        "updatedAt": int(row["updated_at"]),
    }


@router.put("/items/{remote_id}/playback")
async def set_playback(remote_id: str, body: PlaybackBody, request: Request):
    database = request.app.state.database
    if await database.fetchone("SELECT 1 FROM items WHERE remote_id=?", (remote_id,)) is None:
        return JSONResponse(status_code=404, content={"code": "ITEM_NOT_FOUND", "message": "归档作品不存在"})
    if not resumable(body.position_ms, body.duration_ms):
        # Finished, barely started or too short: next time starts from the top.
        await database.execute("DELETE FROM item_playback WHERE item_id=?", (remote_id,))
        return {"positionMs": None}
    await database.execute(
        "INSERT INTO item_playback (item_id, position_ms, duration_ms, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(item_id) DO UPDATE SET position_ms=excluded.position_ms, "
        "duration_ms=excluded.duration_ms, updated_at=excluded.updated_at",
        (remote_id, body.position_ms, body.duration_ms, int(time.time())),
    )
    return {"positionMs": body.position_ms}

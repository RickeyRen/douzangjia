from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..live_stream import PASS_HEADERS, LiveStreamResolver, StreamUnavailable
from ..posters import PosterCache

router = APIRouter(prefix="/api")


class RangeNotSatisfiable(ValueError):
    pass


def parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return None
    if not value.startswith("bytes=") or "," in value or size <= 0:
        raise RangeNotSatisfiable
    specification = value[6:].strip()
    if "-" not in specification:
        raise RangeNotSatisfiable
    start_text, end_text = specification.split("-", 1)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise RangeNotSatisfiable
            return max(0, size - suffix), size - 1
        start = int(start_text)
        end = int(end_text) if end_text else size - 1
    except ValueError as error:
        raise RangeNotSatisfiable from error
    if start < 0 or start >= size or end < start:
        raise RangeNotSatisfiable
    return start, min(end, size - 1)


def iter_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    remaining = end - start + 1
    with path.open("rb") as source:
        source.seek(start)
        while remaining > 0:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _media_not_found() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"code": "MEDIA_NOT_FOUND", "message": "归档媒体不存在"},
    )


async def _ready_media(request: Request, media_id: int):
    """Return (row, path) for a ready media file confined to ``objects/``."""
    row = await request.app.state.database.fetchone(
        "SELECT relative_path, mime_type, media_type FROM media_files "
        "WHERE id=? AND status='ready'",
        (media_id,),
    )
    if row is None or not row["relative_path"]:
        return None
    root = request.app.state.settings.archive_root.resolve()
    object_root = (root / "objects").resolve()
    path = (root / str(row["relative_path"])).resolve()
    if not path.is_relative_to(object_root) or not path.is_file():
        return None
    return row, path


@router.get("/media/{media_id}/poster")
async def media_poster(media_id: int, request: Request):
    found = await _ready_media(request, media_id)
    if found is None:
        return _media_not_found()
    row, path = found
    cache = getattr(request.app.state, "poster_cache", None)
    if cache is None:
        cache = PosterCache(request.app.state.settings.archive_root)
        request.app.state.poster_cache = cache
    poster = await cache.poster(media_id, path, str(row["media_type"]))
    if poster is None:
        return _media_not_found()
    return FileResponse(
        poster,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=604800"},
    )


@router.get("/media/{media_id}")
async def media(media_id: int, request: Request):
    found = await _ready_media(request, media_id)
    if found is None:
        return _media_not_found()
    row, path = found
    size = path.stat().st_size
    try:
        selected = parse_range(request.headers.get("Range"), size)
    except RangeNotSatisfiable:
        return StreamingResponse(
            iter(()),
            status_code=416,
            headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
        )
    if selected is None:
        start, end, status_code = 0, size - 1, 200
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(size),
        }
    else:
        start, end = selected
        status_code = 206
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        }
    return StreamingResponse(
        iter_file(path, start, end),
        status_code=status_code,
        # iOS players refuse octet-stream; fall back to the file's extension.
        media_type=row["mime_type"] or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        headers=headers,
    )


def _live_stream(request: Request) -> LiveStreamResolver | None:
    state = request.app.state
    resolver = getattr(state, "live_stream", None)
    if resolver is not None:
        return resolver
    runtime = getattr(state, "runtime", None)
    if runtime is None or not hasattr(runtime, "http"):
        return None
    resolver = LiveStreamResolver(
        state.database,
        runtime.http,
        fetch_records=runtime.sync.fetch_item_records,
        refresh_links=runtime.jobs.refresh_links,
    )
    state.live_stream = resolver
    return resolver


@router.get("/items/{remote_id}/stream")
async def item_stream(remote_id: str, request: Request):
    """A work not saved yet, relayed from Douyin so it plays while it downloads."""
    database = request.app.state.database
    if await database.fetchone("SELECT 1 FROM items WHERE remote_id=?", (remote_id,)) is None:
        return JSONResponse(
            status_code=404, content={"code": "ITEM_NOT_FOUND", "message": "归档作品不存在"}
        )
    resolver = _live_stream(request)
    if resolver is None:
        return JSONResponse(
            status_code=503, content={"code": "STREAM_UNAVAILABLE", "message": "在线播放暂不可用"}
        )
    try:
        upstream = await resolver.open(remote_id, request.headers.get("Range"))
    except StreamUnavailable:
        return JSONResponse(
            status_code=409,
            content={"code": "STREAM_UNAVAILABLE", "message": "抖音暂时没给出这个视频，存好后就能播放"},
        )
    headers = {name: upstream.headers[name] for name in PASS_HEADERS if name in upstream.headers}
    headers.setdefault("Accept-Ranges", "bytes")
    headers["Cache-Control"] = "private, no-store"

    async def body() -> AsyncIterator[bytes]:
        try:
            # Mock and already-buffered responses only replay through aiter_bytes.
            chunks = upstream.aiter_bytes() if upstream.is_stream_consumed else upstream.aiter_raw()
            async for chunk in chunks:
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        body(), status_code=upstream.status_code, media_type="video/mp4", headers=headers
    )

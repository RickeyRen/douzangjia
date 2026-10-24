from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

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
        media_type=row["mime_type"] or "application/octet-stream",
        headers=headers,
    )

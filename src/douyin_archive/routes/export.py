"""Take works home: an album or a selection as one ZIP, with metadata beside each file.

The ZIP is stored, not compressed (videos don't shrink), and written straight
into the response as it is read from disk: no temporary copy on the NAS, and a
20 GB album starts downloading at once.
"""

from __future__ import annotations

import csv
import io
import time
import zipfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..library_scope import library_item_sql
from ..paths import sanitize_segment
from ..sidecars import SHANGHAI, build_nfo, display_title, find_poster, load_works

router = APIRouter(prefix="/api")

MAX_SELECTED = 300
CHUNK_BYTES = 1024 * 1024
NAME_TITLE_CHARS = 50
CSV_HEADER = ["标题", "博主", "发布时间", "时长（秒）", "话题", "我的标签", "相册", "备注", "原链接", "文件"]


@router.get("/export")
async def export_zip(
    request: Request,
    album_id: int | None = Query(default=None, alias="albumId"),
    items: str | None = Query(default=None),
):
    database = request.app.state.database
    root: Path = request.app.state.settings.archive_root.resolve()
    if album_id is not None:
        album = await database.fetchone("SELECT name FROM albums WHERE id=?", (album_id,))
        if album is None:
            return JSONResponse(status_code=404, content={"code": "ALBUM_NOT_FOUND", "message": "相册不存在"})
        rows = await database.fetchall(
            "SELECT item_id FROM album_items WHERE album_id=? ORDER BY added_at DESC, item_id DESC",
            (album_id,),
        )
        ids = [str(row["item_id"]) for row in rows]
        folder = sanitize_segment(str(album["name"]), max_length=60)
    else:
        ids = list(dict.fromkeys(part.strip() for part in (items or "").split(",") if part.strip()))
        if not ids:
            return JSONResponse(status_code=400, content={"code": "NOTHING_SELECTED", "message": "没有选择作品"})
        if len(ids) > MAX_SELECTED:
            return JSONResponse(
                status_code=400,
                content={"code": "TOO_MANY", "message": f"一次最多导出 {MAX_SELECTED} 个作品"},
            )
        folder = f"抖藏家导出-{time.strftime('%Y%m%d-%H%M')}"

    entries, listing = await _plan(database, root, ids, folder)
    if not entries:
        return JSONResponse(
            status_code=409, content={"code": "NOTHING_SAVED", "message": "选中的作品还没有存到 NAS"}
        )
    entries.append((f"{folder}/作品清单.csv", _csv(listing)))
    filename = f"{folder}.zip"
    return StreamingResponse(
        _zip_stream(entries),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"douzangjia-export.zip\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


CATALOG_HEADER = [
    "作品 ID", "类型", "标题", "博主", "发布时间", "收藏时间", "时长（秒）", "话题", "我的标签",
    "相册", "备注", "原链接", "是否已存到 NAS", "NAS 上的文件",
]
CATALOG_CHUNK = 500


@router.get("/export/catalog.csv")
async def export_catalog(request: Request):
    """Every work in the library as one spreadsheet: text only, so it stays small enough to keep anywhere."""
    database = request.app.state.database
    rows = await database.fetchall(
        f"SELECT remote_id, item_type FROM items i WHERE {library_item_sql('i')} "
        "ORDER BY first_seen_at DESC, remote_id DESC"
    )
    order = [(str(row["remote_id"]), str(row["item_type"])) for row in rows]

    async def body():
        yield _csv_text([CATALOG_HEADER], bom=True)
        for start in range(0, len(order), CATALOG_CHUNK):
            chunk = order[start : start + CATALOG_CHUNK]
            ids = [item_id for item_id, _ in chunk]
            works = await load_works(database, ids)
            marks = ",".join("?" * len(ids))
            stored: dict[str, list[str]] = {}
            for row in await database.fetchall(
                "SELECT item_id, relative_path FROM media_files "
                f"WHERE item_id IN ({marks}) AND status='ready' AND relative_path IS NOT NULL "
                "ORDER BY item_id, asset_index",
                ids,
            ):
                stored.setdefault(str(row["item_id"]), []).append(str(row["relative_path"]))
            lines = []
            for item_id, kind in chunk:
                work = works.get(item_id)
                if work is None:
                    continue
                author = str(work.get("author_name") or "")
                listing = _listing_row(work, display_title(str(work.get("description") or ""), author), "")
                files = stored.get(item_id, [])
                if kind == "gallery" and files:
                    location = str(Path(files[0]).parent) + "/"
                else:
                    location = files[0] if files else ""
                collected = work.get("first_seen_at")
                lines.append(
                    [
                        item_id,
                        "图集" if kind == "gallery" else "视频",
                        *listing[:3],
                        datetime.fromtimestamp(int(collected), SHANGHAI).strftime("%Y-%m-%d %H:%M") if collected else "",
                        *listing[3:9],
                        "是" if files else "否",
                        location,
                    ]
                )
            yield _csv_text(lines)

    filename = f"抖藏家作品清单-{time.strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        body(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"douzangjia-catalog.csv\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


def _csv_text(rows: list[list[str]], *, bom: bool = False) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return (("\ufeff" if bom else "") + buffer.getvalue()).encode("utf-8")


async def _plan(
    database: Any, root: Path, ids: list[str], folder: str
) -> tuple[list[tuple[str, Path | bytes]], list[list[str]]]:
    """Decide every file in the ZIP up front; streaming then only reads disk."""
    if not ids:
        return [], []
    works: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 500):
        works.update(await load_works(database, ids[start : start + 500]))
    files: dict[str, list[dict[str, Any]]] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        marks = ",".join("?" * len(chunk))
        for row in await database.fetchall(
            "SELECT id, item_id, asset_index, media_type, relative_path FROM media_files "
            f"WHERE item_id IN ({marks}) AND status='ready' AND relative_path IS NOT NULL "
            "ORDER BY item_id, asset_index",
            chunk,
        ):
            files.setdefault(str(row["item_id"]), []).append(dict(row))
    types = {
        str(row["remote_id"]): str(row["item_type"])
        for start in range(0, len(ids), 500)
        for row in await database.fetchall(
            "SELECT remote_id, item_type FROM items WHERE remote_id IN "
            f"({','.join('?' * len(ids[start:start + 500]))})",
            ids[start : start + 500],
        )
    }

    entries: list[tuple[str, Path | bytes]] = []
    listing: list[list[str]] = []
    for item_id in ids:
        work, assets = works.get(item_id), files.get(item_id)
        if work is None or not assets:
            continue
        author = str(work.get("author_name") or "")
        title = display_title(str(work.get("description") or ""), author)
        short = title if len(title) <= NAME_TITLE_CHARS else title[: NAME_TITLE_CHARS - 1] + "…"
        base = sanitize_segment(f"{author} - {short} [{item_id}]", max_length=110)
        if types.get(item_id) == "gallery":
            stored = f"{folder}/{base}/"
            for asset in assets:
                source = root / str(asset["relative_path"])
                entries.append((f"{folder}/{base}/{source.name}", source))
            entries.append((f"{folder}/{base}/{base}.nfo", build_nfo(work)))
        else:
            videos = [asset for asset in assets if asset["media_type"] == "video"] or assets
            first = videos[0]
            source = root / str(first["relative_path"])
            stored = f"{folder}/{base}{source.suffix}"
            entries.append((stored, source))
            for extra in videos[1:]:
                extra_source = root / str(extra["relative_path"])
                entries.append((f"{folder}/{base}_{extra_source.stem}{extra_source.suffix}", extra_source))
            entries.append((f"{folder}/{base}.nfo", build_nfo(work)))
            poster = find_poster(root, item_id, int(first["id"]))
            if poster is not None:
                entries.append((f"{folder}/{base}-poster{poster[1]}", poster[0]))
        listing.append(_listing_row(work, title, stored.removeprefix(f"{folder}/")))
    return entries, listing


def _listing_row(work: dict[str, Any], title: str, stored: str) -> list[str]:
    published = work.get("published_at")
    hashtags, tags = [], []
    # load_works puts Douyin hashtags first, then the owner's tags.
    metadata_tags = list(work.get("tags", ()))
    user_tags = set(work.get("user_tags", ()))
    for tag in metadata_tags:
        (tags if tag in user_tags else hashtags).append(tag)
    duration = work.get("duration_ms")
    return [
        title,
        str(work.get("author_name") or ""),
        datetime.fromtimestamp(int(published), SHANGHAI).strftime("%Y-%m-%d %H:%M") if published else "",
        str(round(int(duration) / 1000)) if duration else "",
        " ".join(f"#{tag}" for tag in hashtags),
        " ".join(tags),
        " / ".join(work.get("genres", ())),
        str(work.get("note") or ""),
        str(work.get("source_url") or ""),
        stored,
    ]


def _csv(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    writer.writerows(rows)
    # BOM so Excel opens the Chinese text correctly.
    return ("﻿" + buffer.getvalue()).encode("utf-8")


class _Sink:
    """Write-only, unseekable: zipfile then streams with data descriptors."""

    def __init__(self) -> None:
        self.parts: list[bytes] = []
        self.size = 0

    def write(self, data: bytes) -> int:
        self.parts.append(bytes(data))
        self.size += len(data)
        return len(data)

    def flush(self) -> None:
        pass

    def drain(self) -> bytes:
        data = b"".join(self.parts)
        self.parts.clear()
        self.size = 0
        return data


def _zip_stream(entries: list[tuple[str, Path | bytes]]) -> Iterator[bytes]:
    # A plain generator: Starlette runs it in a worker thread, off the event loop.
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name, source in entries:
            if isinstance(source, bytes):
                archive.writestr(_info(name, len(source), time.time()), source)
            else:
                try:
                    handle = source.open("rb")
                except OSError:
                    continue  # Gone since planning (self-check moved it aside); skip it.
                with handle:
                    stat = Path(source).stat()
                    info = _info(name, stat.st_size, stat.st_mtime)
                    with archive.open(info, "w") as target:
                        while block := handle.read(CHUNK_BYTES):
                            target.write(block)
                            if sink.size >= CHUNK_BYTES:
                                yield sink.drain()
            if sink.size:
                yield sink.drain()
    if sink.size:
        yield sink.drain()


def _info(name: str, size: int, mtime: float) -> zipfile.ZipInfo:
    stamp = time.localtime(max(mtime, 315_532_800))  # ZIP dates start in 1980.
    info = zipfile.ZipInfo(name, date_time=stamp[:6])
    info.compress_type = zipfile.ZIP_STORED
    info.file_size = size
    info.external_attr = 0o644 << 16
    return info

"""Describe every saved video to media servers with a Kodi-style .nfo beside it.

Jellyfin, Emby and Kodi read ``<video name>.nfo`` next to the video, and Infuse
does once its local-metadata option is on; Plex needs a third-party agent. The
canonical copy sits in the work's own ``objects/<id>/`` folder, so a library
pointed there sees every video; collection projections under ``library/`` get
their own copy. Everything comes from what the archive already stored: no
request is ever made to Douyin here.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import anyio

from .db import Database
from .item_covers import ItemCoverStore
from .storage import CollectionProjector

logger = logging.getLogger(__name__)

RUN_EVERY_SECONDS = 60
# Writing a sidecar is a few small reads and at most one small write; the NAS
# disk is shared, so the first pass over ~15k videos takes a little over an hour.
BATCH_SIZE = 200
# After a full pass, walk again this much later to pick up renamed creators,
# new tags, notes and albums.
REWALK_AFTER_SECONDS = 24 * 3600
CURSOR_NAME = "nfo-sidecars"
SHANGHAI = timezone(timedelta(hours=8))
TITLE_MAX_CHARS = 80

# XML 1.0 forbids most control characters; descriptions occasionally carry them.
_XML_ILLEGAL = re.compile("[^\t\n\r -퟿-�\U00010000-\U0010ffff]")
_HASHTAG = re.compile(r"#[^\s#@]+")
_MENTION = re.compile(r"@[^\s#@]+")
_SPACES = re.compile(r"\s+")
_IMAGE_TYPES = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG", ".png"), (b"RIFF", ".webp"))


def _clean(text: str) -> str:
    return _XML_ILLEGAL.sub("", text)


def display_title(description: str, author: str) -> str:
    """A readable title: the first line without its hashtags and mentions."""
    first_line = next((line for line in description.splitlines() if line.strip()), "")
    title = _SPACES.sub(" ", _MENTION.sub("", _HASHTAG.sub("", first_line))).strip(" ，,。.、")
    if not title:
        title = _SPACES.sub(" ", description).strip()
    if not title:
        return f"{author} 的作品"
    return title if len(title) <= TITLE_MAX_CHARS else title[: TITLE_MAX_CHARS - 1] + "…"


def build_nfo(work: dict[str, Any]) -> bytes:
    """Kodi movie NFO for one work; element names follow the Kodi/Jellyfin schema."""
    author = str(work.get("author_name") or "")
    description = str(work.get("description") or "")
    movie = ET.Element("movie")

    def add(tag: str, value: object, **attributes: str) -> None:
        if value is None or value == "":
            return
        element = ET.SubElement(movie, tag, attributes)
        element.text = _clean(str(value))

    add("title", display_title(description, author))
    plot = [description.strip()]
    if work.get("note"):
        plot.append(f"我的备注：{str(work['note']).strip()}")
    if work.get("source_url"):
        plot.append(f"原链接：{work['source_url']}")
    add("plot", "\n\n".join(part for part in plot if part))
    duration_ms = work.get("duration_ms")
    if duration_ms:
        add("runtime", max(1, round(int(duration_ms) / 60_000)))
    published_at = work.get("published_at")
    if published_at:
        published = datetime.fromtimestamp(int(published_at), SHANGHAI)
        add("premiered", published.strftime("%Y-%m-%d"))
        add("year", published.year)
    add("uniqueid", work.get("remote_id"), type="douyin", default="true")
    for genre in work.get("genres", ()):
        add("genre", genre)
    seen_tags: set[str] = set()
    for tag in work.get("tags", ()):
        if tag and tag not in seen_tags:
            seen_tags.add(tag)
            add("tag", tag)
    add("director", author)
    add("credits", author)
    add("studio", "抖音")
    first_seen = work.get("first_seen_at")
    if first_seen:
        add("dateadded", datetime.fromtimestamp(int(first_seen), SHANGHAI).strftime("%Y-%m-%d %H:%M:%S"))
    ET.indent(movie, space="  ")
    body = ET.tostring(movie, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body + "\n").encode("utf-8")


def _write_if_changed(path: Path, content: bytes) -> bool:
    try:
        if path.read_bytes() == content:
            return False
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.writing")
    temporary.write_bytes(content)
    os.replace(temporary, path)
    return True


def _image_extension(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            head = handle.read(12)
    except OSError:
        return None
    for magic, extension in _IMAGE_TYPES:
        if head.startswith(magic) and (extension != ".webp" or head[8:12] == b"WEBP"):
            return extension
    return None


class SidecarWriter:
    def __init__(
        self,
        database: Database,
        archive_root: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = database
        self.archive_root = archive_root.resolve()
        self.covers = ItemCoverStore(self.archive_root)
        self.posters = self.archive_root / "cache" / "posters"
        self.projector = CollectionProjector(self.archive_root)
        self.clock = clock

    async def run_batch(self) -> int:
        """Advance the walk over saved videos by one batch; returns files written."""
        now = int(self.clock())
        cursor = await self.db.fetchone(
            "SELECT position, started_at FROM job_cursors WHERE name=?", (CURSOR_NAME,)
        )
        position = int(cursor["position"]) if cursor else 0
        started_at = int(cursor["started_at"]) if cursor else now
        if position < 0:
            # Finished a pass: wait, then start over to pick up edits.
            if now - started_at < REWALK_AFTER_SECONDS:
                return 0
            position, started_at = 0, now
        rows = await self.db.fetchall(
            # Primary-key range walk: no index on media_files needed (see 022).
            "SELECT mf.id, mf.item_id, mf.relative_path FROM media_files mf "
            "JOIN items i ON i.remote_id=mf.item_id AND i.item_type='video' "
            "WHERE mf.id>? AND mf.status='ready' AND mf.media_type='video' "
            "AND mf.relative_path IS NOT NULL ORDER BY mf.id LIMIT ?",
            (position, BATCH_SIZE),
        )
        written = await self._write_rows([dict(row) for row in rows]) if rows else 0
        next_position = int(rows[-1]["id"]) if len(rows) == BATCH_SIZE else -1
        await self.db.execute(
            "INSERT INTO job_cursors (name, position, started_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET position=excluded.position, "
            "started_at=excluded.started_at, updated_at=excluded.updated_at",
            (CURSOR_NAME, next_position, started_at, now),
        )
        return written

    async def write_for_item(self, item_id: str) -> int:
        """Right after a download, so a new video never waits for the walk."""
        rows = await self.db.fetchall(
            "SELECT mf.id, mf.item_id, mf.relative_path FROM media_files mf "
            "JOIN items i ON i.remote_id=mf.item_id AND i.item_type='video' "
            "WHERE mf.item_id=? AND mf.status='ready' AND mf.media_type='video' "
            "AND mf.relative_path IS NOT NULL",
            (item_id,),
        )
        return await self._write_rows([dict(row) for row in rows]) if rows else 0

    async def _write_rows(self, rows: list[dict[str, Any]]) -> int:
        works = await self._works({str(row["item_id"]) for row in rows})
        jobs = [(row, works[str(row["item_id"])]) for row in rows if str(row["item_id"]) in works]
        # Disk work stays off the event loop: a stat on the busy NAS can stall.
        return await anyio.to_thread.run_sync(self._write_files, jobs)

    async def _works(self, item_ids: set[str]) -> dict[str, dict[str, Any]]:
        ids = sorted(item_ids)
        marks = ",".join("?" * len(ids))
        works = {
            str(row["remote_id"]): {**dict(row), "tags": [], "genres": [], "collections": []}
            for row in await self.db.fetchall(
                "SELECT remote_id, author_name, description, published_at, first_seen_at, "
                f"duration_ms, source_url, metadata_json FROM items WHERE remote_id IN ({marks})",
                ids,
            )
        }
        for work in works.values():
            try:
                metadata = json.loads(work.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                metadata = {}
            hashtags = metadata.get("hashtags") if isinstance(metadata, dict) else None
            if isinstance(hashtags, list):
                work["tags"].extend(str(tag) for tag in hashtags if str(tag).strip())
        for row in await self.db.fetchall(
            f"SELECT item_id, tag FROM item_tags WHERE item_id IN ({marks}) ORDER BY item_id, tag", ids
        ):
            works[str(row["item_id"])]["tags"].append(str(row["tag"]))
        for row in await self.db.fetchall(
            f"SELECT item_id, note FROM item_notes WHERE item_id IN ({marks})", ids
        ):
            works[str(row["item_id"])]["note"] = str(row["note"])
        for row in await self.db.fetchall(
            "SELECT ai.item_id, a.name FROM album_items ai JOIN albums a ON a.id=ai.album_id "
            f"WHERE ai.item_id IN ({marks}) ORDER BY a.position, a.name",
            ids,
        ):
            works[str(row["item_id"])]["genres"].append(str(row["name"]))
        for row in await self.db.fetchall(
            "SELECT ci.item_id, c.name FROM collection_items ci "
            "JOIN collections c ON c.remote_id=ci.collection_id "
            f"WHERE ci.item_id IN ({marks}) ORDER BY c.first_seen_at, c.remote_id",
            ids,
        ):
            works[str(row["item_id"])]["collections"].append(str(row["name"]))
            works[str(row["item_id"])]["genres"].append(str(row["name"]))
        return works

    def _write_files(self, jobs: list[tuple[dict[str, Any], dict[str, Any]]]) -> int:
        written = 0
        for row, work in jobs:
            video = self.archive_root / str(row["relative_path"])
            try:
                if not video.is_file():
                    continue
                content = build_nfo(work)
                written += _write_if_changed(video.with_suffix(".nfo"), content)
                written += self._place_poster(video, str(row["item_id"]), int(row["id"]))
                # Same title rule as the projector, so the names line up.
                title = str(work["description"] or work["author_name"] or work["remote_id"])
                for collection in work["collections"]:
                    projected = self.projector.destination(collection, title, str(work["remote_id"]), video)
                    if projected.is_file():
                        written += _write_if_changed(projected.with_suffix(".nfo"), content)
            except OSError as error:
                logger.warning("could not write media-server sidecar for %s: %s", row["item_id"], error)
        return written

    def _place_poster(self, video: Path, item_id: str, media_id: int) -> int:
        """Douyin's own cover if kept, else the grid poster; never fetched here."""
        for source in (self.covers.path_for(item_id), self.posters / f"{media_id}.jpg"):
            extension = _image_extension(source)
            if extension is None:
                continue
            target = video.with_name(f"{video.stem}-poster{extension}")
            if target.exists():
                return 0
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)
            return 1
        return 0

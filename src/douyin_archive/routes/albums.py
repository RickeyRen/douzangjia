from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api")

MAX_TAGS_PER_ITEM = 30
MAX_NOTE_LENGTH = 4000


class AlbumBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def strip(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("相册名不能为空")
        return cleaned


class ItemIds(BaseModel):
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=500)


class TagsBody(BaseModel):
    tags: list[str] = Field(max_length=MAX_TAGS_PER_ITEM)

    @field_validator("tags")
    @classmethod
    def clean(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for raw in value:
            tag = " ".join(str(raw).replace("#", "").split()).strip()[:40]
            if tag and tag not in seen:
                seen.append(tag)
        return seen


class NoteBody(BaseModel):
    note: str = Field(max_length=MAX_NOTE_LENGTH)


def _not_found(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"code": code, "message": message})


async def _album_payload(database, album_id: int) -> dict[str, Any] | None:
    row = await database.fetchone(
        "SELECT a.*, COUNT(ai.item_id) AS item_count, MAX(ai.added_at) AS last_added_at "
        "FROM albums a LEFT JOIN album_items ai ON ai.album_id=a.id WHERE a.id=? GROUP BY a.id",
        (album_id,),
    )
    if row is None:
        return None
    covers = await database.fetchall(
        "SELECT i.cover_url, (SELECT mf.id FROM media_files mf WHERE mf.item_id=i.remote_id "
        "AND mf.status='ready' ORDER BY mf.asset_index LIMIT 1) AS media_id "
        "FROM album_items ai JOIN items i ON i.remote_id=ai.item_id WHERE ai.album_id=? "
        "ORDER BY media_id IS NULL, ai.added_at DESC LIMIT 4",
        (album_id,),
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "itemCount": row["item_count"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "lastAddedAt": row["last_added_at"],
        "covers": [
            f"/api/media/{cover['media_id']}/poster" if cover["media_id"] else cover["cover_url"]
            for cover in covers
            if cover["media_id"] or cover["cover_url"]
        ],
    }


@router.get("/albums")
async def list_albums(request: Request) -> dict[str, Any]:
    rows = await request.app.state.database.fetchall("SELECT id FROM albums ORDER BY position, created_at")
    items = [await _album_payload(request.app.state.database, int(row["id"])) for row in rows]
    return {"items": [item for item in items if item is not None]}


@router.post("/albums", status_code=201)
async def create_album(body: AlbumBody, request: Request):
    database = request.app.state.database
    now = int(time.time())
    existing = await database.fetchone("SELECT id FROM albums WHERE name=?", (body.name,))
    if existing is not None:
        return JSONResponse(status_code=409, content={"code": "ALBUM_EXISTS", "message": "已经有同名相册"})
    row = await database.fetchone(
        "INSERT INTO albums (name, position, created_at, updated_at) "
        "VALUES (?, (SELECT COALESCE(MAX(position), 0) + 1 FROM albums), ?, ?) RETURNING id",
        (body.name, now, now),
    )
    return await _album_payload(database, int(row["id"]))


@router.patch("/albums/{album_id}")
async def rename_album(album_id: int, body: AlbumBody, request: Request):
    database = request.app.state.database
    clash = await database.fetchone("SELECT id FROM albums WHERE name=? AND id<>?", (body.name, album_id))
    if clash is not None:
        return JSONResponse(status_code=409, content={"code": "ALBUM_EXISTS", "message": "已经有同名相册"})
    cursor = await database.execute(
        "UPDATE albums SET name=?, updated_at=? WHERE id=?", (body.name, int(time.time()), album_id)
    )
    if cursor.rowcount == 0:
        return _not_found("ALBUM_NOT_FOUND", "相册不存在")
    return await _album_payload(database, album_id)


@router.delete("/albums/{album_id}")
async def delete_album(album_id: int, request: Request):
    database = request.app.state.database
    async with database.transaction(immediate=True):
        await database.execute("DELETE FROM album_items WHERE album_id=?", (album_id,))
        cursor = await database.execute("DELETE FROM albums WHERE id=?", (album_id,))
    if cursor.rowcount == 0:
        return _not_found("ALBUM_NOT_FOUND", "相册不存在")
    return {"deleted": True}


@router.put("/albums/{album_id}/items")
async def add_album_items(album_id: int, body: ItemIds, request: Request):
    database = request.app.state.database
    if await database.fetchone("SELECT 1 FROM albums WHERE id=?", (album_id,)) is None:
        return _not_found("ALBUM_NOT_FOUND", "相册不存在")
    now = int(time.time())
    added = 0
    async with database.transaction(immediate=True):
        for item_id in body.item_ids:
            cursor = await database.execute(
                "INSERT OR IGNORE INTO album_items (album_id, item_id, added_at) "
                "SELECT ?, remote_id, ? FROM items WHERE remote_id=?",
                (album_id, now, item_id),
            )
            added += cursor.rowcount
        await database.execute("UPDATE albums SET updated_at=? WHERE id=?", (now, album_id))
    return {"added": added, "album": await _album_payload(database, album_id)}


@router.delete("/albums/{album_id}/items")
async def remove_album_items(album_id: int, body: ItemIds, request: Request):
    database = request.app.state.database
    placeholders = ",".join("?" for _ in body.item_ids)
    cursor = await database.execute(
        f"DELETE FROM album_items WHERE album_id=? AND item_id IN ({placeholders})",
        (album_id, *body.item_ids),
    )
    return {"removed": cursor.rowcount, "album": await _album_payload(database, album_id)}


@router.get("/tags")
async def list_tags(request: Request) -> dict[str, Any]:
    rows = await request.app.state.database.fetchall(
        "SELECT tag, COUNT(*) AS item_count FROM item_tags GROUP BY tag ORDER BY item_count DESC, tag"
    )
    return {"items": [{"tag": row["tag"], "itemCount": row["item_count"]} for row in rows]}


@router.put("/items/{remote_id}/tags")
async def set_item_tags(remote_id: str, body: TagsBody, request: Request):
    database = request.app.state.database
    if await database.fetchone("SELECT 1 FROM items WHERE remote_id=?", (remote_id,)) is None:
        return _not_found("ITEM_NOT_FOUND", "归档作品不存在")
    now = int(time.time())
    async with database.transaction(immediate=True):
        await database.execute("DELETE FROM item_tags WHERE item_id=?", (remote_id,))
        for tag in body.tags:
            await database.execute(
                "INSERT INTO item_tags (item_id, tag, created_at) VALUES (?, ?, ?)", (remote_id, tag, now)
            )
    return {"tags": body.tags}


@router.put("/items/{remote_id}/note")
async def set_item_note(remote_id: str, body: NoteBody, request: Request):
    database = request.app.state.database
    if await database.fetchone("SELECT 1 FROM items WHERE remote_id=?", (remote_id,)) is None:
        return _not_found("ITEM_NOT_FOUND", "归档作品不存在")
    note = body.note.strip()
    if note:
        await database.execute(
            "INSERT INTO item_notes (item_id, note, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at",
            (remote_id, note, int(time.time())),
        )
    else:
        await database.execute("DELETE FROM item_notes WHERE item_id=?", (remote_id,))
    return {"note": note or None}

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed_media(root: Path, relative_path: str, *, media_id: int = 1) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT OR IGNORE INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('734', '作者', '作品', 'video', 100, 100)"
    )
    await database.execute(
        "INSERT INTO media_files "
        "(id, item_id, asset_index, media_type, relative_path, byte_size, mime_type, "
        "status, created_at, updated_at) "
        "VALUES (?, '734', 0, 'video', ?, 10, 'video/mp4', 'ready', 100, 100)",
        (media_id, relative_path),
    )
    await database.close()


def media_client(root: Path, master_key: str, relative_path: str) -> TestClient:
    asyncio.run(seed_media(root, relative_path))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"password": "a secure local passphrase"})
    return client


def test_media_range_returns_partial_bytes(tmp_path: Path, master_key: str) -> None:
    media = tmp_path / "objects" / "734" / "000.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"0123456789")
    client = media_client(tmp_path, master_key, "objects/734/000.mp4")
    try:
        response = client.get("/api/media/1", headers={"Range": "bytes=2-5"})
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["accept-ranges"] == "bytes"


def test_invalid_or_multiple_range_returns_416(tmp_path: Path, master_key: str) -> None:
    media = tmp_path / "objects" / "734" / "000.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"0123456789")
    client = media_client(tmp_path, master_key, "objects/734/000.mp4")
    try:
        response = client.get("/api/media/1", headers={"Range": "bytes=5-2,7-8"})
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */10"


def test_database_path_cannot_escape_object_store(tmp_path: Path, master_key: str) -> None:
    outside = tmp_path.parent / "outside-secret.mp4"
    outside.write_bytes(b"must-not-leak")
    client = media_client(tmp_path, master_key, "../outside-secret.mp4")
    try:
        response = client.get("/api/media/1")
    finally:
        client.__exit__(None, None, None)
        outside.unlink()
    assert response.status_code == 404
    assert b"must-not-leak" not in response.content


def test_media_requires_authentication(tmp_path: Path, master_key: str) -> None:
    media = tmp_path / "objects" / "734" / "000.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"0123456789")
    client = media_client(tmp_path, master_key, "objects/734/000.mp4")
    try:
        client.cookies.clear()
        response = client.get("/api/media/1")
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 401

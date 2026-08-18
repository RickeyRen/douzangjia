import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed_feed(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO collections "
        "(remote_id, name, name_history_json, first_seen_at, last_seen_at) "
        "VALUES ('1001', '想去的地方', '[\"想去的地方\"]', 100, 300)"
    )
    for remote_id, stamp in (("736", 300), ("735", 200), ("734", 100)):
        await database.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, '作者', ?, 'video', ?, ?)",
            (remote_id, f"作品 {remote_id}", stamp, stamp),
        )
        await database.execute(
            "INSERT INTO collection_items "
            "(collection_id, item_id, first_seen_at, last_seen_at) "
            "VALUES ('1001', ?, ?, ?)",
            (remote_id, stamp, stamp),
        )
    await database.close()


def build_client(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed_feed(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"password": "a secure local passphrase"})
    return client


def test_feed_cursor_has_no_duplicates(tmp_path: Path, master_key: str) -> None:
    client = build_client(tmp_path, master_key)
    try:
        first = client.get("/api/feed?limit=2")
        second = client.get(f"/api/feed?limit=2&cursor={first.json()['nextCursor']}")
    finally:
        client.__exit__(None, None, None)

    first_ids = {item["awemeId"] for item in first.json()["items"]}
    second_ids = {item["awemeId"] for item in second.json()["items"]}
    assert first.status_code == 200
    assert first_ids == {"736", "735"}
    assert second_ids == {"734"}
    assert first_ids.isdisjoint(second_ids)


def test_collection_filter_and_detail_include_local_metadata(
    tmp_path: Path, master_key: str
) -> None:
    client = build_client(tmp_path, master_key)
    try:
        collections = client.get("/api/collections")
        feed = client.get("/api/feed?collectionId=1001&search=735")
        detail = client.get("/api/items/735")
    finally:
        client.__exit__(None, None, None)

    assert collections.json()["items"][0]["name"] == "想去的地方"
    assert collections.json()["items"][0]["itemCount"] == 3
    assert [item["awemeId"] for item in feed.json()["items"]] == ["735"]
    assert detail.json()["collections"] == [
        {"id": "1001", "name": "想去的地方"}
    ]


def test_archive_api_requires_local_admin_session(tmp_path: Path, master_key: str) -> None:
    client = build_client(tmp_path, master_key)
    try:
        client.cookies.clear()
        rejected = client.get("/api/feed")
        login = client.post(
            "/api/session", json={"password": "a secure local passphrase"}
        )
        accepted = client.get("/api/feed")
    finally:
        client.__exit__(None, None, None)

    assert rejected.status_code == 401
    assert rejected.json()["code"] == "AUTH_REQUIRED"
    assert login.status_code == 200
    assert accepted.status_code == 200

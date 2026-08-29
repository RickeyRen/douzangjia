import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.routes.feed import _local_state


async def seed_feed(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO collections "
        "(remote_id, name, name_history_json, first_seen_at, last_seen_at) "
        "VALUES ('1001', '想去的地方', '[\"想去的地方\"]', 100, 300)"
    )
    for remote_id, stamp, author in (
        ("736", 300, "作者"),
        ("735", 200, "作者"),
        ("734", 100, "另一作者"),
    ):
        await database.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, 'video', ?, ?)",
            (remote_id, author, f"作品 {remote_id}", stamp, stamp),
        )
        await database.execute(
            "INSERT INTO collection_items "
            "(collection_id, item_id, first_seen_at, last_seen_at) "
            "VALUES ('1001', ?, ?, ?)",
            (remote_id, stamp, stamp),
        )
    payload = '{"assets":[{"asset_index":0,"media_type":"video","expected_size":10}]}'
    gallery_payload = '{"assets":[{"asset_index":0,"media_type":"image","expected_size":10},{"asset_index":1,"media_type":"image","expected_size":20},{"asset_index":2,"media_type":"image","expected_size":30}]}'
    for remote_id, status in (("736", "completed"), ("735", "running"), ("734", "failed")):
        await database.execute(
            "INSERT INTO download_jobs "
            "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
            "created_at, updated_at) VALUES ('download', ?, ?, ?, 1, 0, 1, 1)",
            (remote_id, gallery_payload if remote_id == "734" else payload, status),
        )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, relative_path, byte_size, mime_type, status, "
        "created_at, updated_at, downloaded_bytes, total_bytes, speed_bps) "
        "VALUES ('736', 0, 'video', 'objects/736/000.mp4', 10, 'video/mp4', "
        "'ready', 1, 1, 10, 10, 0)"
    )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, mime_type, status, created_at, updated_at, "
        "downloaded_bytes, total_bytes, speed_bps) "
        "VALUES ('735', 0, 'video', 'video/mp4', 'running', 1, 1, 4, 10, 2)"
    )
    await database.close()


def build_client(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed_feed(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
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


def test_author_filter_and_local_download_state(
    tmp_path: Path, master_key: str
) -> None:
    client = build_client(tmp_path, master_key)
    try:
        response = client.get("/api/feed?author=作者")
    finally:
        client.__exit__(None, None, None)

    items = response.json()["items"]
    assert response.status_code == 200
    assert [item["awemeId"] for item in items] == ["736", "735"]
    assert items[0]["local"] == {
        "state": "downloaded",
        "readyAssets": 1,
        "totalAssets": 1,
        "downloadedBytes": 10,
        "totalBytes": 10,
    }
    assert items[1]["local"] == {
        "state": "downloading",
        "readyAssets": 0,
        "totalAssets": 1,
        "downloadedBytes": 4,
        "totalBytes": 10,
    }

    client = build_client(tmp_path / "failed", master_key)
    try:
        failed = client.get("/api/feed?author=另一作者").json()["items"][0]
    finally:
        client.__exit__(None, None, None)
    assert failed["local"] == {
        "state": "failed",
        "readyAssets": 0,
        "totalAssets": 3,
        "downloadedBytes": 0,
        "totalBytes": 60,
    }


def test_local_state_mapping_does_not_mark_partial_archives_as_downloaded() -> None:
    assert _local_state("pending", ready_assets=0, total_assets=2) == "waiting"
    assert _local_state("retry", ready_assets=1, total_assets=2) == "retry"
    assert _local_state("failed", ready_assets=1, total_assets=2) == "failed"


def test_archive_api_requires_local_admin_session(tmp_path: Path, master_key: str) -> None:
    client = build_client(tmp_path, master_key)
    try:
        client.cookies.clear()
        rejected = client.get("/api/feed")
        login = client.post(
            "/api/session", json={"username": "test-admin", "password": "a secure local passphrase"}
        )
        accepted = client.get("/api/feed")
    finally:
        client.__exit__(None, None, None)

    assert rejected.status_code == 401
    assert rejected.json()["code"] == "AUTH_REQUIRED"
    assert login.status_code == 200
    assert accepted.status_code == 200

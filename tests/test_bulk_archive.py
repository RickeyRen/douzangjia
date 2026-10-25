import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


def payload_for(remote_id: str) -> str:
    return json.dumps(
        {
            "remote_id": remote_id,
            "assets": [
                {
                    "remote_id": remote_id,
                    "asset_index": 0,
                    "media_type": "video",
                    "url": f"https://media.test/{remote_id}.mp4",
                    "expected_size": 10,
                }
            ],
        }
    )


async def seed(root: Path) -> None:
    database = await Database(root / "data" / "archive.sqlite3").open()
    await database.execute(
        "INSERT INTO library_sources (id, kind, remote_id, name, sync_status, first_seen_at, last_seen_at) "
        "VALUES ('account:likes', 'like', 'self', '喜欢', 'complete', 1, 1)"
    )
    for index in range(1, 5):
        remote_id = f"90{index}"
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, 'a', ?, 'video', ?, ?)",
            (remote_id, f"作品 {index}", index, index),
        )
        if index != 4:  # 904 has no synced payload anywhere
            await database.execute(
                "INSERT INTO source_items (source_id, item_id, remote_order, metadata_json, first_seen_at, last_seen_at) "
                "VALUES ('account:likes', ?, ?, ?, 1, 1)",
                (remote_id, remote_id, payload_for(remote_id)),
            )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, mime_type, status, "
        "created_at, updated_at) VALUES ('901', 0, 'video', 'objects/901/000.mp4', 4096, 'video/mp4', 'ready', 1, 1)"
    )
    await database.close()


def client_for(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
    client.headers["X-CSRF-Token"] = client.cookies["archive_csrf"]
    return client


def test_selection_batches_skip_items_without_payload(tmp_path: Path, master_key: str) -> None:
    """Catches one unsyncable item aborting a whole hand-picked download."""
    client = client_for(tmp_path, master_key)
    try:
        response = client.post("/api/archive/selection", json={"itemIds": ["902", "903", "904", "902"]})
        batches = client.get("/api/archive/batches").json()["items"]
        nothing = client.post("/api/archive/selection", json={"itemIds": ["nope"]})
        jobs = client.get("/api/jobs").json()["items"]
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 202
    assert response.json()["skipped"] == 1
    assert response.json()["batch"]["kind"] == "selection"
    assert batches[0]["kind"] == "selection" and batches[0]["totalItems"] == 2
    assert nothing.status_code == 404
    assert sorted(job["remoteId"] for job in jobs) == ["902", "903"]


def test_missing_summary_and_archive_everything(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        summary = client.get("/api/archive/missing").json()
        queued = client.post("/api/archive/missing")
        again = client.post("/api/archive/missing")
        jobs = client.get("/api/jobs").json()["items"]
    finally:
        client.__exit__(None, None, None)

    assert summary == {"missing": 3, "estimatedBytes": 3 * 4096}
    assert queued.status_code == 202 and queued.json()["skipped"] == 1
    assert queued.json()["batch"]["kind"] == "missing"
    # The active "missing" batch is reused instead of duplicated.
    assert again.json()["batch"]["id"] == queued.json()["batch"]["id"]
    assert sorted(job["remoteId"] for job in jobs) == ["902", "903"]


def test_bulk_star_round_trip(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        starred = client.post("/api/items/bulk-star", json={"itemIds": ["901", "903", "ghost"]})
        listed = client.get("/api/feed?starred=true").json()["items"]
        unstarred = client.post("/api/items/bulk-star", json={"itemIds": ["901"], "starred": False})
    finally:
        client.__exit__(None, None, None)

    assert starred.json() == {"starred": ["901", "903"]}
    assert sorted(item["awemeId"] for item in listed) == ["901", "903"]
    assert unstarred.json() == {"starred": []}

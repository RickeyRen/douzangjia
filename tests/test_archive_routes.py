import asyncio
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed_archive_targets(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    now = int(time.time())
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, first_seen_at, last_seen_at) "
        "VALUES ('creator-1', '旅行作者', ?, ?)",
        (now, now),
    )
    await database.execute(
        "INSERT INTO library_sources "
        "(id, kind, remote_id, name, first_seen_at, last_seen_at) "
        "VALUES ('favorite_collection:1001', 'favorite_collection', '1001', "
        "'想去的地方', ?, ?)",
        (now, now),
    )
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, "
        "last_seen_at, creator_id) VALUES "
        "('734', '旅行作者', '海边', 'video', ?, ?, 'creator-1')",
        (now, now),
    )
    await database.execute(
        "INSERT INTO source_items "
        "(source_id, item_id, remote_order, first_seen_at, last_seen_at) "
        "VALUES ('favorite_collection:1001', '734', '1', ?, ?)",
        (now, now),
    )
    await database.execute(
        "INSERT INTO download_jobs "
        "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "created_at, updated_at) VALUES ('download', '734', ?, 'pending', 0, ?, ?, ?)",
        (json.dumps({"remote_id": "734", "assets": []}), now, now, now),
    )
    await database.close()


def build_client(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed_archive_targets(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"password": "a secure local passphrase"})
    return client


def mutation_headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("archive_csrf") or ""}


def test_item_source_and_creator_archive_routes_are_idempotent(
    tmp_path: Path, master_key: str
) -> None:
    client = build_client(tmp_path, master_key)
    headers = mutation_headers(client)
    try:
        item = client.post("/api/archive/items/734", headers=headers)
        repeated = client.post("/api/archive/items/734", headers=headers)
        source = client.post(
            "/api/archive/sources/favorite_collection:1001", headers=headers
        )
        creator = client.post("/api/archive/creators/creator-1", headers=headers)
        batches = client.get("/api/archive/batches")
    finally:
        client.__exit__(None, None, None)

    assert item.status_code == 202
    assert repeated.json()["id"] == item.json()["id"]
    assert source.status_code == 202
    assert creator.status_code == 202
    assert batches.status_code == 200
    assert {entry["kind"] for entry in batches.json()["items"]} == {
        "item",
        "source",
        "creator",
    }


def test_archive_route_rejects_unknown_target(tmp_path: Path, master_key: str) -> None:
    client = build_client(tmp_path, master_key)
    try:
        response = client.post(
            "/api/archive/items/missing", headers=mutation_headers(client)
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 404
    assert response.json()["code"] == "ARCHIVE_TARGET_NOT_FOUND"


def test_creator_subscription_and_batch_controls_are_persistent(
    tmp_path: Path, master_key: str
) -> None:
    client = build_client(tmp_path, master_key)
    headers = mutation_headers(client)
    try:
        batch = client.post("/api/archive/items/734", headers=headers).json()
        paused = client.post(
            f"/api/archive/batches/{batch['id']}/pause", headers=headers
        )
        resumed = client.post(
            f"/api/archive/batches/{batch['id']}/resume", headers=headers
        )
        subscription = client.put(
            "/api/creator-subscriptions/creator-1",
            headers=headers,
            json={
                "enabled": True,
                "scanIntervalSeconds": 3600,
                "archiveNewItems": True,
            },
        )
    finally:
        client.__exit__(None, None, None)

    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"
    assert subscription.status_code == 200
    assert subscription.json()["enabled"] is True
    assert subscription.json()["scanIntervalSeconds"] == 3600

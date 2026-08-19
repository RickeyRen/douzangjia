import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed_library(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO creators "
        "(remote_id, nickname, first_seen_at, last_seen_at) "
        "VALUES ('creator-1', '旅行作者', 1, 1)"
    )
    await database.execute(
        "INSERT INTO library_sources "
        "(id, kind, remote_id, name, declared_count, sync_status, "
        "first_seen_at, last_seen_at) "
        "VALUES ('likes', 'like', 'self', '喜欢', 4, 'complete', 1, 1)"
    )
    for remote_id, remote_order, stamp in (
        ("item-3", "0003", 300),
        ("item-2", "0002", 200),
        ("item-1", "0001", 100),
    ):
        await database.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, first_seen_at, "
            "last_seen_at, creator_id) VALUES (?, '旅行作者', ?, 'video', ?, ?, 'creator-1')",
            (remote_id, f"作品 {remote_id}", stamp, stamp),
        )
        await database.execute(
            "INSERT INTO source_items "
            "(source_id, item_id, remote_order, first_seen_at, last_seen_at) "
            "VALUES ('likes', ?, ?, ?, ?)",
            (remote_id, remote_order, stamp, stamp),
        )
    await database.close()


def build_client(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed_library(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"password": "a secure local passphrase"})
    return client


def test_library_sources_expose_remote_sync_gap(
    tmp_path: Path, master_key: str
) -> None:
    """Catches an API that labels a source complete despite a count mismatch."""
    client = build_client(tmp_path, master_key)
    try:
        response = client.get("/api/library/sources")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    source = response.json()["items"][0]
    assert source["id"] == "likes"
    assert source["declaredCount"] == 4
    assert source["discoveredCount"] == 3
    assert source["archivedCount"] == 0
    assert source["missingCount"] == 1
    assert source["complete"] is False


def test_library_feed_uses_a_stable_source_cursor(
    tmp_path: Path, master_key: str
) -> None:
    """Catches a cursor that repeats or skips source items across pages."""
    client = build_client(tmp_path, master_key)
    try:
        first = client.get("/api/library/feed?sourceId=likes&limit=2")
        second = client.get(
            "/api/library/feed",
            params={
                "sourceId": "likes",
                "limit": 2,
                "cursor": first.json()["nextCursor"],
            },
        )
    finally:
        client.__exit__(None, None, None)

    assert first.status_code == 200
    assert [item["awemeId"] for item in first.json()["items"]] == [
        "item-3",
        "item-2",
    ]
    assert first.json()["nextCursor"] is not None
    assert second.status_code == 200
    assert [item["awemeId"] for item in second.json()["items"]] == ["item-1"]
    assert second.json()["nextCursor"] is None


def test_library_feed_can_filter_by_stable_creator_id(
    tmp_path: Path, master_key: str
) -> None:
    """Catches creator pages that rely on mutable display names."""
    client = build_client(tmp_path, master_key)
    try:
        response = client.get("/api/library/feed?creatorId=creator-1&limit=2")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert [item["awemeId"] for item in response.json()["items"]] == [
        "item-3",
        "item-2",
    ]
    assert response.json()["items"][0]["creatorId"] == "creator-1"
    assert response.json()["nextCursor"] is not None

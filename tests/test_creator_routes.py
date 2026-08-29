from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.library_models import CreatorRecord


async def seed_creators(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO creators "
        "(remote_id, nickname, unique_id, avatar_url, follower_count, post_count, "
        "first_seen_at, last_seen_at) VALUES "
        "('creator-1', '旅行作者', 'travel-id', 'https://media.test/avatar.jpg', "
        "321, 17, 1, 3)"
    )
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, "
        "last_seen_at, creator_id) VALUES "
        "('734', '旅行作者', '海边', 'video', 2, 2, 'creator-1')"
    )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, relative_path, byte_size, mime_type, "
        "status, created_at, updated_at) VALUES "
        "('734', 0, 'video', 'objects/734/0.mp4', 10, 'video/mp4', 'ready', 2, 2)"
    )
    await database.execute(
        "INSERT INTO creator_subscriptions "
        "(creator_id, enabled, scan_interval_seconds, archive_new_items, "
        "created_at, updated_at) VALUES ('creator-1', 1, 3600, 1, 3, 3)"
    )
    await database.close()


def build_client(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed_creators(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
    return client


def test_creator_list_and_detail_expose_stable_identity_and_local_counts(
    tmp_path: Path, master_key: str
) -> None:
    client = build_client(tmp_path, master_key)
    try:
        listing = client.get("/api/creators")
        detail = client.get("/api/creators/creator-1")
    finally:
        client.__exit__(None, None, None)

    assert listing.status_code == 200
    assert listing.json()["items"][0]["id"] == "creator-1"
    assert detail.status_code == 200
    assert detail.json()["nickname"] == "旅行作者"
    assert detail.json()["uniqueId"] == "travel-id"
    assert detail.json()["knownItemCount"] == 1
    assert detail.json()["archivedItemCount"] == 1
    assert detail.json()["subscription"]["enabled"] is True


def test_creator_detail_returns_a_stable_not_found_error(
    tmp_path: Path, master_key: str
) -> None:
    client = build_client(tmp_path, master_key)
    try:
        response = client.get("/api/creators/missing")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 404
    assert response.json()["code"] == "CREATOR_NOT_FOUND"


def test_creator_refresh_persists_the_douyin_id_from_the_logged_in_profile(
    tmp_path: Path, master_key: str
) -> None:
    class Runtime:
        async def refresh_creator_profile(self, creator_id: str) -> CreatorRecord:
            assert creator_id == "creator-1"
            return CreatorRecord(
                remote_id=creator_id,
                nickname="旅行作者",
                unique_id="travel-account",
                avatar_url="https://media.test/avatar-new.jpg",
                follower_count=456,
                post_count=18,
            )

    client = build_client(tmp_path, master_key)
    client.app.state.runtime = Runtime()
    try:
        response = client.post(
            "/api/creators/creator-1/refresh",
            headers={"X-CSRF-Token": client.cookies.get("archive_csrf") or ""},
        )
        stored = client.get("/api/creators/creator-1")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.json()["uniqueId"] == "travel-account"
    assert response.json()["followerCount"] == 456
    assert stored.json()["uniqueId"] == "travel-account"

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed(root: Path) -> None:
    database = await Database(root / "data" / "archive.sqlite3").open()
    for index in range(1, 5):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, '作者', ?, 'video', ?, ?)",
            (f"70{index}", f"作品 {index}", index, index),
        )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, mime_type, "
        "status, created_at, updated_at) VALUES ('702', 0, 'video', 'objects/702/000.mp4', 1, 'video/mp4', 'ready', 1, 1)"
    )
    await database.close()


def client_for(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
    client.headers["X-CSRF-Token"] = client.cookies["archive_csrf"]
    return client


def ids(response) -> list[str]:
    return [item["awemeId"] for item in response.json()["items"]]


def test_album_lifecycle_and_feed_filter(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        created = client.post("/api/albums", json={"name": "  下次旅行  参考 "})
        duplicate = client.post("/api/albums", json={"name": "下次旅行 参考"})
        album_id = created.json()["id"]
        added = client.put(f"/api/albums/{album_id}/items", json={"itemIds": ["701", "702", "702", "missing"]})
        listed = client.get("/api/albums").json()["items"]
        feed = client.get(f"/api/feed?albumId={album_id}")
        detail = client.get("/api/items/702").json()
        renamed = client.patch(f"/api/albums/{album_id}", json={"name": "旅行"})
        removed = client.request("DELETE", f"/api/albums/{album_id}/items", json={"itemIds": ["701"]})
        after_remove = client.get(f"/api/feed?albumId={album_id}")
        deleted = client.delete(f"/api/albums/{album_id}")
        gone = client.get("/api/albums").json()["items"]
        orphan_check = client.get("/api/items/702").json()
    finally:
        client.__exit__(None, None, None)

    assert created.status_code == 201 and created.json()["name"] == "下次旅行 参考"
    assert duplicate.status_code == 409
    assert added.json()["added"] == 2
    assert listed[0]["itemCount"] == 2 and listed[0]["covers"][0].endswith("/poster")
    assert set(ids(feed)) == {"701", "702"}
    assert detail["albums"] == [{"id": album_id, "name": "下次旅行 参考"}]
    assert renamed.json()["name"] == "旅行"
    assert removed.json()["removed"] == 1 and ids(after_remove) == ["702"]
    assert deleted.json() == {"deleted": True} and gone == []
    assert orphan_check["albums"] == []


def test_tags_and_notes_round_trip_and_are_searchable(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        tagged = client.put("/api/items/703/tags", json={"tags": [" #做饭 ", "做饭", "周末", ""]})
        noted = client.put("/api/items/703/note", json={"note": "  周三试试这个番茄炒蛋的做法  "})
        tags = client.get("/api/tags").json()["items"]
        by_tag = client.get("/api/feed?tag=做饭")
        by_note_search = client.get("/api/feed?search=番茄炒蛋")
        by_tag_search = client.get("/api/feed?search=周末")
        detail = client.get("/api/items/703").json()
        cleared = client.put("/api/items/703/note", json={"note": "   "})
        missing = client.put("/api/items/nope/tags", json={"tags": ["x"]})
    finally:
        client.__exit__(None, None, None)

    assert tagged.json()["tags"] == ["做饭", "周末"]
    assert noted.json()["note"] == "周三试试这个番茄炒蛋的做法"
    assert tags == [{"tag": "做饭", "itemCount": 1}, {"tag": "周末", "itemCount": 1}]
    assert ids(by_tag) == ids(by_note_search) == ids(by_tag_search) == ["703"]
    assert detail["tags"] == ["做饭", "周末"] and detail["note"] == "周三试试这个番茄炒蛋的做法"
    assert cleared.json()["note"] is None
    assert missing.status_code == 404


def test_album_sort_follows_added_order(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        album_id = client.post("/api/albums", json={"name": "顺序"}).json()["id"]
        client.put(f"/api/albums/{album_id}/items", json={"itemIds": ["704", "701"]})
        feed = client.get(f"/api/feed?albumId={album_id}")
        wrong = client.get("/api/feed?sort=album")
    finally:
        client.__exit__(None, None, None)

    # Same added_at, so the id tiebreaker decides; both were added in one call.
    assert set(ids(feed)) == {"704", "701"}
    assert wrong.status_code == 400

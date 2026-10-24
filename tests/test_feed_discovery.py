import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, unique_id, first_seen_at, last_seen_at) "
        "VALUES ('c1', '旅行家小鹿', 'deer2026', 1, 1)"
    )
    # (remote_id, archived at, published at, type, creator)
    for remote_id, archived, published, kind, creator in (
        ("7000000000000000005", 500, 100, "video", None),
        ("7000000000000000004", 400, 900, "gallery", "c1"),
        ("7000000000000000003", 300, None, "video", "c1"),
        ("7000000000000000002", 200, 700, "video", None),
        ("7000000000000000001", 100, 50, "gallery", None),
    ):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, published_at, "
            "first_seen_at, last_seen_at, creator_id) VALUES (?, '作者', ?, ?, ?, ?, ?, ?)",
            (remote_id, f"作品 {remote_id[-1]}", kind, published, archived, archived, creator),
        )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, "
        "mime_type, status, created_at, updated_at) VALUES "
        "('7000000000000000004', 0, 'image', 'objects/4/000.jpg', 10, 'image/jpeg', "
        "'ready', 1, 1)"
    )
    await database.execute(
        "INSERT INTO library_sources (id, kind, remote_id, name, sync_status, "
        "first_seen_at, last_seen_at) VALUES ('account:likes', 'like', 'self', '喜欢', "
        "'complete', 1, 1)"
    )
    for remote_id, order in (("7000000000000000001", "0003"), ("7000000000000000003", "0002")):
        await database.execute(
            "INSERT INTO source_items (source_id, item_id, remote_order, first_seen_at, "
            "last_seen_at) VALUES ('account:likes', ?, ?, 1, 1)",
            (remote_id, order),
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
    return [item["awemeId"][-1] for item in response.json()["items"]]


def test_published_sort_falls_back_to_archive_time(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        first = client.get("/api/feed?sort=published&limit=3")
        rest = client.get(f"/api/feed?sort=published&limit=3&cursor={first.json()['nextCursor']}")
    finally:
        client.__exit__(None, None, None)

    # item 3 has no publish time, so its archive time (300) places it.
    assert ids(first) + ids(rest) == ["4", "2", "3", "5", "1"]


def test_random_order_is_stable_per_seed_and_pages_without_duplicates(
    tmp_path: Path, master_key: str
) -> None:
    """Catches shuffle pages repeating or dropping items while scrolling."""
    client = client_for(tmp_path, master_key)
    try:
        def walk(seed: int) -> list[str]:
            seen, cursor = [], None
            while True:
                query = f"/api/feed?sort=random&seed={seed}&limit=2"
                page = client.get(query + (f"&cursor={cursor}" if cursor else ""))
                seen += ids(page)
                cursor = page.json()["nextCursor"]
                if cursor is None:
                    return seen

        first_walk, again, other_seed = walk(7), walk(7), walk(11)
    finally:
        client.__exit__(None, None, None)

    assert sorted(first_walk) == ["1", "2", "3", "4", "5"]
    assert first_walk == again
    assert other_seed != first_walk


def test_filters_compose_with_source_order(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        source = client.get("/api/feed?sourceId=account:likes")
        source_galleries = client.get("/api/feed?sourceId=account:likes&type=gallery")
        downloaded = client.get("/api/feed?downloaded=true")
        creator = client.get("/api/feed?creatorId=c1")
        by_nickname = client.get("/api/feed?search=小鹿")
        by_douyin_id = client.get("/api/feed?search=deer2026")
    finally:
        client.__exit__(None, None, None)

    assert ids(source) == ["1", "3"]
    assert ids(source_galleries) == ["1"]
    assert ids(downloaded) == ["4"]
    assert ids(creator) == ["4", "3"]
    assert ids(by_nickname) == ids(by_douyin_id) == ["4", "3"]


def test_star_round_trip_feeds_starred_view(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        first = client.put("/api/items/7000000000000000002/star")
        repeat = client.put("/api/items/7000000000000000002/star")
        client.put("/api/items/7000000000000000005/star")
        starred = client.get("/api/feed?starred=true")
        detail = client.get("/api/items/7000000000000000002")
        removed = client.delete("/api/items/7000000000000000002/star")
        after = client.get("/api/feed?starred=true")
        missing = client.put("/api/items/does-not-exist/star")
    finally:
        client.__exit__(None, None, None)

    assert first.json()["starred"] is True
    assert repeat.json()["starredAt"] == first.json()["starredAt"]
    assert set(ids(starred)) == {"2", "5"}
    assert detail.json()["starred"] is True
    assert removed.json() == {"starred": False, "starredAt": None}
    assert ids(after) == ["5"]
    assert missing.status_code == 404


def test_star_requires_csrf(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        del client.headers["X-CSRF-Token"]
        response = client.put("/api/items/7000000000000000002/star")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 403


def test_thumbnail_prefers_local_poster(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        items = {item["awemeId"][-1]: item for item in client.get("/api/feed").json()["items"]}
    finally:
        client.__exit__(None, None, None)

    media_id = items["4"]["media"][0]["id"]
    assert items["4"]["thumbnailUrl"] == f"/api/media/{media_id}/poster"
    assert items["4"]["media"][0]["posterUrl"] == f"/api/media/{media_id}/poster"
    assert items["5"]["thumbnailUrl"] is None


def test_invalid_sort_and_cursor_are_rejected(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        unknown = client.get("/api/feed?sort=views")
        source_without_id = client.get("/api/feed?sort=source")
        text_cursor_for_time_sort = client.get(
            "/api/feed?cursor=WyIwMDAxIiwiNyJd"  # ["0001","7"]
        )
    finally:
        client.__exit__(None, None, None)

    assert unknown.status_code == source_without_id.status_code == 400
    assert text_cursor_for_time_sort.json()["code"] == "INVALID_CURSOR"

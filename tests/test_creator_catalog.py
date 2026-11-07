from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.creator_catalog import PAUSE_SECONDS, CreatorCatalogScanner
from douyin_archive.db import Database
from douyin_archive.item_covers import ItemCoverPreserver
from douyin_archive.library_models import CreatorRecord
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.library_scope import library_item_sql


def record(item_id: str, creator_id: str = "c1") -> dict:
    return {
        "aweme_id": item_id,
        "desc": f"作品 {item_id}",
        "aweme_type": 0,
        "create_time": 100,
        "author": {"nickname": "乐酷", "sec_uid": creator_id},
        "video": {"cover": {"url_list": [f"https://x/{item_id}.jpg"]}, "play_addr": {"url_list": ["https://x/v.mp4"]}},
        "statistics": {"digg_count": 5},
    }


async def open_db(root: Path, *, post_count: int = 2) -> Database:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await LibraryRepository(database).upsert_creator(CreatorRecord("c1", "乐酷", "leku", post_count=post_count))
    return database


def scanner_for(database: Database, pages: list[list[dict]]) -> CreatorCatalogScanner:
    async def scan(creator_id: str):
        for page in pages:
            yield page

    return CreatorCatalogScanner(database, scan)


def test_scan_records_only_the_creators_works_outside_the_library(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        scanner = scanner_for(database, [[record("1"), record("2", "someone-else")], [record("3")]])
        seen = await scanner.scan_creator("c1")
        creator = await database.fetchone(
            "SELECT catalog_scanned_at, catalog_item_count FROM creators WHERE remote_id='c1'"
        )
        catalog = await database.fetchall("SELECT item_id FROM creator_catalog_items ORDER BY item_id")
        items = await database.fetchone("SELECT COUNT(*) AS n FROM items")
        await database.close()
        return seen, creator, catalog, items

    seen, creator, catalog, items = asyncio.run(scenario())

    assert seen == 2
    assert [row["item_id"] for row in catalog] == ["1", "3"]
    assert creator["catalog_item_count"] == 2 and creator["catalog_scanned_at"]
    # The library feeds scan items; a catalog must not grow them.
    assert items["n"] == 0


def test_removed_creators_works_move_into_items_outside_the_library_scope(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        scanner = scanner_for(database, [[record("1"), record("3")]])
        await scanner.scan_creator("c1")
        untouched = await scanner.promote_removed_creators()
        await database.execute("UPDATE creators SET archive_status='reset' WHERE remote_id='c1'")
        promoted = await scanner.promote_removed_creators()
        again = await scanner.promote_removed_creators()
        rows = await database.fetchall("SELECT remote_id, creator_id, cover_url FROM items ORDER BY remote_id")
        scoped = await database.fetchone(f"SELECT COUNT(*) AS n FROM items i WHERE {library_item_sql('i')}")
        await database.close()
        return untouched, promoted, again, rows, scoped

    untouched, promoted, again, rows, scoped = asyncio.run(scenario())

    assert (untouched, promoted, again) == (0, 2, 0)
    assert [row["remote_id"] for row in rows] == ["1", "3"]
    assert rows[0]["cover_url"] == "https://x/1.jpg"
    assert scoped["n"] == 0


def test_repeated_empty_pages_pause_the_scan_and_leave_creators_unmarked(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        scanner = scanner_for(database, [])
        for _ in range(3):
            await scanner.scan_creator("c1")
        row = await database.fetchone("SELECT catalog_scanned_at FROM creators WHERE remote_id='c1'")
        await database.close()
        return scanner.paused_until, row

    paused_until, row = asyncio.run(scenario())

    assert paused_until > PAUSE_SECONDS
    assert row["catalog_scanned_at"] is None


def test_a_creator_without_public_works_is_not_a_warning_sign(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path, post_count=0)
        scanner = scanner_for(database, [])
        await scanner.scan_creator("c1")
        row = await database.fetchone("SELECT catalog_scanned_at FROM creators WHERE remote_id='c1'")
        await database.close()
        return scanner.paused_until, row

    paused_until, row = asyncio.run(scenario())

    assert paused_until == 0
    assert row["catalog_scanned_at"] is not None


def test_covers_are_saved_once_and_served_instead_of_douyins(tmp_path: Path, master_key: str) -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "gone" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"jpeg")

    async def scenario():
        database = await open_db(tmp_path)
        await database.execute(
            "INSERT INTO creator_catalog_items (item_id, creator_id, author_name, item_type, cover_url, "
            "first_seen_at, last_seen_at) VALUES ('1', 'c1', 'a', 'video', 'https://x/1.jpg', 1, 1), "
            "('2', 'c1', 'a', 'video', 'https://x/gone.jpg', 1, 1)"
        )
        # A favourite without a saved video also keeps its cover.
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at, "
            "creator_id, cover_url) VALUES ('3', 'a', 'd', 'video', 1, 1, 'c1', 'https://x/3.jpg')"
        )
        await database.execute("INSERT INTO item_stars (item_id, starred_at) VALUES ('3', 1)")
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            preserver = ItemCoverPreserver(database, tmp_path, client=client)
            saved = await preserver.run_batch()
            await preserver.run_batch()
        states = await database.fetchall("SELECT item_id, cover_state FROM creator_catalog_items ORDER BY item_id")
        await database.close()
        return saved, states

    saved, states = asyncio.run(scenario())

    assert saved == 2
    assert [(row["item_id"], row["cover_state"]) for row in states] == [("1", 1), ("2", 2), ("3", 1)]
    assert len(calls) == 3

    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
        item = client.get("/api/items/3").json()
        assert item["coverUrl"] == "/api/items/3/cover"
        assert item["thumbnailUrl"] == "/api/items/3/cover"
        assert client.get("/api/items/3/cover").content == b"jpeg"
        assert client.get("/api/items/2/cover").status_code == 404


def test_a_gallery_that_had_no_cover_url_is_retried_when_one_arrives(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        await database.execute(
            "INSERT INTO creator_catalog_items (item_id, creator_id, author_name, item_type, cover_state, "
            "first_seen_at, last_seen_at) VALUES ('3', 'c1', 'a', 'gallery', 2, 1, 1)"
        )
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at, "
            "creator_id, cover_url) VALUES ('3', 'a', 'd', 'gallery', 1, 1, 'c1', 'https://x/3.jpg')"
        )
        await database.execute("INSERT INTO item_stars (item_id, starred_at) VALUES ('3', 1)")
        await ItemCoverPreserver(database, tmp_path).enlist_library_items()
        row = await database.fetchone("SELECT cover_url, cover_state FROM creator_catalog_items WHERE item_id='3'")
        await database.close()
        return row

    row = asyncio.run(scenario())

    assert (row["cover_url"], row["cover_state"]) == ("https://x/3.jpg", 0)


def test_migration_rescans_only_creators_whose_galleries_lack_covers(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        await LibraryRepository(database).upsert_creator(CreatorRecord("c2", "二号", "two", post_count=1))
        await database.execute("UPDATE creators SET catalog_scanned_at=100")
        await database.execute(
            "INSERT INTO creator_catalog_items (item_id, creator_id, author_name, item_type, cover_url, "
            "first_seen_at, last_seen_at) VALUES ('1', 'c1', 'a', 'gallery', NULL, 1, 1), "
            "('2', 'c2', 'a', 'video', 'https://x/2.jpg', 1, 1)"
        )
        script = (Path(__file__).parents[1] / "src/douyin_archive/migrations/018_gallery_covers.sql").read_text()
        await database.connection.executescript(script)
        rows = await database.fetchall("SELECT remote_id, catalog_scanned_at FROM creators ORDER BY remote_id")
        await database.close()
        return rows

    rows = asyncio.run(scenario())

    assert [(row["remote_id"], row["catalog_scanned_at"]) for row in rows] == [("c1", None), ("c2", 100)]

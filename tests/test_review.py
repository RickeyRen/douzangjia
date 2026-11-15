import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive import review as review_module
from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.review import SHANGHAI, CollectionReview

AUG = 1_786_000_000  # 2026-08 in Shanghai time
SEP = 1_788_700_000  # 2026-09
PUB_2024 = 1_710_000_000
PUB_2025 = 1_740_000_000


def seed(connection) -> None:
    def source(source_id: str, kind: str) -> None:
        connection.execute(
            "INSERT INTO library_sources (id, kind, remote_id, name, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, ?, 1, 1)",
            (source_id, kind, source_id, source_id),
        )

    source("likes", "like")
    source("fav", "favorite_video")
    source("history", "watch_history")
    connection.execute(
        "INSERT INTO creators (remote_id, nickname, avatar_url, first_seen_at, last_seen_at) "
        "VALUES ('c1', '露营的阿光', 'https://example.test/a.jpg', 1, 1)"
    )
    works = [
        # item, creator, published, [(source, first seen)], saved, remote status
        ("1", "c1", PUB_2024, [("likes", AUG), ("fav", SEP)], True, "deleted"),
        ("2", "c1", PUB_2025, [("fav", SEP)], False, "private"),
        ("3", "c1", PUB_2025, [("likes", SEP)], True, "available"),
        ("4", None, PUB_2025, [("likes", AUG)], False, None),
        # Only seen in watch history: not something the owner collected.
        ("5", "c1", PUB_2025, [("history", AUG)], True, "deleted"),
    ]
    for item, creator, published, sources, saved, remote in works:
        connection.execute(
            "INSERT INTO items (remote_id, item_type, author_name, description, published_at, creator_id, "
            "first_seen_at, last_seen_at) VALUES (?, 'video', '旧昵称', 'd', ?, ?, 1, 1)",
            (item, published, creator),
        )
        for source_id, seen in sources:
            connection.execute(
                "INSERT INTO source_items (source_id, item_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
                (source_id, item, seen, seen),
            )
        connection.execute(
            "INSERT INTO media_files (item_id, asset_index, media_type, status, created_at, updated_at) "
            "VALUES (?, 0, 'video', ?, 1, 1)",
            (item, "ready" if saved else "pending"),
        )
        if remote:
            connection.execute(
                "INSERT INTO remote_checks (item_id, status, updated_at) VALUES (?, ?, 1)", (item, remote)
            )


def test_review_counts_only_collected_works(tmp_path: Path) -> None:
    """Catches watch history or followed accounts inflating the owner's review."""

    async def scenario() -> dict:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await database.close()
        with sqlite3.connect(tmp_path / "archive.sqlite3") as connection:
            seed(connection)
        database = await Database(tmp_path / "archive.sqlite3").open()
        body = await CollectionReview(database).build()
        await database.close()
        return body

    body = asyncio.run(scenario())
    assert body["totals"] == {"items": 4, "saved": 2, "since": AUG}
    assert body["firstMonth"] == "2026-08"
    # Work 1 counts in August, when it was first collected, not again in September.
    assert body["months"] == [
        {"month": "2026-08", "added": 2, "saved": 1},
        {"month": "2026-09", "added": 2, "saved": 1},
    ]
    assert body["publishedYears"] == [{"year": "2024", "count": 1}, {"year": "2025", "count": 3}]
    assert body["topCreators"] == [
        {"id": "c1", "name": "露营的阿光", "count": 3, "vanished": 2, "avatarUrl": "https://example.test/a.jpg"}
    ]
    assert body["vanished"] == {"total": 2, "saved": 1, "lost": 1}


def test_snapshot_is_rebuilt_once_a_day_and_served_by_the_api(tmp_path: Path, master_key: str) -> None:
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        with sqlite3.connect(tmp_path / "data" / "archive.sqlite3") as connection:
            seed(connection)
        first = client.get("/api/review").json()
        assert first == {"state": "building"}

        async def wait_for_snapshot() -> None:
            for _ in range(50):
                if client.app.state.review_task.done():
                    return
                await asyncio.sleep(0.02)

        client.portal.call(wait_for_snapshot)
        body = client.get("/api/review").json()
        assert body["totals"]["items"] == 4 and body["builtAt"] > 0
        client.cookies.clear()
        assert client.get("/api/review").status_code == 401

    async def ticks() -> None:
        database = await Database(tmp_path / "data" / "archive.sqlite3").open()
        built = body["builtAt"]
        clock = [built + 60.0]
        review = CollectionReview(database, clock=lambda: clock[0])
        assert await review.run_tick() is False
        # Old enough, but in the middle of the day: wait for the quiet hours.
        noon = built + review_module.REBUILD_AFTER_SECONDS
        while datetime.fromtimestamp(noon, SHANGHAI).hour != 12:
            noon += 3600
        clock[0] = noon
        assert await review.run_tick() is False
        clock[0] = noon + 16 * 3600  # 04:00 Shanghai
        assert await review.run_tick() is True
        await database.close()

    asyncio.run(ticks())

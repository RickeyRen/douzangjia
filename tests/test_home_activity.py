import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.routes.home import home_activity

SHANGHAI = ZoneInfo("Asia/Shanghai")
# 2026-11-08 14:00 in Shanghai.
NOW = int(datetime(2026, 11, 8, 14, 0, tzinfo=SHANGHAI).timestamp())


def at(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=SHANGHAI).timestamp())


async def seed(database: Database) -> None:
    for index in range(1, 6):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, "
            "last_seen_at) VALUES (?, 'x', '', 'video', 1, 1)",
            (f"i{index}",),
        )
    files = [
        # Just before and just after Shanghai midnight land on different days.
        ("i1", 0, at(2026, 11, 7, 23, 59)),
        ("i2", 0, at(2026, 11, 8, 0, 1)),
        # A gallery's second image finishing later does not count the item again.
        ("i3", 0, at(2026, 11, 8, 9)),
        ("i3", 1, at(2026, 11, 8, 10)),
        # Older than the 70-day window.
        ("i4", 0, at(2026, 8, 1, 12)),
    ]
    for item, index, completed in files:
        await database.execute(
            "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, "
            "mime_type, status, created_at, updated_at, completed_at) "
            "VALUES (?, ?, 'video', ?, 10, 'video/mp4', 'ready', 1, 1, ?)",
            (item, index, f"objects/{item}/{index}.mp4", completed),
        )
    # A failed file never counts.
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, "
        "mime_type, status, created_at, updated_at, completed_at) "
        "VALUES ('i5', 0, 'video', 'objects/i5/0.mp4', 10, 'video/mp4', 'failed', 1, 1, ?)",
        (at(2026, 11, 8, 11),),
    )
    samples = [
        (NOW - 25 * 3600, 999.0),  # outside the 24-hour window
        (NOW - 3600, 100.0),
        (NOW - 3600 + 60, 300.0),
        (NOW - 600, 50.0),
    ]
    for sampled_at, bps in samples:
        await database.execute(
            "INSERT INTO metric_samples (resolution, sampled_at, download_speed_bps) "
            "VALUES ('raw', ?, ?)",
            (sampled_at, bps),
        )
    await database.execute(
        "INSERT INTO metric_samples (resolution, sampled_at, download_speed_bps) "
        "VALUES ('minute', ?, 777)",
        (NOW - 1800,),
    )
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, first_seen_at, last_seen_at, archive_status, "
        "archive_status_since) VALUES ('c1', 'a', 1, 1, 'banned', ?), "
        "('c2', 'b', 1, 1, 'reset', ?)",
        (NOW - 3600, NOW - 30 * 86400),
    )


def test_activity_counts_saves_per_shanghai_day_and_buckets_speed(tmp_path: Path) -> None:
    async def scenario() -> dict:
        database = await Database(tmp_path / "archive.sqlite3").open()
        try:
            await seed(database)
            return await home_activity(database, {"items_week": 3, "creators_week": 1}, now=NOW)
        finally:
            await database.close()

    activity = asyncio.run(scenario())
    daily = activity["dailySaved"]
    assert len(daily) == 70
    assert daily[-1] == {"date": "2026-11-08", "count": 2}
    assert daily[-2] == {"date": "2026-11-07", "count": 1}
    assert daily[0]["date"] == "2026-08-31"
    assert sum(day["count"] for day in daily) == 3

    bucket = activity["speedBucketSeconds"]
    assert bucket == 600
    speed = activity["speed"]
    assert [point["bps"] for point in speed] == [200.0, 50.0]
    assert all(point["at"] % bucket == 0 for point in speed)

    assert activity["week"] == {"items": 3, "saved": 3, "creators": 1, "vanished": 1}


def test_home_returns_activity_alongside_stats(tmp_path: Path, master_key: str) -> None:
    async def prepare() -> None:
        database = await Database(tmp_path / "data" / "archive.sqlite3").open()
        await database.close()

    asyncio.run(prepare())
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        body = client.get("/api/home").json()

    assert len(body["activity"]["dailySaved"]) == 70
    assert body["activity"]["speed"] == []
    assert body["activity"]["week"] == {"items": 0, "saved": 0, "creators": 0, "vanished": 0}

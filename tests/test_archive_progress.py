import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient
from test_bulk_archive import payload_for

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def seed(root: Path) -> None:
    """Two favorites, one of them saved, plus feed leftovers from a creator met only there."""
    database = await Database(root / "data" / "archive.sqlite3").open()
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, unique_id, first_seen_at, last_seen_at) "
        "VALUES ('fav', '收藏的博主', 'fav', 1, 1), ('feed', '推荐里的博主', 'feed', 1, 1)"
    )
    await database.execute(
        "INSERT INTO library_sources (id, kind, remote_id, name, sync_status, first_seen_at, last_seen_at) "
        "VALUES ('account:favorite_videos', 'favorite_video', 'self', '抖音全部收藏', 'complete', 1, 1), "
        "('account:recommendations', 'recommend', 'self', '推荐', 'complete', 1, 1), "
        "('account:watch_history', 'watch_history', 'self', '观看历史', 'complete', 1, 1)"
    )
    for remote_id, creator, source in (
        ("801", "fav", "account:favorite_videos"),
        ("802", "fav", "account:favorite_videos"),
        ("803", "feed", "account:recommendations"),
        ("804", "feed", "account:watch_history"),
        ("805", "feed", None),
    ):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, "
            "last_seen_at, creator_id) VALUES (?, 'a', ?, 'video', 1, 1, ?)",
            (remote_id, f"作品 {remote_id}", creator),
        )
        if source:
            await database.execute(
                "INSERT INTO source_items (source_id, item_id, remote_order, metadata_json, "
                "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, 1, 1)",
                (source, remote_id, remote_id, payload_for(remote_id)),
            )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, "
        "mime_type, status, created_at, updated_at) VALUES "
        "('801', 0, 'video', 'objects/801/000.mp4', 1000, 'video/mp4', 'ready', 1, 1)"
    )
    await database.close()


def client_for(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
    client.headers["X-CSRF-Token"] = client.cookies["archive_csrf"]
    return client


def run_sql(root: Path, sql: str, parameters: tuple = ()) -> None:
    async def apply() -> None:
        database = await Database(root / "data" / "archive.sqlite3").open()
        await database.execute(sql, parameters)
        await database.close()

    asyncio.run(apply())


def test_feed_leftovers_stay_out_of_counts_and_bulk_download(tmp_path: Path, master_key: str) -> None:
    """Catches recommend/history leftovers inflating the library and the "save everything" scope."""
    client = client_for(tmp_path, master_key)
    try:
        home = client.get("/api/home").json()
        feed = client.get("/api/feed").json()["items"]
        recommend = client.get("/api/feed?sourceId=account:recommendations").json()["items"]
        creators = client.get("/api/creators").json()["items"]
        missing = client.get("/api/archive/missing").json()
        queued = client.post("/api/archive/missing").json()
    finally:
        client.__exit__(None, None, None)

    assert home["stats"]["items"] == 2
    assert home["stats"]["creators"] == 1
    assert sorted(item["awemeId"] for item in feed) == ["801", "802"]
    # The recommend source itself is still browsable.
    assert [item["awemeId"] for item in recommend] == ["803"]
    assert [creator["id"] for creator in creators] == ["fav"]
    assert missing == {"missing": 1, "estimatedBytes": 1000}
    assert queued["batch"]["totalItems"] == 1


def test_starred_feed_item_joins_the_library(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        client.put("/api/items/803/star")
        home = client.get("/api/home").json()
    finally:
        client.__exit__(None, None, None)

    assert home["stats"]["items"] == 3
    assert home["stats"]["creators"] == 2


def test_progress_reports_active_batch_and_failures(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        idle = client.get("/api/archive/progress").json()
        batch = client.post("/api/archive/missing").json()["batch"]
        active = client.get("/api/archive/progress").json()
        batches = client.get("/api/archive/batches").json()["items"]
    finally:
        client.__exit__(None, None, None)

    assert idle == {"active": None, "failures": [], "failedTotal": 0}
    progress = active["active"]
    assert progress["status"] == "running"
    assert progress["batches"][0]["id"] == batch["id"]
    assert progress["batches"][0]["label"] == "全部未存作品"
    assert progress["totalItems"] == 1
    assert progress["completedItems"] == 0
    assert progress["waitingItems"] == 1
    assert progress["estimatedTotalBytes"] == 1000
    assert batches[0]["label"] == "全部未存作品"


def test_retry_failed_requeues_jobs_and_reopens_batch(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        batch = client.post("/api/archive/missing").json()["batch"]
        run_sql(
            tmp_path,
            "UPDATE download_jobs SET status='failed', attempts=5, "
            "last_error_code='DOWNLOAD_FAILED', updated_at=? WHERE remote_id='802'",
            (int(time.time()),),
        )
        failed = client.get("/api/archive/progress").json()
        finished = client.get(f"/api/archive/batches/{batch['id']}").json()
        retried = client.post("/api/archive/retry-failed").json()
        after = client.get("/api/archive/progress").json()
        jobs = client.get("/api/jobs").json()["items"]
    finally:
        client.__exit__(None, None, None)

    # Nothing is left to download once the only item failed, so the batch ends.
    assert failed["active"] is None
    assert failed["failedTotal"] == 1
    assert failed["failures"][0]["remoteId"] == "802"
    assert failed["failures"][0]["errorCode"] == "DOWNLOAD_FAILED"
    assert finished["status"] == "failed"
    assert retried == {"retried": 1}
    assert after["failedTotal"] == 0
    assert after["active"]["batches"][0]["id"] == batch["id"]
    job = next(job for job in jobs if job["remoteId"] == "802")
    assert job["status"] == "pending" and job["attempts"] == 0

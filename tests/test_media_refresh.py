import asyncio
import json
import time
from pathlib import Path

import httpx

from douyin_archive.db import Database
from douyin_archive.media_refresh import MediaUrlRefresher
from douyin_archive.repositories import JobRepository
from douyin_archive.worker import Worker

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "douyin" / "collection_items.json").read_text()
)


async def queue(database: Database, remote_id: str, *, attempts: int, code: str) -> None:
    now = int(time.time())
    await database.execute(
        "INSERT INTO download_jobs (kind, remote_id, payload_json, status, attempts, "
        "next_attempt_at, last_error_code, created_at, updated_at) "
        "VALUES ('download', ?, ?, 'retry', ?, ?, ?, ?, ?)",
        (
            remote_id,
            json.dumps({"remote_id": remote_id, "assets": [{"url": "https://stale.test/x"}]}),
            attempts,
            now + 3600,
            code,
            now,
            now,
        ),
    )


def test_expired_links_are_resigned_and_requeued(tmp_path: Path) -> None:
    """Catches bulk downloads stalling on play URLs that expired after the sync."""

    async def scenario() -> tuple[list[dict], list[list[str]]]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await queue(database, "734", attempts=1, code="MEDIA_URL_EXPIRED")
        await queue(database, "735", attempts=1, code="MEDIA_HTTP_ERROR")
        await queue(database, "999", attempts=1, code="MEDIA_URL_EXPIRED")
        await queue(database, "998", attempts=9, code="MEDIA_URL_EXPIRED")
        await queue(database, "997", attempts=1, code="DOWNLOAD_FAILED")
        calls: list[list[str]] = []

        async def fetch(ids: list[str]) -> list[dict]:
            calls.append(ids)
            return FIXTURE["aweme_list"]

        refreshed = await MediaUrlRefresher(database, fetch).run_batch()
        rows = await database.fetchall(
            "SELECT remote_id, status, last_error_code, payload_json FROM download_jobs "
            "ORDER BY remote_id"
        )
        await database.close()
        assert refreshed == 2
        return [dict(row) for row in rows], calls

    rows, calls = asyncio.run(scenario())
    by_id = {row["remote_id"]: row for row in rows}
    assert sorted(calls[0]) == ["734", "735", "998", "999"]
    assert by_id["734"]["status"] == "pending" and by_id["734"]["last_error_code"] is None
    assert json.loads(by_id["734"]["payload_json"])["assets"][0]["url"].startswith(
        "https://media.test/video.mp4"
    )
    assert by_id["735"]["status"] == "pending"
    # Missing from the answer is not proof of deletion: it backs off and stays queued.
    for remote_id in ("999", "998"):
        assert (by_id[remote_id]["status"], by_id[remote_id]["last_error_code"]) == (
            "retry",
            "MEDIA_URL_UNAVAILABLE",
        )
    assert by_id["997"]["last_error_code"] == "DOWNLOAD_FAILED"


def test_forbidden_media_is_marked_for_refresh(tmp_path: Path) -> None:
    async def scenario() -> tuple[str, str]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        jobs = JobRepository(database)
        await jobs.enqueue_unique("download", "734", {"remote_id": "734", "assets": []})

        async def forbidden(job) -> None:
            request = httpx.Request("GET", "https://stale.test/x")
            raise httpx.HTTPStatusError(
                "forbidden", request=request, response=httpx.Response(403, request=request)
            )

        await Worker(jobs, forbidden, worker_id="w").run_once()
        job = await jobs.get_by_key("download", "734")
        await database.close()
        return job.status, job.last_error_code

    assert asyncio.run(scenario()) == ("retry", "MEDIA_URL_EXPIRED")


def test_a_link_douyin_never_hands_out_stops_retrying_so_the_batch_can_finish(tmp_path: Path) -> None:
    """Catches the progress bar sitting at 99% for weeks behind a few unfetchable items."""
    from douyin_archive.archive_repository import ArchiveBatchRepository

    async def scenario() -> tuple[dict, dict, str]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        now = int(time.time())
        await database.execute(
            "INSERT INTO archive_batches (id, kind, target_id, status, discovered_count, created_at, "
            "updated_at) VALUES (7, 'missing', 'all', 'running', 1, ?, ?)",
            (now, now),
        )
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES ('999', 'a', 'gone', 'video', 1, 1)"
        )
        await queue(database, "998", attempts=1, code="MEDIA_URL_EXPIRED")
        await queue(database, "999", attempts=240, code="MEDIA_URL_EXPIRED")
        await database.execute("UPDATE download_jobs SET batch_id=7 WHERE remote_id='999'")
        job = await database.fetchone("SELECT id FROM download_jobs WHERE remote_id='999'")
        await database.execute(
            "INSERT INTO archive_batch_items (batch_id, item_id, job_id, created_at) VALUES (7, '999', ?, ?)",
            (job["id"], now),
        )

        async def fetch(ids: list[str]) -> list[dict]:
            return []

        await MediaUrlRefresher(database, fetch).run_batch()
        rows = {
            row["remote_id"]: dict(row)
            for row in await database.fetchall("SELECT remote_id, status, last_error_code FROM download_jobs")
        }
        batch = await ArchiveBatchRepository(database).get_batch(7)
        await database.close()
        return rows["998"], rows["999"], batch.status

    young, old, batch_status = asyncio.run(scenario())
    assert young["status"] == "retry"
    assert (old["status"], old["last_error_code"]) == ("failed", "MEDIA_URL_UNAVAILABLE")
    # The only item failed for good, so the batch no longer counts as running.
    assert batch_status == "failed"


def test_resigned_links_jump_ahead_of_stale_first_tries(tmp_path: Path) -> None:
    """Catches re-signed jobs expiring again behind thousands of stale queued ones."""

    async def scenario() -> str:
        database = await Database(tmp_path / "archive.sqlite3").open()
        # A stale first try that has been due for an hour.
        await database.execute(
            "INSERT INTO download_jobs (kind, remote_id, payload_json, status, attempts, "
            "next_attempt_at, created_at, updated_at) VALUES ('download', '111', ?, 'pending', 0, ?, 1, 1)",
            (json.dumps({"remote_id": "111", "assets": []}), int(time.time()) - 3600),
        )
        await queue(database, "734", attempts=1, code="MEDIA_URL_EXPIRED")

        async def fetch(ids: list[str]) -> list[dict]:
            return FIXTURE["aweme_list"]

        await MediaUrlRefresher(database, fetch).run_batch()
        job = await JobRepository(database).claim_next(worker_id="w1")
        await database.close()
        assert job is not None
        return job.remote_id

    assert asyncio.run(scenario()) == "734"

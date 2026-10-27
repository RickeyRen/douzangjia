import asyncio
import json
import time
from pathlib import Path

import httpx

from douyin_archive.db import Database
from douyin_archive.media_refresh import GIVE_UP_AFTER_ATTEMPTS, MediaUrlRefresher
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
        await queue(database, "998", attempts=GIVE_UP_AFTER_ATTEMPTS, code="MEDIA_URL_EXPIRED")
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
    # Not returned yet: waits for the regular backoff instead of being re-asked every run.
    assert (by_id["999"]["status"], by_id["999"]["last_error_code"]) == ("retry", "MEDIA_URL_UNAVAILABLE")
    assert (by_id["998"]["status"], by_id["998"]["last_error_code"]) == ("failed", "MEDIA_GONE")
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

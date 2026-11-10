import asyncio
import json
from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.repositories import JobRepository

FRESH = {"remote_id": "x", "assets": [{"url": "https://fresh.test/x.mp4", "asset_index": 0}]}


async def _scenario(root: Path) -> dict[str, tuple]:
    database = await Database(root / "archive.sqlite3").open()
    try:
        rows = [
            ("1", "retry", "MEDIA_URL_EXPIRED", None),
            ("2", "retry", "MEDIA_URL_UNAVAILABLE", None),
            ("3", "pending", None, None),
            ("4", "retry", "STORAGE_FULL", None),
            ("5", "running", None, None),
            ("6", "completed", None, None),
            ("7", "pending", None, 5),
        ]
        for remote_id, status, code, paused in rows:
            await database.execute(
                "INSERT INTO download_jobs (kind, remote_id, payload_json, status, attempts, "
                "next_attempt_at, last_error_code, paused_at, created_at, updated_at) "
                "VALUES ('download', ?, '{\"assets\":[{\"url\":\"https://stale.test\"}]}', ?, 1, 9999999999, ?, ?, 1, 1)",
                (remote_id, status, code, paused),
            )
        jobs = JobRepository(database)
        changed = {rid: await jobs.refresh_links(rid, {**FRESH, "remote_id": rid}) for rid, *_ in rows}
        assert await jobs.refresh_links("1", {"remote_id": "1", "assets": []}) is False
        result = {}
        for row in await database.fetchall(
            "SELECT remote_id, status, next_attempt_at, last_error_code, payload_json FROM download_jobs"
        ):
            fresh = "fresh.test" in json.loads(row["payload_json"])["assets"][0]["url"]
            result[row["remote_id"]] = (changed[row["remote_id"]], row["status"], row["next_attempt_at"], fresh)
        return result
    finally:
        await database.close()


def test_list_pages_hand_fresh_links_to_waiting_downloads(tmp_path: Path) -> None:
    """Catches bulk downloads waiting hours on the detail API for links a list page already gave."""
    result = asyncio.run(_scenario(tmp_path))
    for rid in ("1", "2", "3"):
        assert result[rid] == (True, "pending", 0, True)
    # Other failures, in-flight, finished and paused jobs keep their state.
    assert result["4"][:2] == (False, "retry")
    assert result["5"][:2] == (False, "running")
    assert result["6"][:2] == (False, "completed")
    assert result["7"] == (False, "pending", 9999999999, False)

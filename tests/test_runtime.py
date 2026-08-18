from collections.abc import AsyncIterator
from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.repositories import ArchiveRepository, JobRepository
from douyin_archive.runtime import RuntimeSyncCoordinator


class FakeAuth:
    async def load_cookies(self) -> list[dict[str, object]]:
        return [{"name": "sessionid", "value": "encrypted-before-use"}]


class FakeSource:
    closed = False

    async def fetch_collections(self) -> dict:
        return {"collections": [{"id": "1001", "name": "想去的地方"}]}

    async def iter_raw_pages(self, remote_id: str) -> AsyncIterator[dict]:
        assert remote_id == "1001"
        yield {
            "items": [
                {
                    "aweme_id": "734",
                    "desc": "海边日落",
                    "author": {"nickname": "旅行家"},
                    "video": {"play_addr": {"url_list": ["https://media.test/734"]}},
                }
            ],
            "has_more": False,
        }

    async def close(self) -> None:
        self.closed = True


async def test_trigger_sync_returns_run_id_and_finishes_in_background(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    source = FakeSource()
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        source_factory=lambda _: source,
    )

    run_id = await coordinator.trigger_sync(full_scan=True)
    queued = await database.fetchone("SELECT status FROM sync_runs WHERE id=?", (run_id,))
    assert queued is not None
    assert queued["status"] in {"queued", "running", "completed"}

    await coordinator.wait_for_idle()
    finished = await database.fetchone("SELECT status FROM sync_runs WHERE id=?", (run_id,))
    assert finished is not None
    assert finished["status"] == "completed"
    assert await JobRepository(database).count() == 1
    assert source.closed is True
    await coordinator.close()
    await database.close()

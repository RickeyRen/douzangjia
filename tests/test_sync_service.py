from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.models import MediaAsset, RemoteItem
from douyin_archive.provider.base import RemoteCollection, RemotePage
from douyin_archive.repositories import ArchiveRepository, JobRepository
from douyin_archive.sync_service import SyncService


def item(remote_id: str) -> RemoteItem:
    return RemoteItem(
        remote_id=remote_id,
        author_name="作者",
        description=f"作品 {remote_id}",
        item_type="video",
        assets=(MediaAsset(remote_id, 0, "video", f"https://media.test/{remote_id}"),),
    )


class FakeProvider:
    async def list_collections(self) -> list[RemoteCollection]:
        return [
            RemoteCollection("1001", "想去的地方", 2),
            RemoteCollection("1002", "好看的美女", 1),
        ]

    async def iter_collection_pages(
        self, remote_id: str, *, full_scan: bool
    ) -> AsyncIterator[RemotePage]:
        assert full_scan is True
        if remote_id == "1001":
            yield RemotePage((item("734"),), "next", True)
            yield RemotePage((item("735"),), None, False)
        else:
            yield RemotePage((item("734"),), None, False)


@pytest.fixture
async def sync_components(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    archive = ArchiveRepository(database)
    jobs = JobRepository(database)
    yield database, archive, jobs
    await database.close()


async def test_full_sync_persists_pages_and_deduplicates_downloads(
    sync_components,
) -> None:
    database, archive, jobs = sync_components
    result = await SyncService(FakeProvider(), archive, jobs).run(full_scan=True)

    assert result.status == "completed"
    assert result.discovered == 3
    assert result.enqueued == 2
    assert await archive.count_collection_items("1001") == 2
    assert await archive.count_collection_items("1002") == 1
    assert await jobs.count() == 2
    run = await database.fetchone("SELECT * FROM sync_runs WHERE id=?", (result.run_id,))
    assert run is not None
    assert run["status"] == "completed"


async def test_sync_failure_records_stable_error_code(sync_components) -> None:
    class FailingProvider(FakeProvider):
        async def list_collections(self) -> list[RemoteCollection]:
            from douyin_archive.provider.base import SessionExpired

            raise SessionExpired("expired")

    database, archive, jobs = sync_components
    result = await SyncService(FailingProvider(), archive, jobs).run(full_scan=False)
    assert result.status == "failed"
    row = await database.fetchone("SELECT error_code FROM sync_runs WHERE id=?", (result.run_id,))
    assert row is not None
    assert row["error_code"] == "DOUYIN_SESSION_EXPIRED"

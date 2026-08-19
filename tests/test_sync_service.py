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
        creator_id="creator-1",
        creator_unique_id="author-account",
        creator_avatar_url="https://media.test/avatar.jpg",
        creator_follower_count=25,
        creator_post_count=2,
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
    sources = await database.fetchall(
        "SELECT id, declared_count, sync_status FROM library_sources ORDER BY id"
    )
    assert [(row["id"], row["declared_count"], row["sync_status"]) for row in sources] == [
        ("favorite_collection:1001", 2, "complete"),
        ("favorite_collection:1002", 1, "complete"),
    ]
    creator = await database.fetchone(
        "SELECT * FROM creators WHERE remote_id='creator-1'"
    )
    assert creator is not None
    assert creator["unique_id"] == "author-account"
    assert creator["post_count"] == 2


async def test_incremental_sync_repairs_a_collection_with_a_remote_count_gap(
    sync_components,
) -> None:
    """Catches the old 30-known-item shortcut preserving an incomplete collection."""
    database, archive, jobs = sync_components
    await archive.upsert_collection("1001", "想去的地方")
    await archive.upsert_item(
        remote_id="734",
        author_name="作者",
        description="已知作品",
        item_type="video",
    )
    await archive.link_collection_item("1001", "734")

    class RepairProvider:
        requested_full_scan: bool | None = None

        async def list_collections(self) -> list[RemoteCollection]:
            return [RemoteCollection("1001", "想去的地方", 2)]

        async def iter_collection_pages(
            self, remote_id: str, *, full_scan: bool
        ) -> AsyncIterator[RemotePage]:
            self.requested_full_scan = full_scan
            yield RemotePage((item("734"), item("735")), None, False)

    provider = RepairProvider()
    result = await SyncService(provider, archive, jobs).run(full_scan=False)

    assert result.status == "completed"
    assert provider.requested_full_scan is True
    source = await database.fetchone(
        "SELECT declared_count, sync_status FROM library_sources "
        "WHERE id='favorite_collection:1001'"
    )
    assert source is not None
    assert (source["declared_count"], source["sync_status"]) == (2, "complete")
    links = await database.fetchone(
        "SELECT COUNT(*) AS total FROM source_items "
        "WHERE source_id='favorite_collection:1001'"
    )
    assert links is not None and links["total"] == 2


async def test_unknown_remote_count_never_marks_a_source_complete(
    sync_components,
) -> None:
    database, archive, jobs = sync_components

    class UnknownCountProvider:
        async def list_collections(self) -> list[RemoteCollection]:
            return [RemoteCollection("1001", "想去的地方", None)]

        async def iter_collection_pages(
            self, remote_id: str, *, full_scan: bool
        ) -> AsyncIterator[RemotePage]:
            yield RemotePage((item("734"),), None, False)

    result = await SyncService(UnknownCountProvider(), archive, jobs).run(full_scan=False)

    assert result.status == "completed"
    source = await database.fetchone(
        "SELECT declared_count, sync_status, error_code FROM library_sources "
        "WHERE id='favorite_collection:1001'"
    )
    assert source is not None
    assert source["declared_count"] is None
    assert source["sync_status"] == "incomplete"
    assert source["error_code"] == "COUNT_UNKNOWN"


async def test_repeated_sync_preserves_completed_download_jobs(
    sync_components,
) -> None:
    _database, archive, jobs = sync_components

    class OneItemProvider:
        async def list_collections(self) -> list[RemoteCollection]:
            return [RemoteCollection("1001", "想去的地方", 1)]

        async def iter_collection_pages(
            self, remote_id: str, *, full_scan: bool
        ) -> AsyncIterator[RemotePage]:
            yield RemotePage((item("734"),), None, False)

    provider = OneItemProvider()
    first = await SyncService(provider, archive, jobs).run(full_scan=True)
    claimed = await jobs.claim_next(worker_id="worker-a")
    assert claimed is not None
    await jobs.complete(claimed.id)

    second = await SyncService(provider, archive, jobs).run(full_scan=True)

    completed = await jobs.get_by_key("download", "734")
    assert first.enqueued == 1
    assert second.enqueued == 0
    assert completed is not None
    assert completed.status == "completed"
    assert await jobs.claim_next(worker_id="worker-b") is None


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

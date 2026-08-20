from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.download_policy import DownloadPolicyService
from douyin_archive.library_models import LibrarySource, LibrarySourceKind
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.models import MediaAsset, RemoteItem
from douyin_archive.provider.base import RemoteCollection, RemotePage
from douyin_archive.repositories import ArchiveRepository, JobRepository
from douyin_archive.sync_service import SyncService


def item(remote_id: str) -> RemoteItem:
    return RemoteItem(
        remote_id=remote_id,
        author_name="作者",
        description=remote_id,
        item_type="video",
        assets=(MediaAsset(remote_id, 0, "video", f"https://media.test/{remote_id}.mp4"),),
    )


@pytest.fixture
async def components(tmp_path: Path):
    database = await Database(tmp_path / "archive.sqlite3").open()
    archive = ArchiveRepository(database)
    jobs = JobRepository(database)
    policy = DownloadPolicyService(database, jobs)
    yield database, archive, jobs, policy
    await database.close()


async def test_disabled_collection_still_syncs_metadata_without_a_job(components) -> None:
    """Catches discovery ignoring the user's category selection."""
    database, archive, jobs, policy = components
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="favorite_collection:travel",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="travel",
            name="想去的地方",
        )
    )
    await policy.set_enabled("favorite_collection:travel", False)

    class Provider:
        async def list_collections(self) -> list[RemoteCollection]:
            return [RemoteCollection("travel", "想去的地方", 1)]

        async def iter_collection_pages(
            self, remote_id: str, *, full_scan: bool
        ) -> AsyncIterator[RemotePage]:
            yield RemotePage((item("travel-1"),), None, False)

    result = await SyncService(Provider(), archive, jobs, policy).run(full_scan=True)

    link = await database.fetchone(
        "SELECT metadata_json FROM source_items "
        "WHERE source_id='favorite_collection:travel' AND item_id='travel-1'"
    )
    assert result.discovered == 1
    assert result.enqueued == 0
    assert link is not None and "travel-1.mp4" in link["metadata_json"]
    assert await jobs.count() == 0
    remote_check = await database.fetchone(
        "SELECT status, evidence_code FROM remote_checks WHERE item_id='travel-1'"
    )
    assert remote_check is not None
    assert remote_check["status"] == "available"
    assert remote_check["evidence_code"] == "OK"


async def test_enabled_account_category_downloads_newly_discovered_items(
    components,
) -> None:
    """Catches enabled account categories remaining metadata-only."""
    database, archive, jobs, policy = components
    await LibraryRepository(database).ensure_account_sources()
    await policy.set_enabled("account:likes", True)

    class Provider:
        async def list_collections(self) -> list[RemoteCollection]:
            return []

        async def iter_collection_pages(self, remote_id: str, *, full_scan: bool):
            if False:
                yield remote_id, full_scan

        def supported_account_sources(self) -> tuple[str, ...]:
            return ("like",)

        async def iter_account_pages(self, kind: str, *, full_scan: bool):
            yield RemotePage((item("liked-1"),), None, False)

    result = await SyncService(Provider(), archive, jobs, policy).run(full_scan=True)

    job = await jobs.get_by_key("download", "liked-1")
    assert result.enqueued == 1
    assert job is not None and job.status == "pending"


async def test_shared_collection_discovery_records_two_intents_and_one_job(
    components,
) -> None:
    """Catches source deduplication losing the reason a shared video is retained."""
    database, archive, jobs, policy = components

    class Provider:
        async def list_collections(self) -> list[RemoteCollection]:
            return [
                RemoteCollection("one", "收藏夹一", 1),
                RemoteCollection("two", "收藏夹二", 1),
            ]

        async def iter_collection_pages(
            self, remote_id: str, *, full_scan: bool
        ) -> AsyncIterator[RemotePage]:
            yield RemotePage((item("shared-1"),), None, False)

    result = await SyncService(Provider(), archive, jobs, policy).run(full_scan=True)

    intents = await database.fetchall(
        "SELECT origin_id FROM download_intents "
        "WHERE item_id='shared-1' AND active=1 ORDER BY origin_id"
    )
    assert result.enqueued == 1
    assert await jobs.count() == 1
    assert [row["origin_id"] for row in intents] == [
        "favorite_collection:one",
        "favorite_collection:two",
    ]

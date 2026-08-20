from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path

import pytest

from douyin_archive.archive_repository import ArchiveBatchRepository
from douyin_archive.archive_service import ArchiveService
from douyin_archive.db import Database
from douyin_archive.library_models import LibrarySource, LibrarySourceKind
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.models import MediaAsset, RemoteItem
from douyin_archive.repositories import ArchiveRepository, JobRepository


def item(remote_id: str) -> RemoteItem:
    return RemoteItem(
        remote_id=remote_id,
        author_name="作者",
        description=f"作品 {remote_id}",
        item_type="video",
        assets=(
            MediaAsset(
                remote_id=remote_id,
                asset_index=0,
                media_type="video",
                url=f"https://media.test/{remote_id}.mp4",
            ),
        ),
    )


@pytest.fixture
async def components(tmp_path: Path):
    database = await Database(tmp_path / "archive.sqlite3").open()
    archive = ArchiveRepository(database)
    jobs = JobRepository(database)
    library = LibraryRepository(database)
    policy_module = importlib.import_module("douyin_archive.download_policy")
    policy = policy_module.DownloadPolicyService(database, jobs)
    yield database, archive, jobs, library, policy
    await database.close()


async def seed_source_item(
    archive: ArchiveRepository,
    library: LibraryRepository,
    source_id: str,
    source_kind: LibrarySourceKind,
    remote_id: str,
) -> RemoteItem:
    await library.upsert_source(
        LibrarySource(
            id=source_id,
            kind=source_kind,
            remote_id=source_id.rsplit(":", 1)[-1],
            name=source_id,
        )
    )
    remote = item(remote_id)
    await archive.upsert_item(
        remote_id=remote.remote_id,
        author_name=remote.author_name,
        description=remote.description,
        item_type=remote.item_type,
    )
    await library.link_source_item(source_id, remote_id, "1", asdict(remote))
    return remote


async def test_new_favorite_collection_defaults_to_auto_download(components) -> None:
    """Catches newly discovered folders defaulting off after migration."""
    _database, _archive, _jobs, library, policy = components
    await library.upsert_source(
        LibrarySource(
            id="favorite_collection:travel",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="travel",
            name="想去的地方",
        )
    )

    source = await policy.get_source("favorite_collection:travel")

    assert source is not None
    assert source.enabled is True


async def test_enabling_source_backfills_discovered_items(components) -> None:
    """Catches a toggle that changes UI state but never creates download work."""
    database, archive, jobs, library, policy = components
    remote = await seed_source_item(
        archive, library, "account:likes", LibrarySourceKind.LIKE, "liked-1"
    )

    updated = await policy.set_enabled("account:likes", True)

    job = await jobs.get_by_key("download", remote.remote_id)
    intent = await database.fetchone(
        "SELECT active FROM download_intents "
        "WHERE item_id=? AND origin_type='source' AND origin_id='account:likes'",
        (remote.remote_id,),
    )
    assert updated.enabled is True
    assert job is not None and job.status == "pending"
    assert intent is not None and intent["active"] == 1


async def test_disabling_one_shared_source_keeps_the_job_active(components) -> None:
    """Catches one folder switch pausing a video still selected elsewhere."""
    _database, archive, jobs, library, policy = components
    remote = await seed_source_item(
        archive,
        library,
        "favorite_collection:one",
        LibrarySourceKind.FAVORITE_COLLECTION,
        "shared-1",
    )
    await seed_source_item(
        archive,
        library,
        "favorite_collection:two",
        LibrarySourceKind.FAVORITE_COLLECTION,
        "shared-1",
    )
    await policy.set_enabled("favorite_collection:one", True)
    await policy.set_enabled("favorite_collection:two", True)

    await policy.set_enabled("favorite_collection:one", False)

    job = await jobs.get_by_key("download", remote.remote_id)
    assert job is not None and job.status == "pending"


async def test_disabling_last_source_pauses_pending_but_preserves_completed(
    components,
) -> None:
    """Catches category changes deleting or requeueing completed local media."""
    _database, archive, jobs, library, policy = components
    await seed_source_item(
        archive,
        library,
        "favorite_collection:one",
        LibrarySourceKind.FAVORITE_COLLECTION,
        "pending-1",
    )
    await seed_source_item(
        archive,
        library,
        "favorite_collection:one",
        LibrarySourceKind.FAVORITE_COLLECTION,
        "completed-1",
    )
    await policy.set_enabled("favorite_collection:one", True)
    completed = await jobs.get_by_key("download", "completed-1")
    assert completed is not None
    await jobs.complete(completed.id)

    await policy.set_enabled("favorite_collection:one", False)

    pending = await jobs.get_by_key("download", "pending-1")
    preserved = await jobs.get_by_key("download", "completed-1")
    assert pending is not None and pending.status == "paused"
    assert preserved is not None and preserved.status == "completed"


async def test_manual_archive_intent_survives_source_disable(components) -> None:
    """Catches an automatic policy overriding an explicit Save to NAS action."""
    database, archive, jobs, library, policy = components
    await seed_source_item(
        archive,
        library,
        "account:likes",
        LibrarySourceKind.LIKE,
        "manual-1",
    )
    await policy.set_enabled("account:likes", True)
    service = ArchiveService(
        database,
        jobs,
        ArchiveBatchRepository(database),
        download_policy=policy,
    )
    await service.archive_item("manual-1")

    await policy.set_enabled("account:likes", False)

    job = await jobs.get_by_key("download", "manual-1")
    manual = await database.fetchone(
        "SELECT active FROM download_intents "
        "WHERE item_id='manual-1' AND origin_type='manual'"
    )
    assert job is not None and job.status == "pending"
    assert manual is not None and manual["active"] == 1

from dataclasses import asdict
from pathlib import Path

import pytest

from douyin_archive.archive_repository import ArchiveBatchRepository
from douyin_archive.archive_service import (
    ArchivePayloadUnavailable,
    ArchiveService,
    ArchiveTargetNotFound,
)
from douyin_archive.db import Database
from douyin_archive.library_models import (
    CreatorRecord,
    LibrarySource,
    LibrarySourceKind,
)
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.models import MediaAsset, RemoteItem
from douyin_archive.repositories import ArchiveRepository, JobRepository


def remote_item(remote_id: str, creator_id: str = "creator-1") -> RemoteItem:
    return RemoteItem(
        remote_id=remote_id,
        author_name="旅行作者",
        description=f"作品 {remote_id}",
        item_type="video",
        assets=(
            MediaAsset(
                remote_id,
                0,
                "video",
                f"https://media.test/{remote_id}.mp4",
            ),
        ),
        creator_id=creator_id,
    )


@pytest.fixture
async def archive_components(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    archive = ArchiveRepository(database)
    jobs = JobRepository(database)
    batches = ArchiveBatchRepository(database)
    yield database, archive, jobs, batches, ArchiveService(database, jobs, batches)
    await database.close()


async def seed_item(archive: ArchiveRepository, jobs: JobRepository, remote_id: str):
    item = remote_item(remote_id)
    await LibraryRepository(archive.db).upsert_creator(
        CreatorRecord(item.creator_id or "creator-1", item.author_name)
    )
    await archive.upsert_item(
        remote_id=item.remote_id,
        author_name=item.author_name,
        description=item.description,
        item_type=item.item_type,
        creator_id=item.creator_id,
    )
    return await jobs.enqueue_unique("download", remote_id, asdict(item))


async def test_single_item_archive_reuses_a_completed_job_without_requeueing(
    archive_components,
) -> None:
    _database, archive, jobs, _batches, service = archive_components
    job = await seed_item(archive, jobs, "734")
    claimed = await jobs.claim_next(worker_id="worker-a")
    assert claimed is not None
    await jobs.complete(claimed.id)

    batch = await service.archive_item("734")

    preserved = await jobs.get(job.id)
    assert preserved is not None and preserved.status == "completed"
    assert await jobs.claim_next(worker_id="worker-b") is None
    assert batch.status == "completed"
    assert batch.discovered_count == 1
    assert batch.completed_count == 1


async def test_source_archive_expands_every_known_item_without_duplicate_jobs(
    archive_components,
) -> None:
    database, archive, jobs, _batches, service = archive_components
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="favorite_collection:1001",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="1001",
            name="想去的地方",
        )
    )
    first = await seed_item(archive, jobs, "734")
    await seed_item(archive, jobs, "735")
    await library.link_source_item("favorite_collection:1001", "734", "2")
    await library.link_source_item("favorite_collection:1001", "735", "1")
    claimed = await jobs.claim_next(worker_id="worker-a")
    assert claimed is not None and claimed.id == first.id
    await jobs.complete(claimed.id)

    batch = await service.archive_source("favorite_collection:1001")

    assert await jobs.count() == 2
    assert batch.discovered_count == 2
    assert batch.completed_count == 1
    assert batch.status == "running"


async def test_creator_archive_uses_stable_creator_identity(archive_components) -> None:
    database, archive, jobs, _batches, service = archive_components
    library = LibraryRepository(database)
    await library.upsert_creator(CreatorRecord("creator-1", "旅行作者"))
    await seed_item(archive, jobs, "734")
    await seed_item(archive, jobs, "735")

    batch = await service.archive_creator("creator-1")

    assert batch.kind == "creator"
    assert batch.target_id == "creator-1"
    assert batch.discovered_count == 2


async def test_selective_archive_creates_job_from_synced_source_payload(
    archive_components,
) -> None:
    database, archive, jobs, _batches, service = archive_components
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="account:likes",
            kind=LibrarySourceKind.LIKE,
            remote_id="self",
            name="喜欢",
        )
    )
    synced = remote_item("liked-734")
    await library.upsert_creator(CreatorRecord("creator-1", "旅行作者"))
    await archive.upsert_item(
        remote_id=synced.remote_id,
        author_name=synced.author_name,
        description=synced.description,
        item_type=synced.item_type,
        creator_id=synced.creator_id,
    )
    await library.link_source_item(
        "account:likes", synced.remote_id, "2", asdict(synced)
    )

    batch = await service.archive_item(synced.remote_id)

    job = await jobs.get_by_key("download", synced.remote_id)
    assert job is not None
    assert job.status == "pending"
    assert job.payload["assets"][0]["url"].endswith("liked-734.mp4")
    assert batch.status == "running"
    assert batch.discovered_count == 1


async def test_invalid_synced_source_payload_is_not_queued(archive_components) -> None:
    database, archive, jobs, _batches, service = archive_components
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="account:likes",
            kind=LibrarySourceKind.LIKE,
            remote_id="self",
            name="喜欢",
        )
    )
    await archive.upsert_item(
        remote_id="broken-liked-item",
        author_name="作者",
        description="无媒体详情",
        item_type="video",
    )
    await library.link_source_item(
        "account:likes", "broken-liked-item", "1", {"remote_id": "wrong"}
    )

    with pytest.raises(ArchivePayloadUnavailable):
        await service.archive_item("broken-liked-item")

    assert await jobs.count() == 0


@pytest.mark.parametrize(
    ("method", "target"),
    [
        ("archive_item", "missing-item"),
        ("archive_source", "missing-source"),
        ("archive_creator", "missing-creator"),
    ],
)
async def test_unknown_archive_target_is_rejected(
    archive_components, method: str, target: str
) -> None:
    *_unused, service = archive_components

    with pytest.raises(ArchiveTargetNotFound):
        await getattr(service, method)(target)

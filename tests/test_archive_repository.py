from pathlib import Path

import pytest

from douyin_archive.archive_repository import ArchiveBatchRepository
from douyin_archive.db import Database
from douyin_archive.library_models import CreatorRecord
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.repositories import ArchiveRepository


@pytest.fixture
async def batch_components(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    yield database, ArchiveBatchRepository(database)
    await database.close()


async def test_active_batch_creation_is_idempotent(batch_components) -> None:
    database, repository = batch_components

    first = await repository.create_batch("source", "favorite_collection:1001")
    repeated = await repository.create_batch("source", "favorite_collection:1001")

    assert repeated.id == first.id
    assert await repository.count_batches() == 1

    await repository.set_status(first.id, "completed")
    replacement = await repository.create_batch("source", "favorite_collection:1001")

    assert replacement.id != first.id
    assert await repository.count_batches() == 2
    row = await database.fetchone("SELECT status FROM archive_batches WHERE id=?", (first.id,))
    assert row is not None and row["status"] == "completed"


async def test_batch_item_links_are_idempotent_and_update_discovery_count(
    batch_components,
) -> None:
    database, repository = batch_components
    archive = ArchiveRepository(database)
    await archive.upsert_item(
        remote_id="734",
        author_name="旅行作者",
        description="海边",
        item_type="video",
    )
    batch = await repository.create_batch("item", "734")

    await repository.add_item(batch.id, "734")
    await repository.add_item(batch.id, "734")

    snapshot = await repository.get_batch(batch.id)
    assert snapshot is not None
    assert snapshot.discovered_count == 1
    assert snapshot.total_items == 1


async def test_creator_subscription_upsert_preserves_one_schedule(
    batch_components,
) -> None:
    database, repository = batch_components
    await LibraryRepository(database).upsert_creator(
        CreatorRecord(remote_id="creator-1", nickname="旅行作者")
    )

    await repository.upsert_subscription(
        "creator-1", enabled=True, scan_interval_seconds=1800, archive_new_items=True
    )
    await repository.upsert_subscription(
        "creator-1", enabled=False, scan_interval_seconds=3600, archive_new_items=False
    )

    subscription = await repository.get_subscription("creator-1")
    assert subscription is not None
    assert subscription.enabled is False
    assert subscription.scan_interval_seconds == 3600
    assert subscription.archive_new_items is False
    row = await database.fetchone("SELECT COUNT(*) AS total FROM creator_subscriptions")
    assert row is not None and row["total"] == 1

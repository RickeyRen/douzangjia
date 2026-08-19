from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.library_models import (
    CreatorRecord,
    LibrarySource,
    LibrarySourceKind,
    LibrarySyncStatus,
)
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.repositories import ArchiveRepository


@pytest.fixture
async def database(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    yield database
    await database.close()


async def test_source_item_link_is_idempotent_and_exposes_missing_count(
    database: Database,
) -> None:
    """Catches duplicate links or a false complete state when remote count is larger."""
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    await archive.upsert_item(
        remote_id="item-1",
        author_name="author",
        description="clip",
        item_type="video",
    )
    await library.upsert_source(
        LibrarySource(
            id="likes",
            kind=LibrarySourceKind.LIKE,
            remote_id="self",
            name="喜欢",
            declared_count=2,
            sync_status=LibrarySyncStatus.COMPLETE,
        )
    )

    await library.link_source_item("likes", "item-1", "0001")
    await library.link_source_item("likes", "item-1", "0001")

    integrity = await library.source_integrity("likes")
    assert integrity is not None
    assert integrity.discovered_count == 1
    assert integrity.declared_count == 2
    assert integrity.missing_count == 1
    assert integrity.archived_count == 0
    assert integrity.complete is False


async def test_source_integrity_requires_a_declared_remote_count(
    database: Database,
) -> None:
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="favorite_collection:unknown",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="unknown",
            name="未知数量收藏夹",
            declared_count=None,
            sync_status=LibrarySyncStatus.COMPLETE,
        )
    )

    integrity = await library.source_integrity("favorite_collection:unknown")

    assert integrity is not None
    assert integrity.complete is False


async def test_source_upsert_preserves_identity_and_updates_remote_state(
    database: Database,
) -> None:
    """Catches replacement inserts that lose the stable source row."""
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="favorites-travel",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="remote-1",
            name="想去的地方",
            declared_count=17,
        )
    )
    before = await database.fetchone(
        "SELECT first_seen_at FROM library_sources WHERE id='favorites-travel'"
    )

    await library.upsert_source(
        LibrarySource(
            id="favorites-travel",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="remote-1",
            name="旅行清单",
            declared_count=19,
            sync_status=LibrarySyncStatus.INCOMPLETE,
            error_code="COUNT_MISMATCH",
        )
    )
    after = await database.fetchone(
        "SELECT * FROM library_sources WHERE id='favorites-travel'"
    )

    assert before is not None
    assert after is not None
    assert after["first_seen_at"] == before["first_seen_at"]
    assert after["name"] == "旅行清单"
    assert after["declared_count"] == 19
    assert after["sync_status"] == "incomplete"
    assert after["error_code"] == "COUNT_MISMATCH"


async def test_creator_upsert_preserves_first_seen_and_refreshes_counts(
    database: Database,
) -> None:
    """Catches creator refreshes that duplicate a renamed account."""
    library = LibraryRepository(database)
    await library.upsert_creator(
        CreatorRecord(remote_id="creator-1", nickname="旧昵称", post_count=10)
    )
    before = await database.fetchone(
        "SELECT first_seen_at FROM creators WHERE remote_id='creator-1'"
    )

    await library.upsert_creator(
        CreatorRecord(
            remote_id="creator-1",
            nickname="新昵称",
            unique_id="douyin-user",
            follower_count=120,
            post_count=11,
        )
    )
    after = await database.fetchone(
        "SELECT * FROM creators WHERE remote_id='creator-1'"
    )

    assert before is not None
    assert after is not None
    assert after["first_seen_at"] == before["first_seen_at"]
    assert after["nickname"] == "新昵称"
    assert after["follower_count"] == 120
    assert after["post_count"] == 11


async def test_checkpoint_save_is_idempotent_for_same_page(database: Database) -> None:
    """Catches resume metadata that grows duplicate rows after a retry."""
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="watch-later",
            kind=LibrarySourceKind.WATCH_LATER,
            remote_id="self",
            name="稍后再看",
        )
    )

    await library.save_checkpoint(
        "watch-later",
        cursor="cursor-2",
        page_index=1,
        discovered_count=20,
        response_digest="digest-1",
    )
    await library.save_checkpoint(
        "watch-later",
        cursor="cursor-2",
        page_index=1,
        discovered_count=21,
        response_digest="digest-2",
        stop_reason="interrupted",
    )

    rows = await database.fetchall(
        "SELECT * FROM sync_checkpoints WHERE source_id='watch-later'"
    )
    assert len(rows) == 1
    assert rows[0]["discovered_count"] == 21
    assert rows[0]["response_digest"] == "digest-2"
    assert rows[0]["stop_reason"] == "interrupted"


async def test_legacy_collection_backfill_is_idempotent(database: Database) -> None:
    """Catches upgrades that leave existing archives absent from the new library API."""
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    await archive.upsert_collection("travel", "想去的地方")
    await archive.upsert_item(
        remote_id="legacy-item",
        author_name="旅行作者",
        description="旧归档",
        item_type="video",
    )
    await archive.link_collection_item("travel", "legacy-item")

    await library.backfill_legacy_collections()
    await library.backfill_legacy_collections()

    source = await database.fetchone(
        "SELECT * FROM library_sources WHERE id='favorite_collection:travel'"
    )
    integrity = await library.source_integrity("favorite_collection:travel")
    assert source is not None
    assert source["kind"] == "favorite_collection"
    assert source["name"] == "想去的地方"
    assert source["sync_status"] == "incomplete"
    assert integrity is not None and integrity.discovered_count == 1

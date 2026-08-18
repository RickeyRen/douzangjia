from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.repositories import ArchiveRepository


@pytest.fixture
async def database(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    yield database
    await database.close()


async def test_schema_enables_wal(database: Database) -> None:
    row = await database.fetchone("PRAGMA journal_mode")
    assert row is not None
    assert row[0].lower() == "wal"


async def test_schema_creates_archive_tables(database: Database) -> None:
    rows = await database.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {
        "auth_sessions",
        "collection_items",
        "collections",
        "download_jobs",
        "items",
        "media_files",
        "settings",
        "sync_runs",
    } <= names


async def test_collection_rename_preserves_name_history(database: Database) -> None:
    repository = ArchiveRepository(database)
    await repository.upsert_collection("folder-1", "想去的地方")
    await repository.upsert_collection("folder-1", "周末想去")

    collection = await repository.get_collection("folder-1")
    assert collection is not None
    assert collection.name == "周末想去"
    assert collection.name_history == ["想去的地方", "周末想去"]


async def test_rediscovery_never_removes_collection_membership(database: Database) -> None:
    repository = ArchiveRepository(database)
    await repository.upsert_collection("folder-1", "想去的地方")
    await repository.upsert_item(
        remote_id="734",
        author_name="旅行家",
        description="海边日落",
        item_type="video",
    )
    await repository.link_collection_item("folder-1", "734")
    await repository.link_collection_item("folder-1", "734")

    assert await repository.count_collection_items("folder-1") == 1

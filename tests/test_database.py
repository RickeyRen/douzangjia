import asyncio
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


async def test_schema_creates_library_source_tables(database: Database) -> None:
    """Catches a release that omits the account-library migration."""
    rows = await database.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {
        "creators",
        "library_sources",
        "source_items",
        "sync_checkpoints",
    } <= names


async def test_schema_extends_items_with_creator_and_remote_metadata(
    database: Database,
) -> None:
    """Catches a migration that creates sources but cannot describe their items."""
    rows = await database.fetchall("PRAGMA table_info(items)")
    names = {row["name"] for row in rows}
    assert {
        "cover_url",
        "creator_id",
        "duration_ms",
        "source_url",
        "statistics_json",
        "visibility",
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


async def test_operations_cannot_interleave_with_an_open_transaction(
    database: Database,
) -> None:
    await database.execute("CREATE TABLE transaction_probe (value TEXT NOT NULL)")
    transaction_started = asyncio.Event()
    release_transaction = asyncio.Event()
    outsider_finished = asyncio.Event()

    async def hold_transaction() -> None:
        async with database.transaction(immediate=True):
            await database.execute(
                "INSERT INTO transaction_probe(value) VALUES ('inside')"
            )
            transaction_started.set()
            await release_transaction.wait()

    async def write_outside_transaction() -> None:
        await transaction_started.wait()
        await database.execute(
            "INSERT INTO transaction_probe(value) VALUES ('outside')"
        )
        outsider_finished.set()

    transaction_task = asyncio.create_task(hold_transaction())
    outsider_task = asyncio.create_task(write_outside_transaction())
    await transaction_started.wait()
    await asyncio.sleep(0.05)
    interleaved = outsider_finished.is_set()
    release_transaction.set()
    await asyncio.gather(transaction_task, outsider_task)

    assert interleaved is False
    rows = await database.fetchall("SELECT value FROM transaction_probe ORDER BY rowid")
    assert [row["value"] for row in rows] == ["inside", "outside"]

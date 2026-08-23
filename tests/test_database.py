import asyncio
import sqlite3
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


async def test_schema_creates_archive_batch_and_subscription_tables(
    database: Database,
) -> None:
    rows = await database.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {
        "archive_batches",
        "archive_batch_items",
        "creator_subscriptions",
        "job_events",
    } <= names

    job_columns = {
        row["name"] for row in await database.fetchall("PRAGMA table_info(download_jobs)")
    }
    assert {"batch_id", "priority", "paused_at", "cancel_requested_at"} <= job_columns


async def test_recommend_source_migration_preserves_existing_memberships(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "upgrade.sqlite3"
    migration_dir = Path(__file__).parents[1] / "src/douyin_archive/migrations"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    for migration in sorted(migration_dir.glob("*.sql")):
        if migration.name >= "006_recommend_source.sql":
            break
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 1)",
            (migration.name,),
        )
    connection.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('existing-item', '作者', '作品', 'video', 1, 1)"
    )
    connection.execute(
        "INSERT INTO library_sources "
        "(id, kind, remote_id, name, first_seen_at, last_seen_at) "
        "VALUES ('account:posts', 'post', 'self', '作品', 1, 1)"
    )
    connection.execute(
        "INSERT INTO source_items "
        "(source_id, item_id, metadata_json, first_seen_at, last_seen_at) "
        "VALUES ('account:posts', 'existing-item', '{}', 1, 1)"
    )
    connection.commit()
    connection.close()

    database = await Database(database_path).open()
    try:
        membership = await database.fetchone(
            "SELECT item_id FROM source_items WHERE source_id='account:posts'"
        )
        foreign_key_errors = await database.fetchall("PRAGMA foreign_key_check")
        await database.execute(
            "INSERT INTO library_sources "
            "(id, kind, remote_id, name, first_seen_at, last_seen_at) "
            "VALUES ('account:recommendations', 'recommend', 'self', '推荐', 2, 2)"
        )
    finally:
        await database.close()

    assert membership is not None
    assert membership["item_id"] == "existing-item"
    assert foreign_key_errors == []


async def test_all_favorites_migration_merges_legacy_source_without_data_loss(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "all-favorites-upgrade.sqlite3"
    migration_dir = Path(__file__).parents[1] / "src/douyin_archive/migrations"
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    for migration in sorted(migration_dir.glob("*.sql")):
        if migration.name >= "009_merge_all_favorites.sql":
            break
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 1)",
            (migration.name,),
        )
    for item_id in ("real-item", "legacy-item"):
        connection.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, '作者', '作品', 'video', 1, 1)",
            (item_id,),
        )
    connection.execute(
        "INSERT INTO library_sources "
        "(id, kind, remote_id, name, sync_status, first_seen_at, last_seen_at, "
        "auto_download_enabled, download_policy_updated_at) VALUES "
        "('account:favorite_videos', 'favorite_video', 'self', '收藏视频', "
        "'incomplete', 1, 10, 0, 5), "
        "('favorite_collection:__douyin_all_favorites__', 'favorite_collection', "
        "'__douyin_all_favorites__', '抖音全部收藏', 'incomplete', 2, 9, 1, 8)"
    )
    connection.execute(
        "INSERT INTO source_items "
        "(source_id, item_id, metadata_json, first_seen_at, last_seen_at) VALUES "
        "('account:favorite_videos', 'real-item', '{}', 1, 10), "
        "('favorite_collection:__douyin_all_favorites__', 'legacy-item', '{}', 2, 9)"
    )
    connection.execute(
        "INSERT INTO download_intents "
        "(item_id, origin_type, origin_id, active, payload_json, created_at, updated_at) "
        "VALUES ('legacy-item', 'source', "
        "'favorite_collection:__douyin_all_favorites__', 1, '{}', 2, 9)"
    )
    connection.commit()
    connection.close()

    database = await Database(database_path).open()
    try:
        sources = await database.fetchall(
            "SELECT id, name, auto_download_enabled, download_policy_updated_at "
            "FROM library_sources WHERE id IN "
            "('account:favorite_videos', 'favorite_collection:__douyin_all_favorites__')"
        )
        memberships = await database.fetchall(
            "SELECT item_id FROM source_items "
            "WHERE source_id='account:favorite_videos' ORDER BY item_id"
        )
        intents = await database.fetchall(
            "SELECT item_id, origin_id, active FROM download_intents ORDER BY item_id"
        )
        foreign_key_errors = await database.fetchall("PRAGMA foreign_key_check")
    finally:
        await database.close()

    assert [tuple(row) for row in sources] == [
        ("account:favorite_videos", "抖音全部收藏", 1, 8)
    ]
    assert [row["item_id"] for row in memberships] == ["legacy-item", "real-item"]
    assert [tuple(row) for row in intents] == [
        ("legacy-item", "account:favorite_videos", 1)
    ]
    assert foreign_key_errors == []


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

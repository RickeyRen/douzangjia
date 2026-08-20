from __future__ import annotations

import sqlite3
from pathlib import Path

from douyin_archive.db import Database


def _create_pre_observability_database(path: Path) -> None:
    migration_dir = Path(__file__).parents[1] / "src/douyin_archive/migrations"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    for migration in sorted(migration_dir.glob("*.sql")):
        if migration.name >= "007_observability_home.sql":
            break
        connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, 1)",
            (migration.name,),
        )
    connection.executemany(
        "INSERT INTO library_sources "
        "(id, kind, remote_id, name, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, 1, 1)",
        (
            ("favorite_collection:travel", "favorite_collection", "travel", "想去的地方"),
            ("account:posts", "post", "self", "作品"),
            ("account:likes", "like", "self", "喜欢"),
            ("account:watch_history", "watch_history", "self", "观看历史"),
        ),
    )
    connection.commit()
    connection.close()


async def test_upgrade_preserves_current_collection_download_behavior(
    tmp_path: Path,
) -> None:
    """Catches an upgrade that silently stops existing favorite downloads."""
    path = tmp_path / "upgrade.sqlite3"
    _create_pre_observability_database(path)

    database = await Database(path).open()
    try:
        rows = await database.fetchall(
            "SELECT id, auto_download_enabled FROM library_sources ORDER BY id"
        )
    finally:
        await database.close()

    assert [(row["id"], row["auto_download_enabled"]) for row in rows] == [
        ("account:likes", 0),
        ("account:posts", 0),
        ("account:watch_history", 0),
        ("favorite_collection:travel", 1),
    ]


async def test_observability_schema_supports_health_metrics_and_file_details(
    tmp_path: Path,
) -> None:
    """Catches a partial migration that cannot persist a dashboard requirement."""
    database = await Database(tmp_path / "archive.sqlite3").open()
    try:
        tables = {
            row["name"]
            for row in await database.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        source_columns = {
            row["name"]
            for row in await database.fetchall("PRAGMA table_info(library_sources)")
        }
        media_columns = {
            row["name"]
            for row in await database.fetchall("PRAGMA table_info(media_files)")
        }
    finally:
        await database.close()

    assert {"download_intents", "douyin_account", "metric_samples", "remote_checks"} <= tables
    assert {"auto_download_enabled", "download_policy_updated_at"} <= source_columns
    assert {
        "width",
        "height",
        "codec",
        "fps",
        "bit_rate",
        "duration_ms",
        "probe_status",
        "probed_at",
        "completed_at",
    } <= media_columns

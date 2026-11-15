import asyncio
import sqlite3
from pathlib import Path

from douyin_archive.db_backup import BACKUP_EVERY_SECONDS, DatabaseBackups


def make_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE notes (body TEXT)")
        connection.execute("INSERT INTO notes VALUES ('album and tags live here')")


def test_daily_backup_is_checked_and_only_the_last_week_is_kept(tmp_path: Path) -> None:
    """Catches losing albums, tags and notes with no copy to restore from."""
    source = tmp_path / "data" / "archive.sqlite3"
    source.parent.mkdir()
    make_database(source)
    backup_dir = tmp_path / "data" / "backups"
    backup_dir.mkdir()
    deploy_copy = backup_dir / "archive-pre-abc.sqlite3"
    deploy_copy.write_bytes(b"made by the deploy script")
    clock = [1_800_000_000.0]
    backups = DatabaseBackups(source, backup_dir, keep=3, clock=lambda: clock[0])

    async def scenario() -> None:
        first = await backups.run_tick()
        assert first is not None
        with sqlite3.connect(first) as copy:
            assert copy.execute("SELECT body FROM notes").fetchone()[0] == "album and tags live here"
        # Within a day nothing new is made.
        assert await backups.run_tick() is None
        for _ in range(4):
            clock[0] += BACKUP_EVERY_SECONDS + 1
            assert await backups.backup_now() is not None
        summary = backups.summary()
        assert len(summary["backups"]) == 3 and summary["lastError"] is None
        assert summary["backups"][0]["createdAt"] == int(clock[0])
        # Copies it did not make are never touched.
        assert deploy_copy.exists()
        assert not list(backup_dir.glob("*.part"))

    asyncio.run(scenario())


def test_backup_of_a_wal_database_is_one_self_contained_file(tmp_path: Path) -> None:
    """Catches .part-wal / .part-shm litter piling up next to each daily copy."""
    source = tmp_path / "archive.sqlite3"
    live = sqlite3.connect(source)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("CREATE TABLE notes (body TEXT)")
    live.execute("INSERT INTO notes VALUES ('kept')")
    live.commit()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    # Litter an older build left behind; ours to clear. Other files are not.
    (backup_dir / "auto-20261101-030000.sqlite3.part-wal").write_bytes(b"")
    (backup_dir / "auto-20261101-030000.sqlite3.part-shm").write_bytes(b"x")
    (backup_dir / "archive-pre-abc.sqlite3-wal").write_bytes(b"not ours")
    backups = DatabaseBackups(source, backup_dir, clock=lambda: 1_800_000_000.0)

    try:
        target = asyncio.run(backups.backup_now())
    finally:
        live.close()

    assert target is not None
    assert sorted(path.name for path in backup_dir.iterdir()) == sorted(
        [target.name, "archive-pre-abc.sqlite3-wal"]
    )
    copy = sqlite3.connect(target)
    try:
        assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert copy.execute("SELECT body FROM notes").fetchone()[0] == "kept"
    finally:
        copy.close()

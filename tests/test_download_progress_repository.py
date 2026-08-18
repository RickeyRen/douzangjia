from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.models import MediaAsset
from douyin_archive.repositories import DownloadProgressRepository


async def _insert_item(database: Database) -> None:
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('734', '旅行家', '海边日落', 'video', 1, 1)"
    )


async def test_progress_survives_database_reopen(tmp_path: Path) -> None:
    path = tmp_path / "data" / "archive.sqlite3"
    database = Database(path)
    await database.open()
    await _insert_item(database)
    repository = DownloadProgressRepository(database)
    asset = MediaAsset("734", 0, "video", "https://media.test/734", "video/mp4", 10)

    await repository.prepare_asset(asset, downloaded_bytes=3)
    await repository.update(
        "734",
        0,
        status="running",
        downloaded_bytes=5,
        total_bytes=10,
        speed_bps=2.5,
    )
    await database.close()

    reopened = Database(path)
    await reopened.open()
    rows = await DownloadProgressRepository(reopened).get_for_item("734")

    assert len(rows) == 1
    assert rows[0].status == "running"
    assert rows[0].downloaded_bytes == 5
    assert rows[0].total_bytes == 10
    assert rows[0].speed_bps == 2.5
    assert rows[0].progress_updated_at is not None
    await reopened.close()


async def test_prepare_preserves_a_ready_media_file(tmp_path: Path) -> None:
    database = Database(tmp_path / "data" / "archive.sqlite3")
    await database.open()
    await _insert_item(database)
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, relative_path, byte_size, mime_type, "
        "status, created_at, updated_at) "
        "VALUES ('734', 0, 'video', 'objects/734/000.mp4', 10, 'video/mp4', "
        "'ready', 1, 1)"
    )
    repository = DownloadProgressRepository(database)

    await repository.prepare_asset(
        MediaAsset("734", 0, "video", "https://media.test/734", "video/mp4", 10),
        downloaded_bytes=3,
    )
    row = (await repository.get_for_item("734"))[0]

    assert row.status == "ready"
    assert row.relative_path == "objects/734/000.mp4"
    assert row.downloaded_bytes == 10
    assert row.total_bytes == 10
    await database.close()

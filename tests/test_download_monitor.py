import json
from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.download_monitor import DownloadMonitor


def _payload(remote_id: str, *, expected_size: int | None) -> str:
    return json.dumps(
        {
            "remote_id": remote_id,
            "assets": [
                {
                    "remote_id": remote_id,
                    "asset_index": 0,
                    "media_type": "video",
                    "url": f"https://media.test/{remote_id}",
                    "mime_type": "video/mp4",
                    "expected_size": expected_size,
                }
            ],
        },
        separators=(",", ":"),
    )


async def _seed_monitor(database: Database) -> None:
    await database.execute(
        "INSERT INTO collections "
        "(remote_id, name, name_history_json, first_seen_at, last_seen_at) "
        "VALUES ('1001', '想去的地方', '[\"想去的地方\"]', 1, 1)"
    )
    for remote_id, description in (
        ("734", "海边日落"),
        ("735", "山间公路"),
        ("736", "旧日收藏"),
    ):
        await database.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, '旅行家', ?, 'video', 1, 1)",
            (remote_id, description),
        )
        await database.execute(
            "INSERT INTO collection_items "
            "(collection_id, item_id, first_seen_at, last_seen_at) "
            "VALUES ('1001', ?, 1, 1)",
            (remote_id,),
        )
    await database.execute(
        "INSERT INTO download_jobs "
        "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "last_error_code, created_at, updated_at) VALUES "
        "('download', '734', ?, 'retry', 8, 120, 'MEDIA_HTTP_ERROR', 1, 90), "
        "('download', '735', ?, 'running', 1, 0, NULL, 1, 100), "
        "('download', '736', ?, 'completed', 1, 0, NULL, 1, 80)",
        (_payload("734", expected_size=10), _payload("735", expected_size=20), _payload("736", expected_size=7)),
    )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, relative_path, byte_size, mime_type, status, "
        "created_at, updated_at, downloaded_bytes, total_bytes, speed_bps, progress_updated_at) "
        "VALUES "
        "('734', 0, 'video', NULL, NULL, 'video/mp4', 'running', 1, 90, 3, 10, 4, 90), "
        "('735', 0, 'video', NULL, NULL, 'video/mp4', 'running', 1, 100, 10, 20, 5, 100), "
        "('736', 0, 'video', 'objects/736/000.mp4', 7, 'video/mp4', 'ready', 1, 80, 0, NULL, 0, NULL)"
    )


async def test_snapshot_aggregates_queue_and_complete_task_details(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await _seed_monitor(database)

    snapshot = await DownloadMonitor(database, clock=lambda: 100).snapshot(limit=50)

    assert snapshot["summary"] == {
        "pending": 0,
        "running": 1,
        "retry": 1,
        "failed": 0,
        "completed": 1,
        "downloadedBytes": 13,
        "totalBytes": 30,
        "speedBps": 5.0,
        "etaSeconds": 4,
    }
    assert [item["remoteId"] for item in snapshot["items"]] == ["735", "734", "736"]
    retry = snapshot["items"][1]
    assert retry["description"] == "海边日落"
    assert retry["collections"] == ["想去的地方"]
    assert retry["attempts"] == 8
    assert retry["nextAttemptAt"] == 120
    assert retry["errorCode"] == "MEDIA_HTTP_ERROR"
    assert retry["assets"][0] == {
        "index": 0,
        "fileName": "000.mp4",
        "mediaType": "video",
        "status": "retry",
        "downloadedBytes": 3,
        "totalBytes": 10,
        "speedBps": 0.0,
        "etaSeconds": None,
        "updatedAt": 90,
    }
    completed = snapshot["items"][2]
    assert completed["downloadedBytes"] == 7
    assert completed["totalBytes"] == 7
    assert completed["assets"][0]["downloadedBytes"] == 7
    assert completed["assets"][0]["totalBytes"] == 7
    await database.close()


async def test_unknown_totals_and_stale_speed_do_not_invent_eta(tmp_path: Path) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('734', '作者', '未知大小', 'video', 1, 1)"
    )
    await database.execute(
        "INSERT INTO download_jobs "
        "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "created_at, updated_at) VALUES ('download', '734', ?, 'running', 1, 0, 1, 10)",
        (_payload("734", expected_size=None),),
    )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, mime_type, status, created_at, updated_at, "
        "downloaded_bytes, total_bytes, speed_bps, progress_updated_at) "
        "VALUES ('734', 0, 'video', 'video/mp4', 'running', 1, 10, 3, NULL, 100, 10)"
    )

    snapshot = await DownloadMonitor(database, clock=lambda: 30).snapshot(limit=50)

    assert snapshot["summary"]["downloadedBytes"] == 3
    assert snapshot["summary"]["totalBytes"] is None
    assert snapshot["summary"]["speedBps"] == 0
    assert snapshot["summary"]["etaSeconds"] is None
    assert snapshot["items"][0]["totalBytes"] is None
    assert snapshot["items"][0]["etaSeconds"] is None
    await database.close()

from pathlib import Path

import httpx

from douyin_archive.archive_handler import ArchiveJobHandler
from douyin_archive.db import Database
from douyin_archive.downloader import MediaDownloader
from douyin_archive.media_probe import MediaTechnical
from douyin_archive.models import DownloadJob
from douyin_archive.repositories import DownloadProgressRepository
from douyin_archive.storage import CollectionProjector, ObjectStore


async def test_download_job_registers_media_and_projects_every_collection(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO collections "
        "(remote_id, name, name_history_json, first_seen_at, last_seen_at) VALUES "
        "('1001', '想去的地方', '[\"想去的地方\"]', 1, 1), "
        "('1002', '好看的美女', '[\"好看的美女\"]', 1, 1)"
    )
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('734', '旅行家', '海边日落', 'video', 1, 1)"
    )
    await database.execute(
        "INSERT INTO collection_items "
        "(collection_id, item_id, first_seen_at, last_seen_at) VALUES "
        "('1001', '734', 1, 1), ('1002', '734', 1, 1)"
    )

    async def media(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"original-media")

    store = ObjectStore(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(media)) as client:

        class FakeProbe:
            async def probe(self, _: Path) -> MediaTechnical:
                return MediaTechnical(
                    status="ready",
                    width=1080,
                    height=1920,
                    codec="h264",
                    fps=30.0,
                    bit_rate=4_500_000,
                    duration_ms=15_200,
                )

        handler = ArchiveJobHandler(
            database,
            MediaDownloader(store, client),
            CollectionProjector(tmp_path),
            archive_root=tmp_path,
            media_probe=FakeProbe(),
        )
        await handler(
            DownloadJob(
                id=1,
                kind="download",
                remote_id="734",
                payload={
                    "remote_id": "734",
                    "author_name": "旅行家",
                    "description": "海边日落",
                    "item_type": "video",
                    "assets": [
                        {
                            "remote_id": "734",
                            "asset_index": 0,
                            "media_type": "video",
                            "url": "https://media.test/734",
                            "mime_type": "video/mp4",
                            "expected_size": None,
                        }
                    ],
                },
                status="running",
                attempts=1,
                next_attempt_at=0,
                claimed_by="worker",
                last_error_code=None,
            )
        )

    row = await database.fetchone(
        "SELECT relative_path, byte_size, status, width, height, codec, fps, "
        "bit_rate, duration_ms, probe_status, probed_at, completed_at "
        "FROM media_files WHERE item_id='734'"
    )
    assert row is not None
    assert row["status"] == "ready"
    assert row["byte_size"] == len(b"original-media")
    assert row["width"] == 1080
    assert row["height"] == 1920
    assert row["codec"] == "h264"
    assert row["fps"] == 30.0
    assert row["bit_rate"] == 4_500_000
    assert row["duration_ms"] == 15_200
    assert row["probe_status"] == "ready"
    assert row["probed_at"] is not None
    assert row["completed_at"] is not None
    progress = (await DownloadProgressRepository(database).get_for_item("734"))[0]
    assert progress.status == "ready"
    assert progress.downloaded_bytes == len(b"original-media")
    assert progress.total_bytes == len(b"original-media")
    assert progress.speed_bps == 0
    object_file = tmp_path / row["relative_path"]
    first = next((tmp_path / "library" / "想去的地方").iterdir())
    second = next((tmp_path / "library" / "好看的美女").iterdir())
    assert object_file.read_bytes() == b"original-media"
    assert first.stat().st_ino == second.stat().st_ino == object_file.stat().st_ino
    await database.close()


async def test_handler_persists_resumed_part_before_stream_finishes(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO collections "
        "(remote_id, name, name_history_json, first_seen_at, last_seen_at) "
        "VALUES ('1001', '想去的地方', '[\"想去的地方\"]', 1, 1)"
    )
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('734', '旅行家', '海边日落', 'video', 1, 1)"
    )
    await database.execute(
        "INSERT INTO collection_items "
        "(collection_id, item_id, first_seen_at, last_seen_at) "
        "VALUES ('1001', '734', 1, 1)"
    )
    observed_running_bytes: list[int] = []

    class ResumeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"def"
            row = await database.fetchone(
                "SELECT status, downloaded_bytes FROM media_files "
                "WHERE item_id='734' AND asset_index=0"
            )
            assert row is not None
            assert row["status"] == "running"
            observed_running_bytes.append(int(row["downloaded_bytes"]))

    async def media(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=3-"
        return httpx.Response(
            206,
            stream=ResumeStream(),
            headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
        )

    store = ObjectStore(tmp_path)
    part = store.part_path("734", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"abc")
    async with httpx.AsyncClient(transport=httpx.MockTransport(media)) as client:
        handler = ArchiveJobHandler(
            database,
            MediaDownloader(store, client, progress_interval_seconds=0),
            CollectionProjector(tmp_path),
            archive_root=tmp_path,
        )
        await handler(
            DownloadJob(
                id=1,
                kind="download",
                remote_id="734",
                payload={
                    "assets": [
                        {
                            "remote_id": "734",
                            "asset_index": 0,
                            "media_type": "video",
                            "url": "https://media.test/734",
                            "mime_type": "video/mp4",
                            "expected_size": 6,
                        }
                    ]
                },
                status="running",
                attempts=1,
                next_attempt_at=0,
                claimed_by="worker",
                last_error_code=None,
            )
        )

    assert observed_running_bytes == [6]
    progress = (await DownloadProgressRepository(database).get_for_item("734"))[0]
    assert progress.status == "ready"
    assert progress.downloaded_bytes == 6
    assert progress.total_bytes == 6
    await database.close()

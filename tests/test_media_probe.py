from __future__ import annotations

from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.media_probe import MediaProbe, MediaProbeBackfill, MediaTechnical, parse_ffprobe
from douyin_archive.repositories import ArchiveRepository


def test_parse_ffprobe_extracts_primary_video_stream() -> None:
    result = parse_ffprobe(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                    "avg_frame_rate": "30000/1001",
                    "bit_rate": "4500000",
                    "duration": "15.2",
                }
            ],
            "format": {"duration": "15.25", "bit_rate": "4700000"},
        }
    )

    assert result.width == 1080
    assert result.height == 1920
    assert result.codec == "h264"
    assert round(result.fps or 0, 3) == 29.97
    assert result.bit_rate == 4_500_000
    assert result.duration_ms == 15_200


async def test_probe_reports_unavailable_without_ffprobe(tmp_path: Path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"not-a-real-video")

    result = await MediaProbe(executable=None, discover_executable=False).probe(path)

    assert result.status == "unavailable"
    assert result.width is None


async def test_probe_reports_failed_for_invalid_output(tmp_path: Path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"not-a-real-video")
    executable = tmp_path / "fake-ffprobe"
    executable.write_text("#!/bin/sh\nprintf 'not json'\n", encoding="utf-8")
    executable.chmod(0o755)

    result = await MediaProbe(executable=str(executable)).probe(path)

    assert result.status == "failed"


async def test_backfill_probes_existing_ready_media_without_redownloading(
    tmp_path: Path,
) -> None:
    database = await Database(tmp_path / "data" / "archive.sqlite3").open()
    await ArchiveRepository(database).upsert_item(
        remote_id="734",
        author_name="作者",
        description="旧视频",
        item_type="video",
    )
    media = tmp_path / "objects" / "734" / "000.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"existing-video")
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, relative_path, byte_size, status, "
        "created_at, updated_at) VALUES "
        "('734', 0, 'video', 'objects/734/000.mp4', 14, 'ready', 1, 1)"
    )

    class Probe:
        async def probe(self, path: Path) -> MediaTechnical:
            assert path == media
            return MediaTechnical(status="ready", width=1080, height=1920, codec="h264", fps=30)

    processed = await MediaProbeBackfill(database, tmp_path, Probe()).run_batch(limit=10)
    row = await database.fetchone(
        "SELECT width, height, codec, fps, probe_status, probed_at "
        "FROM media_files WHERE item_id='734'"
    )
    await database.close()

    assert processed == 1
    assert row is not None
    assert dict(row) == {
        "width": 1080,
        "height": 1920,
        "codec": "h264",
        "fps": 30.0,
        "probe_status": "ready",
        "probed_at": row["probed_at"],
    }
    assert row["probed_at"] is not None

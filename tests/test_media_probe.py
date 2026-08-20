from __future__ import annotations

from pathlib import Path

from douyin_archive.media_probe import MediaProbe, parse_ffprobe


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

from pathlib import Path

import httpx
import pytest

from douyin_archive.downloader import (
    DownloadProgressSnapshot,
    IncompleteDownload,
    MediaDownloader,
)
from douyin_archive.models import MediaAsset
from douyin_archive.storage import ObjectStore


async def test_download_streams_to_canonical_object(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert "Range" not in request.headers
        return httpx.Response(200, content=b"abcdef", headers={"Content-Length": "6"})

    store = ObjectStore(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        downloader = MediaDownloader(store, client)
        result = await downloader.download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6)
        )

    assert result == store.object_path("734", "000.mp4")
    assert result.read_bytes() == b"abcdef"


async def test_download_resumes_existing_part(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=3-"
        return httpx.Response(
            206,
            content=b"def",
            headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
        )

    store = ObjectStore(tmp_path)
    part = store.part_path("734", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"abc")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await MediaDownloader(store, client).download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6)
        )

    assert result.read_bytes() == b"abcdef"


async def test_truncated_response_keeps_part_and_never_finalizes(tmp_path: Path) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abc", headers={"Content-Length": "3"})

    store = ObjectStore(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IncompleteDownload):
            await MediaDownloader(store, client).download(
                MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6)
            )

    assert store.part_path("734", "000.mp4").read_bytes() == b"abc"
    assert not store.object_path("734", "000.mp4").exists()


async def test_existing_complete_object_skips_network(tmp_path: Path) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be called")

    store = ObjectStore(tmp_path)
    destination = store.object_path("734", "000.mp4")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"abcdef")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await MediaDownloader(store, client).download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6)
        )

    assert result == destination


async def test_download_reports_real_initial_and_completed_bytes(tmp_path: Path) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abcdef", headers={"Content-Length": "6"})

    snapshots: list[DownloadProgressSnapshot] = []

    async def collect(snapshot: DownloadProgressSnapshot) -> None:
        snapshots.append(snapshot)

    store = ObjectStore(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MediaDownloader(store, client, progress_interval_seconds=0).download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6),
            on_progress=collect,
        )

    assert snapshots[0].downloaded_bytes == 0
    assert snapshots[0].total_bytes == 6
    assert snapshots[-1].downloaded_bytes == 6
    assert snapshots[-1].total_bytes == 6
    assert snapshots[-1].eta_seconds == 0


async def test_resume_reports_existing_part_before_new_bytes(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=3-"
        return httpx.Response(
            206,
            content=b"def",
            headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"},
        )

    snapshots: list[DownloadProgressSnapshot] = []

    async def collect(snapshot: DownloadProgressSnapshot) -> None:
        snapshots.append(snapshot)

    store = ObjectStore(tmp_path)
    part = store.part_path("734", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"abc")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MediaDownloader(store, client, progress_interval_seconds=0).download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6),
            on_progress=collect,
        )

    assert snapshots[0].downloaded_bytes == 3
    assert snapshots[-1].downloaded_bytes == 6


async def test_unknown_total_never_invents_percentage_or_eta(tmp_path: Path) -> None:
    class UnknownLengthStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"abc"

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=UnknownLengthStream())

    snapshots: list[DownloadProgressSnapshot] = []

    async def collect(snapshot: DownloadProgressSnapshot) -> None:
        snapshots.append(snapshot)

    store = ObjectStore(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MediaDownloader(store, client, progress_interval_seconds=0).download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4"),
            on_progress=collect,
        )

    assert snapshots[-1].downloaded_bytes == 3
    assert snapshots[-1].total_bytes is None
    assert snapshots[-1].eta_seconds is None


async def test_streamed_bytes_report_speed_and_eta(tmp_path: Path) -> None:
    class ChunkedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"abc"
            yield b"def"

    class Clock:
        value = 0.0

        def __call__(self) -> float:
            self.value += 1.0
            return self.value

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, stream=ChunkedStream(), headers={"Content-Length": "6"}
        )

    snapshots: list[DownloadProgressSnapshot] = []

    async def collect(snapshot: DownloadProgressSnapshot) -> None:
        snapshots.append(snapshot)

    store = ObjectStore(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MediaDownloader(
            store, client, progress_interval_seconds=0, clock=Clock()
        ).download(
            MediaAsset("734", 0, "video", "https://media.test/signed", "video/mp4", 6),
            on_progress=collect,
        )

    first_data_snapshot = next(item for item in snapshots if item.downloaded_bytes == 3)
    assert first_data_snapshot.speed_bps == 3
    assert first_data_snapshot.eta_seconds == 1

from pathlib import Path

import httpx
import pytest

from douyin_archive.downloader import IncompleteDownload, MediaDownloader
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

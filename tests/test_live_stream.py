import asyncio
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.live_stream import LiveStreamResolver
from douyin_archive.provider.normalizers import normalize_page, stable_play_url

VIDEO = b"0123456789"
STALE = "https://v26-web-prime.douyinvod.com/video/stale"
STABLE = "https://www.douyin.com/aweme/v1/play/?video_id=v0d00fg10000abc&ratio=1080p&line=0"


def payload(url: str) -> str:
    return json.dumps(
        {
            "remote_id": "734",
            "assets": [
                {"remote_id": "734", "asset_index": 0, "media_type": "video", "url": url,
                 "mime_type": "video/mp4", "expected_size": 10}
            ],
        }
    )


async def seed(root: Path, url: str) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, "
        "last_seen_at) VALUES ('734', '作者', '作品', 'video', 100, 100)"
    )
    await database.execute(
        "INSERT INTO download_jobs (kind, remote_id, payload_json, status, attempts, "
        "next_attempt_at, last_error_code, created_at, updated_at) "
        "VALUES ('download', '734', ?, 'retry', 3, 99999999999, 'MEDIA_URL_EXPIRED', 100, 100)",
        (payload(url),),
    )
    await database.close()


def douyin(request: httpx.Request) -> httpx.Response:
    if request.url.host == "www.douyin.com":
        return httpx.Response(302, headers={"Location": "https://v95-web.douyinvod.com/fresh"})
    if request.url.path == "/fresh":
        start, end = request.headers["Range"].removeprefix("bytes=").split("-")
        start, end = int(start), int(end or len(VIDEO) - 1)
        return httpx.Response(
            206,
            content=VIDEO[start : end + 1],
            headers={"Content-Range": f"bytes {start}-{end}/10", "Content-Length": str(end - start + 1)},
        )
    return httpx.Response(403, text="<html>403 Forbidden</html>")


def client_for(root: Path, master_key: str, resolver_factory) -> TestClient:
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.app.state.live_stream = resolver_factory(client.app.state.database)
    client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
    client.headers["X-CSRF-Token"] = client.cookies["archive_csrf"]
    return client


def test_stream_relays_ranges_through_the_never_expiring_link(tmp_path: Path, master_key: str) -> None:
    asyncio.run(seed(tmp_path, STABLE))
    http = httpx.AsyncClient(transport=httpx.MockTransport(douyin), follow_redirects=True)
    client = client_for(tmp_path, master_key, lambda db: LiveStreamResolver(db, http))
    try:
        response = client.get("/api/items/734/stream", headers={"Range": "bytes=2-5"})
        again = client.get("/api/items/734/stream", headers={"Range": "bytes=6-"})
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-type"] == "video/mp4"
    assert again.content == b"6789"


def test_stream_asks_douyin_once_when_every_link_is_dead(tmp_path: Path, master_key: str) -> None:
    asyncio.run(seed(tmp_path, STALE))
    http = httpx.AsyncClient(transport=httpx.MockTransport(douyin), follow_redirects=True)
    asked: list[list[str]] = []
    refreshed: list[str] = []

    async def fetch(ids: list[str]):
        asked.append(ids)
        return [{"aweme_id": "734", "desc": "作品", "author": {"nickname": "作者"},
                 "video": {"play_addr": {"uri": "v0d00fg10000abc", "url_list": [STALE]}}}]

    async def refresh(item_id: str, _payload: dict) -> bool:
        refreshed.append(item_id)
        return True

    client = client_for(
        tmp_path, master_key,
        lambda db: LiveStreamResolver(db, http, fetch_records=fetch, refresh_links=refresh),
    )
    try:
        first = client.get("/api/items/734/stream", headers={"Range": "bytes=0-1"})
        second = client.get("/api/items/734/stream", headers={"Range": "bytes=0-"})
    finally:
        client.__exit__(None, None, None)
    assert first.status_code == 206 and first.content == b"01"
    assert second.content == VIDEO
    assert asked == [["734"]]
    assert refreshed == ["734"]


def test_stream_says_so_when_douyin_has_nothing(tmp_path: Path, master_key: str) -> None:
    asyncio.run(seed(tmp_path, STALE))
    http = httpx.AsyncClient(transport=httpx.MockTransport(douyin), follow_redirects=True)
    client = client_for(tmp_path, master_key, lambda db: LiveStreamResolver(db, http))
    try:
        response = client.get("/api/items/734/stream", headers={"Range": "bytes=0-"})
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 409
    assert response.json()["code"] == "STREAM_UNAVAILABLE"


def test_save_now_moves_a_backed_off_download_to_the_front(tmp_path: Path, master_key: str) -> None:
    asyncio.run(seed(tmp_path, STALE))
    client = client_for(tmp_path, master_key, lambda db: None)
    try:
        assert client.post("/api/archive/items/734").status_code == 202
        row = asyncio.run(_job(tmp_path))
    finally:
        client.__exit__(None, None, None)
    assert row["status"] == "pending"
    assert row["next_attempt_at"] < 0
    assert row["last_error_code"] is None


async def _job(root: Path):
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    try:
        return await database.fetchone("SELECT * FROM download_jobs WHERE remote_id='734'")
    finally:
        await database.close()


def test_videos_download_through_the_player_endpoint() -> None:
    page = normalize_page({"aweme_list": [{
        "aweme_id": "9", "desc": "", "author": {"nickname": "a"},
        "video": {"play_addr": {"uri": "v0200fg10000xyz", "url_list": [STALE], "data_size": 5}},
    }]})
    asset = page.items[0].assets[0]
    assert asset.url == "https://www.douyin.com/aweme/v1/play/?video_id=v0200fg10000xyz&ratio=1080p&line=0"
    assert asset.expected_size is None
    # A gallery's soundtrack uri is a full URL, never a video id.
    assert stable_play_url({"uri": "https://sf11-cdn-tos.douyinstatic.com/obj/x.mp3"}) is None

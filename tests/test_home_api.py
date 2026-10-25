import asyncio
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.posters import PosterCache
from douyin_archive.routes.home import sync_health

NOW = 2_000_000_000


async def seed(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, unique_id, avatar_url, first_seen_at, "
        "last_seen_at) VALUES ('c1', '小鹿', 'deer', NULL, 1, 1)"
    )
    for index in range(1, 4):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, "
            "last_seen_at, creator_id, cover_url) VALUES (?, '小鹿', ?, ?, ?, ?, 'c1', ?)",
            (
                f"70{index}",
                f"作品 {index}",
                "gallery" if index == 3 else "video",
                index,
                index,
                f"https://cdn.invalid/{index}.jpg",
            ),
        )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, "
        "mime_type, status, created_at, updated_at) VALUES "
        "('702', 0, 'video', 'objects/702/000.mp4', 2048, 'video/mp4', 'ready', 1, 1)"
    )
    await database.execute(
        "INSERT INTO library_sources (id, kind, remote_id, name, sync_status, first_seen_at, "
        "last_seen_at) VALUES ('favorite_collection:9', 'favorite_collection', '9', '想去的地方', "
        "'complete', 1, 1), ('account:watch_history', 'watch_history', 'self', '观看历史', "
        "'complete', 1, 1)"
    )
    for item in ("701", "702"):
        for source in ("favorite_collection:9", "account:watch_history"):
            await database.execute(
                "INSERT INTO source_items (source_id, item_id, remote_order, first_seen_at, "
                "last_seen_at) VALUES (?, ?, ?, 1, 1)",
                (source, item, item),
            )
    await database.close()


def test_home_summarizes_library_for_the_landing_page(tmp_path: Path, master_key: str) -> None:
    asyncio.run(seed(tmp_path))
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        client.put("/api/items/701/star", headers={"X-CSRF-Token": client.cookies["archive_csrf"]})
        body = client.get("/api/home").json()

    assert body["stats"] == {
        "items": 3,
        "videos": 2,
        "galleries": 1,
        "downloadedItems": 1,
        "archivedBytes": 2048,
        "creators": 1,
        "starred": 1,
        "gone": 0,
        "remoteChecked": 0,
    }
    assert [item["awemeId"] for item in body["recent"]] == ["703", "702", "701"]
    assert [item["awemeId"] for item in body["starred"]] == ["701"]
    # Watch history is not a shelf; the collection prefers downloaded posters first.
    assert [shelf["name"] for shelf in body["shelves"]] == ["想去的地方"]
    assert body["shelves"][0]["covers"][0].endswith("/poster")
    assert body["shelves"][0]["covers"][1] == "https://cdn.invalid/1.jpg"
    assert body["creators"][0] == {
        "id": "c1",
        "nickname": "小鹿",
        "uniqueId": "deer",
        "avatarUrl": None,
        "itemCount": 3,
    }
    assert body["health"]["state"] == "login_required"


class FakeCoordinator:
    def __init__(self, state: str = "ok") -> None:
        self.state = state

    async def probe(self) -> str:
        return self.state


async def health_for(
    root: Path, runs: list[tuple[str, int]], *, session: str = "authenticated", browser="ok"
) -> dict:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    try:
        await database.execute(
            "INSERT INTO auth_sessions (provider, encrypted_cookies, status, updated_at) "
            "VALUES ('douyin', 'x', ?, 1)",
            (session,),
        )
        for status, finished in runs:
            await database.execute(
                "INSERT INTO sync_runs (mode, phase, status, started_at, finished_at, error_code) "
                "VALUES ('incremental', 'done', ?, ?, ?, ?)",
                (
                    status,
                    finished - 10,
                    finished,
                    "DOUYIN_RESPONSE_CHANGED" if status == "failed" else None,
                ),
            )
    except BaseException:
        await database.close()
        raise
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                database=database,
                settings=SimpleNamespace(sync_interval_seconds=300),
                browser_coordinator=FakeCoordinator(browser),
            )
        )
    )
    try:
        return await sync_health(request, now=NOW)
    finally:
        await database.close()


@pytest.mark.parametrize(
    ("runs", "session", "browser", "expected"),
    [
        ([("completed", NOW - 60)], "authenticated", "ok", "ok"),
        ([("completed", NOW - 120), ("running", NOW)], "authenticated", "ok", "syncing"),
        ([], "authenticated", "ok", "never"),
        ([("completed", NOW - 600), ("failed", NOW - 300), ("failed", NOW - 10)], "authenticated", "ok", "failing"),
        ([("completed", NOW - 600), ("failed", NOW - 10)], "authenticated", "ok", "ok"),
        ([("completed", NOW - 60)], "authenticated", "disconnected", "failing"),
        ([("completed", NOW - 60)], "expired", "ok", "login_required"),
        # The production outage: the scheduler died without recording any run.
        ([("completed", NOW - 31 * 24 * 3600)], "authenticated", "not_started", "stale"),
    ],
)
def test_sync_health_states(
    tmp_path: Path, runs: list, session: str, browser: str, expected: str
) -> None:
    health = asyncio.run(health_for(tmp_path, runs, session=session, browser=browser))

    assert health["state"] == expected
    if expected == "stale":
        assert health["lastErrorCode"] == "SYNC_STALLED"
        assert health["staleAfterSeconds"] == 1800


def fake_ffmpeg(directory: Path, *, succeed: bool = True) -> Path:
    """A stand-in that writes a JPEG marker to its last argument, like ffmpeg -y out."""
    script = directory / "ffmpeg"
    calls = directory / "calls.log"
    body = 'out="${@: -1}"; printf jpeg > "$out"' if succeed else "exit 1"
    script.write_text(f'#!/bin/bash\necho "$@" >> "{calls}"\n{body}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_poster_cache_renders_once_and_remembers_failures(tmp_path: Path) -> None:
    source = tmp_path / "objects" / "1" / "000.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    tools = tmp_path / "tools"
    tools.mkdir()

    cache = PosterCache(tmp_path, executable=str(fake_ffmpeg(tools)))
    first = asyncio.run(cache.poster(1, source, "video"))
    second = asyncio.run(cache.poster(1, source, "video"))

    assert first == second == tmp_path / "cache" / "posters" / "1.jpg"
    assert first.read_bytes() == b"jpeg"
    calls = (tools / "calls.log").read_text().splitlines()
    assert len(calls) == 1
    assert "-ss 1" in calls[0]

    broken_tools = tmp_path / "broken"
    broken_tools.mkdir()
    broken = PosterCache(tmp_path / "other", executable=str(fake_ffmpeg(broken_tools, succeed=False)))
    assert asyncio.run(broken.poster(2, source, "video")) is None
    assert asyncio.run(broken.poster(2, source, "video")) is None
    # One seek attempt plus one from the first frame, and nothing on the retry.
    assert len((broken_tools / "calls.log").read_text().splitlines()) == 2
    assert not list((tmp_path / "other" / "cache" / "posters").glob("*"))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs a real ffmpeg")
def test_poster_endpoint_serves_rendered_jpeg(tmp_path: Path, master_key: str) -> None:
    import subprocess

    asyncio.run(seed(tmp_path))
    video = tmp_path / "objects" / "702" / "000.mp4"
    video.parent.mkdir(parents=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=320x568:d=2",
         "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        media_id = client.get("/api/feed").json()["items"][1]["media"][0]["id"]
        response = client.get(f"/api/media/{media_id}/poster")
        missing = client.get("/api/media/999/poster")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"
    assert missing.status_code == 404

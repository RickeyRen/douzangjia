import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.avatars import AvatarCache, avatar_route
from douyin_archive.config import Settings
from douyin_archive.db import Database

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 64


def transport(calls: list[str], *, status: int = 200, content_type: str = "image/jpeg") -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, content=JPEG, headers={"content-type": content_type})

    return httpx.MockTransport(handle)


def test_cache_fetches_once_and_refetches_when_the_url_changes(tmp_path: Path) -> None:
    calls: list[str] = []

    async def scenario() -> list[Path | None]:
        client = httpx.AsyncClient(transport=transport(calls))
        cache = AvatarCache(tmp_path, client=client)
        try:
            return [
                await cache.get("c1", "https://cdn.test/a.jpg"),
                await cache.get("c1", "https://cdn.test/a.jpg"),
                await cache.get("c1", "https://cdn.test/b.jpg"),
                await cache.get("c1", None),
            ]
        finally:
            await client.aclose()

    results = asyncio.run(scenario())
    assert calls == ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"]
    assert results[0] == results[1] == results[2] == results[3]
    assert results[0] is not None and results[0].read_bytes() == JPEG


def test_cache_rejects_non_images_and_keeps_an_older_copy(tmp_path: Path) -> None:
    async def scenario() -> tuple[Path | None, Path | None]:
        good = httpx.AsyncClient(transport=transport([], content_type="image/png"))
        bad = httpx.AsyncClient(transport=transport([], content_type="text/html"))
        try:
            first = await AvatarCache(tmp_path, client=good).get("c2", "https://cdn.test/ok.png")
            second = await AvatarCache(tmp_path, client=bad).get("c2", "https://cdn.test/broken")
            missing = await AvatarCache(tmp_path, client=bad).get("c3", "https://cdn.test/nope")
            return (first if first == second else None, missing)
        finally:
            await good.aclose()
            await bad.aclose()

    kept, missing = asyncio.run(scenario())
    assert kept is not None and missing is None


def test_avatar_route_helper() -> None:
    assert avatar_route("c1", "https://cdn.test/a.jpg") == "/api/creators/c1/avatar"
    assert avatar_route("c1", None) is None
    assert avatar_route(None, "https://cdn.test/a.jpg") == "https://cdn.test/a.jpg"


def test_creator_endpoints_serve_cached_avatars(tmp_path: Path, master_key: str) -> None:
    """Catches grids hot-linking Douyin's CDN for every avatar."""

    async def seed() -> None:
        database = await Database(tmp_path / "data" / "archive.sqlite3").open()
        await database.execute(
            "INSERT INTO creators (remote_id, nickname, unique_id, avatar_url, first_seen_at, last_seen_at) "
            "VALUES ('c1', '小鹿', 'deer', 'https://cdn.test/deer.jpg', 1, 1)"
        )
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at, creator_id) "
            "VALUES ('701', '小鹿', 'x', 'video', 1, 1, 'c1')"
        )
        await database.close()

    asyncio.run(seed())
    calls: list[str] = []
    app = create_app(Settings(archive_root=tmp_path, master_key=master_key))
    app.state.avatar_cache = AvatarCache(tmp_path, client=httpx.AsyncClient(transport=transport(calls)))
    with TestClient(app) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        creator = client.get("/api/creators/c1").json()
        item = client.get("/api/items/701").json()
        avatar = client.get("/api/creators/c1/avatar")
        again = client.get("/api/creators/c1/avatar")
        unknown = client.get("/api/creators/nobody/avatar")

    assert creator["avatarUrl"] == "/api/creators/c1/avatar"
    assert item["creator"]["avatarUrl"] == "/api/creators/c1/avatar"
    assert avatar.status_code == 200 and avatar.content == JPEG
    assert again.headers["cache-control"].startswith("private")
    assert calls == ["https://cdn.test/deer.jpg"]
    assert unknown.status_code == 404

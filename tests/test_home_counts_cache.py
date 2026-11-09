import asyncio
import types
from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.routes import home


def test_library_counts_are_served_from_cache_and_recounted_when_stale(tmp_path: Path, monkeypatch) -> None:
    async def scenario() -> tuple[int, int, int]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        request = types.SimpleNamespace(app=types.SimpleNamespace(state=types.SimpleNamespace(database=database)))
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES ('a', 'x', '', 'video', 1, 1)"
        )
        await database.execute("INSERT INTO item_stars (item_id, starred_at) VALUES ('a', 1)")
        first = (await home.library_counts(request))["items"]
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES ('b', 'x', '', 'video', 2, 2)"
        )
        await database.execute("INSERT INTO item_stars (item_id, starred_at) VALUES ('b', 2)")
        cached = (await home.library_counts(request))["items"]
        monkeypatch.setattr(home, "LIBRARY_TOTALS_TTL_SECONDS", -1)
        await home.library_counts(request)
        await request.app.state.home_library_refresh
        fresh = (await home.library_counts(request))["items"]
        await database.close()
        return first, cached, fresh

    assert asyncio.run(scenario()) == (1, 1, 2)

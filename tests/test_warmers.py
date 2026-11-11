import asyncio
from pathlib import Path
from types import SimpleNamespace

from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.warmers import warm_once


def test_warming_builds_home_and_vanished_without_a_request(tmp_path: Path, master_key: str) -> None:
    """Catches the background warmer breaking when a page starts reading request-only state."""

    async def scenario() -> None:
        database = await Database(tmp_path / "archive.sqlite3").open()
        try:
            state = SimpleNamespace(
                database=database,
                settings=Settings(archive_root=tmp_path, master_key=master_key),
            )
            await warm_once(SimpleNamespace(state=state))
            # The home page's cached totals are filled as a side effect.
            assert getattr(state, "home_library_counts", None) is not None
        finally:
            await database.close()

    asyncio.run(scenario())

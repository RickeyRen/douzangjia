import asyncio
from pathlib import Path

from douyin_archive.db import Database


def test_ready_file_probe_uses_the_item_index(tmp_path: Path) -> None:
    """Catches an index on media_files(status, ...) hijacking the per-item probe.

    That probe runs once per library item on home, the unsaved count and the
    bulk queue; scanning every ready file instead stalled the whole server.
    """

    async def scenario() -> str:
        database = await Database(tmp_path / "archive.sqlite3").open()
        rows = await database.fetchall(
            "EXPLAIN QUERY PLAN SELECT 1 FROM media_files mf WHERE mf.item_id=? AND mf.status='ready'",
            ("1",),
        )
        await database.close()
        return " ".join(str(row["detail"]) for row in rows)

    plan = asyncio.run(scenario())
    assert "item_id=?" in plan, plan

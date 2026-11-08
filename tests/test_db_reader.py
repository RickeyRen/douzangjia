import asyncio

import pytest

from douyin_archive.db import Database


@pytest.mark.asyncio
async def test_reads_do_not_wait_for_another_tasks_write_transaction(tmp_path):
    database = await Database(tmp_path / "archive.sqlite3").open()
    try:
        await database.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
        await database.execute("INSERT INTO notes(body) VALUES ('kept')")
        entered = asyncio.Event()
        release = asyncio.Event()

        async def long_write() -> None:
            async with database.transaction():
                await database.execute("INSERT INTO notes(body) VALUES ('pending')")
                # The writer sees its own uncommitted row.
                assert len(await database.fetchall("SELECT * FROM notes")) == 2
                entered.set()
                await release.wait()

        writer = asyncio.create_task(long_write())
        await entered.wait()
        rows = await asyncio.wait_for(database.fetchall("SELECT body FROM notes"), timeout=2)
        assert [row["body"] for row in rows] == ["kept"]
        release.set()
        await writer
        rows = await database.fetchall("SELECT body FROM notes ORDER BY id")
        assert [row["body"] for row in rows] == ["kept", "pending"]
    finally:
        await database.close()

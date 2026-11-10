from __future__ import annotations

import asyncio
import logging
import time
import traceback
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from sqlite3 import Row
from typing import Any

import aiosqlite

CACHE_SIZE = -65536  # KiB, i.e. 64 MiB for the writer
# Several readers so one slow query (the home totals take seconds on a busy NAS)
# never makes every other page wait behind it. Each keeps its own page cache, and
# mmap lets them share the OS page cache instead of each copying the database.
READER_COUNT = 4
# A write transaction holding the lock longer than this is logged with where it
# began: every other writer, and reads that need the writer, wait behind it.
SLOW_TRANSACTION_SECONDS = 5.0

logger = logging.getLogger(__name__)
READER_CACHE_SIZE = -65536
READER_MMAP_SIZE = 1024 * 1024 * 1024


def _is_plain_select(sql: str) -> bool:
    text = sql.lstrip().lower()
    return text.startswith("select") and "returning" not in text


class Database:
    """One SQLite connection with migrations and serialized write transactions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None
        self._operation_lock = asyncio.Lock()
        self._transaction_owner: asyncio.Task[Any] | None = None
        # WAL lets reader connections run while the writer is inside a long
        # write transaction, so API requests never queue behind background work.
        self._readers: list[aiosqlite.Connection] = []
        self._idle_readers: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("database is not open")
        return self._connection

    async def open(self) -> Database:
        if self._connection is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path, isolation_level=None)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.execute("PRAGMA busy_timeout=5000")
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute(f"PRAGMA cache_size={CACHE_SIZE}")
        await self._migrate()
        if str(self.path) != ":memory:":
            for _ in range(READER_COUNT):
                reader = await aiosqlite.connect(self.path, isolation_level=None)
                reader.row_factory = aiosqlite.Row
                await reader.execute("PRAGMA busy_timeout=5000")
                await reader.execute("PRAGMA query_only=ON")
                await reader.execute(f"PRAGMA cache_size={READER_CACHE_SIZE}")
                await reader.execute(f"PRAGMA mmap_size={READER_MMAP_SIZE}")
                self._readers.append(reader)
                self._idle_readers.put_nowait(reader)
        return self

    async def close(self) -> None:
        readers, self._readers = self._readers, []
        self._idle_readers = asyncio.Queue()
        for reader in readers:
            await reader.close()
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _migrate(self) -> None:
        migration_dir = Path(__file__).with_name("migrations")
        await self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
        )
        for migration in sorted(migration_dir.glob("*.sql")):
            row = await self.fetchone(
                "SELECT 1 FROM schema_migrations WHERE version=?", (migration.name,)
            )
            if row is not None:
                continue
            script = migration.read_text(encoding="utf-8")
            await self.connection.executescript(script)
            await self.connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) "
                "VALUES (?, unixepoch())",
                (migration.name,),
            )

    async def execute(
        self, sql: str, parameters: Iterable[Any] = ()
    ) -> aiosqlite.Cursor:
        async with self._operation():
            return await self.connection.execute(sql, tuple(parameters))

    async def fetchone(self, sql: str, parameters: Iterable[Any] = ()) -> Row | None:
        async with self._read_connection(sql) as connection:
            cursor = await connection.execute(sql, tuple(parameters))
            try:
                return await cursor.fetchone()
            finally:
                await cursor.close()

    async def fetchall(self, sql: str, parameters: Iterable[Any] = ()) -> list[Row]:
        async with self._read_connection(sql) as connection:
            cursor = await connection.execute(sql, tuple(parameters))
            try:
                return await cursor.fetchall()
            finally:
                await cursor.close()

    @asynccontextmanager
    async def _read_connection(self, sql: str) -> AsyncIterator[aiosqlite.Connection]:
        # Inside its own transaction a task must read its uncommitted writes,
        # and INSERT ... RETURNING goes through fetchone too.
        if (
            not self._readers
            or asyncio.current_task() is self._transaction_owner
            or not _is_plain_select(sql)
        ):
            async with self._operation():
                yield self.connection
            return
        reader = await self._idle_readers.get()
        try:
            yield reader
        finally:
            if reader in self._readers:
                self._idle_readers.put_nowait(reader)

    @asynccontextmanager
    async def _operation(self) -> AsyncIterator[None]:
        if asyncio.current_task() is self._transaction_owner:
            yield
            return
        async with self._operation_lock:
            yield

    @asynccontextmanager
    async def transaction(self, *, immediate: bool = False) -> AsyncIterator[None]:
        current = asyncio.current_task()
        if current is None:
            raise RuntimeError("database transaction requires an asyncio task")
        if current is self._transaction_owner:
            # Joining the outer transaction lets bulk work batch many small writes
            # into one commit; an error still rolls back the whole outer block.
            yield
            return
        async with self._operation_lock:
            self._transaction_owner = current
            started = time.monotonic()
            await self.connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield
            except BaseException:
                await self.connection.rollback()
                raise
            else:
                await self.connection.commit()
            finally:
                self._transaction_owner = None
                held = time.monotonic() - started
                if held >= SLOW_TRANSACTION_SECONDS:
                    logger.warning(
                        "database transaction held the write lock %.1fs, opened at %s",
                        held,
                        _caller_summary(),
                    )


def _caller_summary() -> str:
    frames = [
        frame
        for frame in traceback.extract_stack()[:-1]
        if "douyin_archive" in frame.filename and not frame.filename.endswith("db.py")
    ]
    return " <- ".join(
        f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno} {frame.name}"
        for frame in reversed(frames[-4:])
    ) or "unknown"

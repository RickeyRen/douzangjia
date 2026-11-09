from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from sqlite3 import Row
from typing import Any

import aiosqlite

CACHE_SIZE = -65536  # KiB, i.e. 64 MiB for the writer
# Pages read by the API stay in memory: the whole archive database is a few hundred MiB
# and the NAS evicts its page cache under pressure, which made cold reads take seconds.
READER_CACHE_SIZE = -262144


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
        # WAL lets a second connection read while the first is inside a long
        # write transaction, so API requests never queue behind background work.
        self._reader: aiosqlite.Connection | None = None
        self._read_lock = asyncio.Lock()

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
            reader = await aiosqlite.connect(self.path, isolation_level=None)
            reader.row_factory = aiosqlite.Row
            await reader.execute("PRAGMA busy_timeout=5000")
            await reader.execute("PRAGMA query_only=ON")
            await reader.execute(f"PRAGMA cache_size={READER_CACHE_SIZE}")
            self._reader = reader
        return self

    async def close(self) -> None:
        if self._reader is not None:
            await self._reader.close()
            self._reader = None
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
            self._reader is None
            or asyncio.current_task() is self._transaction_owner
            or not _is_plain_select(sql)
        ):
            async with self._operation():
                yield self.connection
            return
        async with self._read_lock:
            yield self._reader

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
            raise RuntimeError("nested database transactions are not supported")
        async with self._operation_lock:
            self._transaction_owner = current
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

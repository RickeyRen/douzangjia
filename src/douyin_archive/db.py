from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from sqlite3 import Row
from typing import Any

import aiosqlite


class Database:
    """One SQLite connection with migrations and serialized write transactions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None
        self._transaction_lock = asyncio.Lock()

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
        await self._migrate()
        return self

    async def close(self) -> None:
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
        return await self.connection.execute(sql, tuple(parameters))

    async def fetchone(self, sql: str, parameters: Iterable[Any] = ()) -> Row | None:
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, parameters: Iterable[Any] = ()) -> list[Row]:
        cursor = await self.execute(sql, parameters)
        return await cursor.fetchall()

    @asynccontextmanager
    async def transaction(self, *, immediate: bool = False) -> AsyncIterator[None]:
        async with self._transaction_lock:
            await self.connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield
            except BaseException:
                await self.connection.rollback()
                raise
            else:
                await self.connection.commit()

from __future__ import annotations

import json
import time
from typing import Any

from .db import Database
from .models import Collection, DownloadJob


class ArchiveRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def upsert_collection(self, remote_id: str, name: str) -> Collection:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            existing = await self.db.fetchone(
                "SELECT * FROM collections WHERE remote_id=?", (remote_id,)
            )
            if existing is None:
                history = [name]
                await self.db.execute(
                    "INSERT INTO collections "
                    "(remote_id, name, name_history_json, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (remote_id, name, json.dumps(history, ensure_ascii=False), now, now),
                )
            else:
                history = json.loads(existing["name_history_json"])
                if not history or history[-1] != name:
                    history.append(name)
                await self.db.execute(
                    "UPDATE collections SET name=?, name_history_json=?, last_seen_at=? "
                    "WHERE remote_id=?",
                    (name, json.dumps(history, ensure_ascii=False), now, remote_id),
                )
            row = await self.db.fetchone(
                "SELECT * FROM collections WHERE remote_id=?", (remote_id,)
            )
        if row is None:
            raise RuntimeError("collection upsert did not return a row")
        return Collection.from_row(row)

    async def get_collection(self, remote_id: str) -> Collection | None:
        row = await self.db.fetchone(
            "SELECT * FROM collections WHERE remote_id=?", (remote_id,)
        )
        return Collection.from_row(row) if row is not None else None

    async def upsert_item(
        self,
        *,
        remote_id: str,
        author_name: str,
        description: str,
        item_type: str,
        published_at: int | None = None,
        metadata_digest: str | None = None,
    ) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO items "
            "(remote_id, author_name, description, item_type, published_at, "
            "first_seen_at, last_seen_at, metadata_digest) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(remote_id) DO UPDATE SET "
            "author_name=excluded.author_name, description=excluded.description, "
            "item_type=excluded.item_type, published_at=excluded.published_at, "
            "last_seen_at=excluded.last_seen_at, metadata_digest=excluded.metadata_digest",
            (
                remote_id,
                author_name,
                description,
                item_type,
                published_at,
                now,
                now,
                metadata_digest,
            ),
        )

    async def link_collection_item(self, collection_id: str, item_id: str) -> None:
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO collection_items "
            "(collection_id, item_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(collection_id, item_id) DO UPDATE SET "
            "last_seen_at=excluded.last_seen_at",
            (collection_id, item_id, now, now),
        )

    async def count_collection_items(self, collection_id: str) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS total FROM collection_items WHERE collection_id=?",
            (collection_id,),
        )
        return int(row["total"]) if row is not None else 0


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def enqueue_unique(
        self, kind: str, remote_id: str, payload: dict[str, Any]
    ) -> DownloadJob:
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO download_jobs "
            "(kind, remote_id, payload_json, status, attempts, next_attempt_at, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?) "
            "ON CONFLICT(kind, remote_id) DO UPDATE SET "
            "payload_json=excluded.payload_json, updated_at=excluded.updated_at "
            "RETURNING *",
            (kind, remote_id, json.dumps(payload, separators=(",", ":")), now, now, now),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("job enqueue did not return a row")
        return DownloadJob.from_row(row)

    async def claim_next(self, *, worker_id: str) -> DownloadJob | None:
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            candidate = await self.db.fetchone(
                "SELECT id FROM download_jobs "
                "WHERE status IN ('pending', 'retry') AND next_attempt_at <= ? "
                "ORDER BY next_attempt_at, id LIMIT 1",
                (now,),
            )
            if candidate is None:
                return None
            cursor = await self.db.execute(
                "UPDATE download_jobs SET status='running', attempts=attempts+1, "
                "claimed_by=?, claimed_at=?, updated_at=? WHERE id=? RETURNING *",
                (worker_id, now, now, candidate["id"]),
            )
            row = await cursor.fetchone()
        return DownloadJob.from_row(row) if row is not None else None

    async def complete(self, job_id: int) -> None:
        await self.db.execute(
            "UPDATE download_jobs SET status='completed', claimed_by=NULL, "
            "updated_at=? WHERE id=?",
            (int(time.time()), job_id),
        )

    async def fail(
        self, job_id: int, error_code: str, *, retry_after_seconds: int
    ) -> None:
        now = int(time.time())
        await self.db.execute(
            "UPDATE download_jobs SET status='retry', claimed_by=NULL, "
            "last_error_code=?, next_attempt_at=?, updated_at=? WHERE id=?",
            (error_code, now + retry_after_seconds, now, job_id),
        )

    async def get(self, job_id: int) -> DownloadJob | None:
        row = await self.db.fetchone("SELECT * FROM download_jobs WHERE id=?", (job_id,))
        return DownloadJob.from_row(row) if row is not None else None

    async def count(self) -> int:
        row = await self.db.fetchone("SELECT COUNT(*) AS total FROM download_jobs")
        return int(row["total"]) if row is not None else 0

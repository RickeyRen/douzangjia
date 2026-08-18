from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Protocol

from .provider.base import ProviderError, RemoteCollection
from .repositories import ArchiveRepository, JobRepository


class DiscoveryProvider(Protocol):
    async def list_collections(self) -> list[RemoteCollection]: ...

    def iter_collection_pages(self, remote_id: str, *, full_scan: bool): ...


@dataclass(frozen=True, slots=True)
class SyncResult:
    run_id: int
    status: str
    discovered: int
    enqueued: int
    error_code: str | None = None


class SyncService:
    def __init__(
        self,
        provider: DiscoveryProvider,
        archive: ArchiveRepository,
        jobs: JobRepository,
    ) -> None:
        self.provider = provider
        self.archive = archive
        self.jobs = jobs
        self.db = archive.db

    async def run(self, *, full_scan: bool) -> SyncResult:
        now = int(time.time())
        cursor = await self.db.execute(
            "INSERT INTO sync_runs (mode, phase, status, started_at) "
            "VALUES (?, 'discovering', 'running', ?) RETURNING id",
            ("full" if full_scan else "incremental", now),
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("sync run creation failed")
        run_id = int(row["id"])
        discovered = 0
        enqueued = 0
        try:
            collections = await self.provider.list_collections()
            for collection in collections:
                await self.archive.upsert_collection(collection.remote_id, collection.name)
                async for page in self.provider.iter_collection_pages(
                    collection.remote_id, full_scan=full_scan
                ):
                    await self.archive.save_discovery_page(collection.remote_id, page.items)
                    discovered += len(page.items)
                    for item in page.items:
                        existing = await self.jobs.get_by_key("download", item.remote_id)
                        await self.jobs.enqueue_unique(
                            "download", item.remote_id, asdict(item)
                        )
                        if existing is None:
                            enqueued += 1
                    await self.db.execute(
                        "UPDATE sync_runs SET discovered_count=?, enqueued_count=?, "
                        "cursor_json=? WHERE id=?",
                        (
                            discovered,
                            enqueued,
                            json.dumps(
                                {
                                    "collectionId": collection.remote_id,
                                    "cursor": page.next_cursor,
                                },
                                separators=(",", ":"),
                            ),
                            run_id,
                        ),
                    )
        except ProviderError as error:
            return await self._finish_failed(run_id, discovered, enqueued, error.code)
        except Exception:  # noqa: BLE001 - persistent task boundary records a stable code
            return await self._finish_failed(run_id, discovered, enqueued, "SYNC_FAILED")

        await self.db.execute(
            "UPDATE sync_runs SET phase='finished', status='completed', "
            "discovered_count=?, enqueued_count=?, finished_at=? WHERE id=?",
            (discovered, enqueued, int(time.time()), run_id),
        )
        return SyncResult(run_id, "completed", discovered, enqueued)

    async def _finish_failed(
        self, run_id: int, discovered: int, enqueued: int, error_code: str
    ) -> SyncResult:
        await self.db.execute(
            "UPDATE sync_runs SET phase='finished', status='failed', error_code=?, "
            "discovered_count=?, enqueued_count=?, finished_at=? WHERE id=?",
            (error_code, discovered, enqueued, int(time.time()), run_id),
        )
        return SyncResult(run_id, "failed", discovered, enqueued, error_code)

    async def run_incremental(self) -> SyncResult:
        return await self.run(full_scan=False)

    async def run_full(self) -> SyncResult:
        return await self.run(full_scan=True)

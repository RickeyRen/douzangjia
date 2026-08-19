from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Protocol

from .library_models import (
    CreatorRecord,
    LibrarySource,
    LibrarySourceKind,
    LibrarySyncStatus,
)
from .library_repository import LibraryRepository
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
        self.library = LibraryRepository(self.db)

    async def create_run(self, *, full_scan: bool, status: str = "running") -> int:
        now = int(time.time())
        row = await self.db.fetchone(
            "INSERT INTO sync_runs (mode, phase, status, started_at) "
            "VALUES (?, ?, ?, ?) RETURNING id",
            (
                "full" if full_scan else "incremental",
                "queued" if status == "queued" else "discovering",
                status,
                now,
            ),
        )
        if row is None:
            raise RuntimeError("sync run creation failed")
        return int(row["id"])

    async def run(self, *, full_scan: bool, run_id: int | None = None) -> SyncResult:
        if run_id is None:
            run_id = await self.create_run(full_scan=full_scan)
        else:
            await self.db.execute(
                "UPDATE sync_runs SET phase='discovering', status='running' WHERE id=?",
                (run_id,),
            )
        discovered = 0
        enqueued = 0
        try:
            collections = await self.provider.list_collections()
            for collection in collections:
                await self.archive.upsert_collection(collection.remote_id, collection.name)
                source_id = self.library.favorite_collection_source_id(
                    collection.remote_id
                )
                local_count = await self.archive.count_collection_items(
                    collection.remote_id
                )
                scan_all = full_scan or (
                    collection.item_count is not None
                    and local_count < collection.item_count
                )
                scan_started_at = int(time.time())
                source = LibrarySource(
                    id=source_id,
                    kind=LibrarySourceKind.FAVORITE_COLLECTION,
                    remote_id=collection.remote_id,
                    name=collection.name,
                    declared_count=collection.item_count,
                    sync_status=LibrarySyncStatus.RUNNING,
                    last_full_scan_at=scan_started_at if scan_all else None,
                    last_incremental_scan_at=(
                        None if scan_all else scan_started_at
                    ),
                )
                await self.library.upsert_source(source)
                page_index = 0
                last_cursor: str | None = None
                async for page in self.provider.iter_collection_pages(
                    collection.remote_id, full_scan=scan_all
                ):
                    for item in page.items:
                        if item.creator_id:
                            await self.library.upsert_creator(
                                CreatorRecord(
                                    remote_id=item.creator_id,
                                    nickname=item.author_name,
                                    unique_id=item.creator_unique_id,
                                    avatar_url=item.creator_avatar_url,
                                    follower_count=item.creator_follower_count,
                                    post_count=item.creator_post_count,
                                )
                            )
                    await self.archive.save_discovery_page(collection.remote_id, page.items)
                    discovered += len(page.items)
                    for item in page.items:
                        await self.library.link_source_item(
                            source_id,
                            item.remote_id,
                            (
                                f"{item.published_at:020d}"
                                if item.published_at is not None
                                else f"{int(time.time()):020d}"
                            ),
                        )
                        existing = await self.jobs.get_by_key("download", item.remote_id)
                        await self.jobs.enqueue_unique(
                            "download", item.remote_id, asdict(item)
                        )
                        if existing is None:
                            enqueued += 1
                    last_cursor = page.next_cursor
                    await self.library.save_checkpoint(
                        source_id,
                        cursor=page.next_cursor,
                        page_index=page_index,
                        discovered_count=discovered,
                        stop_reason=None if page.has_more else "remote_end",
                    )
                    page_index += 1
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
                integrity = await self.library.source_integrity(source_id)
                source_complete = bool(
                    integrity is not None
                    and (
                        collection.item_count is None
                        or integrity.discovered_count == collection.item_count
                    )
                )
                await self.library.upsert_source(
                    LibrarySource(
                        id=source.id,
                        kind=source.kind,
                        remote_id=source.remote_id,
                        name=source.name,
                        declared_count=source.declared_count,
                        sync_cursor=last_cursor,
                        sync_status=(
                            LibrarySyncStatus.COMPLETE
                            if source_complete
                            else LibrarySyncStatus.INCOMPLETE
                        ),
                        last_full_scan_at=source.last_full_scan_at,
                        last_incremental_scan_at=source.last_incremental_scan_at,
                        error_code=None if source_complete else "COUNT_MISMATCH",
                    )
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

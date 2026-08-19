from __future__ import annotations

from collections.abc import Iterable

from .archive_repository import ArchiveBatch, ArchiveBatchRepository
from .db import Database
from .repositories import JobRepository


class ArchiveTargetNotFound(LookupError):
    pass


class ArchivePayloadUnavailable(RuntimeError):
    pass


class ArchiveService:
    def __init__(
        self,
        database: Database,
        jobs: JobRepository,
        batches: ArchiveBatchRepository | None = None,
    ) -> None:
        self.db = database
        self.jobs = jobs
        self.batches = batches or ArchiveBatchRepository(database)

    async def archive_item(self, remote_id: str) -> ArchiveBatch:
        item = await self.db.fetchone("SELECT remote_id FROM items WHERE remote_id=?", (remote_id,))
        if item is None:
            raise ArchiveTargetNotFound(remote_id)
        return await self._archive_ids("item", remote_id, (remote_id,))

    async def archive_source(self, source_id: str) -> ArchiveBatch:
        source = await self.db.fetchone("SELECT id FROM library_sources WHERE id=?", (source_id,))
        if source is None:
            raise ArchiveTargetNotFound(source_id)
        rows = await self.db.fetchall(
            "SELECT item_id FROM source_items WHERE source_id=? "
            "ORDER BY remote_order DESC, item_id DESC",
            (source_id,),
        )
        return await self._archive_ids(
            "source", source_id, (str(row["item_id"]) for row in rows)
        )

    async def archive_creator(self, creator_id: str) -> ArchiveBatch:
        creator = await self.db.fetchone(
            "SELECT remote_id FROM creators WHERE remote_id=?", (creator_id,)
        )
        if creator is None:
            raise ArchiveTargetNotFound(creator_id)
        rows = await self.db.fetchall(
            "SELECT remote_id FROM items WHERE creator_id=? "
            "ORDER BY COALESCE(published_at, first_seen_at) DESC, remote_id DESC",
            (creator_id,),
        )
        return await self._archive_ids(
            "creator", creator_id, (str(row["remote_id"]) for row in rows)
        )

    async def _archive_ids(
        self, kind: str, target_id: str, item_ids: Iterable[str]
    ) -> ArchiveBatch:
        batch = await self.batches.create_batch(kind, target_id)
        for item_id in item_ids:
            job = await self.jobs.get_by_key("download", item_id)
            if job is None:
                ready = await self.db.fetchone(
                    "SELECT 1 FROM media_files WHERE item_id=? AND status='ready' LIMIT 1",
                    (item_id,),
                )
                if ready is None:
                    await self.batches.set_status(
                        batch.id, "failed", error_code="ITEM_PAYLOAD_UNAVAILABLE"
                    )
                    raise ArchivePayloadUnavailable(item_id)
                await self.batches.add_item(batch.id, item_id)
                continue
            if job.status == "failed":
                job = await self.jobs.enqueue_unique("download", item_id, job.payload)
            await self.db.execute(
                "UPDATE download_jobs SET batch_id=?, priority=MAX(priority, 100) "
                "WHERE id=?",
                (batch.id, job.id),
            )
            await self.batches.add_item(batch.id, item_id, job_id=job.id)
        refreshed = await self.batches.refresh_batch(batch.id)
        if refreshed is None:
            raise RuntimeError("archive batch disappeared during expansion")
        return refreshed

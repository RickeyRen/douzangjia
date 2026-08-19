from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from .archive_repository import ArchiveBatch, ArchiveBatchRepository
from .library_models import CreatorRecord
from .library_repository import LibraryRepository
from .repositories import ArchiveRepository, JobRepository


class CreatorDiscoveryProvider(Protocol):
    def iter_creator_pages(self, creator_id: str, *, full_scan: bool): ...


class CreatorSyncService:
    def __init__(
        self,
        provider: CreatorDiscoveryProvider,
        archive: ArchiveRepository,
        jobs: JobRepository,
        batches: ArchiveBatchRepository,
    ) -> None:
        self.provider = provider
        self.archive = archive
        self.jobs = jobs
        self.batches = batches
        self.library = LibraryRepository(archive.db)

    async def run(
        self,
        creator_id: str,
        batch_id: int,
        *,
        full_scan: bool,
        archive_new_items: bool,
    ) -> ArchiveBatch:
        await self.batches.set_status(batch_id, "discovering")
        try:
            async for page in self.provider.iter_creator_pages(
                creator_id, full_scan=full_scan
            ):
                for item in page.items:
                    if item.creator_id != creator_id:
                        continue
                    await self.library.upsert_creator(
                        CreatorRecord(
                            remote_id=creator_id,
                            nickname=item.author_name,
                            unique_id=item.creator_unique_id,
                            avatar_url=item.creator_avatar_url,
                            follower_count=item.creator_follower_count,
                            post_count=item.creator_post_count,
                        )
                    )
                    await self.archive.upsert_item(
                        remote_id=item.remote_id,
                        author_name=item.author_name,
                        description=item.description,
                        item_type=item.item_type,
                        published_at=item.published_at,
                        creator_id=creator_id,
                    )
                    job = await self.jobs.get_by_key("download", item.remote_id)
                    if archive_new_items and (
                        job is None or job.status == "failed"
                    ):
                        job = await self.jobs.enqueue_unique(
                            "download", item.remote_id, asdict(item)
                        )
                    if job is not None:
                        await self.archive.db.execute(
                            "UPDATE download_jobs SET batch_id=?, "
                            "priority=MAX(priority, 100) WHERE id=?",
                            (batch_id, job.id),
                        )
                    await self.batches.add_item(
                        batch_id,
                        item.remote_id,
                        job_id=job.id if job is not None else None,
                    )
        except Exception:
            await self.batches.set_status(
                batch_id, "failed", error_code="CREATOR_SYNC_FAILED"
            )
            raise
        batch = await self.batches.refresh_batch(batch_id)
        if batch is None:
            raise RuntimeError("creator archive batch disappeared")
        return batch

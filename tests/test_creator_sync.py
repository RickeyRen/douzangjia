from collections.abc import AsyncIterator
from pathlib import Path

from douyin_archive.archive_repository import ArchiveBatchRepository
from douyin_archive.creator_sync import CreatorSyncService
from douyin_archive.db import Database
from douyin_archive.models import MediaAsset, RemoteItem
from douyin_archive.provider.base import RemotePage
from douyin_archive.repositories import ArchiveRepository, JobRepository


def creator_item(remote_id: str) -> RemoteItem:
    return RemoteItem(
        remote_id=remote_id,
        author_name="旅行博主",
        description=f"作品 {remote_id}",
        item_type="video",
        assets=(
            MediaAsset(
                remote_id,
                0,
                "video",
                f"https://media.test/{remote_id}.mp4",
                "video/mp4",
            ),
        ),
        creator_id="creator-sec-uid",
        creator_unique_id="travel-author",
        creator_post_count=2,
    )


class CreatorProvider:
    async def iter_creator_pages(
        self, creator_id: str, *, full_scan: bool
    ) -> AsyncIterator[RemotePage]:
        assert creator_id == "creator-sec-uid"
        assert full_scan is True
        yield RemotePage(
            (creator_item("post-2"), creator_item("post-1")), None, False
        )


async def test_creator_sync_discovers_remote_posts_and_populates_archive_batch(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    try:
        archive = ArchiveRepository(database)
        jobs = JobRepository(database)
        batches = ArchiveBatchRepository(database)
        batch = await batches.create_batch("creator", "creator-sec-uid")

        result = await CreatorSyncService(
            CreatorProvider(), archive, jobs, batches
        ).run(
            "creator-sec-uid",
            batch.id,
            full_scan=True,
            archive_new_items=True,
        )

        assert result.status == "running"
        assert result.discovered_count == 2
        assert await jobs.count() == 2
        creator = await database.fetchone(
            "SELECT nickname, unique_id, post_count FROM creators "
            "WHERE remote_id='creator-sec-uid'"
        )
        assert creator is not None
        assert tuple(creator) == ("旅行博主", "travel-author", 2)
        queued = await database.fetchall(
            "SELECT remote_id, batch_id, priority FROM download_jobs ORDER BY remote_id"
        )
        assert [tuple(row) for row in queued] == [
            ("post-1", batch.id, 100),
            ("post-2", batch.id, 100),
        ]
    finally:
        await database.close()

import asyncio
from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.repositories import JobRepository


@pytest.fixture
async def job_repository(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    yield JobRepository(database)
    await database.close()


async def test_enqueue_unique_uses_kind_and_remote_id(job_repository: JobRepository) -> None:
    first = await job_repository.enqueue_unique("download", "734", {"url": "a"})
    second = await job_repository.enqueue_unique("download", "734", {"url": "b"})

    assert first.id == second.id
    assert await job_repository.count() == 1
    assert second.payload == {"url": "b"}


async def test_different_job_kinds_may_share_remote_id(job_repository: JobRepository) -> None:
    await job_repository.enqueue_unique("download", "734", {"asset": 1})
    await job_repository.enqueue_unique("project", "734", {"collection": "one"})
    assert await job_repository.count() == 2


async def test_concurrent_claimers_receive_different_jobs(
    job_repository: JobRepository,
) -> None:
    first = await job_repository.enqueue_unique("download", "734", {"asset": 1})
    second = await job_repository.enqueue_unique("download", "735", {"asset": 2})

    claimed = await asyncio.gather(
        job_repository.claim_next(worker_id="worker-a"),
        job_repository.claim_next(worker_id="worker-b"),
    )

    assert {job.id for job in claimed if job is not None} == {first.id, second.id}
    assert all(job is not None and job.status == "running" for job in claimed)
    assert all(job is not None and job.attempts == 1 for job in claimed)


async def test_completed_job_is_not_claimed_again(job_repository: JobRepository) -> None:
    queued = await job_repository.enqueue_unique("download", "734", {"asset": 1})
    claimed = await job_repository.claim_next(worker_id="worker-a")
    assert claimed is not None
    await job_repository.complete(claimed.id)

    assert await job_repository.claim_next(worker_id="worker-b") is None
    completed = await job_repository.get(queued.id)
    assert completed is not None
    assert completed.status == "completed"


async def test_new_discovery_requeues_a_completed_download(
    job_repository: JobRepository,
) -> None:
    queued = await job_repository.enqueue_unique("download", "734", {"url": "old"})
    claimed = await job_repository.claim_next(worker_id="worker-a")
    assert claimed is not None
    await job_repository.complete(claimed.id)

    refreshed = await job_repository.enqueue_unique("download", "734", {"url": "fresh"})
    reclaimed = await job_repository.claim_next(worker_id="worker-b")

    assert refreshed.id == queued.id
    assert reclaimed is not None
    assert reclaimed.payload == {"url": "fresh"}

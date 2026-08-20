import time
from pathlib import Path

import pytest

from douyin_archive.archive_repository import ArchiveBatchRepository
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.provider.base import RateLimited
from douyin_archive.repositories import JobRepository
from douyin_archive.scheduler import configure_scheduler
from douyin_archive.worker import Worker


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[tuple[object, str, dict]] = []

    def add_job(self, function, trigger: str, **kwargs) -> None:
        self.jobs.append((function, trigger, kwargs))


class FakeSyncService:
    async def run_incremental(self) -> None:
        pass

    async def run_full(self) -> None:
        pass

    async def run_creator_subscriptions(self) -> None:
        pass


class FakeTelemetry:
    async def sample(self) -> None:
        pass

    async def prune(self) -> None:
        pass


def test_scheduler_runs_every_five_minutes_without_overlap(
    tmp_path: Path, master_key: str
) -> None:
    scheduler = FakeScheduler()
    settings = Settings(archive_root=tmp_path, master_key=master_key)
    configure_scheduler(scheduler, FakeSyncService(), settings)

    interval = next(job for job in scheduler.jobs if job[2]["id"] == "incremental-sync")
    assert interval[1] == "interval"
    assert interval[2]["seconds"] == 300
    assert interval[2]["max_instances"] == 1
    assert interval[2]["coalesce"] is True
    creator_updates = next(
        job for job in scheduler.jobs if job[2]["id"] == "creator-subscriptions"
    )
    assert creator_updates[1] == "interval"
    assert creator_updates[2]["seconds"] == 300
    assert creator_updates[2]["max_instances"] == 1


def test_scheduler_samples_dashboard_metrics_without_blocking_sync(
    tmp_path: Path, master_key: str
) -> None:
    """Catches telemetry being collected only while the dashboard is open."""
    scheduler = FakeScheduler()
    settings = Settings(archive_root=tmp_path, master_key=master_key)

    configure_scheduler(
        scheduler, FakeSyncService(), settings, telemetry=FakeTelemetry()
    )

    sample = next(job for job in scheduler.jobs if job[2]["id"] == "telemetry-sample")
    prune = next(job for job in scheduler.jobs if job[2]["id"] == "telemetry-prune")
    assert sample[1] == "interval"
    assert sample[2]["seconds"] == 5
    assert sample[2]["max_instances"] == 1
    assert prune[1] == "cron"


@pytest.fixture
async def jobs(tmp_path: Path):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    repository = JobRepository(database)
    yield repository
    await database.close()


async def test_rate_limit_sets_provider_cooldown(jobs: JobRepository) -> None:
    queued = await jobs.enqueue_unique("download", "734", {"asset": 1})

    async def rate_limited_handler(_):
        raise RateLimited("cool down", retry_after=900)

    before = int(time.time())
    handled = await Worker(jobs, rate_limited_handler, worker_id="worker-a").run_once()
    updated = await jobs.get(queued.id)

    assert handled is True
    assert updated is not None
    assert updated.status == "retry"
    assert updated.last_error_code == "RATE_LIMITED"
    assert updated.next_attempt_at >= before + 900


async def test_worker_refreshes_linked_archive_batch_after_completion(
    jobs: JobRepository,
) -> None:
    now = int(time.time())
    await jobs.db.execute(
        "INSERT INTO items (remote_id, author_name, description, item_type, "
        "first_seen_at, last_seen_at) VALUES ('734', '作者', '作品', 'video', ?, ?)",
        (now, now),
    )
    queued = await jobs.enqueue_unique("download", "734", {"asset": 1})
    batches = ArchiveBatchRepository(jobs.db)
    batch = await batches.create_batch("item", "734")
    await jobs.db.execute(
        "UPDATE download_jobs SET batch_id=? WHERE id=?",
        (batch.id, queued.id),
    )
    await batches.add_item(batch.id, "734", job_id=queued.id)

    async def successful_handler(_):
        pass

    handled = await Worker(
        jobs, successful_handler, worker_id="worker-a"
    ).run_once()
    updated = await batches.get_batch(batch.id)

    assert handled is True
    assert updated is not None
    assert updated.status == "completed"
    assert updated.completed_count == 1
    assert updated.finished_at is not None


async def test_restart_recovers_stale_running_job(jobs: JobRepository) -> None:
    queued = await jobs.enqueue_unique("download", "734", {"asset": 1})
    claimed = await jobs.claim_next(worker_id="dead-worker")
    assert claimed is not None
    await jobs.db.execute(
        "UPDATE download_jobs SET claimed_at=? WHERE id=?",
        (int(time.time()) - 3600, claimed.id),
    )

    recovered = await jobs.recover_stale_running(older_than_seconds=300)
    updated = await jobs.get(queued.id)

    assert recovered == 1
    assert updated is not None
    assert updated.status == "retry"
    assert updated.last_error_code == "WORKER_RESTARTED"

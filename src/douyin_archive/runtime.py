from __future__ import annotations

import asyncio
import os
import socket
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Protocol

import httpx

from .account_health import AccountHealthService
from .archive_handler import ArchiveJobHandler
from .archive_repository import ArchiveBatch, ArchiveBatchRepository
from .auth_service import AuthService
from .browser_coordinator import BrowserCoordinator
from .config import Settings
from .creator_sync import CreatorSyncService
from .db import Database
from .downloader import MediaDownloader
from .provider.base import SessionExpired
from .provider.douyin import DouyinProvider, PlaywrightDouyinSource
from .repositories import ArchiveRepository, DownloadProgressRepository, JobRepository
from .scheduler import configure_scheduler
from .storage import CollectionProjector, ObjectStore
from .sync_service import SyncResult, SyncService
from .telemetry import TelemetrySampler
from .worker import Worker


class CookieLoader(Protocol):
    async def load_cookies(self) -> list[dict[str, object]] | None: ...


class _ExpiredProvider:
    async def list_collections(self):
        raise SessionExpired("Douyin login is required")

    async def iter_collection_pages(self, remote_id: str, *, full_scan: bool):
        if False:  # pragma: no cover - makes this an async iterator
            yield remote_id, full_scan


async def recover_interrupted_sync_runs(database: Database) -> int:
    now = int(time.time())
    cursor = await database.execute(
        "UPDATE sync_runs SET phase='finished', status='failed', "
        "error_code='SYNC_INTERRUPTED', finished_at=? "
        "WHERE status IN ('queued', 'running')",
        (now,),
    )
    return cursor.rowcount


class RuntimeSyncCoordinator:
    """Build a fresh browser source for each serialized discovery run."""

    def __init__(
        self,
        database: Database,
        archive: ArchiveRepository,
        jobs: JobRepository,
        auth: CookieLoader,
        browser_coordinator: BrowserCoordinator,
        *,
        source_factory: Callable[[], Any] | None = None,
        account_health: AccountHealthService | None = None,
    ) -> None:
        self.database = database
        self.archive = archive
        self.jobs = jobs
        self.auth = auth
        self.browser_coordinator = browser_coordinator
        self.source_factory = source_factory or (
            lambda: PlaywrightDouyinSource(browser_coordinator)
        )
        self.account_health = account_health or AccountHealthService(database)
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()

    async def trigger_sync(self, *, full_scan: bool) -> int:
        service = SyncService(_ExpiredProvider(), self.archive, self.jobs)
        run_id = await service.create_run(full_scan=full_scan, status="queued")
        task = asyncio.create_task(self._run(full_scan=full_scan, run_id=run_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run_id

    async def run_incremental(self) -> SyncResult:
        return await self._run(full_scan=False)

    async def run_full(self) -> SyncResult:
        return await self._run(full_scan=True)

    async def trigger_creator_archive(self, creator_id: str) -> ArchiveBatch:
        batches = ArchiveBatchRepository(self.database)
        batch = await batches.create_batch("creator", creator_id)
        await batches.set_status(batch.id, "discovering")
        task = asyncio.create_task(
            self._run_creator_archive(
                creator_id,
                batch.id,
                full_scan=True,
                archive_new_items=True,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        current = await batches.get_batch(batch.id)
        if current is None:
            raise RuntimeError("creator archive batch disappeared")
        return current

    async def _run_creator_archive(
        self,
        creator_id: str,
        batch_id: int,
        *,
        full_scan: bool,
        archive_new_items: bool,
    ) -> ArchiveBatch | None:
        async with self._lock:
            batches = ArchiveBatchRepository(self.database)
            source = None
            cookies = await self.auth.load_cookies()
            authenticated = await self.browser_coordinator.is_douyin_authenticated()
            if not authenticated and cookies:
                await self.browser_coordinator.add_cookies(cookies)
                authenticated = await self.browser_coordinator.is_douyin_authenticated()
            if not authenticated:
                await batches.set_status(
                    batch_id, "failed", error_code="DOUYIN_SESSION_EXPIRED"
                )
                return await batches.get_batch(batch_id)
            try:
                source = self.source_factory()
                known_ids = await self.archive.list_known_item_ids()
                provider = DouyinProvider(source, known_ids=known_ids)
                return await CreatorSyncService(
                    provider, self.archive, self.jobs, batches
                ).run(
                    creator_id,
                    batch_id,
                    full_scan=full_scan,
                    archive_new_items=archive_new_items,
                )
            finally:
                if source is not None:
                    await source.close()

    async def run_creator_subscriptions(self) -> int:
        batches = ArchiveBatchRepository(self.database)
        subscriptions = await batches.list_due_subscriptions()
        scanned = 0
        for subscription in subscriptions:
            batch = await batches.create_batch("creator", subscription.creator_id)
            try:
                await self._run_creator_archive(
                    subscription.creator_id,
                    batch.id,
                    full_scan=False,
                    archive_new_items=subscription.archive_new_items,
                )
            except Exception:  # noqa: BLE001 - scheduler boundary persists stable state
                await batches.finish_subscription_scan(
                    subscription.creator_id, error_code="CREATOR_SYNC_FAILED"
                )
            else:
                refreshed = await batches.get_batch(batch.id)
                await batches.finish_subscription_scan(
                    subscription.creator_id,
                    error_code=(
                        refreshed.error_code
                        if refreshed is not None and refreshed.status == "failed"
                        else None
                    ),
                )
            scanned += 1
        return scanned

    async def _run(
        self, *, full_scan: bool, run_id: int | None = None
    ) -> SyncResult:
        async with self._lock:
            await self.account_health.record_checking()
            cookies = await self.auth.load_cookies()
            source = None
            authenticated = await self.browser_coordinator.is_douyin_authenticated()
            if not authenticated and cookies:
                await self.browser_coordinator.add_cookies(cookies)
                authenticated = (
                    await self.browser_coordinator.is_douyin_authenticated()
                )
            if authenticated:
                source = self.source_factory()
                known_ids = await self.archive.list_known_item_ids()
                provider = DouyinProvider(source, known_ids=known_ids)
            else:
                await self.database.execute(
                    "UPDATE auth_sessions SET status='expired' WHERE provider='douyin'"
                )
                provider = _ExpiredProvider()
            try:
                result = await SyncService(provider, self.archive, self.jobs).run(
                    full_scan=full_scan, run_id=run_id
                )
                if result.error_code == SessionExpired.code:
                    await self.database.execute(
                        "UPDATE auth_sessions SET status='expired' "
                        "WHERE provider='douyin'"
                    )
                checked_at = int(time.time())
                if result.error_code is not None:
                    await self.account_health.record_failure(
                        result.error_code, checked_at=checked_at
                    )
                else:
                    await self.account_health.record_success(
                        await self.account_health.infer_self_profile(),
                        verified_at=checked_at,
                        sync_completed_at=checked_at,
                    )
                return result
            finally:
                if source is not None:
                    await source.close()

    async def wait_for_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks))

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class ArchiveRuntime:
    """Own the NAS scheduler, discovery browser and durable download workers."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        auth_service: AuthService,
        browser_coordinator: BrowserCoordinator,
    ) -> None:
        self.settings = settings
        self.database = database
        self.auth_service = auth_service
        self.browser_coordinator = browser_coordinator
        self.archive = ArchiveRepository(database)
        self.jobs = JobRepository(database)
        self.sync = RuntimeSyncCoordinator(
            database, self.archive, self.jobs, auth_service, browser_coordinator
        )
        self.http = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(60, connect=20),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/136.0 Safari/537.36"
                ),
                "Referer": "https://www.douyin.com/",
            },
        )
        self.store = ObjectStore(settings.archive_root)
        self.telemetry = TelemetrySampler(database, settings.archive_root)
        handler = ArchiveJobHandler(
            database,
            MediaDownloader(self.store, self.http),
            CollectionProjector(settings.archive_root),
            archive_root=settings.archive_root,
        )
        worker_prefix = f"{socket.gethostname()}-{os.getpid()}"
        self.workers = [
            Worker(self.jobs, handler, worker_id=f"{worker_prefix}-{index}")
            for index in range(2)
        ]
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._scheduler: Any = None

    async def start(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        await recover_interrupted_sync_runs(self.database)
        await self.jobs.recover_stale_running(older_than_seconds=0)
        await DownloadProgressRepository(self.database).backfill_parts(self.store)
        await self.browser_coordinator.start()
        self.auth_service.on_authenticated = self._initial_sync
        self._worker_tasks = [
            asyncio.create_task(worker.run_forever()) for worker in self.workers
        ]
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        configure_scheduler(
            self._scheduler,
            self.sync,
            self.settings,
            telemetry=self.telemetry,
        )
        self._scheduler.start()
        if await self.auth_service.load_cookies():
            await self.sync.trigger_sync(full_scan=False)

    async def stop(self) -> None:
        self.auth_service.on_authenticated = None
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        for task in self._worker_tasks:
            task.cancel()
        for task in self._worker_tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._worker_tasks.clear()
        await self.sync.close()
        await self.http.aclose()

    async def trigger_sync(self, *, full_scan: bool) -> int:
        return await self.sync.trigger_sync(full_scan=full_scan)

    async def trigger_creator_archive(self, creator_id: str) -> ArchiveBatch:
        return await self.sync.trigger_creator_archive(creator_id)

    async def _initial_sync(self) -> int:
        return await self.trigger_sync(full_scan=True)

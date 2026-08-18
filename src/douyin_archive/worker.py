from __future__ import annotations

import asyncio
import errno
from collections.abc import Awaitable, Callable

import httpx

from .models import DownloadJob
from .provider.base import RateLimited
from .repositories import JobRepository

JobHandler = Callable[[DownloadJob], Awaitable[None]]


class Worker:
    def __init__(
        self,
        jobs: JobRepository,
        handler: JobHandler,
        *,
        worker_id: str,
    ) -> None:
        self.jobs = jobs
        self.handler = handler
        self.worker_id = worker_id

    async def run_once(self) -> bool:
        job = await self.jobs.claim_next(worker_id=self.worker_id)
        if job is None:
            return False
        try:
            await self.handler(job)
        except RateLimited as error:
            await self.jobs.fail(job.id, error.code, retry_after_seconds=error.retry_after)
        except OSError as error:
            code = "STORAGE_FULL" if error.errno == errno.ENOSPC else "FILESYSTEM_ERROR"
            await self.jobs.fail(job.id, code, retry_after_seconds=900)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                await self.jobs.fail_terminal(job.id, "MEDIA_GONE")
            elif error.response.status_code == 429:
                await self.jobs.fail(job.id, "RATE_LIMITED", retry_after_seconds=900)
            else:
                await self.jobs.fail(
                    job.id,
                    "MEDIA_HTTP_ERROR",
                    retry_after_seconds=min(3600, 30 * 2**min(job.attempts, 6)),
                )
        except Exception:  # noqa: BLE001 - one bad job must not terminate the worker
            await self.jobs.fail(
                job.id,
                "DOWNLOAD_FAILED",
                retry_after_seconds=min(3600, 30 * 2**min(job.attempts, 6)),
            )
        else:
            await self.jobs.complete(job.id)
        return True

    async def run_forever(self, *, idle_seconds: float = 2.0) -> None:
        await self.jobs.recover_stale_running(older_than_seconds=300)
        while True:
            handled = await self.run_once()
            if not handled:
                await asyncio.sleep(idle_seconds)

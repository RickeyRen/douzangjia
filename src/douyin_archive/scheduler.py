from __future__ import annotations

from typing import Any

from .config import Settings


def configure_scheduler(scheduler: Any, sync_service: Any, settings: Settings) -> None:
    scheduler.add_job(
        sync_service.run_incremental,
        "interval",
        seconds=settings.sync_interval_seconds,
        id="incremental-sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        sync_service.run_incremental,
        "cron",
        hour=3,
        minute=20,
        id="daily-deep-sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        sync_service.run_full,
        "cron",
        day_of_week="sun",
        hour=4,
        minute=10,
        id="weekly-full-sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

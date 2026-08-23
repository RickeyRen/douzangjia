from __future__ import annotations

from typing import Any

from .config import Settings


def configure_scheduler(
    scheduler: Any,
    sync_service: Any,
    settings: Settings,
    *,
    telemetry: Any | None = None,
) -> None:
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
        sync_service.run_creator_subscriptions,
        "interval",
        seconds=settings.sync_interval_seconds,
        id="creator-subscriptions",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        sync_service.run_creator_identity_backfill,
        "interval",
        seconds=120,
        id="creator-identity-backfill",
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
    if telemetry is not None:
        scheduler.add_job(
            telemetry.sample,
            "interval",
            seconds=5,
            id="telemetry-sample",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        scheduler.add_job(
            telemetry.prune,
            "cron",
            hour=2,
            minute=40,
            id="telemetry-prune",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

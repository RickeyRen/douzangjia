from __future__ import annotations

import time
from typing import Any

from .account_health import AccountHealthService
from .db import Database

STALE_MINIMUM_SECONDS = 30 * 60
FAILING_AFTER_CONSECUTIVE = 2


async def sync_health_snapshot(
    database: Database,
    *,
    interval_seconds: int,
    coordinator: Any = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Summarize whether discovery is actually keeping up, for banners and alerts."""
    now = int(time.time()) if now is None else now
    interval = int(interval_seconds)
    account = await AccountHealthService(database).snapshot()
    latest = await database.fetchone(
        "SELECT status, error_code, started_at, finished_at FROM sync_runs "
        "ORDER BY id DESC LIMIT 1"
    )
    last_success = await database.fetchone(
        "SELECT MAX(finished_at) AS finished_at FROM sync_runs WHERE status='completed'"
    )
    recent = await database.fetchall(
        "SELECT status FROM sync_runs WHERE status IN ('completed', 'failed') "
        "ORDER BY id DESC LIMIT 20"
    )
    consecutive_failures = 0
    for row in recent:
        if row["status"] != "failed":
            break
        consecutive_failures += 1
    last_success_at = last_success["finished_at"] if last_success is not None else None
    browser = await coordinator.probe() if coordinator is not None else "not_started"

    stale_after = max(interval * 3, STALE_MINIMUM_SECONDS)
    error_code = latest["error_code"] if latest is not None else None
    if account.get("status") == "expired" or not account.get("sessionStored"):
        state = "login_required"
        error_code = account.get("errorCode") or "DOUYIN_SESSION_EXPIRED"
    elif browser in {"disconnected", "unresponsive"}:
        state = "failing"
        error_code = "BROWSER_DISCONNECTED"
    elif latest is not None and latest["status"] in {"running", "queued"}:
        state = "syncing"
    elif last_success_at is None:
        state = "never"
    elif consecutive_failures >= FAILING_AFTER_CONSECUTIVE:
        state = "failing"
    elif now - int(last_success_at) > stale_after:
        # Catches the scheduler dying before it can even record a failed run.
        state = "stale"
        error_code = error_code or "SYNC_STALLED"
    else:
        state = "ok"
        error_code = None
    return {
        "state": state,
        "lastSuccessAt": last_success_at,
        "lastAttemptAt": latest["started_at"] if latest is not None else None,
        "lastErrorCode": error_code,
        "consecutiveFailures": consecutive_failures,
        "intervalSeconds": interval,
        "staleAfterSeconds": stale_after,
        "browser": browser,
    }

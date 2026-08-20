from __future__ import annotations

import time
from typing import Any

from .db import Database

_EVIDENCE_STATUSES = {
    "OK": "available",
    "ITEM_NOT_FOUND": "deleted",
    "ITEM_PRIVATE": "private",
    "ITEM_RESTRICTED": "restricted",
    "DOUYIN_SESSION_EXPIRED": "auth_required",
    "DOUYIN_VERIFICATION_REQUIRED": "rate_limited",
    "RATE_LIMITED": "rate_limited",
}


def status_for_evidence(evidence_code: str) -> str:
    return _EVIDENCE_STATUSES.get(evidence_code, "unknown")


def evidence_for_probe_response(
    *, http_status: int, status_code: int | None, has_item: bool
) -> str:
    if http_status == 429:
        return "RATE_LIMITED"
    if http_status in {401, 403} or status_code in {8, 1009}:
        return "DOUYIN_SESSION_EXPIRED"
    if http_status == 404:
        return "ITEM_NOT_FOUND"
    if http_status != 200:
        return "NETWORK_TIMEOUT"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code not in {None, 0}:
        return "DOUYIN_RESPONSE_CHANGED"
    return "OK" if has_item else "ITEM_NOT_FOUND"


class RemoteAvailabilityService:
    def __init__(self, database: Database) -> None:
        self.db = database

    async def record(
        self, item_id: str, evidence_code: str, *, checked_at: int | None = None
    ) -> dict[str, Any]:
        now = checked_at if checked_at is not None else int(time.time())
        status = status_for_evidence(evidence_code)
        existing = await self.db.fetchone("SELECT * FROM remote_checks WHERE item_id=?", (item_id,))
        previous_status = str(existing["status"]) if existing is not None else None
        consecutive = (
            int(existing["consecutive_matches"]) + 1
            if existing is not None and previous_status == status
            else 1
        )
        last_available = (
            now
            if status == "available"
            else int(existing["last_available_at"])
            if existing is not None and existing["last_available_at"] is not None
            else None
        )
        await self.db.execute(
            "INSERT INTO remote_checks "
            "(item_id, status, checked_at, evidence_code, consecutive_matches, "
            "last_available_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET status=excluded.status, "
            "checked_at=excluded.checked_at, evidence_code=excluded.evidence_code, "
            "consecutive_matches=excluded.consecutive_matches, "
            "last_available_at=excluded.last_available_at, updated_at=excluded.updated_at",
            (item_id, status, now, evidence_code, consecutive, last_available, now),
        )
        return {
            "status": status,
            "checkedAt": now,
            "evidenceCode": evidence_code,
            "lastAvailableAt": last_available,
        }

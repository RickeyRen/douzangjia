from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.repositories import ArchiveRepository


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ("OK", "available"),
        ("ITEM_NOT_FOUND", "deleted"),
        ("ITEM_PRIVATE", "private"),
        ("ITEM_RESTRICTED", "restricted"),
        ("DOUYIN_SESSION_EXPIRED", "auth_required"),
        ("DOUYIN_VERIFICATION_REQUIRED", "rate_limited"),
        ("RATE_LIMITED", "rate_limited"),
        ("NETWORK_TIMEOUT", "unknown"),
        ("DOUYIN_RESPONSE_CHANGED", "unknown"),
    ],
)
def test_remote_evidence_does_not_turn_transient_failures_into_deletion(
    evidence: str, expected: str
) -> None:
    """Catches network, auth, or risk-control failures being labeled deleted."""
    module = importlib.import_module("douyin_archive.remote_availability")

    assert module.status_for_evidence(evidence) == expected


@pytest.mark.parametrize(
    ("http_status", "status_code", "has_item", "expected"),
    [
        (200, 0, True, "OK"),
        (200, 0, False, "ITEM_NOT_FOUND"),
        (404, None, False, "ITEM_NOT_FOUND"),
        (401, None, False, "DOUYIN_SESSION_EXPIRED"),
        (429, None, False, "RATE_LIMITED"),
        (503, None, False, "NETWORK_TIMEOUT"),
    ],
)
def test_probe_response_requires_explicit_evidence(
    http_status: int, status_code: int | None, has_item: bool, expected: str
) -> None:
    module = importlib.import_module("douyin_archive.remote_availability")

    assert (
        module.evidence_for_probe_response(
            http_status=http_status,
            status_code=status_code,
            has_item=has_item,
        )
        == expected
    )


async def test_remote_check_preserves_last_known_available_time(tmp_path: Path) -> None:
    """Catches later uncertainty erasing the last positive remote observation."""
    module = importlib.import_module("douyin_archive.remote_availability")
    database = await Database(tmp_path / "archive.sqlite3").open()
    try:
        archive = ArchiveRepository(database)
        await archive.upsert_item(
            remote_id="734",
            author_name="作者",
            description="作品",
            item_type="video",
        )
        service = module.RemoteAvailabilityService(database)
        await service.record("734", "OK", checked_at=100)

        uncertain = await service.record("734", "NETWORK_TIMEOUT", checked_at=200)
    finally:
        await database.close()

    assert uncertain["status"] == "unknown"
    assert uncertain["lastAvailableAt"] == 100
    assert uncertain["evidenceCode"] == "NETWORK_TIMEOUT"


async def test_explicit_not_found_is_persisted_as_deleted(tmp_path: Path) -> None:
    """Catches explicit deletion evidence remaining an ambiguous unknown state."""
    module = importlib.import_module("douyin_archive.remote_availability")
    database = await Database(tmp_path / "archive.sqlite3").open()
    try:
        archive = ArchiveRepository(database)
        await archive.upsert_item(
            remote_id="734",
            author_name="作者",
            description="作品",
            item_type="video",
        )
        result = await module.RemoteAvailabilityService(database).record(
            "734", "ITEM_NOT_FOUND", checked_at=300
        )
    finally:
        await database.close()

    assert result["status"] == "deleted"
    assert result["checkedAt"] == 300

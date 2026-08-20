from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.library_models import CreatorRecord
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.repositories import ArchiveRepository


@pytest.fixture
async def health_components(tmp_path: Path):
    database = await Database(tmp_path / "archive.sqlite3").open()
    module = importlib.import_module("douyin_archive.account_health")
    service = module.AccountHealthService(database)
    yield database, module, service
    await database.close()


async def test_saved_cookie_without_real_verification_is_not_healthy(
    health_components,
) -> None:
    """Catches the dashboard claiming health from cookie presence alone."""
    database, _module, service = health_components
    await database.execute(
        "INSERT INTO auth_sessions "
        "(provider, encrypted_cookies, status, updated_at) "
        "VALUES ('douyin', X'00', 'authenticated', 1)"
    )

    snapshot = await service.snapshot()

    assert snapshot["sessionStored"] is True
    assert snapshot["status"] == "unknown"
    assert snapshot["lastVerifiedAt"] is None


async def test_real_verification_persists_identity_and_marks_healthy(
    health_components,
) -> None:
    """Catches a successful probe that still leaves the username unavailable."""
    _database, module, service = health_components
    profile = module.DouyinAccountProfile(
        remote_id="self-sec-uid",
        nickname="天鹰座裂缝之外",
        unique_id="douyin-user",
        avatar_url="https://media.test/avatar.jpg",
    )

    await service.record_success(profile, verified_at=100, sync_completed_at=101)
    snapshot = await service.snapshot()

    assert snapshot == {
        "sessionStored": False,
        "status": "healthy",
        "lastVerifiedAt": 100,
        "lastSyncAt": 101,
        "lastFailureAt": None,
        "errorCode": None,
        "consecutiveFailures": 0,
        "account": {
            "id": "self-sec-uid",
            "nickname": "天鹰座裂缝之外",
            "uniqueId": "douyin-user",
            "avatarUrl": "https://media.test/avatar.jpg",
        },
    }


async def test_profile_rename_updates_name_without_changing_identity(
    health_components,
) -> None:
    """Catches nickname changes creating a second logged-in account row."""
    database, module, service = health_components
    await service.record_success(
        module.DouyinAccountProfile("stable-id", "旧名字"), verified_at=100
    )

    await service.record_success(
        module.DouyinAccountProfile("stable-id", "新名字"), verified_at=200
    )

    rows = await database.fetchall("SELECT remote_id, nickname FROM douyin_account")
    assert [(row["remote_id"], row["nickname"]) for row in rows] == [
        ("stable-id", "新名字")
    ]


@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        ("DOUYIN_SESSION_EXPIRED", "expired"),
        ("DOUYIN_VERIFICATION_REQUIRED", "degraded"),
        ("DOUYIN_RATE_LIMITED", "degraded"),
        ("DOUYIN_NETWORK_ERROR", "degraded"),
    ],
)
async def test_health_failures_keep_distinct_evidence(
    health_components, error_code: str, expected_status: str
) -> None:
    """Catches authentication, risk control, and network failures collapsing together."""
    _database, module, service = health_components
    await service.record_success(
        module.DouyinAccountProfile("stable-id", "用户名"), verified_at=100
    )

    await service.record_failure(error_code, checked_at=200)
    snapshot = await service.snapshot()

    assert snapshot["status"] == expected_status
    assert snapshot["errorCode"] == error_code
    assert snapshot["lastFailureAt"] == 200


async def test_self_profile_is_inferred_from_the_logged_in_posts_source(
    health_components,
) -> None:
    """Catches the known self identity remaining hidden when profile API is sparse."""
    database, _module, service = health_components
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    await library.ensure_account_sources()
    await library.upsert_creator(
        CreatorRecord(
            remote_id="self-sec-uid",
            nickname="天鹰座裂缝之外",
            avatar_url="https://media.test/avatar.jpg",
        )
    )
    await archive.upsert_item(
        remote_id="self-post",
        author_name="天鹰座裂缝之外",
        description="自己的作品",
        item_type="video",
        creator_id="self-sec-uid",
    )
    await library.link_source_item("account:posts", "self-post", "1")

    profile = await service.infer_self_profile()

    assert profile is not None
    assert profile.remote_id == "self-sec-uid"
    assert profile.nickname == "天鹰座裂缝之外"

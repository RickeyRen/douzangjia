from collections.abc import AsyncIterator
from pathlib import Path

from douyin_archive.archive_repository import ArchiveBatchRepository
from douyin_archive.db import Database
from douyin_archive.repositories import ArchiveRepository, JobRepository
from douyin_archive.runtime import RuntimeSyncCoordinator, recover_interrupted_sync_runs


class FakeAuth:
    async def load_cookies(self) -> list[dict[str, object]]:
        return [{"name": "sessionid", "value": "encrypted-before-use"}]


class FakeSource:
    closed = False

    async def fetch_collections(self) -> dict:
        return {"collections": [{"id": "1001", "name": "想去的地方"}]}

    async def iter_raw_pages(self, remote_id: str) -> AsyncIterator[dict]:
        assert remote_id == "1001"
        yield {
            "items": [
                {
                    "aweme_id": "734",
                    "desc": "海边日落",
                    "author": {"nickname": "旅行家"},
                    "video": {"play_addr": {"url_list": ["https://media.test/734"]}},
                }
            ],
            "has_more": False,
        }

    async def close(self) -> None:
        self.closed = True

    async def fetch_creator_profile(self, creator_id: str):
        from douyin_archive.library_models import CreatorRecord

        return CreatorRecord(
            remote_id=creator_id,
            nickname="旅行博主",
            unique_id="travel-account",
        )

    async def iter_creator_raw_pages(
        self,
        creator_id: str,
        *,
        known_ids: set[str],
        full_scan: bool,
    ) -> AsyncIterator[dict]:
        assert creator_id == "creator-sec-uid"
        assert isinstance(full_scan, bool)
        yield {
            "aweme_list": [
                {
                    "aweme_id": "creator-post-1",
                    "desc": "远程博主作品",
                    "author": {
                        "sec_uid": creator_id,
                        "nickname": "旅行博主",
                    },
                    "video": {
                        "play_addr": {
                            "url_list": ["https://media.test/creator-post-1.mp4"]
                        }
                    },
                }
            ],
            "has_more": False,
        }


class FakeBrowserCoordinator:
    def __init__(self, *, authenticated: bool | list[bool] = True) -> None:
        self.authentication_results = (
            list(authenticated) if isinstance(authenticated, list) else [authenticated]
        )
        self.added_cookies: list[dict[str, object]] = []
        self.authentication_checks = 0

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.added_cookies.extend(cookies)

    async def is_douyin_authenticated(self) -> bool:
        self.authentication_checks += 1
        if len(self.authentication_results) > 1:
            return self.authentication_results.pop(0)
        return self.authentication_results[0]


async def test_trigger_sync_returns_run_id_and_finishes_in_background(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    source = FakeSource()
    browser_coordinator = FakeBrowserCoordinator()
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        browser_coordinator,
        source_factory=lambda: source,
    )

    run_id = await coordinator.trigger_sync(full_scan=True)
    queued = await database.fetchone("SELECT status FROM sync_runs WHERE id=?", (run_id,))
    assert queued is not None
    assert queued["status"] in {"queued", "running", "completed"}

    await coordinator.wait_for_idle()
    finished = await database.fetchone("SELECT status FROM sync_runs WHERE id=?", (run_id,))
    assert finished is not None
    assert finished["status"] == "completed"
    assert await JobRepository(database).count() == 1
    assert source.closed is True
    assert browser_coordinator.added_cookies == []
    assert browser_coordinator.authentication_checks == 1
    await coordinator.close()
    await database.close()


async def test_trigger_creator_archive_discovers_remote_posts_in_background(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    source = FakeSource()
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        FakeBrowserCoordinator(),
        source_factory=lambda: source,
    )

    batch = await coordinator.trigger_creator_archive("creator-sec-uid")
    assert batch.status in {"queued", "discovering"}

    await coordinator.wait_for_idle()

    finished = await database.fetchone(
        "SELECT status, discovered_count FROM archive_batches WHERE id=?",
        (batch.id,),
    )
    assert finished is not None
    assert tuple(finished) == ("running", 1)
    assert await JobRepository(database).count() == 1
    assert source.closed is True
    await coordinator.close()
    await database.close()


async def test_due_creator_subscriptions_archive_new_remote_posts(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, first_seen_at, last_seen_at) "
        "VALUES ('creator-sec-uid', '旅行博主', 1, 1)"
    )
    subscriptions = ArchiveBatchRepository(database)
    await subscriptions.upsert_subscription(
        "creator-sec-uid",
        enabled=True,
        scan_interval_seconds=3600,
        archive_new_items=True,
    )
    await database.execute(
        "UPDATE creator_subscriptions SET next_scan_at=0 "
        "WHERE creator_id='creator-sec-uid'"
    )
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        FakeBrowserCoordinator(),
        source_factory=FakeSource,
    )

    scanned = await coordinator.run_creator_subscriptions()

    assert scanned == 1
    subscription = await subscriptions.get_subscription("creator-sec-uid")
    assert subscription is not None
    assert subscription.last_scan_at is not None
    assert subscription.next_scan_at is not None
    assert subscription.next_scan_at >= subscription.last_scan_at + 3600
    assert subscription.last_error_code is None
    assert await JobRepository(database).count() == 1
    await coordinator.close()
    await database.close()


async def test_creator_identity_backfill_updates_one_missing_creator(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, first_seen_at, last_seen_at) "
        "VALUES ('creator-sec-uid', '旅行博主', 1, 1)"
    )
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        FakeBrowserCoordinator(),
        source_factory=FakeSource,
    )

    updated = await coordinator.run_creator_identity_backfill()
    creator = await database.fetchone(
        "SELECT unique_id FROM creators WHERE remote_id='creator-sec-uid'"
    )
    attempt = await database.fetchone(
        "SELECT error_code FROM creator_identity_refresh "
        "WHERE creator_id='creator-sec-uid'"
    )

    assert updated is True
    assert creator is not None and creator["unique_id"] == "travel-account"
    assert attempt is not None and attempt["error_code"] is None
    await coordinator.close()
    await database.close()


async def test_stale_browser_session_is_marked_expired_without_opening_source(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO auth_sessions "
        "(provider, encrypted_cookies, status, last_verified_at, updated_at) "
        "VALUES ('douyin', ?, 'authenticated', 1, 1)",
        (b"encrypted",),
    )
    source_created = False

    def source_factory() -> FakeSource:
        nonlocal source_created
        source_created = True
        return FakeSource()

    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        FakeBrowserCoordinator(authenticated=False),
        source_factory=source_factory,
    )

    result = await coordinator.run_incremental()
    row = await database.fetchone(
        "SELECT status FROM auth_sessions WHERE provider='douyin'"
    )

    assert result.status == "failed"
    assert row is not None
    assert row["status"] == "expired"
    assert source_created is False
    assert coordinator.browser_coordinator.authentication_checks == 2
    assert coordinator.browser_coordinator.added_cookies == [
        {"name": "sessionid", "value": "encrypted-before-use"}
    ]
    await coordinator.close()
    await database.close()


async def test_cookie_backup_is_only_injected_when_profile_needs_recovery(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    browser_coordinator = FakeBrowserCoordinator(authenticated=[False, True])
    source = FakeSource()
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        browser_coordinator,
        source_factory=lambda: source,
    )

    result = await coordinator.run_incremental()
    health = await database.fetchone(
        "SELECT health_status, last_verified_at, last_sync_at "
        "FROM douyin_account WHERE provider='douyin'"
    )

    assert result.status == "completed"
    assert health is not None
    assert health["health_status"] == "healthy"
    assert health["last_verified_at"] is not None
    assert health["last_sync_at"] is not None
    assert browser_coordinator.authentication_checks == 2
    assert browser_coordinator.added_cookies == [
        {"name": "sessionid", "value": "encrypted-before-use"}
    ]
    await coordinator.close()
    await database.close()


async def test_provider_expiry_marks_saved_session_expired(tmp_path: Path) -> None:
    from douyin_archive.provider.base import SessionExpired

    class ExpiredSource(FakeSource):
        async def fetch_collections(self) -> dict:
            raise SessionExpired("expired")

    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO auth_sessions "
        "(provider, encrypted_cookies, status, last_verified_at, updated_at) "
        "VALUES ('douyin', ?, 'authenticated', 1, 1)",
        (b"encrypted",),
    )
    coordinator = RuntimeSyncCoordinator(
        database,
        ArchiveRepository(database),
        JobRepository(database),
        FakeAuth(),
        FakeBrowserCoordinator(authenticated=True),
        source_factory=ExpiredSource,
    )

    result = await coordinator.run_incremental()
    row = await database.fetchone(
        "SELECT status FROM auth_sessions WHERE provider='douyin'"
    )

    assert result.error_code == "DOUYIN_SESSION_EXPIRED"
    assert row is not None and row["status"] == "expired"
    await coordinator.close()
    await database.close()


async def test_startup_marks_previous_sync_runs_interrupted(tmp_path: Path) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO sync_runs (mode, phase, status, started_at) "
        "VALUES ('full', 'discovering', 'running', 1)"
    )

    recovered = await recover_interrupted_sync_runs(database)
    row = await database.fetchone("SELECT status, error_code FROM sync_runs")

    assert recovered == 1
    assert row is not None
    assert (row["status"], row["error_code"]) == ("failed", "SYNC_INTERRUPTED")
    await database.close()

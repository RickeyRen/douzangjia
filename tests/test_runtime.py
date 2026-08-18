from collections.abc import AsyncIterator
from pathlib import Path

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


class FakeBrowserCoordinator:
    def __init__(self, *, authenticated: bool = True) -> None:
        self.authenticated = authenticated
        self.added_cookies: list[dict[str, object]] = []
        self.authentication_checks = 0

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.added_cookies.extend(cookies)

    async def is_douyin_authenticated(self) -> bool:
        self.authentication_checks += 1
        return self.authenticated


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
    assert browser_coordinator.added_cookies == [
        {"name": "sessionid", "value": "encrypted-before-use"}
    ]
    assert browser_coordinator.authentication_checks == 1
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

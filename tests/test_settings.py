import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.runtime import resize_workers
from douyin_archive.scheduler import reschedule_sync
from douyin_archive.settings_store import RuntimeSettings, SettingsStore


async def store_for(root: Path) -> tuple[Database, SettingsStore]:
    database = await Database(root / "archive.sqlite3").open()
    return database, SettingsStore(database, defaults=RuntimeSettings(sync_interval_seconds=600))


def test_store_merges_env_defaults_with_persisted_overrides(tmp_path: Path) -> None:
    async def scenario() -> tuple[RuntimeSettings, RuntimeSettings, set[str], RuntimeSettings]:
        database, store = await store_for(tmp_path)
        try:
            initial = await store.load()
            updated = await store.update({"download_workers": 4})
            overrides = await store.overrides()
            after_reset = await store.reset("download_workers")
            return initial, updated, overrides, after_reset
        finally:
            await database.close()

    initial, updated, overrides, after_reset = asyncio.run(scenario())
    assert initial.sync_interval_seconds == 600 and initial.download_workers == 2
    assert updated.download_workers == 4 and updated.sync_interval_seconds == 600
    assert overrides == {"download_workers"}
    assert after_reset.download_workers == 2


def test_store_rejects_out_of_range_values_and_survives_bad_rows(tmp_path: Path) -> None:
    async def scenario() -> RuntimeSettings:
        database, store = await store_for(tmp_path)
        try:
            with pytest.raises(ValueError):
                await store.update({"download_workers": 99})
            await database.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES ('download_workers', '\"many\"', 1)"
            )
            return await store.load()
        finally:
            await database.close()

    assert asyncio.run(scenario()).download_workers == 2


class FakeRuntime:
    def __init__(self) -> None:
        self.applied: list[RuntimeSettings] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def apply_settings(self, values: RuntimeSettings) -> None:
        self.applied.append(values)


def test_settings_api_validates_and_applies_live(tmp_path: Path, master_key: str) -> None:
    runtime = FakeRuntime()
    app = create_app(
        Settings(archive_root=tmp_path, master_key=master_key, sync_interval_seconds=900),
        runtime_factory=lambda *_args: runtime,
    )
    with TestClient(app) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        csrf = {"X-CSRF-Token": client.cookies["archive_csrf"]}
        before = client.get("/api/settings").json()
        changed = client.put("/api/settings", json={"sync_interval_seconds": 120}, headers=csrf)
        too_small = client.put("/api/settings", json={"sync_interval_seconds": 5}, headers=csrf)
        unknown = client.put("/api/settings", json={"theme": "dark"}, headers=csrf)
        health = client.get("/api/health/sync").json()

    assert before["values"]["sync_interval_seconds"] == 900 and before["overridden"] == []
    assert changed.status_code == 200
    assert changed.json()["values"]["sync_interval_seconds"] == 120
    assert changed.json()["overridden"] == ["sync_interval_seconds"]
    assert too_small.status_code == 400 and too_small.json()["code"] == "INVALID_SETTINGS"
    assert unknown.status_code == 400 and unknown.json()["code"] == "UNKNOWN_SETTING"
    assert [values.sync_interval_seconds for values in runtime.applied] == [120]
    assert health["intervalSeconds"] == 120


def test_worker_pool_resizes_in_place() -> None:
    async def scenario() -> tuple[list[str], int, int]:
        started: list[str] = []

        class FakeWorker:
            def __init__(self, index: int) -> None:
                self.worker_id = f"w-{index}"

            async def run_forever(self) -> None:
                started.append(self.worker_id)
                await asyncio.Event().wait()

        workers: list[FakeWorker] = []
        tasks: list[asyncio.Task[None]] = []
        resize_workers(workers, tasks, FakeWorker, 3)
        await asyncio.sleep(0)
        resize_workers(workers, tasks, FakeWorker, 1)
        await asyncio.sleep(0)
        return started, len(workers), len(tasks)

    started, remaining, task_count = asyncio.run(scenario())
    assert task_count == 1
    assert started == ["w-0", "w-1", "w-2"]
    assert remaining == 1


def test_reschedule_touches_both_sync_jobs() -> None:
    class FakeScheduler:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def reschedule_job(self, job_id: str, *, trigger: str, seconds: int) -> None:
            assert trigger == "interval"
            self.calls.append((job_id, seconds))

    scheduler = FakeScheduler()
    reschedule_sync(scheduler, 120)
    assert scheduler.calls == [("incremental-sync", 120), ("creator-subscriptions", 120)]

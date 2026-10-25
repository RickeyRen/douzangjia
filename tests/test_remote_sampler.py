import asyncio
from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.remote_sampler import RECHECK_AFTER_SECONDS, RemoteCheckSampler

NOW = 2_000_000_000


async def seed(root: Path) -> Database:
    database = await Database(root / "archive.sqlite3").open()
    for index in range(1, 7):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
            "VALUES (?, 'a', '', 'video', ?, ?)",
            (f"70{index}", index, index),
        )
    # 701 checked recently, 702 checked long ago, the rest never.
    await database.execute(
        "INSERT INTO remote_checks (item_id, status, checked_at, updated_at) VALUES ('701', 'available', ?, ?)",
        (NOW - 3600, NOW - 3600),
    )
    await database.execute(
        "INSERT INTO remote_checks (item_id, status, checked_at, updated_at) VALUES ('702', 'available', ?, ?)",
        (NOW - RECHECK_AFTER_SECONDS - 10, NOW),
    )
    return database


def test_budget_scales_with_daily_quota() -> None:
    async def noop(_: str) -> str:
        return "OK"

    assert RemoteCheckSampler(None, noop, per_day=0).budget() == 0  # type: ignore[arg-type]
    assert RemoteCheckSampler(None, noop, per_day=200).budget() == 4  # type: ignore[arg-type]
    assert RemoteCheckSampler(None, noop, per_day=10).budget() == 1  # type: ignore[arg-type]


def test_sampler_prefers_unchecked_items_then_the_stalest(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[str], int, dict[str, str]]:
        database = await seed(tmp_path)
        probed: list[str] = []

        async def checker(remote_id: str) -> str:
            probed.append(remote_id)
            return "ITEM_NOT_FOUND" if remote_id == "706" else "OK"

        sampler = RemoteCheckSampler(database, checker, per_day=200)
        try:
            checked = await sampler.run_batch(now=NOW)
            rows = await database.fetchall("SELECT item_id, status FROM remote_checks")
            return probed, checked, {str(r["item_id"]): str(r["status"]) for r in rows}
        finally:
            await database.close()

    probed, checked, statuses = asyncio.run(scenario())
    # Four per run: the never-checked newest first (706..703), 702 is stale but comes after them.
    assert probed == ["706", "705", "704", "703"]
    assert checked == 4
    assert statuses["706"] == "deleted" and statuses["705"] == "available"
    assert "701" in statuses  # untouched, checked an hour ago


def test_sampler_stops_when_douyin_pushes_back_and_tolerates_probe_errors(tmp_path: Path) -> None:
    async def scenario() -> list[str]:
        database = await seed(tmp_path)
        probed: list[str] = []

        async def checker(remote_id: str) -> str:
            probed.append(remote_id)
            if remote_id == "706":
                raise RuntimeError("browser hiccup")
            return "RATE_LIMITED" if remote_id == "705" else "OK"

        try:
            await RemoteCheckSampler(database, checker, per_day=200).run_batch(now=NOW)
        finally:
            await database.close()
        return probed

    assert asyncio.run(scenario()) == ["706", "705"]


def test_zero_quota_disables_sampling(tmp_path: Path) -> None:
    async def scenario() -> int:
        database = await seed(tmp_path)

        async def checker(_: str) -> str:
            raise AssertionError("must not probe")

        try:
            return await RemoteCheckSampler(database, checker, per_day=0).run_batch(now=NOW)
        finally:
            await database.close()

    assert asyncio.run(scenario()) == 0

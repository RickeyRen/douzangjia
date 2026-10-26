import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from douyin_archive.db import Database
from douyin_archive.notifier import (
    REMIND_AFTER_SECONDS,
    Notification,
    NotificationWatcher,
    Notifier,
)

NOW = 2_000_000_000
GB = 1024**3


def roomy_disk(_: Path):
    """CI runners are nearly full; tests about sync must not see a disk alert."""
    return SimpleNamespace(total=1000 * GB, used=100 * GB, free=900 * GB)


def cramped_disk(_: Path):
    return SimpleNamespace(total=1000 * GB, used=996 * GB, free=4 * GB)


class Recorder:
    def __init__(self, *, fail_channel: str | None = None) -> None:
        self.requests: list[tuple[str, dict]] = []
        self.fail_channel = fail_channel

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append((str(request.url), json.loads(request.content)))
            if self.fail_channel and self.fail_channel in str(request.url):
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={"ok": True})

        return httpx.MockTransport(handle)


CONFIG = {
    "bark": {"url": "https://api.day.app/deviceKEY/"},
    "telegram": {"bot_token": "123:abc", "chat_id": "42"},
    "webhook": {"url": "https://hooks.example.test/douzangjia"},
}


def test_notifier_delivers_to_every_channel_and_isolates_failures() -> None:
    recorder = Recorder(fail_channel="hooks.example.test")
    client = httpx.AsyncClient(transport=recorder.transport())
    notifier = Notifier(CONFIG, client=client)

    report = asyncio.run(notifier.send(Notification("stale", "同步已经停止", "上次成功同步 3 小时前")))
    asyncio.run(client.aclose())

    urls = [url for url, _ in recorder.requests]
    assert urls == [
        "https://api.day.app/deviceKEY",
        "https://api.telegram.org/bot123:abc/sendMessage",
        "https://hooks.example.test/douzangjia",
    ]
    assert recorder.requests[0][1]["title"] == "抖藏家 · 同步已经停止"
    assert recorder.requests[1][1] == {"chat_id": "42", "text": "抖藏家 · 同步已经停止\n上次成功同步 3 小时前"}
    assert recorder.requests[2][1]["event"] == "stale"
    assert report == {"bark": "ok", "telegram": "ok", "webhook": "failed: HTTPStatusError"}


def test_notifier_without_channels_sends_nothing() -> None:
    assert Notifier({}).channels() == []
    assert asyncio.run(Notifier({}).send(Notification("x", "x", "x"))) == {}


class SpyNotifier(Notifier):
    def __init__(self, *, events: dict | None = None) -> None:
        super().__init__({"webhook": {"url": "https://x.test"}, "events": events or {}})
        self.sent: list[Notification] = []

    async def send(self, note: Notification) -> dict[str, str]:
        self.sent.append(note)
        return {"webhook": "ok"}


async def seed_runs(database: Database, *, session: str, runs: list[tuple[str, int]]) -> None:
    await database.execute(
        "INSERT INTO auth_sessions (provider, encrypted_cookies, status, updated_at) VALUES ('douyin', 'x', ?, 1)",
        (session,),
    )
    for status, finished in runs:
        await database.execute(
            "INSERT INTO sync_runs (mode, phase, status, started_at, finished_at) VALUES ('incremental', 'done', ?, ?, ?)",
            (status, finished - 10, finished),
        )


def test_watcher_alerts_once_reminds_later_and_announces_recovery(tmp_path: Path) -> None:
    """Catches the month-long outage going unnoticed, without spamming every minute."""

    async def scenario() -> list[tuple[int, list[str]]]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await seed_runs(database, session="authenticated", runs=[("completed", NOW - 40 * 86_400)])
        notifier = SpyNotifier()
        watcher = NotificationWatcher(database, tmp_path, notifier=notifier, interval_seconds=300, disk_usage=roomy_disk)
        timeline: list[tuple[int, list[str]]] = []
        try:
            for offset in (0, 60, 120, REMIND_AFTER_SECONDS + 1):
                before = len(notifier.sent)
                await watcher.check(now=NOW + offset)
                timeline.append((offset, [note.event for note in notifier.sent[before:]]))
            # A fresh successful run brings sync back.
            await database.execute(
                "INSERT INTO sync_runs (mode, phase, status, started_at, finished_at) "
                "VALUES ('incremental', 'done', 'completed', ?, ?)",
                (NOW + REMIND_AFTER_SECONDS + 50, NOW + REMIND_AFTER_SECONDS + 100),
            )
            before = len(notifier.sent)
            await watcher.check(now=NOW + REMIND_AFTER_SECONDS + 120)
            timeline.append((REMIND_AFTER_SECONDS + 120, [note.event for note in notifier.sent[before:]]))
            before = len(notifier.sent)
            await watcher.check(now=NOW + REMIND_AFTER_SECONDS + 180)
            timeline.append((REMIND_AFTER_SECONDS + 180, [note.event for note in notifier.sent[before:]]))
        finally:
            await database.close()
        return timeline

    assert asyncio.run(scenario()) == [
        (0, ["stale"]),
        (60, []),
        (120, []),
        (REMIND_AFTER_SECONDS + 1, ["stale"]),
        (REMIND_AFTER_SECONDS + 120, ["recovered"]),
        (REMIND_AFTER_SECONDS + 180, []),
    ]


def test_watcher_respects_event_switches_and_login_state(tmp_path: Path) -> None:
    async def scenario() -> list[str]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await seed_runs(database, session="expired", runs=[("completed", NOW - 600)])
        notifier = SpyNotifier(events={"login_required": False})
        watcher = NotificationWatcher(database, tmp_path, notifier=notifier, interval_seconds=300, disk_usage=roomy_disk)
        try:
            await watcher.check(now=NOW)
            state = json.loads((await database.fetchone("SELECT value_json FROM settings WHERE key='notifier_state'"))["value_json"])
        finally:
            await database.close()
        assert state["sync_state"] == "login_required"
        return [note.event for note in notifier.sent]

    assert asyncio.run(scenario()) == []


def test_watcher_is_inert_without_channels(tmp_path: Path) -> None:
    async def scenario() -> list[Notification]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await seed_runs(database, session="expired", runs=[])
        try:
            return await NotificationWatcher(database, tmp_path, notifier=Notifier({}), interval_seconds=300, disk_usage=roomy_disk).check(now=NOW)
        finally:
            await database.close()

    assert asyncio.run(scenario()) == []


def test_watcher_warns_once_when_the_archive_disk_runs_low(tmp_path: Path) -> None:
    async def scenario() -> list[str]:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await seed_runs(database, session="authenticated", runs=[("completed", NOW - 60)])
        notifier = SpyNotifier()
        watcher = NotificationWatcher(database, tmp_path, notifier=notifier, interval_seconds=300, disk_usage=cramped_disk)
        try:
            await watcher.check(now=NOW)
            await watcher.check(now=NOW + 120)
        finally:
            await database.close()
        return [note.event for note in notifier.sent]

    events = asyncio.run(scenario())
    assert events == ["disk_low"]

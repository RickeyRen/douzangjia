from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .db import Database
from .sync_health import sync_health_snapshot

logger = logging.getLogger(__name__)

EVENT_TITLES = {
    "login_required": "抖音登录已失效",
    "failing": "同步连续失败",
    "stale": "同步已经停止",
    "disk_low": "NAS 空间不足",
    "recovered": "同步已恢复",
}
ALERT_STATES = {"login_required", "failing", "stale"}
REMIND_AFTER_SECONDS = 6 * 3600
DISK_LOW_FREE_BYTES = 10 * 1024**3
DISK_LOW_FREE_PERCENT = 5.0


@dataclass(frozen=True, slots=True)
class Notification:
    event: str
    title: str
    body: str
    level: str = "warning"

    def payload(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "title": self.title,
            "body": self.body,
            "level": self.level,
            "at": int(time.time()),
            "app": "抖藏家",
        }


class Notifier:
    """Deliver one message to every configured channel; failures are per channel."""

    def __init__(self, config: dict[str, Any] | None = None, *, client: httpx.AsyncClient | None = None) -> None:
        self.config = config or {}
        self._client = client

    def channels(self) -> list[str]:
        names = []
        if self._bark_url():
            names.append("bark")
        if self._telegram():
            names.append("telegram")
        if self._webhook_url():
            names.append("webhook")
        return names

    def wants(self, event: str) -> bool:
        events = self.config.get("events") or {}
        return bool(events.get(event, True))

    async def send(self, note: Notification) -> dict[str, str]:
        if not self.channels():
            return {}
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10))
        try:
            results = await asyncio.gather(
                *(self._deliver(client, channel, note) for channel in self.channels()),
                return_exceptions=True,
            )
        finally:
            if own_client:
                await client.aclose()
        report: dict[str, str] = {}
        for channel, result in zip(self.channels(), results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("notification via %s failed: %s", channel, result)
                report[channel] = f"failed: {type(result).__name__}"
            else:
                report[channel] = result
        return report

    async def _deliver(self, client: httpx.AsyncClient, channel: str, note: Notification) -> str:
        if channel == "bark":
            response = await client.post(
                self._bark_url(),
                json={"title": f"抖藏家 · {note.title}", "body": note.body, "group": "douzangjia"},
            )
        elif channel == "telegram":
            token, chat_id = self._telegram()
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"抖藏家 · {note.title}\n{note.body}"},
            )
        else:
            response = await client.post(self._webhook_url(), json=note.payload())
        response.raise_for_status()
        return "ok"

    def _bark_url(self) -> str:
        return str((self.config.get("bark") or {}).get("url") or "").strip().rstrip("/")

    def _telegram(self) -> tuple[str, str] | None:
        telegram = self.config.get("telegram") or {}
        token = str(telegram.get("bot_token") or "").strip()
        chat_id = str(telegram.get("chat_id") or "").strip()
        return (token, chat_id) if token and chat_id else None

    def _webhook_url(self) -> str:
        return str((self.config.get("webhook") or {}).get("url") or "").strip()


class NotificationWatcher:
    """Turn health snapshots into at most one alert per problem, plus a recovery."""

    def __init__(
        self,
        database: Database,
        archive_root: Path,
        *,
        notifier: Notifier,
        interval_seconds: int,
        coordinator: Any = None,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    ) -> None:
        self.db = database
        self.archive_root = archive_root
        self.notifier = notifier
        self.interval_seconds = interval_seconds
        self.coordinator = coordinator
        self.disk_usage = disk_usage

    async def check(self, *, now: int | None = None) -> list[Notification]:
        now = int(time.time()) if now is None else now
        if not self.notifier.channels():
            return []
        state = await self._load_state()
        sent: list[Notification] = []
        health = await sync_health_snapshot(
            self.db, interval_seconds=self.interval_seconds, coordinator=self.coordinator, now=now
        )
        sync_state = str(health["state"])
        previous = str(state.get("sync_state") or "ok")
        last_sent = int(state.get("sync_notified_at") or 0)
        if sync_state in ALERT_STATES:
            if sync_state != previous or now - last_sent >= REMIND_AFTER_SECONDS:
                note = _sync_note(sync_state, health, now)
                if self.notifier.wants(sync_state):
                    sent.append(note)
                state["sync_notified_at"] = now
        elif previous in ALERT_STATES and sync_state in {"ok", "syncing"}:
            note = Notification("recovered", EVENT_TITLES["recovered"], "新的收藏已经可以正常同步了。", "info")
            if self.notifier.wants("recovered"):
                sent.append(note)
        if sync_state in ALERT_STATES or sync_state in {"ok", "syncing"}:
            state["sync_state"] = sync_state

        disk_low = self._disk_low()
        if disk_low is not None:
            if not state.get("disk_low") or now - int(state.get("disk_notified_at") or 0) >= REMIND_AFTER_SECONDS:
                if self.notifier.wants("disk_low"):
                    sent.append(Notification("disk_low", EVENT_TITLES["disk_low"], disk_low))
                state["disk_notified_at"] = now
            state["disk_low"] = True
        else:
            state["disk_low"] = False

        for note in sent:
            await self.notifier.send(note)
        await self._save_state(state)
        return sent

    def _disk_low(self) -> str | None:
        try:
            usage = self.disk_usage(self.archive_root)
        except OSError:
            return None
        percent = usage.free / usage.total * 100 if usage.total else 100
        if usage.free < DISK_LOW_FREE_BYTES or percent < DISK_LOW_FREE_PERCENT:
            return f"归档盘只剩 {usage.free / 1024**3:.1f} GB（{percent:.1f}%），新作品很快会下载失败。"
        return None

    async def _load_state(self) -> dict[str, Any]:
        row = await self.db.fetchone("SELECT value_json FROM settings WHERE key='notifier_state'")
        if row is None:
            return {}
        try:
            value = json.loads(str(row["value_json"]))
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    async def _save_state(self, state: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO settings (key, value_json, updated_at) VALUES ('notifier_state', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (json.dumps(state), int(time.time())),
        )


def _sync_note(state: str, health: dict[str, Any], now: int) -> Notification:
    last = health.get("lastSuccessAt")
    ago = f"{max(1, (now - int(last)) // 3600)} 小时前" if last else "从未"
    if state == "login_required":
        body = f"上次成功同步 {ago}。打开抖藏家重新扫码后会自动恢复。"
    elif state == "failing":
        body = f"已连续失败 {health.get('consecutiveFailures', 0)} 次，上次成功 {ago}。"
    else:
        body = f"上次成功同步 {ago}，之后没有新的同步完成。"
    return Notification(state, EVENT_TITLES[state], body)

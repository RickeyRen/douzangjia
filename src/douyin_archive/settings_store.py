from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .db import Database


class RuntimeSettings(BaseModel):
    """Values people may change from the UI; env vars only seed the defaults."""

    sync_interval_seconds: int = Field(default=300, ge=60, le=86_400)
    download_workers: int = Field(default=2, ge=1, le=8)
    remote_check_per_day: int = Field(default=200, ge=0, le=5_000)
    notifications: dict[str, Any] = Field(default_factory=dict)


class SettingsStore:
    def __init__(self, database: Database, *, defaults: RuntimeSettings | None = None) -> None:
        self.db = database
        self.defaults = defaults or RuntimeSettings()

    async def load(self) -> RuntimeSettings:
        rows = await self.db.fetchall("SELECT key, value_json FROM settings")
        stored: dict[str, Any] = {}
        for row in rows:
            try:
                stored[str(row["key"])] = json.loads(str(row["value_json"]))
            except json.JSONDecodeError:
                continue
        merged = {**self.defaults.model_dump(), **stored}
        try:
            return RuntimeSettings.model_validate(merged)
        except ValidationError:
            # A stale or hand-edited row must not take the whole app down.
            return self.defaults

    async def overrides(self) -> set[str]:
        rows = await self.db.fetchall("SELECT key FROM settings")
        return {str(row["key"]) for row in rows} & set(RuntimeSettings.model_fields)

    async def update(self, changes: dict[str, Any]) -> RuntimeSettings:
        current = await self.load()
        candidate = RuntimeSettings.model_validate({**current.model_dump(), **changes})
        now = int(time.time())
        async with self.db.transaction(immediate=True):
            for key in changes:
                value = getattr(candidate, key)
                await self.db.execute(
                    "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                    "updated_at=excluded.updated_at",
                    (key, json.dumps(value, ensure_ascii=False), now),
                )
        return candidate

    async def reset(self, key: str) -> RuntimeSettings:
        await self.db.execute("DELETE FROM settings WHERE key=?", (key,))
        return await self.load()

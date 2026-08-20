from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from .db import Database
from .models import DownloadJob
from .repositories import JobRepository


@dataclass(frozen=True, slots=True)
class DownloadSourcePolicy:
    source_id: str
    kind: str
    name: str
    enabled: bool
    updated_at: int | None


class DownloadPolicyService:
    """Persist why an item should download and keep shared-source choices safe."""

    def __init__(self, database: Database, jobs: JobRepository | None = None) -> None:
        self.db = database
        self.jobs = jobs or JobRepository(database)

    async def get_source(self, source_id: str) -> DownloadSourcePolicy | None:
        row = await self.db.fetchone(
            "SELECT id, kind, name, auto_download_enabled, "
            "download_policy_updated_at FROM library_sources WHERE id=?",
            (source_id,),
        )
        return self._source(row) if row is not None else None

    async def list_sources(self) -> list[DownloadSourcePolicy]:
        rows = await self.db.fetchall(
            "SELECT id, kind, name, auto_download_enabled, "
            "download_policy_updated_at FROM library_sources ORDER BY kind, name, id"
        )
        return [self._source(row) for row in rows]

    async def set_enabled(
        self, source_id: str, enabled: bool
    ) -> DownloadSourcePolicy:
        source = await self.get_source(source_id)
        if source is None:
            raise KeyError(source_id)
        now = int(time.time())
        await self.db.execute(
            "UPDATE library_sources SET auto_download_enabled=?, "
            "download_policy_updated_at=? WHERE id=?",
            (int(enabled), now, source_id),
        )
        if enabled:
            rows = await self.db.fetchall(
                "SELECT item_id, metadata_json FROM source_items "
                "WHERE source_id=? ORDER BY remote_order DESC, item_id DESC",
                (source_id,),
            )
            for row in rows:
                payload = self.valid_payload(str(row["item_id"]), row["metadata_json"])
                if payload is not None:
                    await self.record_intent(
                        str(row["item_id"]), "source", source_id, payload
                    )
        else:
            await self.remove_source_intents(source_id)
        updated = await self.get_source(source_id)
        if updated is None:
            raise RuntimeError("download source disappeared after policy update")
        return updated

    async def record_intent(
        self,
        item_id: str,
        origin_type: str,
        origin_id: str,
        payload: dict[str, Any],
    ) -> DownloadJob:
        if origin_type not in {"source", "manual", "creator"}:
            raise ValueError("invalid download intent origin")
        now = int(time.time())
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        async with self.db.transaction(immediate=True):
            await self.db.execute(
                "INSERT INTO download_intents "
                "(item_id, origin_type, origin_id, active, payload_json, created_at, updated_at) "
                "VALUES (?, ?, ?, 1, ?, ?, ?) "
                "ON CONFLICT(item_id, origin_type, origin_id) DO UPDATE SET "
                "active=1, payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                (item_id, origin_type, origin_id, encoded, now, now),
            )
            existing = await self.jobs.get_by_key("download", item_id)
            if existing is None:
                return await self.jobs.enqueue_unique("download", item_id, payload)
            if existing.status == "completed":
                return existing
            if existing.status in {"failed", "cancelled", "paused"}:
                await self.db.execute(
                    "UPDATE download_jobs SET payload_json=?, status='pending', "
                    "attempts=0, next_attempt_at=?, claimed_by=NULL, claimed_at=NULL, "
                    "last_error_code=NULL, paused_at=NULL, cancel_requested_at=NULL, "
                    "updated_at=? WHERE id=?",
                    (encoded, now, now, existing.id),
                )
                refreshed = await self.jobs.get(existing.id)
                if refreshed is None:
                    raise RuntimeError("download job disappeared after intent activation")
                return refreshed
            await self.db.execute(
                "UPDATE download_jobs SET payload_json=?, updated_at=? WHERE id=?",
                (encoded, now, existing.id),
            )
            refreshed = await self.jobs.get(existing.id)
            if refreshed is None:
                raise RuntimeError("download job disappeared after intent refresh")
            return refreshed

    async def remove_source_intents(self, source_id: str) -> int:
        now = int(time.time())
        rows = await self.db.fetchall(
            "SELECT item_id FROM download_intents "
            "WHERE origin_type='source' AND origin_id=? AND active=1",
            (source_id,),
        )
        await self.db.execute(
            "UPDATE download_intents SET active=0, updated_at=? "
            "WHERE origin_type='source' AND origin_id=? AND active=1",
            (now, source_id),
        )
        paused = 0
        for row in rows:
            item_id = str(row["item_id"])
            active = await self.db.fetchone(
                "SELECT 1 FROM download_intents WHERE item_id=? AND active=1 LIMIT 1",
                (item_id,),
            )
            if active is not None:
                continue
            cursor = await self.db.execute(
                "UPDATE download_jobs SET status='paused', paused_at=?, updated_at=? "
                "WHERE kind='download' AND remote_id=? "
                "AND status IN ('pending', 'retry')",
                (now, now, item_id),
            )
            paused += cursor.rowcount
        return paused

    @staticmethod
    def valid_payload(item_id: str, raw: object) -> dict[str, Any] | None:
        try:
            payload = json.loads(str(raw)) if not isinstance(raw, dict) else raw
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or str(payload.get("remote_id")) != item_id:
            return None
        assets = payload.get("assets")
        if not isinstance(assets, list) or not assets:
            return None
        if not all(
            isinstance(asset, dict)
            and str(asset.get("remote_id")) == item_id
            and bool(asset.get("url"))
            for asset in assets
        ):
            return None
        return payload

    @staticmethod
    def _source(row) -> DownloadSourcePolicy:
        return DownloadSourcePolicy(
            source_id=str(row["id"]),
            kind=str(row["kind"]),
            name=str(row["name"]),
            enabled=bool(row["auto_download_enabled"]),
            updated_at=(
                int(row["download_policy_updated_at"])
                if row["download_policy_updated_at"] is not None
                else None
            ),
        )

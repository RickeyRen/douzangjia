from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from math import ceil
from sqlite3 import Row
from typing import Any

from .db import Database
from .paths import asset_filename

_ACTIVE_STATUSES = {"pending", "running", "retry", "failed"}
_SPEED_FRESH_SECONDS = 5


class DownloadMonitor:
    def __init__(
        self, database: Database, *, clock: Callable[[], float] = time.time
    ) -> None:
        self.database = database
        self.clock = clock

    async def snapshot(self, *, limit: int) -> dict[str, object]:
        # Finished jobs pile up by the thousand; only unfinished ones feed the
        # summary, so read just a page of the recent completions besides them.
        columns = (
            "SELECT id, kind, remote_id, payload_json, status, attempts, "
            "next_attempt_at, last_error_code, updated_at FROM download_jobs "
        )
        jobs = await self.database.fetchall(
            columns + "WHERE kind='download' AND status!='completed' ORDER BY "
            "CASE status WHEN 'running' THEN 0 WHEN 'pending' THEN 1 "
            "WHEN 'retry' THEN 2 WHEN 'failed' THEN 3 ELSE 4 END, "
            "updated_at DESC, id DESC"
        )
        jobs += await self.database.fetchall(
            columns + "WHERE kind='download' AND status='completed' "
            "ORDER BY updated_at DESC, id DESC LIMIT ?",
            (max(0, limit - len(jobs)),),
        )
        completed_total = await self.database.fetchone(
            "SELECT COUNT(*) AS total FROM download_jobs "
            "WHERE kind='download' AND status='completed'"
        )
        job_ids = [str(row["remote_id"]) for row in jobs]
        placeholders = ",".join("?" for _ in job_ids) or "NULL"
        items = await self.database.fetchall(
            "SELECT i.remote_id, i.author_name, i.description FROM items i "
            f"WHERE i.remote_id IN ({placeholders})",
            tuple(job_ids),
        )
        media = await self.database.fetchall(
            f"SELECT m.* FROM media_files m WHERE m.item_id IN ({placeholders}) "
            "ORDER BY m.item_id, m.asset_index",
            tuple(job_ids),
        )
        collection_rows = await self.database.fetchall(
            "SELECT ci.item_id, c.name FROM collection_items ci "
            "JOIN collections c ON c.remote_id=ci.collection_id "
            f"WHERE ci.item_id IN ({placeholders}) ORDER BY ci.item_id, c.name",
            tuple(job_ids),
        )

        item_by_id = {str(row["remote_id"]): row for row in items}
        media_by_item: dict[str, dict[int, Row]] = defaultdict(dict)
        for row in media:
            media_by_item[str(row["item_id"])][int(row["asset_index"])] = row
        collections_by_item: dict[str, list[str]] = defaultdict(list)
        for row in collection_rows:
            collections_by_item[str(row["item_id"])].append(str(row["name"]))

        now = int(self.clock())
        serialized = [
            self._serialize_job(
                row,
                item_by_id.get(str(row["remote_id"])),
                media_by_item.get(str(row["remote_id"]), {}),
                collections_by_item.get(str(row["remote_id"]), []),
                now=now,
            )
            for row in jobs
        ]
        summary = self._summary(serialized)
        summary["completed"] = int(completed_total["total"]) if completed_total else 0
        return {
            "summary": summary,
            "items": serialized[:limit],
        }

    def _serialize_job(
        self,
        job: Row,
        item: Row | None,
        media: dict[int, Row],
        collections: list[str],
        *,
        now: int,
    ) -> dict[str, Any]:
        payload = self._payload(job["payload_json"])
        payload_assets = payload.get("assets")
        assets_by_index: dict[int, dict[str, Any]] = {}
        if isinstance(payload_assets, list):
            for value in payload_assets:
                if not isinstance(value, dict):
                    continue
                try:
                    index = int(value["asset_index"])
                except (KeyError, TypeError, ValueError):
                    continue
                assets_by_index[index] = value
        for index in media:
            assets_by_index.setdefault(index, {})

        assets = [
            self._serialize_asset(
                index,
                assets_by_index[index],
                media.get(index),
                job_status=str(job["status"]),
                now=now,
            )
            for index in sorted(assets_by_index)
        ]
        downloaded_bytes = sum(int(asset["downloadedBytes"]) for asset in assets)
        totals = [asset["totalBytes"] for asset in assets]
        total_bytes = (
            sum(int(value) for value in totals)
            if assets and all(value is not None for value in totals)
            else None
        )
        speed_bps = sum(float(asset["speedBps"]) for asset in assets)
        eta_seconds = self._eta(downloaded_bytes, total_bytes, speed_bps)
        current = next(
            (int(asset["index"]) for asset in assets if asset["status"] != "ready"),
            int(assets[-1]["index"]) if assets else None,
        )
        return {
            "id": int(job["id"]),
            "kind": str(job["kind"]),
            "remoteId": str(job["remote_id"]),
            "author": str(item["author_name"]) if item is not None else "",
            "description": str(item["description"]) if item is not None else "",
            "collections": list(collections),
            "status": str(job["status"]),
            "attempts": int(job["attempts"]),
            "nextAttemptAt": int(job["next_attempt_at"]),
            "errorCode": job["last_error_code"],
            "updatedAt": int(job["updated_at"]),
            "currentAssetIndex": current,
            "downloadedBytes": downloaded_bytes,
            "totalBytes": total_bytes,
            "speedBps": speed_bps,
            "etaSeconds": eta_seconds,
            "assets": assets,
        }

    @staticmethod
    def _payload(value: object) -> dict[str, Any]:
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _asset_status(job_status: str, media_status: str | None) -> str:
        if media_status == "ready":
            return "ready"
        if job_status in {"pending", "retry", "failed"}:
            return job_status
        if job_status == "running":
            return "running" if media_status == "running" else "pending"
        return media_status or job_status

    def _serialize_asset(
        self,
        index: int,
        payload: dict[str, Any],
        media: Row | None,
        *,
        job_status: str,
        now: int,
    ) -> dict[str, object]:
        media_type = str(
            media["media_type"]
            if media is not None
            else payload.get("media_type") or "video"
        )
        mime_type = (
            media["mime_type"]
            if media is not None and media["mime_type"]
            else payload.get("mime_type")
        )
        media_status = str(media["status"]) if media is not None else None
        status = self._asset_status(job_status, media_status)
        byte_size = int(media["byte_size"]) if media is not None and media["byte_size"] is not None else None
        stored_downloaded = (
            int(media["downloaded_bytes"]) if media is not None else 0
        )
        downloaded_bytes = byte_size if status == "ready" and byte_size is not None else stored_downloaded
        stored_total = (
            int(media["total_bytes"])
            if media is not None and media["total_bytes"] is not None
            else None
        )
        expected = payload.get("expected_size")
        expected_size = int(expected) if expected is not None else None
        total_bytes = stored_total or expected_size
        if status == "ready" and total_bytes is None:
            total_bytes = byte_size
        progress_updated_at = (
            int(media["progress_updated_at"])
            if media is not None and media["progress_updated_at"] is not None
            else None
        )
        speed_is_fresh = (
            status == "running"
            and progress_updated_at is not None
            and now - progress_updated_at <= _SPEED_FRESH_SECONDS
        )
        speed_bps = (
            float(media["speed_bps"])
            if media is not None and speed_is_fresh
            else 0.0
        )
        updated_at = (
            progress_updated_at
            if progress_updated_at is not None
            else int(media["updated_at"])
            if media is not None
            else None
        )
        return {
            "index": index,
            "fileName": asset_filename(index, media_type, str(mime_type) if mime_type else None),
            "mediaType": media_type,
            "status": status,
            "downloadedBytes": downloaded_bytes,
            "totalBytes": total_bytes,
            "speedBps": speed_bps,
            "etaSeconds": self._eta(downloaded_bytes, total_bytes, speed_bps),
            "updatedAt": updated_at,
        }

    @staticmethod
    def _eta(
        downloaded_bytes: int, total_bytes: int | None, speed_bps: float
    ) -> int | None:
        if total_bytes is None:
            return None
        if downloaded_bytes >= total_bytes:
            return 0
        if speed_bps <= 0:
            return None
        return ceil((total_bytes - downloaded_bytes) / speed_bps)

    def _summary(self, jobs: list[dict[str, Any]]) -> dict[str, object]:
        counts = Counter(str(job["status"]) for job in jobs)
        active = [job for job in jobs if job["status"] in _ACTIVE_STATUSES]
        downloaded_bytes = sum(int(job["downloadedBytes"]) for job in active)
        total_values = [job["totalBytes"] for job in active]
        total_bytes = (
            sum(int(value) for value in total_values)
            if all(value is not None for value in total_values)
            else None
        )
        speed_bps = sum(float(job["speedBps"]) for job in active)
        return {
            "pending": counts["pending"],
            "running": counts["running"],
            "retry": counts["retry"],
            "failed": counts["failed"],
            "completed": counts["completed"],
            "downloadedBytes": downloaded_bytes,
            "totalBytes": total_bytes,
            "speedBps": speed_bps,
            "etaSeconds": self._eta(downloaded_bytes, total_bytes, speed_bps),
        }

from __future__ import annotations

import json
import time
from collections.abc import Iterable

from .archive_repository import ArchiveBatch, ArchiveBatchRepository
from .db import Database
from .download_policy import DownloadPolicyService
from .library_scope import library_item_sql
from .repositories import JobRepository


class ArchiveTargetNotFound(LookupError):
    pass


class ArchivePayloadUnavailable(RuntimeError):
    pass


class ArchiveService:
    def __init__(
        self,
        database: Database,
        jobs: JobRepository,
        batches: ArchiveBatchRepository | None = None,
        download_policy: DownloadPolicyService | None = None,
    ) -> None:
        self.db = database
        self.jobs = jobs
        self.batches = batches or ArchiveBatchRepository(database)
        self.download_policy = download_policy or DownloadPolicyService(database, jobs)

    async def archive_item(self, remote_id: str) -> ArchiveBatch:
        item = await self.db.fetchone("SELECT remote_id FROM items WHERE remote_id=?", (remote_id,))
        if item is None:
            raise ArchiveTargetNotFound(remote_id)
        return await self._archive_ids("item", remote_id, (remote_id,))

    async def archive_source(self, source_id: str) -> ArchiveBatch:
        source = await self.db.fetchone("SELECT id FROM library_sources WHERE id=?", (source_id,))
        if source is None:
            raise ArchiveTargetNotFound(source_id)
        rows = await self.db.fetchall(
            "SELECT item_id FROM source_items WHERE source_id=? "
            "ORDER BY remote_order DESC, item_id DESC",
            (source_id,),
        )
        return await self._archive_ids(
            "source", source_id, (str(row["item_id"]) for row in rows)
        )

    async def archive_creator(self, creator_id: str) -> ArchiveBatch:
        creator = await self.db.fetchone(
            "SELECT remote_id FROM creators WHERE remote_id=?", (creator_id,)
        )
        if creator is None:
            raise ArchiveTargetNotFound(creator_id)
        rows = await self.db.fetchall(
            "SELECT remote_id FROM items WHERE creator_id=? "
            "ORDER BY COALESCE(published_at, first_seen_at) DESC, remote_id DESC",
            (creator_id,),
        )
        return await self._archive_ids(
            "creator", creator_id, (str(row["remote_id"]) for row in rows)
        )

    async def archive_selection(self, item_ids: Iterable[str]) -> tuple[ArchiveBatch, int]:
        """Queue a hand-picked set; items without a synced payload are skipped, not fatal."""
        wanted = list(dict.fromkeys(item_ids))
        placeholders = ",".join("?" for _ in wanted)
        rows = await self.db.fetchall(
            f"SELECT remote_id FROM items WHERE remote_id IN ({placeholders})", tuple(wanted)
        ) if wanted else []
        known = {str(row["remote_id"]) for row in rows}
        ordered = [item_id for item_id in wanted if item_id in known]
        if not ordered:
            raise ArchiveTargetNotFound("selection")
        return await self._archive_ids("selection", f"sel-{int(time.time())}", ordered, strict=False)

    async def missing_summary(self) -> dict[str, int | None]:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS missing FROM items i WHERE NOT EXISTS "
            "(SELECT 1 FROM media_files mf WHERE mf.item_id=i.remote_id AND mf.status='ready') "
            f"AND {library_item_sql('i')}"
        )
        sizes = await self.db.fetchone(
            "SELECT COUNT(DISTINCT item_id) AS items, COALESCE(SUM(byte_size), 0) AS bytes "
            "FROM media_files WHERE status='ready'"
        )
        missing = int(row["missing"]) if row else 0
        average = int(sizes["bytes"]) / int(sizes["items"]) if sizes and int(sizes["items"]) else None
        return {"missing": missing, "estimatedBytes": int(average * missing) if average else None}

    async def archive_missing(self) -> tuple[ArchiveBatch, int]:
        """Queue every library item that has no ready media yet, newest first."""
        rows = await self.db.fetchall(
            "SELECT remote_id FROM items i WHERE NOT EXISTS "
            "(SELECT 1 FROM media_files mf WHERE mf.item_id=i.remote_id AND mf.status='ready') "
            f"AND {library_item_sql('i')} "
            "ORDER BY first_seen_at DESC, remote_id DESC"
        )
        return await self._archive_ids(
            "missing", "all", (str(row["remote_id"]) for row in rows), strict=False
        )

    async def _archive_ids(
        self, kind: str, target_id: str, item_ids: Iterable[str], *, strict: bool = True
    ) -> ArchiveBatch | tuple[ArchiveBatch, int]:
        batch = await self.batches.create_batch(kind, target_id)
        skipped = 0
        for item_id in item_ids:
            job = await self.jobs.get_by_key("download", item_id)
            if job is None:
                ready = await self.db.fetchone(
                    "SELECT 1 FROM media_files WHERE item_id=? AND status='ready' LIMIT 1",
                    (item_id,),
                )
                if ready is not None:
                    await self.batches.add_item(batch.id, item_id)
                    continue
                payload = await self._synced_payload(item_id)
                if payload is None:
                    if not strict:
                        skipped += 1
                        continue
                    await self.batches.set_status(
                        batch.id, "failed", error_code="ITEM_PAYLOAD_UNAVAILABLE"
                    )
                    raise ArchivePayloadUnavailable(item_id)
            else:
                payload = job.payload
            job = await self.download_policy.record_intent(
                item_id, "manual", f"{kind}:{target_id}", payload
            )
            await self.db.execute(
                "UPDATE download_jobs SET batch_id=?, priority=MAX(priority, 100) "
                "WHERE id=?",
                (batch.id, job.id),
            )
            await self.batches.add_item(batch.id, item_id, job_id=job.id)
        refreshed = await self.batches.refresh_batch(batch.id)
        if refreshed is None:
            raise RuntimeError("archive batch disappeared during expansion")
        return (refreshed, skipped) if not strict else refreshed

    async def _synced_payload(self, item_id: str) -> dict[str, object] | None:
        rows = await self.db.fetchall(
            "SELECT metadata_json FROM source_items WHERE item_id=? "
            "ORDER BY last_seen_at DESC, source_id",
            (item_id,),
        )
        for row in rows:
            try:
                payload = json.loads(str(row["metadata_json"]))
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict) or str(payload.get("remote_id")) != item_id:
                continue
            assets = payload.get("assets")
            if not isinstance(assets, list) or not assets:
                continue
            if not all(
                isinstance(asset, dict)
                and str(asset.get("remote_id")) == item_id
                and bool(asset.get("url"))
                for asset in assets
            ):
                continue
            return payload
        return None

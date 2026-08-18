from __future__ import annotations

import hashlib
import time
from pathlib import Path

import anyio

from .db import Database
from .downloader import MediaDownloader
from .models import DownloadJob, MediaAsset
from .storage import CollectionProjector


class ArchiveJobHandler:
    """Persist one remote item's assets and project them into every collection."""

    def __init__(
        self,
        database: Database,
        downloader: MediaDownloader,
        projector: CollectionProjector,
        *,
        archive_root: Path,
    ) -> None:
        self.database = database
        self.downloader = downloader
        self.projector = projector
        self.archive_root = archive_root.resolve()

    async def __call__(self, job: DownloadJob) -> None:
        if job.kind != "download":
            raise ValueError(f"unsupported job kind: {job.kind}")
        assets = tuple(self._asset(value) for value in job.payload.get("assets", ()))
        item = await self.database.fetchone(
            "SELECT description, author_name FROM items WHERE remote_id=?",
            (job.remote_id,),
        )
        if item is None:
            raise ValueError("download job item is missing")
        title = str(item["description"] or item["author_name"] or job.remote_id)
        collections = await self.database.fetchall(
            "SELECT c.name FROM collections c "
            "JOIN collection_items ci ON ci.collection_id=c.remote_id "
            "WHERE ci.item_id=? ORDER BY c.first_seen_at, c.remote_id",
            (job.remote_id,),
        )

        for asset in assets:
            object_file = await self.downloader.download(asset)
            relative_path = object_file.resolve().relative_to(self.archive_root).as_posix()
            byte_size = object_file.stat().st_size
            checksum = await anyio.to_thread.run_sync(self._sha256, object_file)
            now = int(time.time())
            await self.database.execute(
                "INSERT INTO media_files "
                "(item_id, asset_index, media_type, relative_path, byte_size, "
                "checksum_sha256, mime_type, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?) "
                "ON CONFLICT(item_id, asset_index) DO UPDATE SET "
                "media_type=excluded.media_type, relative_path=excluded.relative_path, "
                "byte_size=excluded.byte_size, checksum_sha256=excluded.checksum_sha256, "
                "mime_type=excluded.mime_type, status='ready', updated_at=excluded.updated_at",
                (
                    job.remote_id,
                    asset.asset_index,
                    asset.media_type,
                    relative_path,
                    byte_size,
                    checksum,
                    asset.mime_type,
                    now,
                    now,
                ),
            )
            for collection in collections:
                await self.projector.project(
                    str(collection["name"]), title, job.remote_id, object_file
                )

    @staticmethod
    def _asset(value: object) -> MediaAsset:
        if not isinstance(value, dict):
            raise TypeError("download job contains an invalid media asset")
        return MediaAsset(
            remote_id=str(value["remote_id"]),
            asset_index=int(value["asset_index"]),
            media_type=str(value["media_type"]),
            url=str(value["url"]),
            mime_type=str(value["mime_type"]) if value.get("mime_type") else None,
            expected_size=(
                int(value["expected_size"])
                if value.get("expected_size") is not None
                else None
            ),
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

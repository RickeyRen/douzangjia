from __future__ import annotations

import errno
import os
import shutil
import time
from pathlib import Path

import anyio

from .paths import sanitize_segment


class ObjectStore:
    def __init__(self, archive_root: Path) -> None:
        self.root = archive_root
        self.objects = archive_root / "objects"
        self.temporary = archive_root / "tmp"

    def object_path(self, remote_id: str, filename: str) -> Path:
        return self.objects / sanitize_segment(remote_id) / sanitize_segment(filename)

    def part_path(self, remote_id: str, filename: str) -> Path:
        safe_id = sanitize_segment(remote_id)
        safe_name = sanitize_segment(filename)
        return self.temporary / safe_id / f"{safe_name}.part"

    async def finalize(self, part: Path, remote_id: str, filename: str) -> Path:
        destination = self.object_path(remote_id, filename)

        def move_into_place() -> Path:
            if not part.is_file() or part.stat().st_size <= 0:
                raise ValueError("cannot finalize an empty object")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_file() and destination.stat().st_size > 0:
                part.unlink(missing_ok=True)
                return destination
            os.replace(part, destination)
            return destination

        return await anyio.to_thread.run_sync(move_into_place)

    async def cleanup_orphan_parts(self, *, older_than_seconds: int) -> int:
        cutoff = time.time() - older_than_seconds

        def cleanup() -> int:
            if not self.temporary.exists():
                return 0
            removed = 0
            for part in self.temporary.rglob("*.part"):
                if part.is_file() and part.stat().st_mtime < cutoff:
                    part.unlink()
                    removed += 1
            return removed

        return await anyio.to_thread.run_sync(cleanup)


class CollectionProjector:
    def __init__(self, archive_root: Path) -> None:
        self.library = archive_root / "library"

    async def project(
        self,
        collection_name: str,
        title: str,
        remote_id: str,
        object_file: Path,
    ) -> Path:
        extension = object_file.suffix.lower()
        asset_suffix = "" if object_file.stem == "000" else f"_{object_file.stem}"
        filename = sanitize_segment(f"{title}_{remote_id}{asset_suffix}") + extension
        destination = self.library / sanitize_segment(collection_name) / filename

        def create_projection() -> Path:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                return destination
            try:
                os.link(object_file, destination)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                temporary = destination.with_suffix(destination.suffix + ".copying")
                shutil.copy2(object_file, temporary)
                os.replace(temporary, destination)
            return destination

        return await anyio.to_thread.run_sync(create_projection)

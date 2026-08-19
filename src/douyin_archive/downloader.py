from __future__ import annotations

import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import anyio
import httpx

from .models import MediaAsset
from .paths import asset_filename
from .storage import ObjectStore

_CONTENT_RANGE_TOTAL = re.compile(r"bytes\s+\d+-\d+/(\d+|\*)", re.IGNORECASE)
_CONTENT_RANGE_UNSATISFIED_TOTAL = re.compile(
    r"(?:bytes\s+)?\*/(\d+)", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class DownloadProgressSnapshot:
    downloaded_bytes: int
    total_bytes: int | None
    speed_bps: float
    eta_seconds: int | None


ProgressCallback = Callable[[DownloadProgressSnapshot], Awaitable[None]]


class IncompleteDownload(Exception):
    pass


class MediaDownloader:
    def __init__(
        self,
        store: ObjectStore,
        client: httpx.AsyncClient,
        *,
        progress_interval_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.client = client
        self.progress_interval_seconds = max(0.0, progress_interval_seconds)
        self.clock = clock

    async def download(
        self, asset: MediaAsset, *, on_progress: ProgressCallback | None = None
    ) -> Path:
        filename = asset_filename(asset.asset_index, asset.media_type, asset.mime_type)
        destination = self.store.object_path(asset.remote_id, filename)
        if (
            destination.is_file()
            and destination.stat().st_size > 0
            and (
                asset.expected_size is None
                or destination.stat().st_size == asset.expected_size
            )
        ):
            size = destination.stat().st_size
            await self._report(on_progress, size, asset.expected_size or size, 0)
            return destination

        part = self.store.part_path(asset.remote_id, filename)
        part.parent.mkdir(parents=True, exist_ok=True)
        resume_at = part.stat().st_size if part.exists() else 0
        if asset.expected_size is not None and resume_at > asset.expected_size:
            part.unlink()
            resume_at = 0

        headers = {"Accept-Encoding": "identity"}
        if resume_at:
            headers["Range"] = f"bytes={resume_at}-"

        expected_total = asset.expected_size
        async with self.client.stream("GET", asset.url, headers=headers) as response:
            if resume_at and response.status_code == 200:
                resume_at = 0
            content_range = response.headers.get("Content-Range", "")
            unsatisfied = _CONTENT_RANGE_UNSATISFIED_TOTAL.fullmatch(
                content_range.strip()
            )
            if (
                resume_at
                and response.status_code == 416
                and unsatisfied is not None
                and int(unsatisfied.group(1)) == resume_at
            ):
                await self._report(on_progress, resume_at, resume_at, 0)
                return await self.store.finalize(part, asset.remote_id, filename)
            response.raise_for_status()
            match = _CONTENT_RANGE_TOTAL.fullmatch(content_range.strip())
            if response.status_code == 206 and match and match.group(1) != "*":
                expected_total = int(match.group(1))
            if expected_total is None and not resume_at:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    expected_total = int(content_length)

            downloaded_bytes = resume_at
            last_reported_bytes = downloaded_bytes
            last_reported_at = self.clock()
            current_speed = 0.0
            await self._report(
                on_progress, downloaded_bytes, expected_total, current_speed
            )
            mode = "ab" if resume_at and response.status_code == 206 else "wb"
            chunks = (
                response.aiter_bytes(256 * 1024)
                if response.is_stream_consumed
                else response.aiter_raw()
            )
            async with await anyio.open_file(part, mode) as output:
                async for chunk in chunks:
                    if chunk:
                        await output.write(chunk)
                        downloaded_bytes += len(chunk)
                        now = self.clock()
                        elapsed = now - last_reported_at
                        if (
                            self.progress_interval_seconds == 0
                            or elapsed >= self.progress_interval_seconds
                        ):
                            current_speed = (
                                (downloaded_bytes - last_reported_bytes) / elapsed
                                if elapsed > 0
                                else 0.0
                            )
                            await self._report(
                                on_progress,
                                downloaded_bytes,
                                expected_total,
                                current_speed,
                            )
                            last_reported_bytes = downloaded_bytes
                            last_reported_at = now
                await output.flush()
                os.fsync(output.fileno())

        actual_size = part.stat().st_size
        await self._report(on_progress, actual_size, expected_total, current_speed)
        if expected_total is not None and actual_size != expected_total:
            raise IncompleteDownload(
                f"media length mismatch: expected {expected_total}, received {actual_size}"
            )
        if actual_size <= 0:
            raise IncompleteDownload("media response was empty")
        return await self.store.finalize(part, asset.remote_id, filename)

    @staticmethod
    async def _report(
        callback: ProgressCallback | None,
        downloaded_bytes: int,
        total_bytes: int | None,
        speed_bps: float,
    ) -> None:
        if callback is None:
            return
        eta_seconds = None
        if total_bytes is not None and downloaded_bytes >= total_bytes:
            eta_seconds = 0
        elif total_bytes is not None and speed_bps > 0:
            eta_seconds = ceil((total_bytes - downloaded_bytes) / speed_bps)
        await callback(
            DownloadProgressSnapshot(
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes,
                speed_bps=max(0.0, speed_bps),
                eta_seconds=eta_seconds,
            )
        )

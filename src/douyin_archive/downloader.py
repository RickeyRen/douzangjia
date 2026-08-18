from __future__ import annotations

import os
import re
from pathlib import Path

import anyio
import httpx

from .models import MediaAsset
from .paths import asset_filename
from .storage import ObjectStore

_CONTENT_RANGE_TOTAL = re.compile(r"bytes\s+\d+-\d+/(\d+|\*)", re.IGNORECASE)


class IncompleteDownload(Exception):
    pass


class MediaDownloader:
    def __init__(self, store: ObjectStore, client: httpx.AsyncClient) -> None:
        self.store = store
        self.client = client

    async def download(self, asset: MediaAsset) -> Path:
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
            response.raise_for_status()
            content_range = response.headers.get("Content-Range", "")
            match = _CONTENT_RANGE_TOTAL.fullmatch(content_range.strip())
            if expected_total is None and match and match.group(1) != "*":
                expected_total = int(match.group(1))
            if expected_total is None and not resume_at:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    expected_total = int(content_length)

            mode = "ab" if resume_at and response.status_code == 206 else "wb"
            async with await anyio.open_file(part, mode) as output:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    if chunk:
                        await output.write(chunk)
                await output.flush()
                os.fsync(output.fileno())

        actual_size = part.stat().st_size
        if expected_total is not None and actual_size != expected_total:
            raise IncompleteDownload(
                f"media length mismatch: expected {expected_total}, received {actual_size}"
            )
        if actual_size <= 0:
            raise IncompleteDownload("media response was empty")
        return await self.store.finalize(part, asset.remote_id, filename)

"""Play a work that is not on the NAS yet straight from Douyin while it downloads.

The NAS relays byte ranges from Douyin's CDN, so players keep seeking, the
owner's cookies never leave the NAS and no Douyin URL reaches the client.
The download itself stays with the workers: two writers on one ``.part``
file would corrupt it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict
from typing import Any

import httpx

from .db import Database
from .provider.normalizers import is_stable_play_url, normalize_page

logger = logging.getLogger(__name__)

RecordFetcher = Callable[[list[str]], Awaitable[Sequence[dict[str, Any]]]]
LinkRefresher = Callable[[str, dict[str, object]], Awaitable[bool]]

# Douyin's redirect target stays signed for hours; reuse it for every range a
# player asks for instead of asking Douyin's player endpoint each time.
RESOLVED_TTL_SECONDS = 20 * 60
# One fresh detail answer per work per while: players ask for many ranges.
DETAIL_RETRY_SECONDS = 10 * 60
DETAIL_TIMEOUT_SECONDS = 25
PASS_HEADERS = ("Content-Range", "Content-Length", "Accept-Ranges", "Last-Modified", "ETag")


class StreamUnavailable(Exception):
    pass


class LiveStreamResolver:
    def __init__(
        self,
        database: Database,
        client: httpx.AsyncClient,
        *,
        fetch_records: RecordFetcher | None = None,
        refresh_links: LinkRefresher | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db = database
        self.client = client
        self.fetch_records = fetch_records
        self.refresh_links = refresh_links
        self.clock = clock
        self._resolved: dict[str, tuple[str, float]] = {}
        self._detail_asked: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def open(self, item_id: str, range_header: str | None) -> httpx.Response:
        """An upstream response with 200/206 and an open body, or StreamUnavailable."""
        cached = self._resolved.get(item_id)
        if cached is not None and cached[1] > self.clock():
            response = await self._get(cached[0], range_header, item_id=item_id)
            if response is not None:
                return response
            self._resolved.pop(item_id, None)
        lock = self._locks.setdefault(item_id, asyncio.Lock())
        async with lock:
            for url in await self.known_urls(item_id):
                response = await self._get(url, range_header, item_id=item_id)
                if response is not None:
                    return response
            fresh = await self._fresh_url(item_id)
            if fresh is not None:
                response = await self._get(fresh, range_header, item_id=item_id)
                if response is not None:
                    return response
        raise StreamUnavailable(item_id)

    async def known_urls(self, item_id: str) -> list[str]:
        """Video links on record, the ones that never expire first."""
        rows = await self.db.fetchall(
            "SELECT payload_json AS payload FROM download_jobs "
            "WHERE kind='download' AND remote_id=? "
            "UNION ALL SELECT metadata_json AS payload FROM source_items WHERE item_id=?",
            (item_id, item_id),
        )
        urls: list[str] = []
        for row in rows:
            url = _video_url(row["payload"], item_id)
            if url and url not in urls:
                urls.append(url)
        return sorted(urls, key=lambda url: not is_stable_play_url(url))

    async def _fresh_url(self, item_id: str) -> str | None:
        if self.fetch_records is None:
            return None
        asked = self._detail_asked.get(item_id)
        if asked is not None and self.clock() - asked < DETAIL_RETRY_SECONDS:
            return None
        self._detail_asked[item_id] = self.clock()
        try:
            records = await asyncio.wait_for(
                self.fetch_records([item_id]), timeout=DETAIL_TIMEOUT_SECONDS
            )
        except Exception:  # a failed lookup just means "not playable now"
            logger.warning("live stream detail lookup failed for %s", item_id, exc_info=True)
            return None
        for item in normalize_page({"aweme_list": list(records)}).items:
            if item.remote_id != item_id:
                continue
            video = next((asset for asset in item.assets if asset.media_type == "video"), None)
            if video is None:
                return None
            if self.refresh_links is not None:
                # The waiting download takes the same working link.
                await self.refresh_links(item_id, asdict(item))
            return video.url
        return None

    async def _get(
        self, url: str, range_header: str | None, *, item_id: str
    ) -> httpx.Response | None:
        headers = {"Accept-Encoding": "identity"}
        if range_header:
            headers["Range"] = range_header
        try:
            response = await self.client.send(
                self.client.build_request("GET", url, headers=headers), stream=True
            )
        except httpx.HTTPError:
            logger.info("live stream upstream unreachable", exc_info=True)
            return None
        if response.status_code in (200, 206):
            self._resolved[item_id] = (str(response.url), self.clock() + RESOLVED_TTL_SECONDS)
            return response
        await response.aclose()
        return None


def _video_url(raw: object, item_id: str) -> str | None:
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or str(payload.get("remote_id")) != item_id:
        return None
    for asset in payload.get("assets") or []:
        if isinstance(asset, dict) and asset.get("media_type") == "video" and asset.get("url"):
            return str(asset["url"])
    return None

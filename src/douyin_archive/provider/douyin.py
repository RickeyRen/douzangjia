from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from .base import ProviderChanged, RawPageSource, RemoteCollection, RemotePage
from .normalizers import normalize_collections, normalize_page


class DouyinProvider:
    def __init__(self, source: RawPageSource, *, known_ids: set[str]) -> None:
        self.source = source
        self.known_ids = known_ids

    async def list_collections(self) -> list[RemoteCollection]:
        return normalize_collections(await self.source.fetch_collections())

    async def iter_collection_pages(
        self, remote_id: str, *, full_scan: bool
    ) -> AsyncIterator[RemotePage]:
        consecutive_known = 0
        seen_cursors: set[str] = set()
        async for raw_page in self.source.iter_raw_pages(remote_id):
            page = normalize_page(raw_page)
            selected = []
            stop = False
            for item in page.items:
                if not full_scan and item.remote_id in self.known_ids:
                    consecutive_known += 1
                    if consecutive_known >= 30:
                        stop = True
                        break
                else:
                    consecutive_known = 0
                    selected.append(item)
            if selected:
                yield RemotePage(tuple(selected), page.next_cursor, page.has_more)
            if stop or not page.has_more:
                return
            if page.next_cursor is not None:
                if page.next_cursor in seen_cursors:
                    return
                seen_cursors.add(page.next_cursor)


class PlaywrightDouyinSource:
    """Capture JSON responses emitted by Douyin's own favorites UI."""

    FAVORITES_URL = (
        "https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection"
    )
    COLLECTION_PATH_MARKERS = ("mix/listcollection", "collection/list")
    ITEM_PATH_MARKERS = ("mix/aweme", "collection/aweme", "aweme/favorite")

    def __init__(self, cookies: list[dict[str, object]]) -> None:
        self.cookies = cookies
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._responses: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._collection_names: dict[str, str] = {}

    async def open(self) -> None:
        if self._page is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 1000}, locale="zh-CN"
        )
        await self._context.add_cookies(self.cookies)
        self._page = await self._context.new_page()
        self._page.on("response", self._capture_response)

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            await self._browser.close()
            await self._playwright.stop()
        self._playwright = self._browser = self._context = self._page = None

    async def fetch_collections(self) -> dict:
        await self.open()
        await self._page.goto(
            self.FAVORITES_URL, wait_until="domcontentloaded", timeout=45_000
        )
        await self._click_text_candidates(("收藏", "收藏夹"))
        payload = await self._wait_for(self.COLLECTION_PATH_MARKERS)
        collections = normalize_collections(payload)
        self._collection_names = {item.remote_id: item.name for item in collections}
        return payload

    async def iter_raw_pages(self, remote_id: str) -> AsyncIterator[dict]:
        await self.open()
        if not self._collection_names:
            await self.fetch_collections()
        await self._open_collection(remote_id)
        while True:
            try:
                payload = await self._wait_for(self.ITEM_PATH_MARKERS)
            except TimeoutError:
                return
            yield payload
            page = normalize_page(payload)
            if not page.has_more:
                return
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._page.wait_for_timeout(900)

    async def _capture_response(self, response: Any) -> None:
        url = response.url
        if not any(
            marker in url for marker in (*self.COLLECTION_PATH_MARKERS, *self.ITEM_PATH_MARKERS)
        ):
            return
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            return
        with suppress(ValueError):
            payload = await response.json()
            if isinstance(payload, dict):
                await self._responses.put((url, payload))

    async def _wait_for(self, markers: tuple[str, ...]) -> dict:
        for _ in range(12):
            try:
                url, payload = await asyncio.wait_for(self._responses.get(), timeout=2.5)
            except TimeoutError:
                continue
            if any(marker in url for marker in markers):
                return payload
        raise TimeoutError("expected Douyin browser response was not observed")

    async def _click_text_candidates(self, labels: tuple[str, ...]) -> None:
        from playwright.async_api import Error as PlaywrightError

        for label in labels:
            with suppress(PlaywrightError):
                locator = self._page.get_by_text(label, exact=True).first
                if await locator.is_visible(timeout=1_000):
                    await locator.click(timeout=2_000)
                    await self._page.wait_for_timeout(800)

    async def _open_collection(self, remote_id: str) -> None:
        from playwright.async_api import Error as PlaywrightError

        selectors = (f"a[href*='{remote_id}']", f"[data-id='{remote_id}']")
        for selector in selectors:
            with suppress(PlaywrightError):
                locator = self._page.locator(selector).first
                if await locator.is_visible(timeout=1_000):
                    await locator.click(timeout=3_000)
                    return
        name = self._collection_names.get(remote_id)
        if name:
            with suppress(PlaywrightError):
                await self._page.get_by_text(name, exact=True).first.click(timeout=3_000)
                return
        raise ProviderChanged("favorite collection entry was not found in the browser UI")

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any
from urllib.parse import urlsplit

from ..browser_coordinator import BrowserCoordinator, CoordinatorPageLease
from .base import ProviderChanged, RawPageSource, RemoteCollection, RemotePage
from .normalizers import normalize_collections, normalize_page

logger = logging.getLogger(__name__)
ALL_FAVORITES_REMOTE_ID = "__douyin_all_favorites__"
ALL_FAVORITES_NAME = "抖音全部收藏"


def _payload_shape(payload: dict[str, Any]) -> dict[str, object]:
    """Describe response structure without retaining any response values."""

    def describe(value: object, *, nested: bool) -> object:
        if isinstance(value, list):
            return f"list[{len(value)}]"
        if isinstance(value, dict):
            if nested:
                return "dict"
            return {
                str(key): describe(child, nested=True)
                for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            }
        return type(value).__name__

    return {
        str(key): describe(value, nested=False)
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
    }


def _has_collection_schema(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    envelope = data if isinstance(data, dict) else payload
    return any(
        isinstance(envelope.get(key), list)
        for key in ("collects_list", "mix_infos", "mix_list", "collections", "items")
    )


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
    COLLECTION_PATH_MARKERS = (
        "mix/listcollection",
        "aweme/listcollection",
        "collection/list",
    )
    ITEM_PATH_MARKERS = ("mix/aweme", "collection/aweme", "aweme/favorite")
    COLLECTS_LIST_PATH = "/aweme/v1/web/collects/list/"
    COLLECTS_ITEMS_PATH = "/aweme/v1/web/collects/video/list/"
    ALL_FAVORITES_PATH = "/aweme/v1/web/aweme/listcollection/"

    def __init__(self, coordinator: BrowserCoordinator) -> None:
        self.coordinator = coordinator
        self._lease: CoordinatorPageLease | None = None
        self._page: Any = None
        self._responses: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self._collection_names: dict[str, str] = {}
        self._observed_paths: deque[str] = deque(maxlen=32)
        self._direct_collections = False

    async def open(self) -> None:
        if self._page is not None:
            return
        self._lease = await self.coordinator.acquire_page(viewport=(1440, 1000))
        self._page = self._lease.page
        self._page.on("response", self._capture_response)

    async def close(self) -> None:
        page = self._page
        lease = self._lease
        self._page = None
        self._lease = None
        if page is not None:
            page.remove_listener("response", self._capture_response)
        if lease is not None:
            await lease.release()
        self._responses = asyncio.Queue()
        self._collection_names.clear()
        self._observed_paths.clear()
        self._direct_collections = False

    async def fetch_collections(self) -> dict:
        await self.open()
        await self._page.goto(
            self.FAVORITES_URL, wait_until="domcontentloaded", timeout=45_000
        )
        direct_payload = await self._fetch_collections_api()
        signer_capabilities = await self._page.evaluate(
            """
            () => ({
              bytedAcrawler: typeof globalThis.byted_acrawler,
              bytedSign: typeof globalThis.byted_acrawler?.sign,
              webmssdk: typeof globalThis._webmsSDK,
              webmssdkSign: typeof globalThis._webmsSDK?.sign,
            })
            """
        )
        logger.warning(
            "Douyin direct collection response status=%s shape=%s signer=%s",
            direct_payload.get("status_code"),
            _payload_shape(direct_payload),
            signer_capabilities,
        )
        # Validate authentication/rate-limit status even when the response no
        # longer contains a collection list. This prevents an expired session
        # from being misreported as a provider layout change.
        normalize_collections(direct_payload)
        if _has_collection_schema(direct_payload):
            collections = normalize_collections(direct_payload)
            self._collection_names = {
                item.remote_id: item.name for item in collections
            }
            self._direct_collections = True
            return direct_payload
        await self._click_text_candidates(("收藏", "收藏夹"))
        payload = await self._wait_for_collections()
        collections = normalize_collections(payload)
        self._collection_names = {item.remote_id: item.name for item in collections}
        return payload

    async def iter_raw_pages(self, remote_id: str) -> AsyncIterator[dict]:
        await self.open()
        if not self._collection_names:
            await self.fetch_collections()
        if self._direct_collections:
            async for payload in self._iter_collection_api(remote_id):
                yield payload
            return
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

    async def _fetch_collections_api(self) -> dict:
        last_payload: dict = {}
        for attempt in range(3):
            try:
                last_payload = await self._browser_json(
                    self.COLLECTS_LIST_PATH,
                    {"cursor": 0, "count": 50},
                )
            except ProviderChanged:
                if attempt == 2:
                    raise
            else:
                if _has_collection_schema(last_payload):
                    records = list(last_payload.get("collects_list", []))
                    if not any(
                        str(record.get("collects_id_str", ""))
                        == ALL_FAVORITES_REMOTE_ID
                        for record in records
                        if isinstance(record, dict)
                    ):
                        records.append(
                            {
                                "collects_id_str": ALL_FAVORITES_REMOTE_ID,
                                "collects_name": ALL_FAVORITES_NAME,
                            }
                        )
                    return {**last_payload, "collects_list": records}
            if attempt < 2:
                await asyncio.sleep(1)
        return last_payload

    async def _iter_collection_api(self, remote_id: str) -> AsyncIterator[dict]:
        cursor: int | str = 0
        seen: set[str] = set()
        path = (
            self.ALL_FAVORITES_PATH
            if remote_id == ALL_FAVORITES_REMOTE_ID
            else self.COLLECTS_ITEMS_PATH
        )
        while True:
            collection_params = (
                {}
                if remote_id == ALL_FAVORITES_REMOTE_ID
                else {"collects_id": remote_id}
            )
            for attempt in range(3):
                try:
                    payload = await self._browser_json(
                        path,
                        {**collection_params, "cursor": cursor, "count": 20},
                    )
                except ProviderChanged:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1)
                else:
                    break
            yield payload
            page = normalize_page(payload)
            if not page.has_more or page.next_cursor is None:
                return
            if page.next_cursor in seen:
                return
            seen.add(page.next_cursor)
            cursor = page.next_cursor

    async def _browser_json(self, path: str, params: dict[str, object]) -> dict:
        try:
            evaluation = asyncio.create_task(
                self._page.evaluate(
                    """
            async ({path, params}) => {
              const url = new URL(path, window.location.origin);
              const common = {
                device_platform: 'webapp',
                aid: '6383',
                channel: 'channel_pc_web',
                pc_client_type: '1',
                version_code: '170400',
                version_name: '17.4.0',
                cookie_enabled: 'true',
                browser_language: navigator.language || 'zh-CN',
                browser_platform: navigator.platform || 'Linux x86_64',
                browser_name: 'Chrome',
                browser_online: String(navigator.onLine),
                engine_name: 'Blink',
                os_name: 'Linux',
                platform: 'PC',
              };
              for (const [key, value] of Object.entries({...common, ...params})) {
                url.searchParams.set(key, String(value));
              }
              const controller = new AbortController();
              const timer = window.setTimeout(() => controller.abort(), 20_000);
              try {
                const response = await fetch(url.toString(), {
                  credentials: 'include',
                  headers: {Accept: 'application/json, text/plain, */*'},
                  signal: controller.signal,
                });
                if (!response.ok) return {status_code: response.status};
                const data = await response.json();
                return data && typeof data === 'object' ? data : {};
              } catch (error) {
                return {
                  __browser_error: error?.name === 'AbortError' ? 'timeout' : 'network',
                };
              } finally {
                window.clearTimeout(timer);
              }
            }
                    """,
                    {"path": path, "params": params},
                )
            )
            completed, _ = await asyncio.wait({evaluation}, timeout=25)
            if evaluation not in completed:
                evaluation.cancel()
                evaluation.add_done_callback(self._consume_task_result)
                raise TimeoutError("Douyin browser API evaluation timed out")
            payload = evaluation.result()
        except Exception as error:
            logger.warning(
                "Douyin browser API evaluation failed error_type=%s",
                type(error).__name__,
            )
            raise ProviderChanged("Douyin browser API evaluation failed") from error
        if not isinstance(payload, dict):
            raise ProviderChanged("Douyin browser API returned a non-object payload")
        if payload.get("__browser_error") in {"timeout", "network"}:
            raise ProviderChanged("Douyin browser API request did not complete")
        return payload

    @staticmethod
    def _consume_task_result(task: asyncio.Task[Any]) -> None:
        with suppress(asyncio.CancelledError, Exception):
            task.result()

    async def _capture_response(self, response: Any) -> None:
        url = response.url
        parsed = urlsplit(url)
        if parsed.hostname and parsed.hostname.lower().endswith("douyin.com"):
            self._observed_paths.append(parsed.path or "/")
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
                if any(marker in url for marker in self.COLLECTION_PATH_MARKERS):
                    logger.warning(
                        "Douyin collection response shape=%s", _payload_shape(payload)
                    )
                await self._responses.put((url, payload))

    async def _wait_for(self, markers: tuple[str, ...]) -> dict:
        for _ in range(12):
            try:
                url, payload = await asyncio.wait_for(self._responses.get(), timeout=2.5)
            except TimeoutError:
                continue
            if any(marker in url for marker in markers):
                return payload
        page_path = urlsplit(str(self._page.url)).path or "/"
        logger.warning(
            "Douyin browser response changed: page_path=%s expected=%s "
            "observed_paths=%s",
            page_path,
            markers,
            list(self._observed_paths),
        )
        raise ProviderChanged("expected Douyin browser response was not observed")

    async def _wait_for_collections(self) -> dict:
        for _ in range(12):
            payload = await self._wait_for(self.COLLECTION_PATH_MARKERS)
            if _has_collection_schema(payload):
                return payload
        raise ProviderChanged("Douyin collection response schema was not observed")

    async def _click_text_candidates(self, labels: tuple[str, ...]) -> None:
        from playwright.async_api import Error as PlaywrightError

        for label in labels:
            locator = self._page.get_by_text(label, exact=True)
            clicked = False
            with suppress(PlaywrightError):
                count = await locator.count()
                for index in range(count):
                    candidate = locator.nth(index)
                    if await candidate.is_visible(timeout=1_000):
                        await candidate.click(timeout=2_000)
                        await self._page.wait_for_timeout(800)
                        clicked = True
                        break
                logger.warning(
                    "Douyin text candidate label=%s matches=%s clicked=%s",
                    label,
                    count,
                    clicked,
                )

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

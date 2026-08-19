from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, ClassVar
from urllib.parse import urlsplit

from ..browser_coordinator import BrowserCoordinator, CoordinatorPageLease
from .base import (
    ProviderChanged,
    RawPageSource,
    RemoteCollection,
    RemotePage,
    RemoteSourceEntity,
    RemoteSourceEntityPage,
)
from .normalizers import normalize_collections, normalize_page

logger = logging.getLogger(__name__)
ALL_FAVORITES_REMOTE_ID = "__douyin_all_favorites__"
ALL_FAVORITES_NAME = "抖音全部收藏"


def _parse_compact_count(raw: str) -> int | None:
    cleaned = raw.strip().replace(",", "")
    multiplier = 10_000 if cleaned.endswith("万") else 1
    if multiplier > 1:
        cleaned = cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except (TypeError, ValueError):
        return None


def _parse_collection_counts(
    page_text: str, expected_names: tuple[str, ...]
) -> dict[str, int]:
    """Extract folder counts from Douyin's visible collection view."""

    counts: dict[str, int] = {}
    for name in expected_names:
        if not name:
            continue
        match = re.search(
            rf"(?:^|\n)\s*{re.escape(name)}\s*(?:\n|\r|\s)+"
            rf"共\s*([\d,.]+(?:万)?)\s*作品",
            page_text,
        )
        if match is None:
            continue
        parsed = _parse_compact_count(match.group(1))
        if parsed is not None:
            counts[name] = parsed
    return counts


def _merge_collection_counts(
    payload: dict[str, Any], counts: dict[str, int]
) -> dict[str, Any]:
    records = payload.get("collects_list")
    if not isinstance(records, list) or not counts:
        return payload
    enriched: list[object] = []
    for value in records:
        if not isinstance(value, dict):
            enriched.append(value)
            continue
        record = dict(value)
        statistics = record.get("statis")
        has_api_count = (
            isinstance(statistics, dict) and statistics.get("aweme_count") is not None
        ) or any(record.get(key) is not None for key in ("aweme_count", "item_count"))
        name = str(record.get("collects_name", "")).strip()
        if not has_api_count and name in counts:
            record["aweme_count"] = counts[name]
        enriched.append(record)
    return {**payload, "collects_list": enriched}


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
        async for page in self._normalized_pages(
            self.source.iter_raw_pages(remote_id), full_scan=full_scan
        ):
            yield page

    def supported_account_sources(self) -> tuple[str, ...]:
        if not hasattr(self.source, "iter_account_raw_pages"):
            return ()
        return PlaywrightDouyinSource.SUPPORTED_ACCOUNT_SOURCES

    async def iter_account_pages(
        self, kind: str, *, full_scan: bool
    ) -> AsyncIterator[RemotePage]:
        iterator = self.source.iter_account_raw_pages(
            kind,
            known_ids=self.known_ids,
            full_scan=full_scan,
        )
        async for page in self._normalized_pages(iterator, full_scan=full_scan):
            yield page

    def supported_account_entity_sources(self) -> tuple[str, ...]:
        if not hasattr(self.source, "iter_account_raw_entity_pages"):
            return ()
        return PlaywrightDouyinSource.SUPPORTED_ACCOUNT_ENTITY_SOURCES

    async def iter_account_entity_pages(
        self, kind: str, *, full_scan: bool
    ) -> AsyncIterator[RemoteSourceEntityPage]:
        del full_scan
        async for raw_page in self.source.iter_account_raw_entity_pages(kind):
            records = raw_page.get("entities", [])
            if not isinstance(records, list):
                raise ProviderChanged("Douyin entity page returned invalid records")
            entities: list[RemoteSourceEntity] = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                remote_id = str(record.get("remote_id", "")).strip()
                title = str(record.get("title", "")).strip()
                if not remote_id or not title:
                    continue
                entities.append(
                    RemoteSourceEntity(
                        remote_id=remote_id,
                        entity_type=str(record.get("entity_type", "external")),
                        title=title,
                        subtitle=(
                            str(record["subtitle"]).strip()
                            if record.get("subtitle")
                            else None
                        ),
                        cover_url=(
                            str(record["cover_url"])
                            if record.get("cover_url")
                            else None
                        ),
                        source_url=(
                            str(record["source_url"])
                            if record.get("source_url")
                            else None
                        ),
                        remote_order=(
                            str(record["remote_order"])
                            if record.get("remote_order") is not None
                            else None
                        ),
                        metadata=(
                            record.get("metadata", {})
                            if isinstance(record.get("metadata", {}), dict)
                            else {}
                        ),
                    )
                )
            yield RemoteSourceEntityPage(
                tuple(entities),
                str(raw_page["cursor"]) if raw_page.get("cursor") is not None else None,
                bool(raw_page.get("has_more", False)),
            )

    async def iter_creator_pages(
        self, creator_id: str, *, full_scan: bool
    ) -> AsyncIterator[RemotePage]:
        iterator = self.source.iter_creator_raw_pages(
            creator_id,
            known_ids=self.known_ids,
            full_scan=full_scan,
        )
        async for page in self._normalized_pages(iterator, full_scan=full_scan):
            yield page

    async def _normalized_pages(
        self, raw_pages: AsyncIterator[dict], *, full_scan: bool
    ) -> AsyncIterator[RemotePage]:
        consecutive_known = 0
        seen_cursors: set[str] = set()
        async for raw_page in raw_pages:
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
    SELF_URL = "https://www.douyin.com/user/self?from_tab_name=main"
    FOLLOWING_URL = "https://www.douyin.com/follow?from_nav=1"
    FAVORITE_MUSIC_URL = (
        f"{SELF_URL}&showTab=favorite_collection&showSubTab=music"
    )
    SUPPORTED_ACCOUNT_ENTITY_SOURCES = ("favorite_music",)
    SUPPORTED_ACCOUNT_SOURCES = (
        "post",
        "recommend",
        "like",
        "favorite_video",
        "favorite_series",
        "favorite_drama",
        "watch_history",
        "watch_later",
        "reservation",
        "following",
    )
    ACCOUNT_SOURCE_TABS: ClassVar[dict[str, str]] = {
        "post": "post",
        "recommend": "recommend",
        "like": "like",
        "favorite_video": "favorite_collection",
        "watch_history": "record",
        "watch_later": "watch_later",
        "reservation": "my_appointment",
    }
    ACCOUNT_SOURCE_URLS: ClassVar[dict[str, str]] = {
        "following": FOLLOWING_URL,
        "favorite_series": (
            f"{SELF_URL}&showTab=favorite_collection&showSubTab=compilation"
        ),
        "favorite_drama": (
            f"{SELF_URL}&showTab=favorite_collection&showSubTab=playlet"
        ),
    }
    ACCOUNT_SOURCE_CLICKS: ClassVar[dict[str, tuple[tuple[str, ...], ...]]] = {
        "post": (("作品",),),
        "recommend": (("推荐",),),
        "like": (("喜欢",),),
        "favorite_video": (("收藏",), ("视频", "收藏视频")),
        "watch_history": (("观看历史",),),
        "watch_later": (("稍后再看",),),
    }
    COLLECTION_PATH_MARKERS = (
        "mix/listcollection",
        "aweme/listcollection",
        "collection/list",
    )
    ITEM_PATH_MARKERS = ("mix/aweme", "collection/aweme", "aweme/favorite")
    COLLECTS_LIST_PATH = "/aweme/v1/web/collects/list/"
    COLLECTS_ITEMS_PATH = "/aweme/v1/web/collects/video/list/"
    ALL_FAVORITES_PATH = "/aweme/v1/web/aweme/listcollection/"
    DETAIL_PATH = "/aweme/v1/web/aweme/detail/"

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
            counts = await self._read_collection_counts_from_page(
                tuple(
                    item.name
                    for item in collections
                    if item.remote_id != ALL_FAVORITES_REMOTE_ID
                )
            )
            direct_payload = _merge_collection_counts(direct_payload, counts)
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

    async def _read_collection_counts_from_page(
        self, expected_names: tuple[str, ...]
    ) -> dict[str, int]:
        if not expected_names:
            return {}
        counts: dict[str, int] = {}
        try:
            for _ in range(8):
                await self._click_text_candidates(("收藏", "收藏夹"))
                await self._page.wait_for_timeout(800)
                page_text = await self._page.locator("body").inner_text(timeout=5_000)
                counts.update(_parse_collection_counts(page_text, expected_names))
                if len(counts) == len(expected_names):
                    break
        except Exception as error:  # noqa: BLE001 - best-effort UI fallback
            logger.warning(
                "Douyin collection count fallback unavailable error_type=%s",
                type(error).__name__,
            )
        logger.warning(
            "Douyin collection count fallback matched=%s expected=%s",
            len(counts),
            len(expected_names),
        )
        return counts

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

    async def iter_account_raw_pages(
        self,
        kind: str,
        *,
        known_ids: set[str] | None = None,
        full_scan: bool = True,
    ) -> AsyncIterator[dict]:
        if kind not in self.SUPPORTED_ACCOUNT_SOURCES:
            raise ProviderChanged("unsupported Douyin account source")
        await self.open()
        target_url = self.ACCOUNT_SOURCE_URLS.get(kind)
        if target_url is None:
            tab_key = self.ACCOUNT_SOURCE_TABS[kind]
            target_url = f"{self.SELF_URL}&showTab={tab_key}"
        await self._page.goto(
            target_url,
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        await self._page.wait_for_timeout(1_000)
        if kind == "favorite_video":
            await self._click_text_candidates(("视频", "收藏视频"))

        discovered_ids: list[str] = []
        if kind in {"favorite_series", "favorite_drama"}:
            nested_links = await self._visible_nested_links(kind)
            for nested_link in nested_links:
                await self._page.goto(
                    nested_link, wait_until="domcontentloaded", timeout=45_000
                )
                await self._page.wait_for_timeout(800)
                discovered_ids.extend(
                    await self._collect_visible_item_ids(
                        known_ids=known_ids, full_scan=full_scan
                    )
                )
        else:
            discovered_ids = await self._collect_visible_item_ids(
                known_ids=known_ids, full_scan=full_scan
            )
        discovered_ids = list(dict.fromkeys(discovered_ids))
        async for payload in self._detail_pages(discovered_ids):
            yield payload

    async def iter_account_raw_entity_pages(
        self, kind: str
    ) -> AsyncIterator[dict[str, object]]:
        if kind not in self.SUPPORTED_ACCOUNT_ENTITY_SOURCES:
            raise ProviderChanged("unsupported Douyin account entity source")
        await self.open()
        await self._page.goto(
            self.FAVORITE_MUSIC_URL,
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        await self._page.wait_for_timeout(1_000)
        await self._click_text_candidates(("音乐",))
        await self._page.wait_for_timeout(500)
        seen: set[str] = set()
        stable_rounds = 0
        order = 0
        while stable_rounds < 3:
            visible = await self._visible_music_entities()
            records: list[dict[str, object]] = []
            for record in visible:
                identity = "\n".join(
                    (
                        str(record.get("title", "")).strip(),
                        str(record.get("subtitle", "")).strip(),
                        str(record.get("duration", "")).strip(),
                        str(record.get("coverUrl", "")).split("?", 1)[0],
                    )
                )
                if not identity.strip() or identity in seen:
                    continue
                seen.add(identity)
                remote_id = "music:" + hashlib.sha256(identity.encode()).hexdigest()[:24]
                records.append(
                    {
                        "remote_id": remote_id,
                        "entity_type": "music",
                        "title": str(record.get("title", "")).strip(),
                        "subtitle": str(record.get("subtitle", "")).strip() or None,
                        "cover_url": str(record.get("coverUrl", "")).strip() or None,
                        "source_url": self.FAVORITE_MUSIC_URL,
                        "remote_order": f"{1_000_000_000 - order:010d}",
                        "metadata": {"duration": record.get("duration")},
                    }
                )
                order += 1
            if records:
                stable_rounds = 0
                yield {
                    "entities": records,
                    "cursor": str(order),
                    "has_more": True,
                }
            else:
                stable_rounds += 1
            if stable_rounds < 3:
                await self._scroll_source_entities()
                await self._page.wait_for_timeout(750)

    async def _visible_music_entities(self) -> list[dict[str, object]]:
        result = await self._page.evaluate(
            """
            () => { // __yingcangVisibleMusicEntities
              const visible = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const result = [];
              for (const item of document.querySelectorAll('li')) {
                if (!visible(item) || !item.textContent?.includes('取消收藏')) continue;
                const image = [...item.querySelectorAll('img')].find((candidate) => {
                  const rect = candidate.getBoundingClientRect();
                  return rect.width >= 60 && rect.height >= 60;
                });
                if (!image) continue;
                const lines = (item.innerText || '').split(/\\n+/)
                  .map((value) => value.trim())
                  .filter((value) => value && !['去使用', '取消收藏'].includes(value));
                const duration = lines.find((value) => /^\\d{1,2}:\\d{2}$/.test(value)) || '';
                const labels = lines.filter((value) => value !== duration);
                if (!labels[0]) continue;
                result.push({
                  title: labels[0],
                  subtitle: labels[1] || '',
                  duration,
                  coverUrl: image.currentSrc || image.src || '',
                });
              }
              return result;
            }
            """
        )
        if not isinstance(result, list):
            raise ProviderChanged("Douyin music source returned invalid entities")
        return [value for value in result if isinstance(value, dict)]

    async def _scroll_source_entities(self) -> None:
        await self._page.evaluate(
            """
            () => { // __yingcangScrollSourceEntities
              const cards = [...document.querySelectorAll('li')].filter((item) =>
                item.textContent?.includes('取消收藏') && item.querySelector('img')
              );
              const last = cards[cards.length - 1];
              let element = last?.parentElement || document.body;
              let scrollRoot = null;
              while (element && element !== document.documentElement) {
                const style = getComputedStyle(element);
                if (element.scrollHeight > element.clientHeight + 64 &&
                    ['auto', 'scroll'].includes(style.overflowY)) {
                  scrollRoot = element;
                  break;
                }
                element = element.parentElement;
              }
              last?.scrollIntoView({block: 'end'});
              if (scrollRoot) scrollRoot.scrollTo({top: scrollRoot.scrollHeight});
              else window.scrollTo(0, document.documentElement.scrollHeight);
              return true;
            }
            """
        )

    async def _visible_nested_links(self, kind: str) -> list[str]:
        patterns = (
            ("/collection/",)
            if kind == "favorite_series"
            else ("/series/", "/collection/")
        )
        result = await self._page.evaluate(
            """
            ({patterns}) => { // __yingcangVisibleNestedLinks
              const visible = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              return [...new Set([...document.querySelectorAll('a[href]')]
                .filter((anchor) => visible(anchor) && !anchor.closest('footer'))
                .map((anchor) => anchor.href)
                .filter((href) => patterns.some((pattern) => href.includes(pattern))))];
            }
            """,
            {"patterns": list(patterns)},
        )
        if not isinstance(result, list):
            raise ProviderChanged("Douyin nested source returned invalid links")
        return [str(value) for value in result if str(value).startswith("https://")]

    async def iter_creator_raw_pages(
        self,
        creator_id: str,
        *,
        known_ids: set[str] | None = None,
        full_scan: bool = True,
    ) -> AsyncIterator[dict]:
        await self.open()
        await self._page.goto(
            f"https://www.douyin.com/user/{creator_id}",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        discovered_ids = await self._collect_visible_item_ids(
            known_ids=known_ids, full_scan=full_scan
        )
        async for payload in self._detail_pages(discovered_ids):
            yield payload

    async def _collect_visible_item_ids(
        self, *, known_ids: set[str] | None, full_scan: bool
    ) -> list[str]:
        discovered_ids: list[str] = []
        discovered_set: set[str] = set()
        stable_rounds = 0
        for _ in range(1_000):
            visible_ids = await self._visible_account_item_ids()
            if not full_scan and known_ids:
                visible_ids = self._trim_after_known_streak(visible_ids, known_ids)
            new_ids = [item_id for item_id in visible_ids if item_id not in discovered_set]
            if new_ids:
                discovered_ids.extend(new_ids)
                discovered_set.update(new_ids)
                stable_rounds = 0
            else:
                stable_rounds += 1
            if stable_rounds >= 3:
                break
            await self._scroll_account_panel()
            await self._page.wait_for_timeout(750)
        return discovered_ids

    async def _detail_pages(self, discovered_ids: list[str]) -> AsyncIterator[dict]:
        for offset in range(0, len(discovered_ids), 20):
            chunk = discovered_ids[offset : offset + 20]
            payload = await self._fetch_aweme_details(chunk)
            yield {
                **payload,
                "cursor": str(offset + len(chunk)),
                "has_more": offset + len(chunk) < len(discovered_ids),
            }

    @staticmethod
    def _trim_after_known_streak(
        item_ids: list[str], known_ids: set[str]
    ) -> list[str]:
        consecutive_known = 0
        for index, item_id in enumerate(item_ids):
            if item_id in known_ids:
                consecutive_known += 1
                if consecutive_known >= 30:
                    return item_ids[: index - 29]
            else:
                consecutive_known = 0
        return item_ids

    async def _visible_account_item_ids(self) -> list[str]:
        result = await self._page.evaluate(
            r"""
            () => { // __yingcangVisibleAccountIds
              const visible = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  rect.width > 0 && rect.height > 0;
              };
              const ids = [];
              const seen = new Set();
              const currentMatch = location.pathname.match(/\/(?:video|note)\/(\d+)/);
              if (currentMatch) {
                seen.add(currentMatch[1]);
                ids.push(currentMatch[1]);
              }
              for (const element of document.querySelectorAll('[data-e2e-aweme-id]')) {
                if (!visible(element) || element.closest('footer')) continue;
                const itemId = element.getAttribute('data-e2e-aweme-id') || '';
                if (/^\d+$/.test(itemId) && !seen.has(itemId)) {
                  seen.add(itemId);
                  ids.push(itemId);
                }
              }
              for (const anchor of document.querySelectorAll(
                'a[href*="/video/"], a[href*="/note/"]'
              )) {
                if (!visible(anchor) || anchor.closest('footer')) continue;
                if (!anchor.querySelector('img, picture, video')) continue;
                if (anchor.href.includes('source=Baiduspider')) continue;
                const match = anchor.href.match(/\/(?:video|note)\/(\d+)/);
                if (match && !seen.has(match[1])) {
                  seen.add(match[1]);
                  ids.push(match[1]);
                }
              }
              return ids;
            }
            """
        )
        if not isinstance(result, list):
            raise ProviderChanged("Douyin account tab returned invalid item ids")
        return [str(value) for value in result if str(value).isdigit()]

    async def _scroll_account_panel(self) -> None:
        await self._page.evaluate(
            """
            () => { // __yingcangScrollAccountPanel
              const visible = (element) => {
                const style = getComputedStyle(element);
                return style.display !== 'none' && style.visibility !== 'hidden' &&
                  element.getBoundingClientRect().height > 0;
              };
              const items = [...document.querySelectorAll(
                '[data-e2e-aweme-id], a[href*="/video/"], a[href*="/note/"]'
              )].filter(visible);
              const lastItem = items[items.length - 1];
              let element = lastItem?.parentElement || document.body;
              let scrollRoot = null;
              while (element && element !== document.documentElement) {
                const style = getComputedStyle(element);
                if (element.scrollHeight > element.clientHeight + 64 &&
                    ['auto', 'scroll'].includes(style.overflowY)) {
                  scrollRoot = element;
                  break;
                }
                element = element.parentElement;
              }
              lastItem?.scrollIntoView({block: 'end'});
              if (scrollRoot) {
                scrollRoot.scrollTo({top: scrollRoot.scrollHeight, behavior: 'instant'});
              } else {
                window.scrollTo(0, document.documentElement.scrollHeight);
              }
              return true;
            }
            """
        )

    async def _fetch_aweme_details(self, item_ids: list[str]) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                payload = await self._page.evaluate(
                    """
            async ({ids, path}) => { // __yingcangFetchDetails
              const fetchOne = async (id) => {
                const url = new URL(path, window.location.origin);
                url.searchParams.set('aweme_id', id);
                url.searchParams.set('aid', '6383');
                url.searchParams.set('device_platform', 'webapp');
                for (let attempt = 0; attempt < 3; attempt += 1) {
                  const controller = new AbortController();
                  const timeout = window.setTimeout(() => controller.abort(), 5_000);
                  try {
                    const response = await fetch(url.toString(), {
                      credentials: 'include',
                      cache: 'no-store',
                      signal: controller.signal,
                      headers: {Accept: 'application/json, text/plain, */*'},
                    });
                    if (!response.ok) return null;
                    const data = JSON.parse(await response.text());
                    return data?.aweme_detail || data?.aweme_list?.[0] || null;
                  } catch {
                    if (attempt < 2) {
                      await new Promise((resolve) => setTimeout(resolve, 350 * (attempt + 1)));
                    }
                  } finally {
                    window.clearTimeout(timeout);
                  }
                }
                return null;
              };
              const records = new Array(ids.length).fill(null);
              let nextIndex = 0;
              const worker = async () => {
                while (nextIndex < ids.length) {
                  const index = nextIndex;
                  nextIndex += 1;
                  records[index] = await fetchOne(ids[index]);
                }
              };
              const workerCount = Math.min(4, ids.length);
              const workers = Array.from({length: workerCount}, () => worker());
              await Promise.all(workers);
              return {status_code: 0, aweme_list: records.filter(Boolean)};
            }
            """,
                    {"ids": item_ids, "path": self.DETAIL_PATH},
                )
                if isinstance(payload, dict):
                    return payload
                last_error = TypeError("Douyin item detail response was not an object")
            except Exception as error:  # noqa: BLE001 - browser failures are retryable
                last_error = error
            logger.warning(
                "Douyin item detail retry attempt=%s error_type=%s",
                attempt + 1,
                type(last_error).__name__,
            )
            if attempt < 2:
                await self._page.wait_for_timeout(500 * (attempt + 1))
        raise ProviderChanged("Douyin item detail response changed") from last_error

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
              const request = (async () => {
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
                }
              })();
              let timer;
              const timeout = new Promise((resolve) => {
                timer = window.setTimeout(() => {
                  controller.abort();
                  resolve({__browser_error: 'timeout'});
                }, 20_000);
              });
              try {
                return await Promise.race([request, timeout]);
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
        except asyncio.CancelledError as error:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            logger.warning("Douyin browser API child task was cancelled")
            raise ProviderChanged("Douyin browser API task was cancelled") from error
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
        # Playwright can lose a response body when the official page navigates
        # while the asynchronous callback is still reading it. The response
        # observer is diagnostic/fallback-only and must never fail the sync.
        with suppress(Exception):
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

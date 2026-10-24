from types import SimpleNamespace

import pytest

from douyin_archive.provider.base import ProviderChanged
from douyin_archive.provider.douyin import (
    MAX_PAGE_CRASH_RECOVERIES,
    PageCrashed,
    PlaywrightDouyinSource,
    is_page_crash,
)

CRASH = RuntimeError("Page.evaluate: Target crashed")


def ids(start: int, count: int) -> list[str]:
    return [str(start + index) for index in range(count)]


def detail_payload(item_ids: list[str]) -> dict:
    return {
        "status_code": 0,
        "aweme_list": [
            {
                "aweme_id": remote_id,
                "author": {"nickname": "作者"},
                "video": {"play_addr": {"url_list": [f"https://media.test/{remote_id}.mp4"]}},
            }
            for remote_id in item_ids
        ],
    }


class FeedPage:
    """A likes feed that reveals 20 more ids per scroll and can crash on cue."""

    def __init__(self, feed: list[str], *, crash_after_reads: int | None = None, crash_on_details: bool = False) -> None:
        self.feed = feed
        self.crash_after_reads = crash_after_reads
        self.crash_on_details = crash_on_details
        self.reads = 0
        self.detail_calls: list[list[str]] = []
        self.routes: list[object] = []
        self.handlers: dict[str, object] = {}
        self.url = "https://www.douyin.com/user/self"
        self.crashed = False

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler: object) -> None:
        self.handlers.pop(event, None)

    async def route(self, pattern: str, handler: object) -> None:
        self.routes.append(handler)

    async def goto(self, url: str, **_kwargs) -> None:
        if self.crashed:
            raise CRASH

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None

    async def evaluate(self, script: str, arguments=None):
        if self.crashed:
            raise CRASH
        if "__yingcangActivateProfileTab" in script:
            return "active"
        if "__yingcangVisibleAccountIds" in script:
            self.reads += 1
            if self.crash_after_reads is not None and self.reads > self.crash_after_reads:
                self.crashed = True
                raise CRASH
            return self.feed[: 20 * self.reads]
        if "__yingcangScrollAccountPanel" in script:
            return True
        if "__yingcangFetchDetails" in script:
            requested = list(arguments["ids"])
            if self.crash_on_details:
                self.crashed = True
                raise CRASH
            self.detail_calls.append(requested)
            return detail_payload(requested)
        raise AssertionError(f"unexpected evaluation: {script[:60]}")


class Lease:
    def __init__(self, page: FeedPage) -> None:
        self.page = page
        self.released = False

    async def release(self) -> None:
        self.released = True


class SequenceCoordinator:
    def __init__(self, pages: list[FeedPage]) -> None:
        self.leases = [Lease(page) for page in pages]
        self.handed_out: list[Lease] = []

    async def acquire_page(self, *, viewport, serialized: bool = True) -> Lease:
        lease = self.leases[len(self.handed_out)]
        self.handed_out.append(lease)
        return lease


async def collect(source: PlaywrightDouyinSource, kind: str = "like") -> list[dict]:
    return [page async for page in source.iter_account_raw_pages(kind)]


def flattened_ids(pages: list[dict]) -> list[str]:
    return [item["aweme_id"] for page in pages for item in page["aweme_list"]]


async def test_scroll_crash_reopens_a_lightweight_page_and_finishes_the_feed() -> None:
    """Catches the catch-up sync dying when the renderer crashes deep in a feed."""
    feed = ids(1000, 60)
    first = FeedPage(feed, crash_after_reads=2)  # crashes after revealing 40 ids
    second = FeedPage(feed)
    coordinator = SequenceCoordinator([first, second])
    source = PlaywrightDouyinSource(coordinator)

    pages = await collect(source)

    assert flattened_ids(pages) == feed
    assert [page["has_more"] for page in pages] == [True, True, False]
    assert [page["cursor"] for page in pages] == ["20", "40", "60"]
    # The replacement page only fetches details for the unread tail.
    assert second.detail_calls == [feed[40:60]]
    assert coordinator.handed_out[0].released is True
    assert len(second.routes) == 1 and not first.routes


async def test_crash_while_fetching_details_is_not_retried_on_the_dead_page() -> None:
    feed = ids(2000, 20)
    first = FeedPage(feed, crash_on_details=True)
    second = FeedPage(feed)
    source = PlaywrightDouyinSource(SequenceCoordinator([first, second]))

    pages = await collect(source)

    assert flattened_ids(pages) == feed
    assert first.detail_calls == []
    assert second.detail_calls == [feed]


async def test_gives_up_after_bounded_reopens() -> None:
    feed = ids(3000, 40)
    pages = [FeedPage(feed, crash_after_reads=1) for _ in range(MAX_PAGE_CRASH_RECOVERIES + 1)]
    coordinator = SequenceCoordinator(pages)
    source = PlaywrightDouyinSource(coordinator)

    with pytest.raises(PageCrashed) as caught:
        await collect(source)

    assert caught.value.code == "DOUYIN_PAGE_CRASHED"
    assert len(coordinator.handed_out) == MAX_PAGE_CRASH_RECOVERIES + 1


async def test_ordinary_failures_do_not_trigger_a_reopen() -> None:
    class MissingTab(FeedPage):
        async def evaluate(self, script: str, arguments=None):
            if "__yingcangActivateProfileTab" in script:
                return "missing"
            return await super().evaluate(script, arguments)

    coordinator = SequenceCoordinator([MissingTab(ids(1, 20)), FeedPage(ids(1, 20))])
    source = PlaywrightDouyinSource(coordinator)

    with pytest.raises(ProviderChanged):
        await collect(source)

    assert len(coordinator.handed_out) == 1


async def test_lightweight_mode_blocks_media_but_keeps_page_requests() -> None:
    feed = ids(4000, 20)
    first = FeedPage(feed, crash_after_reads=0)
    second = FeedPage(feed)
    source = PlaywrightDouyinSource(SequenceCoordinator([first, second]))
    await collect(source)
    handler = second.routes[0]

    decisions = {}
    for resource_type in ("image", "media", "font", "document", "xhr", "script"):
        calls = []

        async def abort(calls=calls) -> None:
            calls.append("abort")

        async def proceed(calls=calls) -> None:
            calls.append("continue")

        route = SimpleNamespace(request=SimpleNamespace(resource_type=resource_type), abort=abort, continue_=proceed)
        await handler(route)
        decisions[resource_type] = calls[0]

    assert decisions == {
        "image": "abort",
        "media": "abort",
        "font": "abort",
        "document": "continue",
        "xhr": "continue",
        "script": "continue",
    }


def test_page_crash_detection_follows_wrapped_errors() -> None:
    wrapped = ProviderChanged("Douyin item detail response changed")
    wrapped.__cause__ = CRASH

    assert is_page_crash(CRASH)
    assert is_page_crash(wrapped)
    assert not is_page_crash(RuntimeError("Timeout 45000ms exceeded"))
    assert not is_page_crash(None)

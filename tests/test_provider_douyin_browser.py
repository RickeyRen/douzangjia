import logging

import pytest

from douyin_archive.provider import douyin as douyin_module
from douyin_archive.provider.base import ProviderChanged
from douyin_archive.provider.douyin import (
    ALL_FAVORITES_REMOTE_ID,
    PlaywrightDouyinSource,
    _payload_shape,
)


class FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.url = "https://www.douyin.com/user/self?private=page-token"

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler: object) -> None:
        if self.handlers.get(event) == handler:
            self.handlers.pop(event)


class FakeLease:
    def __init__(self) -> None:
        self.page = FakePage()
        self.released = False

    async def release(self) -> None:
        self.released = True


class FakeCoordinator:
    def __init__(self) -> None:
        self.lease = FakeLease()
        self.requested_viewports: list[tuple[int, int]] = []
        self.closed = False

    async def acquire_page(self, *, viewport: tuple[int, int]) -> FakeLease:
        self.requested_viewports.append(viewport)
        return self.lease


async def test_source_uses_coordinator_page_without_launching_browser() -> None:
    coordinator = FakeCoordinator()
    source = PlaywrightDouyinSource(coordinator)

    await source.open()

    assert coordinator.requested_viewports == [(1440, 1000)]
    assert "response" in coordinator.lease.page.handlers

    await source.close()

    assert coordinator.lease.released is True
    assert coordinator.lease.page.handlers == {}
    assert coordinator.closed is False


async def test_source_captures_current_listcollection_endpoint() -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.url = (
                "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
                "?device_platform=webapp"
            )
            self.headers = {"content-type": "application/json; charset=utf-8"}

        async def json(self) -> dict:
            return {"mix_list": [{"mix_id": "1001", "mix_name": "想去的地方"}]}

    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()
    await source._capture_response(FakeResponse())

    assert source._responses.qsize() == 1
    await source.close()


async def test_collection_wait_skips_flat_favorite_video_response() -> None:
    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()
    url = "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
    await source._responses.put((url, {"aweme_list": [{"aweme_id": "734"}]}))
    expected = {"mix_list": [{"mix_id": "1001", "mix_name": "想去的地方"}]}
    await source._responses.put((url, expected))

    payload = await source._wait_for_collections()

    assert payload == expected
    await source.close()


async def test_direct_collects_api_uses_browser_session_and_paginates() -> None:
    class DirectApiPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[dict] = []
            self.scripts: list[str] = []

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.scripts.append(script)
            self.calls.append(arguments)
            if arguments["path"].endswith("/collects/list/"):
                return {
                    "status_code": 0,
                    "collects_list": [
                        {
                            "collects_id_str": "2001",
                            "collects_name": "想去的地方",
                        }
                    ],
                    "has_more": 0,
                }
            cursor = arguments["params"]["cursor"]
            return {
                "status_code": 0,
                "aweme_list": [{"aweme_id": f"item-{cursor}"}],
                "cursor": 20,
                "has_more": int(cursor == 0),
            }

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = DirectApiPage()

    collections = await source._fetch_collections_api()
    pages = [page async for page in source._iter_collection_api("2001")]

    assert collections["collects_list"][0]["collects_id_str"] == "2001"
    assert collections["collects_list"][-1] == {
        "collects_id_str": ALL_FAVORITES_REMOTE_ID,
        "collects_name": "抖音全部收藏",
    }
    assert [page["aweme_list"][0]["aweme_id"] for page in pages] == [
        "item-0",
        "item-20",
    ]
    assert source._page.calls[0]["path"].endswith("/collects/list/")
    assert source._page.calls[1]["params"]["collects_id"] == "2001"
    assert "AbortController" in source._page.scripts[0]


async def test_all_favorites_use_the_flat_favorites_endpoint() -> None:
    class FlatFavoritesPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.paths: list[str] = []

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.paths.append(arguments["path"])
            return {
                "status_code": 0,
                "aweme_list": [{"aweme_id": "all-1"}],
                "cursor": 20,
                "has_more": 0,
            }

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = FlatFavoritesPage()

    pages = [page async for page in source._iter_collection_api(ALL_FAVORITES_REMOTE_ID)]

    assert pages[0]["aweme_list"][0]["aweme_id"] == "all-1"
    assert source._page.paths == ["/aweme/v1/web/aweme/listcollection/"]


async def test_browser_api_timeout_is_a_stable_provider_error() -> None:
    class TimedOutPage(FakePage):
        async def evaluate(self, script: str, arguments: dict) -> dict:
            return {"__browser_error": "timeout"}

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = TimedOutPage()

    with pytest.raises(ProviderChanged):
        await source._browser_json(source.COLLECTS_LIST_PATH, {"cursor": 0})


async def test_collection_api_retries_empty_transient_response() -> None:
    class TransientPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.attempts += 1
            if self.attempts == 1:
                return {"status_code": 0}
            return {"status_code": 0, "collects_list": [], "has_more": False}

        async def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 1_000

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = TransientPage()

    payload = await source._fetch_collections_api()

    assert "collects_list" in payload
    assert source._page.attempts == 2


def test_payload_shape_never_contains_response_values() -> None:
    shape = _payload_shape(
        {
            "status_code": 0,
            "data": {"secret_field": "private-value", "items": [{"id": "private-id"}]},
            "cursor": "private-cursor",
        }
    )

    assert shape == {
        "cursor": "str",
        "data": {"items": "list[1]", "secret_field": "str"},
        "status_code": "int",
    }
    assert "private-value" not in repr(shape)
    assert "private-id" not in repr(shape)
    assert "private-cursor" not in repr(shape)


async def test_click_candidates_uses_visible_duplicate_instead_of_hidden_first() -> None:
    class Candidate:
        def __init__(self, index: int, clicks: list[int]) -> None:
            self.index = index
            self.clicks = clicks

        async def is_visible(self, *, timeout: int) -> bool:
            return self.index == 1

        async def click(self, *, timeout: int) -> None:
            self.clicks.append(self.index)

    class TextLocator:
        def __init__(self, clicks: list[int]) -> None:
            self.candidates = [Candidate(0, clicks), Candidate(1, clicks)]
            self.first = self.candidates[0]

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    class TextPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.clicks: list[int] = []

        def get_by_text(self, label: str, *, exact: bool) -> TextLocator:
            assert label == "收藏夹"
            assert exact is True
            return TextLocator(self.clicks)

        async def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 800

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = TextPage()
    source._page = page

    await source._click_text_candidates(("收藏夹",))

    assert page.clicks == [1]


async def test_response_timeout_logs_only_sanitized_paths(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.url = "https://www.douyin.com/aweme/v1/web/tab/feed/?msToken=secret"
            self.headers = {"content-type": "text/html"}

    async def timeout_immediately(awaitable, *, timeout):
        awaitable.close()
        raise TimeoutError

    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()
    await source._capture_response(FakeResponse())
    monkeypatch.setattr(douyin_module.asyncio, "wait_for", timeout_immediately)

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderChanged):
        await source._wait_for(source.COLLECTION_PATH_MARKERS)

    assert "/user/self" in caplog.text
    assert "/aweme/v1/web/tab/feed/" in caplog.text
    assert "page-token" not in caplog.text
    assert "msToken" not in caplog.text
    assert "secret" not in caplog.text
    await source.close()

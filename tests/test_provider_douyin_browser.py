import logging

import pytest

from douyin_archive.provider import douyin as douyin_module
from douyin_archive.provider.base import ProviderChanged
from douyin_archive.provider.douyin import PlaywrightDouyinSource


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

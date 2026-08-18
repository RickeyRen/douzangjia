import asyncio
from pathlib import Path
from typing import Any

import pytest

from douyin_archive.browser_coordinator import (
    BrowserCoordinator,
    BrowserProfileLocked,
)
from douyin_archive.browser_profile import BrowserProfileStore


class FakePage:
    def __init__(self, *, redirected_url: str | None = None) -> None:
        self.url = "about:blank"
        self.redirected_url = redirected_url
        self.viewport: dict[str, int] | None = None
        self.closed = False

    async def set_viewport_size(self, viewport: dict[str, int]) -> None:
        self.viewport = viewport

    async def goto(self, url: str, **_options: Any) -> None:
        self.url = self.redirected_url or url

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(
        self,
        *,
        cookies: list[dict[str, object]] | None = None,
        redirected_url: str | None = None,
    ) -> None:
        self._cookies = cookies or []
        self.redirected_url = redirected_url
        self.pages: list[FakePage] = []
        self.added_cookies: list[dict[str, object]] = []
        self.closed = False

    async def new_page(self) -> FakePage:
        page = FakePage(redirected_url=self.redirected_url)
        self.pages.append(page)
        return page

    async def cookies(self) -> list[dict[str, object]]:
        return self._cookies

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.added_cookies.extend(cookies)
        self._cookies = cookies

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, context: FakeContext, *, error: Exception | None = None) -> None:
        self.context = context
        self.error = error
        self.persistent_launches: list[tuple[Path, dict[str, Any]]] = []

    async def launch_persistent_context(
        self, user_data_dir: str, **options: Any
    ) -> FakeContext:
        if self.error is not None:
            raise self.error
        self.persistent_launches.append((Path(user_data_dir), options))
        return self.context


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


def make_coordinator(
    tmp_path: Path,
    *,
    cookies: list[dict[str, object]] | None = None,
    redirected_url: str | None = None,
    error: Exception | None = None,
) -> tuple[BrowserCoordinator, FakePlaywright, FakeContext]:
    context = FakeContext(cookies=cookies, redirected_url=redirected_url)
    playwright = FakePlaywright(FakeChromium(context, error=error))
    coordinator = BrowserCoordinator(
        BrowserProfileStore(tmp_path), playwright_factory=lambda: playwright
    )
    return coordinator, playwright, context


async def test_coordinator_launches_persistent_context_once(tmp_path: Path) -> None:
    coordinator, playwright, _context = make_coordinator(tmp_path)

    await coordinator.start()
    await coordinator.start()

    launches = playwright.chromium.persistent_launches
    assert [path for path, _options in launches] == [
        tmp_path / "data" / "chromium-profile"
    ]
    assert launches[0][1]["viewport"] == {"width": 1280, "height": 800}
    await coordinator.close()


async def test_page_leases_are_serialized_and_close_only_their_page(
    tmp_path: Path,
) -> None:
    coordinator, _playwright, context = make_coordinator(tmp_path)
    first = await coordinator.acquire_page(viewport=(1280, 800))
    waiting = asyncio.create_task(coordinator.acquire_page(viewport=(1440, 1000)))
    await asyncio.sleep(0)

    assert not waiting.done()

    await first.release()
    second = await waiting
    assert first.page.closed is True
    assert second.page.viewport == {"width": 1440, "height": 1000}
    assert context.closed is False
    await second.release()
    await coordinator.close()


async def test_authenticated_session_requires_douyin_cookie_and_no_login_redirect(
    tmp_path: Path,
) -> None:
    cookies = [{"name": "sessionid_ss", "value": "kept", "domain": ".douyin.com"}]
    coordinator, _playwright, _context = make_coordinator(tmp_path, cookies=cookies)

    assert await coordinator.is_douyin_authenticated() is True

    await coordinator.close()


async def test_login_redirect_marks_persisted_cookie_as_stale(tmp_path: Path) -> None:
    cookies = [{"name": "sessionid", "value": "stale", "domain": ".douyin.com"}]
    coordinator, _playwright, _context = make_coordinator(
        tmp_path,
        cookies=cookies,
        redirected_url="https://www.douyin.com/passport/web/login/",
    )

    assert await coordinator.is_douyin_authenticated() is False

    await coordinator.close()


async def test_profile_lock_is_reported_without_deleting_profile(tmp_path: Path) -> None:
    coordinator, _playwright, _context = make_coordinator(
        tmp_path, error=RuntimeError("ProcessSingleton profile in use")
    )

    with pytest.raises(BrowserProfileLocked):
        await coordinator.start()

    assert (tmp_path / "data" / "chromium-profile").is_dir()

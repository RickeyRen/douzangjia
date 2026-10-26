import asyncio
from pathlib import Path
from typing import Any

import pytest

from douyin_archive.browser_coordinator import (
    BrowserCoordinator,
    BrowserProfileLocked,
)
from douyin_archive.browser_profile import BrowserProfileStore

DRIVER_CRASH = RuntimeError(
    "BrowserContext.cookies: unable to perform operation on "
    "<WriteUnixTransport closed=True reading=False 0x7fac919d1220>; "
    "the handler is closed"
)


class FakePage:
    def __init__(
        self,
        *,
        redirected_url: str | None = None,
        goto_error: Exception | None = None,
    ) -> None:
        self.url = "about:blank"
        self.redirected_url = redirected_url
        self.goto_error = goto_error
        self.viewport: dict[str, int] | None = None
        self.closed = False
        self.close_hangs = False
        self.events: list[str] = []

    async def set_viewport_size(self, viewport: dict[str, int]) -> None:
        self.viewport = viewport

    async def goto(self, url: str, **_options: Any) -> None:
        self.events.append(f"goto:{url}")
        if self.goto_error is not None:
            raise self.goto_error
        self.url = self.redirected_url or url

    async def close(self) -> None:
        self.events.append("close")
        if self.close_hangs:
            await asyncio.Event().wait()
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
        self.close_hangs = False
        self.page_close_hangs = False
        self.error: Exception | None = None
        self.goto_error: Exception | None = None
        self.close_handlers: list[Any] = []

    def on(self, event: str, handler: Any) -> None:
        if event == "close":
            self.close_handlers.append(handler)

    def emit_close(self) -> None:
        for handler in self.close_handlers:
            handler(self)

    async def new_page(self) -> FakePage:
        if self.error is not None:
            raise self.error
        page = FakePage(redirected_url=self.redirected_url, goto_error=self.goto_error)
        page.close_hangs = self.page_close_hangs
        self.pages.append(page)
        return page

    async def cookies(self) -> list[dict[str, object]]:
        if self.error is not None:
            raise self.error
        return self._cookies

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.added_cookies.extend(cookies)
        self._cookies = cookies

    async def close(self) -> None:
        if self.close_hangs:
            await asyncio.Event().wait()
        self.closed = True


class FakeChromium:
    def __init__(self, context: FakeContext, *, error: Exception | None = None) -> None:
        self.context = context
        self.error = error
        self.persistent_launches: list[tuple[Path, dict[str, Any]]] = []
        self.relaunch_contexts: list[FakeContext] = []

    async def launch_persistent_context(
        self, user_data_dir: str, **options: Any
    ) -> FakeContext:
        if self.error is not None:
            raise self.error
        self.persistent_launches.append((Path(user_data_dir), options))
        if len(self.persistent_launches) > 1 and self.relaunch_contexts:
            return self.relaunch_contexts.pop(0)
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


def make_crashing_coordinator(
    tmp_path: Path,
    *,
    cookies: list[dict[str, object]] | None = None,
) -> tuple[BrowserCoordinator, FakePlaywright, FakeContext, FakeContext]:
    """The first context dies like the Playwright driver did after its OOM."""
    coordinator, playwright, dead = make_coordinator(tmp_path, cookies=cookies)
    fresh = FakeContext(cookies=cookies)
    playwright.chromium.relaunch_contexts.append(fresh)
    return coordinator, playwright, dead, fresh


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


async def test_runtime_state_reports_started_and_serialized_busy_state(
    tmp_path: Path,
) -> None:
    """Catches the dashboard guessing whether the persistent browser is active."""
    coordinator, _playwright, _context = make_coordinator(tmp_path)

    assert coordinator.runtime_state() == {
        "started": False,
        "busy": False,
        "disconnected": False,
    }

    lease = await coordinator.acquire_page()
    assert coordinator.runtime_state() == {
        "started": True,
        "busy": True,
        "disconnected": False,
    }

    await lease.release()
    assert coordinator.runtime_state() == {
        "started": True,
        "busy": False,
        "disconnected": False,
    }
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


async def test_auxiliary_page_can_open_while_discovery_page_is_leased(
    tmp_path: Path,
) -> None:
    coordinator, _playwright, context = make_coordinator(tmp_path)
    discovery = await coordinator.acquire_page(viewport=(1440, 1000))

    auxiliary = await asyncio.wait_for(
        coordinator.acquire_page(viewport=(1440, 1000), serialized=False),
        timeout=0.1,
    )

    assert len(context.pages) == 2
    await auxiliary.release()
    assert discovery.page.closed is False
    await discovery.release()
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


async def test_driver_crash_relaunches_context_for_cookie_reads(tmp_path: Path) -> None:
    """Catches the sync loop reusing a dead Playwright connection forever."""
    cookies = [{"name": "sessionid", "value": "kept", "domain": ".douyin.com"}]
    coordinator, playwright, dead, fresh = make_crashing_coordinator(
        tmp_path, cookies=cookies
    )
    await coordinator.start()
    dead.error = DRIVER_CRASH

    assert await coordinator.cookies() == cookies

    assert len(playwright.chromium.persistent_launches) == 2
    assert dead.closed is True
    assert coordinator.context is fresh
    assert coordinator.runtime_state()["disconnected"] is False
    await coordinator.close()


async def test_driver_crash_relaunches_context_for_new_pages(tmp_path: Path) -> None:
    coordinator, _playwright, dead, fresh = make_crashing_coordinator(tmp_path)
    await coordinator.start()
    dead.error = DRIVER_CRASH

    lease = await coordinator.acquire_page(viewport=(1440, 1000))

    assert lease.context is fresh
    assert fresh.pages == [lease.page]
    await lease.release()
    assert coordinator.runtime_state()["busy"] is False
    await coordinator.close()


async def test_context_close_event_triggers_relaunch_on_next_use(tmp_path: Path) -> None:
    coordinator, playwright, dead, fresh = make_crashing_coordinator(tmp_path)
    await coordinator.start()

    dead.emit_close()
    assert coordinator.runtime_state()["started"] is False
    assert coordinator.runtime_state()["disconnected"] is True

    lease = await coordinator.acquire_page()

    assert lease.context is fresh
    assert len(playwright.chromium.persistent_launches) == 2
    await lease.release()
    await coordinator.close()


async def test_navigation_disconnect_retries_authentication_check(tmp_path: Path) -> None:
    cookies = [{"name": "sessionid_ss", "value": "kept", "domain": ".douyin.com"}]
    coordinator, playwright, dead, _fresh = make_crashing_coordinator(
        tmp_path, cookies=cookies
    )
    dead.goto_error = RuntimeError(
        "Page.goto: Target page, context or browser has been closed"
    )

    assert await coordinator.is_douyin_authenticated() is True

    assert len(playwright.chromium.persistent_launches) == 2
    assert coordinator.runtime_state()["busy"] is False
    await coordinator.close()


async def test_unrelated_errors_do_not_relaunch_browser(tmp_path: Path) -> None:
    coordinator, playwright, context = make_coordinator(tmp_path)
    await coordinator.start()
    context.error = ValueError("cookie payload rejected")

    with pytest.raises(ValueError):
        await coordinator.cookies()

    assert len(playwright.chromium.persistent_launches) == 1
    assert context.closed is False
    await coordinator.close()


async def test_probe_reports_connection_state_through_crash_and_recovery(
    tmp_path: Path,
) -> None:
    """Catches readiness staying green while the browser connection is dead."""
    coordinator, _playwright, dead, _fresh = make_crashing_coordinator(tmp_path)
    assert await coordinator.probe() == "not_started"

    await coordinator.start()
    assert await coordinator.probe() == "ok"

    dead.error = DRIVER_CRASH
    assert await coordinator.probe() == "disconnected"
    assert await coordinator.probe() == "disconnected"

    await coordinator.cookies()
    assert await coordinator.probe() == "ok"
    await coordinator.close()
    assert await coordinator.probe() == "not_started"


async def test_release_navigates_to_blank_before_closing_page(tmp_path: Path) -> None:
    """Catches closed Douyin pages staying in the driver through Web Worker sessions."""
    coordinator, _playwright, _context = make_coordinator(tmp_path)
    lease = await coordinator.acquire_page()
    await lease.page.goto("https://www.douyin.com/user/self")

    await lease.release()
    await lease.release()

    assert lease.page.events == [
        "goto:https://www.douyin.com/user/self",
        "goto:about:blank",
        "close",
    ]
    await coordinator.close()


async def test_release_still_closes_page_when_blank_navigation_fails(
    tmp_path: Path,
) -> None:
    coordinator, _playwright, context = make_coordinator(tmp_path)
    context.goto_error = DRIVER_CRASH
    lease = await coordinator.acquire_page()

    await lease.release()

    assert lease.page.events == ["goto:about:blank", "close"]
    assert coordinator.runtime_state()["busy"] is False
    next_lease = await asyncio.wait_for(coordinator.acquire_page(), timeout=0.1)
    await next_lease.release()
    await coordinator.close()


class RecordingProfileStore(BrowserProfileStore):
    def __init__(self, archive_root: Path) -> None:
        super().__init__(archive_root)
        self.kills = 0

    def kill_singleton_owner(self, **_kwargs: Any) -> bool:
        self.kills += 1
        return True


async def test_hung_page_close_discards_browser_and_relaunches_on_next_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches the day-long stall where page.close() never answered and kept the sync lock."""
    from douyin_archive import browser_coordinator as module

    monkeypatch.setattr(module, "PAGE_CLOSE_TIMEOUT_SECONDS", 0.05)
    coordinator, playwright, stuck, fresh = make_crashing_coordinator(tmp_path)
    stuck.page_close_hangs = True
    lease = await coordinator.acquire_page()

    await asyncio.wait_for(lease.release(), timeout=2)

    assert lease.page.events == ["goto:about:blank", "close"]
    assert coordinator.runtime_state()["busy"] is False
    assert stuck.closed is True
    assert playwright.stopped is True
    assert await coordinator.probe() == "disconnected"

    next_lease = await asyncio.wait_for(coordinator.acquire_page(), timeout=1)
    assert next_lease.context is fresh
    assert len(playwright.chromium.persistent_launches) == 2
    await next_lease.release()
    await coordinator.close()


async def test_hung_context_close_kills_chromium_holding_the_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from douyin_archive import browser_coordinator as module

    monkeypatch.setattr(module, "CONTEXT_CLOSE_TIMEOUT_SECONDS", 0.05)
    context = FakeContext()
    context.close_hangs = True
    playwright = FakePlaywright(FakeChromium(context))
    store = RecordingProfileStore(tmp_path)
    coordinator = BrowserCoordinator(store, playwright_factory=lambda: playwright)
    await coordinator.start()

    await asyncio.wait_for(coordinator.discard_stuck(), timeout=2)

    assert store.kills == 1
    assert playwright.stopped is True
    assert await coordinator.probe() == "disconnected"
    assert coordinator.runtime_state()["busy"] is False


async def test_discard_stuck_without_browser_is_a_no_op(tmp_path: Path) -> None:
    coordinator, _playwright, _context = make_coordinator(tmp_path)

    await coordinator.discard_stuck()

    assert await coordinator.probe() == "not_started"

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlsplit

from .browser_launch import chromium_persistent_launch_options
from .browser_profile import BrowserProfileStore

LOGIN_VIEWPORT = (1280, 800)
FAVORITES_VIEWPORT = (1440, 1000)
FAVORITES_URL = (
    "https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection"
)
DOUYIN_SESSION_COOKIES = {"sessionid", "sessionid_ss"}
PROBE_TIMEOUT_SECONDS = 5.0
# Playwright surfaces a dead driver or browser through several error shapes;
# a crashed Node driver only leaves the closed asyncio transport message.
DISCONNECT_MARKERS = (
    "handler is closed",
    "has been closed",
    "connection closed",
    "browser closed",
    "target closed",
)

T = TypeVar("T")


def is_disconnect_error(error: BaseException) -> bool:
    if type(error).__name__ == "TargetClosedError":
        return True
    message = str(error).lower()
    return any(marker in message for marker in DISCONNECT_MARKERS)


class BrowserProfileLocked(RuntimeError):
    """Raised when Chromium reports that another process owns the profile."""


@dataclass(slots=True)
class CoordinatorPageLease:
    coordinator: BrowserCoordinator
    page: Any
    context: Any
    serialized: bool = True
    _released: bool = False

    async def __aenter__(self) -> Any:
        return self.page

    async def __aexit__(self, *_exc: object) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            with suppress(Exception):
                await self.page.close()
        finally:
            if self.serialized:
                self.coordinator._release_lease()


class BrowserCoordinator:
    """Own one persistent Chromium context and serialize page consumers."""

    def __init__(
        self,
        profile_store: BrowserProfileStore,
        *,
        launch_options: Callable[[], dict[str, Any]] = chromium_persistent_launch_options,
        playwright_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.profile_store = profile_store
        self._launch_options = launch_options
        self._playwright_factory = playwright_factory
        self._playwright: Any = None
        self._context: Any = None
        self._context_closed = False
        self._disconnected = False
        self._start_lock = asyncio.Lock()
        self._lease_lock = asyncio.Lock()

    @property
    def context(self) -> Any:
        if self._context is None:
            raise RuntimeError("browser coordinator is not started")
        return self._context

    def runtime_state(self) -> dict[str, object]:
        return {
            "started": self._is_live(),
            "busy": self._lease_lock.locked(),
            "disconnected": self._disconnected,
        }

    async def probe(self) -> str:
        """Report ``ok``, ``not_started``, ``disconnected`` or ``unresponsive``."""
        context = self._context
        if context is None or self._context_closed:
            return "disconnected" if self._disconnected or context else "not_started"
        try:
            await asyncio.wait_for(context.cookies(), timeout=PROBE_TIMEOUT_SECONDS)
        except TimeoutError:
            return "unresponsive"
        except Exception as error:
            if not is_disconnect_error(error):
                raise
            await self._discard(context)
            return "disconnected"
        return "ok"

    async def start(self) -> None:
        if self._is_live():
            return
        async with self._start_lock:
            if self._is_live():
                return
            if self._context is not None:
                await self._discard_locked(self._context)
            profile_path = self.profile_store.prepare()
            self._playwright = await self._create_playwright()
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(
                    str(profile_path),
                    **self._launch_options(),
                    viewport={"width": LOGIN_VIEWPORT[0], "height": LOGIN_VIEWPORT[1]},
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
            except Exception as error:
                playwright = self._playwright
                self._playwright = None
                if playwright is not None:
                    with suppress(Exception):
                        await playwright.stop()
                message = str(error).lower()
                if "processsingleton" in message or "profile in use" in message:
                    raise BrowserProfileLocked(
                        "persistent Chromium profile is already in use"
                    ) from error
                raise
            self._context_closed = False
            self._disconnected = False
            context = self._context
            on = getattr(context, "on", None)
            if on is not None:
                on("close", lambda *_args: self._mark_closed(context))

    async def acquire_page(
        self,
        *,
        viewport: tuple[int, int] = LOGIN_VIEWPORT,
        serialized: bool = True,
    ) -> CoordinatorPageLease:
        if serialized:
            await self._lease_lock.acquire()
        try:
            async def open_page(context: Any) -> CoordinatorPageLease:
                page = await context.new_page()
                await page.set_viewport_size(
                    {"width": viewport[0], "height": viewport[1]}
                )
                return CoordinatorPageLease(self, page, context, serialized=serialized)

            return await self._with_context(open_page)
        except BaseException:
            if serialized:
                self._release_lease()
            raise

    async def has_douyin_session_cookie(self) -> bool:
        cookies = await self.cookies()
        return any(
            str(cookie.get("name", "")) in DOUYIN_SESSION_COOKIES
            and str(cookie.get("domain", "")).lstrip(".").lower().endswith("douyin.com")
            for cookie in cookies
        )

    async def cookies(self) -> list[dict[str, object]]:
        return await self._with_context(lambda context: context.cookies())

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        await self._with_context(lambda context: context.add_cookies(cookies))

    async def is_douyin_authenticated(self) -> bool:
        try:
            return await self._check_douyin_authenticated()
        except Exception as error:
            if not is_disconnect_error(error) or self._context is None:
                raise
            await self._discard(self._context)
        return await self._check_douyin_authenticated()

    async def _check_douyin_authenticated(self) -> bool:
        if not await self.has_douyin_session_cookie():
            return False

        lease = await self.acquire_page(viewport=FAVORITES_VIEWPORT)
        try:
            await lease.page.goto(
                FAVORITES_URL,
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            current = urlsplit(str(lease.page.url))
            path = current.path.lower()
            return "passport" not in path and not path.startswith("/login")
        finally:
            await lease.release()

    async def close(self) -> None:
        async with self._lease_lock:
            context = self._context
            playwright = self._playwright
            self._context = None
            self._playwright = None
            self._context_closed = False
            self._disconnected = False
            if context is not None:
                with suppress(Exception):
                    await context.close()
            if playwright is not None:
                with suppress(Exception):
                    await playwright.stop()

    def _is_live(self) -> bool:
        return self._context is not None and not self._context_closed

    def _mark_closed(self, context: Any) -> None:
        if self._context is context:
            self._context_closed = True
            self._disconnected = True

    async def _with_context(self, operation: Callable[[Any], Awaitable[T]]) -> T:
        """Run ``operation`` once more on a relaunched context after a disconnect."""
        await self.start()
        context = self.context
        try:
            return await operation(context)
        except Exception as error:
            if not is_disconnect_error(error):
                raise
            await self._discard(context)
        await self.start()
        return await operation(self.context)

    async def _discard(self, context: Any) -> None:
        async with self._start_lock:
            await self._discard_locked(context)

    async def _discard_locked(self, context: Any) -> None:
        # Another caller may already have replaced the dead context.
        if self._context is not context:
            return
        playwright = self._playwright
        self._context = None
        self._playwright = None
        self._context_closed = False
        self._disconnected = True
        with suppress(Exception):
            await context.close()
        if playwright is not None:
            with suppress(Exception):
                await playwright.stop()

    async def _create_playwright(self) -> Any:
        if self._playwright_factory is None:
            from playwright.async_api import async_playwright

            return await async_playwright().start()
        value = self._playwright_factory()
        return await value if inspect.isawaitable(value) else value

    def _release_lease(self) -> None:
        if self._lease_lock.locked():
            self._lease_lock.release()

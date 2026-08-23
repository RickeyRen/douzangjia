from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .browser_launch import chromium_persistent_launch_options
from .browser_profile import BrowserProfileStore

LOGIN_VIEWPORT = (1280, 800)
FAVORITES_VIEWPORT = (1440, 1000)
FAVORITES_URL = (
    "https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection"
)
DOUYIN_SESSION_COOKIES = {"sessionid", "sessionid_ss"}


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
        self._start_lock = asyncio.Lock()
        self._lease_lock = asyncio.Lock()

    @property
    def context(self) -> Any:
        if self._context is None:
            raise RuntimeError("browser coordinator is not started")
        return self._context

    async def start(self) -> None:
        if self._context is not None:
            return
        async with self._start_lock:
            if self._context is not None:
                return
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

    async def acquire_page(
        self,
        *,
        viewport: tuple[int, int] = LOGIN_VIEWPORT,
        serialized: bool = True,
    ) -> CoordinatorPageLease:
        if serialized:
            await self._lease_lock.acquire()
        try:
            await self.start()
            page = await self.context.new_page()
            await page.set_viewport_size(
                {"width": viewport[0], "height": viewport[1]}
            )
            return CoordinatorPageLease(
                self, page, self.context, serialized=serialized
            )
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
        await self.start()
        return await self.context.cookies()

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        await self.start()
        await self.context.add_cookies(cookies)

    async def is_douyin_authenticated(self) -> bool:
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
            if context is not None:
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

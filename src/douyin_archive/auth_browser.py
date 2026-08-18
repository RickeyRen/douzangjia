from __future__ import annotations

import secrets
import time
from contextlib import suppress
from dataclasses import dataclass, field
from math import hypot
from typing import Any

from .auth_service import BrowserLogin
from .browser_launch import chromium_launch_options

LOGIN_VIEWPORT_WIDTH = 520
LOGIN_VIEWPORT_HEIGHT = 680
DRAG_START_DISTANCE = 4.0


@dataclass(slots=True)
class PointerGesture:
    origin: tuple[float, float] | None = None
    pressed: bool = False


async def _click_element_at(page: Any, x: float, y: float) -> None:
    """Click the actual interactive DOM element at a viewport coordinate."""

    surface = page
    local_x = x
    local_y = y
    handles: list[Any] = []
    try:
        for _depth in range(6):
            handle = await surface.evaluate_handle(
                """
                ({x, y}) => {
                  const hit = document.elementFromPoint(x, y);
                  if (!hit) return null;
                  return hit.closest(
                    'button, a, [role="button"], [onclick], input, label'
                  ) || hit;
                }
                """,
                {"x": local_x, "y": local_y},
            )
            handles.append(handle)
            element = handle.as_element()
            if element is None:
                await page.mouse.click(x, y)
                return
            nested_frame = await element.content_frame()
            if nested_frame is None:
                await element.click(timeout=2_000)
                return
            bounds = await element.evaluate(
                "element => { const rect = element.getBoundingClientRect(); "
                "return {x: rect.x, y: rect.y}; }"
            )
            local_x -= float(bounds["x"])
            local_y -= float(bounds["y"])
            surface = nested_frame
        await page.mouse.click(x, y)
    finally:
        for handle in reversed(handles):
            await handle.dispose()


async def replay_pointer(
    page: Any,
    gesture: PointerGesture,
    action: str,
    x: float,
    y: float,
) -> None:
    """Forward one normalized pointer event to the login viewport."""

    if action not in {"down", "move", "up"}:
        raise ValueError("unsupported pointer action")
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("pointer coordinates must be normalized")

    viewport_x = x * LOGIN_VIEWPORT_WIDTH
    viewport_y = y * LOGIN_VIEWPORT_HEIGHT
    if action == "down":
        if gesture.pressed:
            await page.mouse.up()
        gesture.origin = (viewport_x, viewport_y)
        gesture.pressed = False
    elif action == "move":
        if gesture.origin is None:
            await page.mouse.move(viewport_x, viewport_y)
            return
        if not gesture.pressed and hypot(
            viewport_x - gesture.origin[0], viewport_y - gesture.origin[1]
        ) >= DRAG_START_DISTANCE:
            await page.mouse.move(*gesture.origin)
            await page.mouse.down()
            gesture.pressed = True
        if gesture.pressed:
            await page.mouse.move(viewport_x, viewport_y)
    elif action == "up":
        if gesture.origin is None:
            return
        if gesture.pressed:
            await page.mouse.move(viewport_x, viewport_y)
            await page.mouse.up()
        else:
            await _click_element_at(page, viewport_x, viewport_y)
        gesture.origin = None
        gesture.pressed = False
        await page.wait_for_timeout(120)


async def replay_drag(page: Any, points: list[tuple[float, float]]) -> None:
    """Replay a user-provided normalized drag path in the login viewport."""

    if len(points) < 2:
        raise ValueError("a drag path requires at least two points")
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in points):
        raise ValueError("drag points must be normalized")

    first_x, first_y = points[0]
    await page.mouse.move(
        first_x * LOGIN_VIEWPORT_WIDTH,
        first_y * LOGIN_VIEWPORT_HEIGHT,
    )
    await page.mouse.down()
    for x, y in points[1:]:
        await page.mouse.move(
            x * LOGIN_VIEWPORT_WIDTH,
            y * LOGIN_VIEWPORT_HEIGHT,
        )
        await page.wait_for_timeout(16)
    await page.mouse.up()
    await page.wait_for_timeout(700)


@dataclass(slots=True)
class _BrowserSession:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    deadline: float
    pointer_gesture: PointerGesture = field(default_factory=PointerGesture)


class AuthBrowser:
    """Temporary headless Chromium contexts used only for Douyin QR login."""

    LOGIN_URL = "https://www.douyin.com/"

    def __init__(self) -> None:
        self._sessions: dict[str, _BrowserSession] = {}

    async def start(self, *, timeout_seconds: int) -> BrowserLogin:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright

        login_id = secrets.token_urlsafe(18)
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(**chromium_launch_options())
        context = await browser.new_context(
            viewport={"width": LOGIN_VIEWPORT_WIDTH, "height": LOGIN_VIEWPORT_HEIGHT},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()
        session = _BrowserSession(
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
            deadline=time.monotonic() + timeout_seconds,
        )
        self._sessions[login_id] = session
        try:
            await page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=45_000)
            await self._open_login_dialog(page)
            screenshot = await self._capture_login_area(page)
            return BrowserLogin(login_id, "awaiting_scan", screenshot)
        except PlaywrightError:
            await self.close(login_id)
            return BrowserLogin(login_id, "failed", None, "DOUYIN_LOGIN_PAGE_FAILED")

    async def poll(self, login_id: str) -> BrowserLogin:
        session = self._sessions[login_id]
        if time.monotonic() >= session.deadline:
            return BrowserLogin(login_id, "expired", None)
        cookies = await session.context.cookies()
        if any(
            cookie.get("name") in {"sessionid", "sessionid_ss"}
            and str(cookie.get("domain", "")).endswith("douyin.com")
            for cookie in cookies
        ):
            return BrowserLogin(login_id, "authenticated", None)
        screenshot = await self._capture_login_area(session.page)
        return BrowserLogin(login_id, "awaiting_scan", screenshot)

    async def cookies(self, login_id: str) -> list[dict[str, object]]:
        return await self._sessions[login_id].context.cookies()

    async def drag(self, login_id: str, points: list[tuple[float, float]]) -> None:
        await replay_drag(self._sessions[login_id].page, points)

    async def pointer(
        self, login_id: str, action: str, x: float, y: float
    ) -> None:
        session = self._sessions[login_id]
        await replay_pointer(session.page, session.pointer_gesture, action, x, y)

    async def close(self, login_id: str) -> None:
        session = self._sessions.pop(login_id, None)
        if session is None:
            return
        await session.context.close()
        await session.browser.close()
        await session.playwright.stop()

    async def cancel(self, login_id: str) -> None:
        await self.close(login_id)

    @staticmethod
    async def _open_login_dialog(page: Any) -> None:
        from playwright.async_api import Error as PlaywrightError

        for selector in (
            "button:has-text('登录')",
            "text=登录",
            "[data-e2e='login-button']",
        ):
            locator = page.locator(selector).first
            with suppress(PlaywrightError):
                if await locator.is_visible(timeout=1_500):
                    await locator.click(timeout=3_000)
                    await page.wait_for_timeout(1_200)
                    return

    @staticmethod
    async def _capture_login_area(page: Any) -> bytes:
        return await page.screenshot(type="png", full_page=False)

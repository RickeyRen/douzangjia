from __future__ import annotations

import secrets
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from .auth_service import BrowserLogin


@dataclass(slots=True)
class _BrowserSession:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    deadline: float


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
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 520, "height": 680},
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
        from playwright.async_api import Error as PlaywrightError

        for selector in (
            "img[src*='qrcode']",
            "img[alt*='二维码']",
            "[class*='qr'] canvas",
            "[class*='login'] canvas",
        ):
            locator = page.locator(selector).first
            with suppress(PlaywrightError):
                box = await locator.bounding_box(timeout=1_000)
                if box and 100 <= box["width"] <= 500 and 100 <= box["height"] <= 500:
                    padding = 36
                    clip = {
                        "x": max(0, box["x"] - padding),
                        "y": max(0, box["y"] - padding),
                        "width": min(520 - max(0, box["x"] - padding), box["width"] + 72),
                        "height": min(680 - max(0, box["y"] - padding), box["height"] + 72),
                    }
                    return await page.screenshot(type="png", clip=clip)
        return await page.screenshot(type="png", full_page=False)

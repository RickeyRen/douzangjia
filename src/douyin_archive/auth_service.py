from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from .db import Database
from .security import CookieCipher

LoginState = Literal[
    "starting", "awaiting_scan", "authenticated", "expired", "failed", "cancelled"
]

REQUIRED_DOUYIN_COOKIES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "passport_csrf_token",
    "passport_csrf_token_default",
    "odin_tt",
    "ttwid",
    "__ac_nonce",
    "__ac_signature",
    "msToken",
}
COOKIE_FIELDS = {
    "name",
    "value",
    "domain",
    "path",
    "expires",
    "httpOnly",
    "secure",
    "sameSite",
}


@dataclass(frozen=True, slots=True)
class BrowserLogin:
    id: str
    state: LoginState
    screenshot_png: bytes | None
    error_code: str | None = None


class AuthBrowserProtocol(Protocol):
    async def start(self, *, timeout_seconds: int) -> BrowserLogin: ...

    async def poll(self, login_id: str) -> BrowserLogin: ...

    async def cookies(self, login_id: str) -> list[dict[str, object]]: ...

    async def drag(self, login_id: str, points: list[tuple[float, float]]) -> None: ...

    async def pointer(
        self, login_id: str, action: str, x: float, y: float
    ) -> None: ...

    async def close(self, login_id: str) -> None: ...

    async def cancel(self, login_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class LoginStatus:
    id: str
    state: LoginState
    created_at: datetime
    expires_at: datetime
    screenshot_png: bytes | None
    error_code: str | None = None

    @classmethod
    def create(
        cls,
        *,
        login_id: str,
        state: LoginState,
        screenshot_png: bytes | None,
        timeout_seconds: int = 300,
        error_code: str | None = None,
    ) -> LoginStatus:
        now = datetime.now(UTC)
        return cls(
            id=login_id,
            state=state,
            created_at=now,
            expires_at=now + timedelta(seconds=timeout_seconds),
            screenshot_png=screenshot_png,
            error_code=error_code,
        )

    def with_state(
        self,
        state: LoginState,
        *,
        screenshot_png: bytes | None,
        error_code: str | None = None,
    ) -> LoginStatus:
        return replace(
            self,
            state=state,
            screenshot_png=screenshot_png,
            error_code=error_code,
        )

    def as_public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "state": self.state,
            "expiresAt": self.expires_at.isoformat(),
            "hasScreenshot": self.screenshot_png is not None,
        }
        if self.error_code:
            result["errorCode"] = self.error_code
        return result


class AuthService:
    def __init__(
        self,
        database: Database,
        cipher: CookieCipher,
        browser: AuthBrowserProtocol,
        *,
        timeout_seconds: int = 300,
        on_authenticated: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        self.database = database
        self.cipher = cipher
        self.browser = browser
        self.timeout_seconds = timeout_seconds
        self.on_authenticated = on_authenticated
        self.sessions: dict[str, LoginStatus] = {}

    async def begin_login(self) -> LoginStatus:
        for login_id, status in list(self.sessions.items()):
            if status.state in {"starting", "awaiting_scan"}:
                await self.cancel(login_id)
        browser_login = await self.browser.start(timeout_seconds=self.timeout_seconds)
        status = LoginStatus.create(
            login_id=browser_login.id,
            state=browser_login.state,
            screenshot_png=browser_login.screenshot_png,
            timeout_seconds=self.timeout_seconds,
            error_code=browser_login.error_code,
        )
        self.sessions[status.id] = status
        return status

    async def get_status(self, login_id: str) -> LoginStatus:
        status = self._get(login_id)
        if status.state not in {"starting", "awaiting_scan"}:
            return status
        if datetime.now(UTC) >= status.expires_at:
            await self.browser.cancel(login_id)
            expired = status.with_state("expired", screenshot_png=None)
            self.sessions[login_id] = expired
            return expired

        browser_login = await self.browser.poll(login_id)
        status = status.with_state(
            browser_login.state,
            screenshot_png=browser_login.screenshot_png,
            error_code=browser_login.error_code,
        )
        if browser_login.state == "authenticated":
            cookies = self._filter_cookies(await self.browser.cookies(login_id))
            encrypted = self.cipher.encrypt(cookies)
            now = int(time.time())
            await self.database.execute(
                "INSERT INTO auth_sessions "
                "(provider, encrypted_cookies, status, last_verified_at, updated_at) "
                "VALUES ('douyin', ?, 'authenticated', ?, ?) "
                "ON CONFLICT(provider) DO UPDATE SET "
                "encrypted_cookies=excluded.encrypted_cookies, status=excluded.status, "
                "last_verified_at=excluded.last_verified_at, updated_at=excluded.updated_at",
                (encrypted, now, now),
            )
            await self.browser.close(login_id)
            status = status.with_state("authenticated", screenshot_png=None)
            if self.on_authenticated is not None:
                await self.on_authenticated()
        elif browser_login.state in {"failed", "expired"}:
            await self.browser.close(login_id)
            status = status.with_state(
                browser_login.state,
                screenshot_png=None,
                error_code=browser_login.error_code,
            )
        self.sessions[login_id] = status
        return status

    async def cancel(self, login_id: str) -> LoginStatus:
        status = self._get(login_id)
        if status.state in {"starting", "awaiting_scan"}:
            await self.browser.cancel(login_id)
        cancelled = status.with_state("cancelled", screenshot_png=None)
        self.sessions[login_id] = cancelled
        return cancelled

    async def drag(
        self, login_id: str, points: list[tuple[float, float]]
    ) -> LoginStatus:
        status = self._get(login_id)
        if status.state not in {"starting", "awaiting_scan"}:
            raise ValueError("login session is not interactive")
        await self.browser.drag(login_id, points)
        return await self.get_status(login_id)

    async def pointer(
        self, login_id: str, action: str, x: float, y: float
    ) -> None:
        status = self._get(login_id)
        if status.state not in {"starting", "awaiting_scan"}:
            raise ValueError("login session is not interactive")
        await self.browser.pointer(login_id, action, x, y)

    async def load_cookies(self) -> list[dict[str, object]] | None:
        row = await self.database.fetchone(
            "SELECT encrypted_cookies FROM auth_sessions "
            "WHERE provider='douyin' AND status='authenticated'"
        )
        if row is None:
            return None
        value = self.cipher.decrypt(bytes(row["encrypted_cookies"]))
        return value if isinstance(value, list) else None

    async def close(self) -> None:
        for login_id, status in list(self.sessions.items()):
            if status.state in {"starting", "awaiting_scan"}:
                await self.browser.cancel(login_id)

    def _get(self, login_id: str) -> LoginStatus:
        try:
            return self.sessions[login_id]
        except KeyError as error:
            raise KeyError("login session not found") from error

    @staticmethod
    def _filter_cookies(cookies: list[dict[str, object]]) -> list[dict[str, object]]:
        filtered: list[dict[str, object]] = []
        for cookie in cookies:
            domain = str(cookie.get("domain", "")).lstrip(".").lower()
            name = str(cookie.get("name", ""))
            if (domain == "douyin.com" or domain.endswith(".douyin.com")) and (
                name in REQUIRED_DOUYIN_COOKIES
            ):
                filtered.append({key: cookie[key] for key in COOKIE_FIELDS if key in cookie})
        return filtered

from pathlib import Path

import pytest

from douyin_archive.auth_service import AuthService, BrowserLogin
from douyin_archive.db import Database
from douyin_archive.security import CookieCipher


class FakeAuthBrowser:
    def __init__(self) -> None:
        self.state = "awaiting_scan"
        self.screenshot = b"\x89PNG\r\nqr"
        self.cookie_values = [
            {"domain": ".douyin.com", "name": "sessionid", "value": "secret"},
            {"domain": ".douyin.com", "name": "unneeded", "value": "discard-me"},
            {"domain": ".example.com", "name": "sessionid", "value": "other-site"},
        ]
        self.closed: list[str] = []

    async def start(self, *, timeout_seconds: int) -> BrowserLogin:
        assert timeout_seconds == 300
        return BrowserLogin("login-1", self.state, self.screenshot)

    async def poll(self, login_id: str) -> BrowserLogin:
        return BrowserLogin(login_id, self.state, self.screenshot)

    async def cookies(self, login_id: str) -> list[dict[str, object]]:
        assert login_id == "login-1"
        return self.cookie_values

    async def close(self, login_id: str) -> None:
        self.closed.append(login_id)

    async def cancel(self, login_id: str) -> None:
        self.closed.append(login_id)


@pytest.fixture
async def auth_components(tmp_path: Path, master_key: str):
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    browser = FakeAuthBrowser()
    service = AuthService(database, CookieCipher(master_key), browser)
    yield service, browser, database
    await database.close()


async def test_successful_login_encrypts_only_required_douyin_cookies(
    auth_components,
) -> None:
    service, browser, database = auth_components
    await service.begin_login()
    browser.state = "authenticated"

    status = await service.get_status("login-1")
    row = await database.fetchone(
        "SELECT encrypted_cookies FROM auth_sessions WHERE provider='douyin'"
    )

    assert status.state == "authenticated"
    assert row is not None
    encrypted = bytes(row["encrypted_cookies"])
    assert b"secret" not in encrypted
    assert b"discard-me" not in encrypted
    assert b"other-site" not in encrypted
    assert service.cipher.decrypt(encrypted) == [
        {"domain": ".douyin.com", "name": "sessionid", "value": "secret"}
    ]
    assert browser.closed == ["login-1"]


async def test_public_status_never_contains_cookie_values(auth_components) -> None:
    service, _, _ = auth_components
    status = await service.begin_login()
    public = status.as_public_dict()
    assert public == {
        "id": "login-1",
        "state": "awaiting_scan",
        "expiresAt": status.expires_at.isoformat(),
        "hasScreenshot": True,
    }
    assert "secret" not in repr(public)


async def test_cancel_closes_temporary_browser(auth_components) -> None:
    service, browser, _ = auth_components
    await service.begin_login()
    status = await service.cancel("login-1")
    assert status.state == "cancelled"
    assert browser.closed == ["login-1"]


async def test_authenticated_login_notifies_runtime_for_initial_sync(
    tmp_path: Path, master_key: str
) -> None:
    database = Database(tmp_path / "archive.sqlite3")
    await database.open()
    browser = FakeAuthBrowser()
    called = 0

    async def on_authenticated() -> None:
        nonlocal called
        called += 1

    service = AuthService(
        database,
        CookieCipher(master_key),
        browser,
        on_authenticated=on_authenticated,
    )
    await service.begin_login()
    browser.state = "authenticated"
    await service.get_status("login-1")

    assert called == 1
    await database.close()

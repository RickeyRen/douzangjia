from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.auth_service import LoginStatus
from douyin_archive.config import Settings


class FakeAuthService:
    def __init__(self) -> None:
        self.status = LoginStatus.create(
            login_id="login-1", state="awaiting_scan", screenshot_png=b"\x89PNG\r\nqr"
        )

    async def begin_login(self) -> LoginStatus:
        return self.status

    async def get_status(self, login_id: str) -> LoginStatus:
        assert login_id == "login-1"
        return self.status

    async def cancel(self, login_id: str) -> LoginStatus:
        assert login_id == "login-1"
        self.status = self.status.with_state("cancelled", screenshot_png=None)
        return self.status


def authenticated_client(tmp_path: Path, master_key: str) -> tuple[TestClient, str]:
    app = create_app(
        Settings(archive_root=tmp_path, master_key=master_key),
        auth_service=FakeAuthService(),
    )
    client = TestClient(app)
    client.__enter__()
    client.post("/api/setup", json={"password": "a secure local passphrase"})
    csrf = client.cookies.get("archive_csrf")
    assert csrf
    return client, csrf


def test_login_routes_return_status_and_png_without_secrets(
    tmp_path: Path, master_key: str
) -> None:
    client, csrf = authenticated_client(tmp_path, master_key)
    try:
        started = client.post("/api/douyin/login", headers={"X-CSRF-Token": csrf})
        status = client.get("/api/douyin/login/login-1")
        screenshot = client.get("/api/douyin/login/login-1/qr.png")
    finally:
        client.__exit__(None, None, None)

    assert started.status_code == 201
    assert status.json()["state"] == "awaiting_scan"
    assert "cookie" not in status.text.lower()
    assert screenshot.headers["content-type"] == "image/png"
    assert screenshot.content.startswith(b"\x89PNG")


def test_cancel_route_requires_csrf_and_clears_screenshot(
    tmp_path: Path, master_key: str
) -> None:
    client, csrf = authenticated_client(tmp_path, master_key)
    try:
        rejected = client.post("/api/douyin/login/login-1/cancel")
        cancelled = client.post(
            "/api/douyin/login/login-1/cancel", headers={"X-CSRF-Token": csrf}
        )
        screenshot = client.get("/api/douyin/login/login-1/qr.png")
    finally:
        client.__exit__(None, None, None)

    assert rejected.status_code == 403
    assert cancelled.json()["state"] == "cancelled"
    assert screenshot.status_code == 404

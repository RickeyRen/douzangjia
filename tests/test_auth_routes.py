import sqlite3
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
        self.dragged: list[tuple[str, list[tuple[float, float]]]] = []
        self.pointer_events: list[tuple[str, str, float, float]] = []
        self.keys: list[tuple[str, str]] = []
        self.status_refresh_modes: list[bool] = []
        self.frames = [b"\xff\xd8live-frame\xff\xd9"]

    async def begin_login(self) -> LoginStatus:
        return self.status

    async def get_status(
        self, login_id: str, *, refresh_screenshot: bool = True
    ) -> LoginStatus:
        assert login_id == "login-1"
        self.status_refresh_modes.append(refresh_screenshot)
        return self.status

    async def frame(self, login_id: str) -> bytes:
        assert login_id == "login-1"
        if not self.frames:
            raise ValueError("stream ended")
        return self.frames.pop(0)

    async def cancel(self, login_id: str) -> LoginStatus:
        assert login_id == "login-1"
        self.status = self.status.with_state("cancelled", screenshot_png=None)
        return self.status

    async def drag(
        self, login_id: str, points: list[tuple[float, float]]
    ) -> LoginStatus:
        self.dragged.append((login_id, points))
        return self.status

    async def pointer(self, login_id: str, action: str, x: float, y: float) -> None:
        self.pointer_events.append((login_id, action, x, y))

    async def key(self, login_id: str, key: str) -> None:
        self.keys.append((login_id, key))


def authenticated_client(tmp_path: Path, master_key: str) -> tuple[TestClient, str]:
    app = create_app(
        Settings(archive_root=tmp_path, master_key=master_key),
        auth_service=FakeAuthService(),
    )
    client = TestClient(app)
    client.__enter__()
    client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
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


def test_status_exposes_account_identity_and_real_health_without_secrets(
    tmp_path: Path, master_key: str
) -> None:
    """Catches the UI receiving only a cookie-presence boolean."""
    client, _csrf = authenticated_client(tmp_path, master_key)
    try:
        connection = sqlite3.connect(tmp_path / "data" / "archive.sqlite3")
        connection.execute(
            "INSERT INTO auth_sessions "
            "(provider, encrypted_cookies, status, last_verified_at, updated_at) "
            "VALUES ('douyin', X'00', 'authenticated', 100, 100)"
        )
        connection.execute(
            "INSERT INTO douyin_account "
            "(provider, remote_id, nickname, health_status, last_verified_at, updated_at) "
            "VALUES ('douyin', 'self-id', '天鹰座裂缝之外', 'healthy', 100, 100)"
        )
        connection.commit()
        connection.close()

        response = client.get("/api/status")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.json()["douyinHealth"] == {
        "sessionStored": True,
        "status": "healthy",
        "lastVerifiedAt": 100,
        "lastSyncAt": None,
        "lastFailureAt": None,
        "errorCode": None,
        "consecutiveFailures": 0,
        "account": {
            "id": "self-id",
            "nickname": "天鹰座裂缝之外",
            "uniqueId": None,
            "avatarUrl": None,
        },
    }
    assert "encrypted" not in response.text.lower()
    assert "cookie" not in response.text.lower()


def test_login_live_stream_returns_multipart_jpeg_and_status_skips_png_refresh(
    tmp_path: Path, master_key: str
) -> None:
    client, csrf = authenticated_client(tmp_path, master_key)
    try:
        client.post("/api/douyin/login", headers={"X-CSRF-Token": csrf})
        status = client.get("/api/douyin/login/login-1")
        stream = client.get("/api/douyin/login/login-1/stream.mjpeg")
        service = client.app.state.auth_service
    finally:
        client.__exit__(None, None, None)

    assert status.status_code == 200
    assert service.status_refresh_modes == [False]
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith(
        "multipart/x-mixed-replace; boundary=frame"
    )
    assert b"Content-Type: image/jpeg" in stream.content
    assert b"\xff\xd8live-frame\xff\xd9" in stream.content


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


def test_drag_route_requires_csrf_and_forwards_normalized_pointer_path(
    tmp_path: Path, master_key: str
) -> None:
    client, csrf = authenticated_client(tmp_path, master_key)
    payload = {
        "points": [
            {"x": 0.1, "y": 0.4},
            {"x": 0.5, "y": 0.4},
            {"x": 0.9, "y": 0.4},
        ]
    }
    try:
        rejected = client.post("/api/douyin/login/login-1/drag", json=payload)
        accepted = client.post(
            "/api/douyin/login/login-1/drag",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        service = client.app.state.auth_service
    finally:
        client.__exit__(None, None, None)

    assert rejected.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["state"] == "awaiting_scan"
    assert service.dragged == [
        ("login-1", [(0.1, 0.4), (0.5, 0.4), (0.9, 0.4)])
    ]


def test_pointer_route_requires_csrf_and_forwards_each_live_event(
    tmp_path: Path, master_key: str
) -> None:
    client, csrf = authenticated_client(tmp_path, master_key)
    payload = {"action": "down", "x": 0.5, "y": 0.4}
    try:
        rejected = client.post("/api/douyin/login/login-1/pointer", json=payload)
        accepted = client.post(
            "/api/douyin/login/login-1/pointer",
            json=payload,
            headers={"X-CSRF-Token": csrf},
        )
        service = client.app.state.auth_service
    finally:
        client.__exit__(None, None, None)

    assert rejected.status_code == 403
    assert accepted.status_code == 202
    assert accepted.json() == {"accepted": True}
    assert service.pointer_events == [("login-1", "down", 0.5, 0.4)]


def test_keyboard_route_allows_digits_and_rejects_unapproved_keys(
    tmp_path: Path, master_key: str
) -> None:
    client, csrf = authenticated_client(tmp_path, master_key)
    try:
        accepted = client.post(
            "/api/douyin/login/login-1/key",
            json={"key": "7"},
            headers={"X-CSRF-Token": csrf},
        )
        rejected = client.post(
            "/api/douyin/login/login-1/key",
            json={"key": "Control+V"},
            headers={"X-CSRF-Token": csrf},
        )
        service = client.app.state.auth_service
    finally:
        client.__exit__(None, None, None)

    assert accepted.status_code == 202
    assert rejected.status_code == 422
    assert service.keys == [("login-1", "7")]

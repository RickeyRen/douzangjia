from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from douyin_archive.api import create_app
from douyin_archive.auth_service import LoginStatus
from douyin_archive.browser_stream import CdpUnavailable, LatestFrameMailbox
from douyin_archive.config import Settings

JPEG = b"\xff\xd8live-cdp-frame\xff\xd9"


class FakeStream:
    def __init__(self) -> None:
        self.mailbox = LatestFrameMailbox()
        self.mailbox.put(JPEG)
        self.unsubscribed = False

    def subscribe(self) -> LatestFrameMailbox:
        return self.mailbox

    def unsubscribe(self, mailbox: LatestFrameMailbox) -> None:
        assert mailbox is self.mailbox
        self.unsubscribed = True
        mailbox.close()


class SocketAuthService:
    def __init__(self, *, cdp_available: bool = True) -> None:
        self.status = LoginStatus.create(
            login_id="login-1",
            state="awaiting_scan",
            screenshot_png=None,
        )
        self.stream = FakeStream()
        self.cdp_available = cdp_available
        self.pointer_events: list[tuple[str, str, float, float]] = []
        self.keys: list[tuple[str, str]] = []

    async def get_status(
        self, login_id: str, *, refresh_screenshot: bool = True
    ) -> LoginStatus:
        if login_id != self.status.id:
            raise KeyError(login_id)
        return self.status

    async def screencast(self, login_id: str) -> FakeStream:
        assert login_id == self.status.id
        if not self.cdp_available:
            raise CdpUnavailable("disabled")
        return self.stream

    async def pointer(self, login_id: str, action: str, x: float, y: float) -> None:
        self.pointer_events.append((login_id, action, x, y))

    async def key(self, login_id: str, key: str) -> None:
        self.keys.append((login_id, key))


def make_client(
    tmp_path: Path, master_key: str, *, cdp_available: bool = True
) -> tuple[TestClient, SocketAuthService]:
    service = SocketAuthService(cdp_available=cdp_available)
    app = create_app(
        Settings(archive_root=tmp_path, master_key=master_key),
        auth_service=service,
    )
    return TestClient(app), service


def authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/setup", json={"password": "a secure local passphrase"}
    )
    assert response.status_code == 201


def test_browser_socket_rejects_missing_admin_session(
    tmp_path: Path, master_key: str
) -> None:
    client, _service = make_client(tmp_path, master_key)
    with client, pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            "/ws/douyin/login/login-1",
            headers={"origin": "http://testserver"},
        ):
            pass

    assert error.value.code == 4401


def test_browser_socket_rejects_cross_origin_session(
    tmp_path: Path, master_key: str
) -> None:
    client, _service = make_client(tmp_path, master_key)
    with client:
        authenticate(client)
        with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect(
            "/ws/douyin/login/login-1",
            headers={"origin": "http://attacker.invalid"},
        ):
            pass

    assert error.value.code == 4403


def test_browser_socket_sends_binary_latest_frame(
    tmp_path: Path, master_key: str
) -> None:
    client, service = make_client(tmp_path, master_key)
    with client:
        authenticate(client)
        with client.websocket_connect(
            "/ws/douyin/login/login-1",
            headers={"origin": "http://testserver"},
        ) as socket:
            status = socket.receive_json()
            frame = socket.receive_bytes()

    assert status == {
        "type": "status",
        "state": "awaiting_scan",
        "width": 1280,
        "height": 800,
        "transport": "cdp",
    }
    assert frame == JPEG
    assert service.stream.unsubscribed is True


def test_browser_socket_forwards_pointer_and_allowed_key(
    tmp_path: Path, master_key: str
) -> None:
    client, service = make_client(tmp_path, master_key)
    with client:
        authenticate(client)
        with client.websocket_connect(
            "/ws/douyin/login/login-1",
            headers={"origin": "http://testserver"},
        ) as socket:
            socket.receive_json()
            socket.send_json(
                {"type": "pointer", "action": "down", "x": 0.25, "y": 0.75}
            )
            socket.send_json({"type": "key", "key": "7"})

    assert service.pointer_events == [("login-1", "down", 0.25, 0.75)]
    assert service.keys == [("login-1", "7")]


def test_browser_socket_reports_mjpeg_fallback(
    tmp_path: Path, master_key: str
) -> None:
    client, _service = make_client(tmp_path, master_key, cdp_available=False)
    with client:
        authenticate(client)
        with client.websocket_connect(
            "/ws/douyin/login/login-1",
            headers={"origin": "http://testserver"},
        ) as socket:
            status = socket.receive_json()

    assert status["transport"] == "mjpeg"

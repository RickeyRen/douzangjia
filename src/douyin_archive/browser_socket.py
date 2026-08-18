from __future__ import annotations

import asyncio
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import WebSocket
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from starlette.websockets import WebSocketDisconnect

from .browser_stream import CdpUnavailable, MailboxClosed
from .session_auth import SessionCodec

LOGIN_VIEWPORT_WIDTH = 1280
LOGIN_VIEWPORT_HEIGHT = 800
ALLOWED_KEYS = Literal[
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "Backspace",
    "Enter",
    "Tab",
]


class PointerMessage(BaseModel):
    type: Literal["pointer"]
    action: Literal["down", "move", "up"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class KeyMessage(BaseModel):
    type: Literal["key"]
    key: ALLOWED_KEYS


BrowserInput = Annotated[PointerMessage | KeyMessage, Field(discriminator="type")]
INPUT_ADAPTER = TypeAdapter(BrowserInput)


def same_origin(websocket: WebSocket) -> bool:
    origin_value = websocket.headers.get("origin")
    host_value = websocket.headers.get("host")
    if not origin_value or not host_value:
        return False
    try:
        origin = urlsplit(origin_value)
        request_host = urlsplit(f"//{host_value}")
        if origin.scheme not in {"http", "https", "ws", "wss"}:
            return False
        if not origin.hostname or not request_host.hostname:
            return False
        origin_port = origin.port or (443 if origin.scheme in {"https", "wss"} else 80)
        request_port = request_host.port or (
            443 if websocket.url.scheme == "wss" else 80
        )
    except ValueError:
        return False
    return (
        origin.hostname.lower() == request_host.hostname.lower()
        and origin_port == request_port
    )


async def handle_browser_socket(
    websocket: WebSocket,
    login_id: str,
    *,
    auth_service: object,
    session_codec: SessionCodec,
    session_cookie: str,
) -> None:
    if not session_codec.is_valid(websocket.cookies.get(session_cookie)):
        await websocket.close(code=4401)
        return
    if not same_origin(websocket):
        await websocket.close(code=4403)
        return

    try:
        status = await auth_service.get_status(  # type: ignore[attr-defined]
            login_id, refresh_screenshot=False
        )
    except KeyError:
        await websocket.close(code=4404)
        return
    if status.state not in {"starting", "awaiting_scan"}:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    try:
        stream = await auth_service.screencast(login_id)  # type: ignore[attr-defined]
    except (CdpUnavailable, KeyError, ValueError):
        await websocket.send_json(_status_message(status.state, "mjpeg"))
        await websocket.close(code=1000)
        return

    mailbox = stream.subscribe()
    await websocket.send_json(_status_message(status.state, "cdp"))

    async def send_frames() -> None:
        while True:
            await websocket.send_bytes(await mailbox.get())

    async def receive_input() -> None:
        while True:
            try:
                payload = await websocket.receive_json()
                message = INPUT_ADAPTER.validate_python(payload)
            except ValidationError:
                await websocket.close(code=4400)
                return
            if isinstance(message, PointerMessage):
                await auth_service.pointer(  # type: ignore[attr-defined]
                    login_id, message.action, message.x, message.y
                )
            else:
                await auth_service.key(login_id, message.key)  # type: ignore[attr-defined]

    tasks = {
        asyncio.create_task(send_frames()),
        asyncio.create_task(receive_input()),
    }
    try:
        _done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    except (asyncio.CancelledError, MailboxClosed, WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        stream.unsubscribe(mailbox)


def _status_message(state: str, transport: str) -> dict[str, object]:
    return {
        "type": "status",
        "state": state,
        "width": LOGIN_VIEWPORT_WIDTH,
        "height": LOGIN_VIEWPORT_HEIGHT,
        "transport": transport,
    }

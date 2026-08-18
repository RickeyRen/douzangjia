import asyncio
import base64
from typing import Any

import pytest

from douyin_archive.browser_stream import (
    CdpScreencast,
    CdpUnavailable,
    LatestFrameMailbox,
    MailboxClosed,
)

JPEG = b"\xff\xd8latest-frame\xff\xd9"
JPEG_B64 = base64.b64encode(JPEG).decode("ascii")


class FakeCdpSession:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.commands: list[tuple[str, dict[str, object] | None]] = []
        self.detached = False

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler: object) -> None:
        if self.handlers.get(event) == handler:
            self.handlers.pop(event)

    async def send(
        self, command: str, params: dict[str, object] | None = None
    ) -> None:
        self.commands.append((command, params))

    async def detach(self) -> None:
        self.detached = True

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        result = self.handlers[event](payload)  # type: ignore[operator]
        if asyncio.iscoroutine(result):
            await result


class FakeContext:
    def __init__(self, cdp: FakeCdpSession) -> None:
        self.cdp = cdp

    async def new_cdp_session(self, _page: object) -> FakeCdpSession:
        return self.cdp


class FakePage:
    def __init__(self, cdp: FakeCdpSession) -> None:
        self.context = FakeContext(cdp)


class FailingContext:
    async def new_cdp_session(self, _page: object) -> None:
        raise RuntimeError("CDP disabled")


class FailingPage:
    context = FailingContext()


async def test_mailbox_replaces_an_unsent_frame() -> None:
    mailbox = LatestFrameMailbox()

    mailbox.put(b"old")
    mailbox.put(b"latest")

    assert await mailbox.get() == b"latest"


async def test_mailbox_close_wakes_a_blocked_consumer() -> None:
    mailbox = LatestFrameMailbox()
    waiting = asyncio.create_task(mailbox.get())
    await asyncio.sleep(0)

    mailbox.close()

    with pytest.raises(MailboxClosed):
        await waiting


async def test_screencast_acknowledges_and_publishes_each_cdp_frame() -> None:
    cdp = FakeCdpSession()
    stream = CdpScreencast(FakePage(cdp))
    await stream.start()
    mailbox = stream.subscribe()

    await cdp.emit("Page.screencastFrame", {"data": JPEG_B64, "sessionId": 41})

    assert cdp.commands[-1] == (
        "Page.screencastFrameAck",
        {"sessionId": 41},
    )
    assert await mailbox.get() == JPEG
    await stream.close()


async def test_close_stops_cdp_and_wakes_subscribers() -> None:
    cdp = FakeCdpSession()
    stream = CdpScreencast(FakePage(cdp))
    await stream.start()
    mailbox = stream.subscribe()

    await stream.close()

    assert ("Page.stopScreencast", None) in cdp.commands
    assert cdp.detached is True
    assert cdp.handlers == {}
    with pytest.raises(MailboxClosed):
        await mailbox.get()


async def test_cdp_creation_failure_has_a_stable_fallback_error() -> None:
    stream = CdpScreencast(FailingPage())

    with pytest.raises(CdpUnavailable):
        await stream.start()

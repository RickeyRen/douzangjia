from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
from typing import Any


class MailboxClosed(RuntimeError):
    pass


class CdpUnavailable(RuntimeError):
    pass


_CLOSED = object()


class LatestFrameMailbox:
    """A one-item async mailbox that discards superseded video frames."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes | object] = asyncio.Queue(maxsize=1)
        self._closed = False

    def put(self, frame: bytes) -> None:
        if self._closed:
            return
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(frame)

    async def get(self) -> bytes:
        frame = await self._queue.get()
        if frame is _CLOSED:
            raise MailboxClosed("frame stream is closed")
        return frame  # type: ignore[return-value]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(_CLOSED)


class CdpScreencast:
    """Publish Chromium CDP screencast frames to latest-only subscribers."""

    def __init__(
        self,
        page: Any,
        *,
        quality: int = 68,
        width: int = 1280,
        height: int = 800,
    ) -> None:
        self.page = page
        self.quality = quality
        self.width = width
        self.height = height
        self._cdp: Any = None
        self._subscribers: set[LatestFrameMailbox] = set()
        self._closed = False

    async def start(self) -> None:
        if self._cdp is not None:
            return
        try:
            cdp = await self.page.context.new_cdp_session(self.page)
            cdp.on("Page.screencastFrame", self._on_frame)
            await cdp.send(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": self.quality,
                    "maxWidth": self.width,
                    "maxHeight": self.height,
                    "everyNthFrame": 1,
                },
            )
        except Exception as error:
            with suppress(Exception):
                cdp.remove_listener("Page.screencastFrame", self._on_frame)
            with suppress(Exception):
                await cdp.detach()
            raise CdpUnavailable("Chromium screencast is unavailable") from error
        self._cdp = cdp

    def subscribe(self) -> LatestFrameMailbox:
        mailbox = LatestFrameMailbox()
        if self._closed:
            mailbox.close()
        else:
            self._subscribers.add(mailbox)
        return mailbox

    def unsubscribe(self, mailbox: LatestFrameMailbox) -> None:
        self._subscribers.discard(mailbox)
        mailbox.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for mailbox in tuple(self._subscribers):
            mailbox.close()
        self._subscribers.clear()
        cdp = self._cdp
        self._cdp = None
        if cdp is None:
            return
        cdp.remove_listener("Page.screencastFrame", self._on_frame)
        with suppress(Exception):
            await cdp.send("Page.stopScreencast")
        with suppress(Exception):
            await cdp.detach()

    async def _on_frame(self, payload: dict[str, Any]) -> None:
        cdp = self._cdp
        if cdp is None:
            return
        await cdp.send(
            "Page.screencastFrameAck",
            {"sessionId": payload["sessionId"]},
        )
        try:
            frame = base64.b64decode(str(payload["data"]), validate=True)
        except (KeyError, ValueError):
            return
        for mailbox in tuple(self._subscribers):
            mailbox.put(frame)

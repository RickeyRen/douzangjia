from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

SENSITIVE_KEYS = {
    "cookie",
    "cookies",
    "encrypted_cookies",
    "token",
    "sessionid",
    "signedurl",
    "signed_url",
}


@dataclass(frozen=True, slots=True)
class DashboardEvent:
    event_type: str
    data: dict[str, object]


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in SENSITIVE_KEYS or _contains_sensitive_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def encode_sse(event: DashboardEvent) -> str:
    return (
        "retry: 1500\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(event.data, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


class DashboardEventBus:
    def __init__(self, *, queue_size: int = 8) -> None:
        self.queue_size = max(1, queue_size)
        self._subscribers: set[asyncio.Queue[DashboardEvent]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, event_type: str, data: dict[str, object]) -> None:
        if _contains_sensitive_key(data):
            raise ValueError("sensitive dashboard event payload")
        event = DashboardEvent(event_type, data)
        for queue in tuple(self._subscribers):
            while queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[DashboardEvent]]:
        queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(self.queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


async def dashboard_event_stream(
    snapshot_loader: Callable[[], Awaitable[dict[str, object]]],
    bus: DashboardEventBus,
    *,
    refresh_seconds: float = 1.0,
) -> AsyncIterator[str]:
    yield encode_sse(DashboardEvent("snapshot", await snapshot_loader()))
    async with bus.subscribe() as queue:
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(), timeout=max(refresh_seconds, 0.1)
                )
            except TimeoutError:
                event = DashboardEvent("snapshot", await snapshot_loader())
            yield encode_sse(event)

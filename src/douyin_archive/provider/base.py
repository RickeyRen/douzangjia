from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from ..models import RemoteItem


class ProviderError(Exception):
    code = "PROVIDER_ERROR"


class SessionExpired(ProviderError):
    code = "DOUYIN_SESSION_EXPIRED"


class RateLimited(ProviderError):
    code = "RATE_LIMITED"

    def __init__(self, message: str, *, retry_after: int = 900) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderChanged(ProviderError):
    code = "DOUYIN_RESPONSE_CHANGED"


@dataclass(frozen=True, slots=True)
class RemoteCollection:
    remote_id: str
    name: str
    item_count: int | None = None


@dataclass(frozen=True, slots=True)
class RemotePage:
    items: tuple[RemoteItem, ...]
    next_cursor: str | None
    has_more: bool


class RawPageSource(Protocol):
    async def fetch_collections(self) -> dict: ...

    def iter_raw_pages(self, remote_id: str) -> AsyncIterator[dict]: ...

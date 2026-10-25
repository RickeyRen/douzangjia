from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

MAX_AVATAR_BYTES = 2 * 1024 * 1024
REFRESH_AFTER_SECONDS = 30 * 86_400


class AvatarCache:
    """Keep creator avatars on the NAS so grids never depend on Douyin's CDN."""

    def __init__(self, archive_root: Path, *, client: httpx.AsyncClient | None = None) -> None:
        self.directory = archive_root.resolve() / "cache" / "avatars"
        self._client = client
        self._locks: dict[str, asyncio.Lock] = {}

    def path_for(self, creator_id: str) -> Path:
        digest = hashlib.sha256(creator_id.encode()).hexdigest()[:24]
        return self.directory / f"{digest}.img"

    async def get(self, creator_id: str, remote_url: str | None) -> Path | None:
        target = self.path_for(creator_id)
        marker = target.with_suffix(".url")
        fresh = target.is_file() and target.stat().st_size > 0
        same_source = marker.is_file() and marker.read_text(encoding="utf-8") == (remote_url or "")
        if fresh and same_source:
            return target
        if not remote_url:
            return target if fresh else None
        lock = self._locks.setdefault(creator_id, asyncio.Lock())
        async with lock:
            if target.is_file() and marker.is_file() and marker.read_text(encoding="utf-8") == remote_url:
                return target
            fetched = await self._download(remote_url, target)
            self._locks.pop(creator_id, None)
            if fetched:
                marker.write_text(remote_url, encoding="utf-8")
                return target
            return target if fresh else None

    async def _download(self, url: str, target: Path) -> bool:
        self.directory.mkdir(parents=True, exist_ok=True)
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(20, connect=10),
            headers={"Referer": "https://www.douyin.com/", "User-Agent": "Mozilla/5.0"},
        )
        temporary = target.with_suffix(".part")
        try:
            async with client.stream("GET", url) as response:
                if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                    return False
                written = 0
                with temporary.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if written > MAX_AVATAR_BYTES:
                            return False
                        handle.write(chunk)
            if written == 0:
                return False
            temporary.replace(target)
            return True
        except (httpx.HTTPError, OSError) as error:
            logger.info("avatar fetch failed for %s: %s", url, error)
            return False
        finally:
            temporary.unlink(missing_ok=True)
            if own_client:
                await client.aclose()


def avatar_route(creator_id: str | None, remote_url: str | None) -> str | None:
    """Prefer the NAS copy; without a creator id only the remote URL exists."""
    if not creator_id:
        return remote_url
    return f"/api/creators/{creator_id}/avatar" if remote_url else None

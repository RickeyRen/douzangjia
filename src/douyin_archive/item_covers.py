"""Keep the cover of every recorded work on the NAS; Douyin drops it with the work."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import httpx

from .db import Database
from .library_scope import library_item_sql

logger = logging.getLogger(__name__)

SAVE_EVERY_SECONDS = 60
BATCH_SIZE = 100
PARALLEL = 4
MAX_COVER_BYTES = 8 * 1024 * 1024
ENLIST_EVERY_RUNS = 60


class ItemCoverStore:
    def __init__(self, archive_root: Path) -> None:
        self.directory = archive_root.resolve() / "cache" / "covers"

    def path_for(self, item_id: str) -> Path:
        digest = hashlib.sha256(item_id.encode()).hexdigest()
        return self.directory / digest[:2] / f"{digest[2:34]}.img"

    def has(self, item_id: str) -> bool:
        try:
            return self.path_for(item_id).stat().st_size > 0
        except OSError:
            return False


def local_cover_route(store: ItemCoverStore, item_id: str) -> str | None:
    return f"/api/items/{item_id}/cover" if store.has(item_id) else None


class ItemCoverPreserver:
    def __init__(self, database: Database, archive_root: Path, client: httpx.AsyncClient | None = None) -> None:
        self.database = database
        self.store = ItemCoverStore(archive_root)
        self._client = client
        self._runs = 0

    async def enlist_library_items(self) -> None:
        """Favourites not yet downloaded have only Douyin's cover as well."""
        await self.database.execute(
            "INSERT INTO creator_catalog_items "
            "(item_id, creator_id, author_name, description, item_type, published_at, duration_ms, "
            "cover_url, source_url, statistics_json, first_seen_at, last_seen_at) "
            "SELECT i.remote_id, i.creator_id, i.author_name, i.description, i.item_type, i.published_at, "
            "i.duration_ms, i.cover_url, i.source_url, i.statistics_json, i.first_seen_at, i.last_seen_at "
            "FROM items i WHERE i.creator_id IS NOT NULL AND i.cover_url IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM media_files mf WHERE mf.item_id=i.remote_id AND mf.status='ready') "
            f"AND {library_item_sql('i')} "
            "ON CONFLICT(item_id) DO UPDATE SET cover_url=excluded.cover_url, "
            "cover_state=CASE WHEN creator_catalog_items.cover_state=2 "
            "AND creator_catalog_items.cover_url IS NOT excluded.cover_url THEN 0 "
            "ELSE creator_catalog_items.cover_state END"
        )

    async def run_batch(self) -> int:
        if self._runs % ENLIST_EVERY_RUNS == 0:
            await self.enlist_library_items()
        self._runs += 1
        # Removed creators first: nothing else will ever show their works.
        rows = await self.database.fetchall(
            "SELECT cc.item_id, cc.cover_url FROM creator_catalog_items cc "
            "JOIN creators c ON c.remote_id=cc.creator_id "
            "WHERE cc.cover_state=0 AND c.archive_status<>'active' LIMIT ?",
            (BATCH_SIZE,),
        )
        if len(rows) < BATCH_SIZE:
            rows = [
                *rows,
                *await self.database.fetchall(
                    "SELECT item_id, cover_url FROM creator_catalog_items WHERE cover_state=0 LIMIT ?",
                    (BATCH_SIZE - len(rows),),
                ),
            ]
        if not rows:
            return 0
        client = self._client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(20, connect=10),
            headers={"Referer": "https://www.douyin.com/", "User-Agent": "Mozilla/5.0"},
        )
        slots = asyncio.Semaphore(PARALLEL)

        async def save(row) -> bool:
            async with slots:
                return await self._save(client, str(row["item_id"]), row["cover_url"])

        try:
            results = await asyncio.gather(*(save(row) for row in rows))
        finally:
            if self._client is None:
                await client.aclose()
        for row, saved in zip(rows, results, strict=True):
            await self.database.execute(
                "UPDATE creator_catalog_items SET cover_state=? WHERE item_id=?",
                (1 if saved else 2, row["item_id"]),
            )
        return sum(results)

    async def _save(self, client: httpx.AsyncClient, item_id: str, url: str | None) -> bool:
        target = self.store.path_for(item_id)
        if self.store.has(item_id):
            return True
        if not url:
            return False
        temporary = target.with_suffix(".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            async with client.stream("GET", url) as response:
                if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                    return False
                written = 0
                with temporary.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if written > MAX_COVER_BYTES:
                            return False
                        handle.write(chunk)
            if written == 0:
                return False
            temporary.replace(target)
            return True
        except (httpx.HTTPError, OSError) as error:
            logger.info("cover fetch failed for %s: %s", item_id, error)
            return False
        finally:
            temporary.unlink(missing_ok=True)

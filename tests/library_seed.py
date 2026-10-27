from __future__ import annotations

from douyin_archive.db import Database

FAVORITES_SOURCE_ID = "test:favorites"


async def keep_all_in_library(database: Database) -> None:
    """File every seeded item under a favorites source so it counts as kept."""
    await database.execute(
        "INSERT OR IGNORE INTO library_sources (id, kind, remote_id, name, sync_status, "
        "first_seen_at, last_seen_at) VALUES (?, 'favorite_video', 'test', '测试收藏', "
        "'complete', 1, 1)",
        (FAVORITES_SOURCE_ID,),
    )
    await database.execute(
        "INSERT OR IGNORE INTO source_items (source_id, item_id, remote_order, "
        "first_seen_at, last_seen_at) SELECT ?, remote_id, NULL, 1, 1 FROM items",
        (FAVORITES_SOURCE_ID,),
    )

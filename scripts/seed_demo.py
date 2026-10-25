"""Fill an empty archive root with synthetic data for screenshots and demos.

Nothing here touches Douyin. Run:
    ARCHIVE_ROOT=/tmp/douzangjia-demo python scripts/seed_demo.py
then start the app against that root. Items get no media, so tiles show
their generated placeholders; descriptions, creators, albums, tags and
remote-check results are all made up.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from douyin_archive.db import Database  # noqa: E402

CREATORS = [
    ("c-travel", "旅行家小鹿", "deer.travel"),
    ("c-food", "厨房里的阿明", "amingcooks"),
    ("c-city", "城市漫游记", "citywalk"),
    ("c-design", "三平米工作室", "3sqm"),
    ("c-fitness", "早起跑步的林", "runlin"),
    ("c-music", "午后唱片店", "noonrecords"),
]
TOPICS = {
    "c-travel": ["杭州西湖边的咖啡馆，秋天真好看", "一个人的房车旅行记录 Day {n}", "藏在古镇里的小书店", "日落时分的海边公路"],
    "c-food": ["番茄炒蛋的正确做法", "十分钟搞定的晚饭：{n} 种做法", "周末烤了一炉面包", "菜市场买到的宝藏食材"],
    "c-city": ["老街区的早晨", "坐错车之后发现的小巷子", "这座城市的 {n} 个屋顶", "雨天的地铁站"],
    "c-design": ["小户型改造前后对比", "我的书桌布置 {n}.0", "一盏灯改变一个角落", "收纳方案分享"],
    "c-fitness": ["晨跑第 {n} 天", "新手也能做的拉伸", "跑步时听的歌单", "坚持一个月的变化"],
    "c-music": ["今天收到的黑胶", "一张唱片背后的故事", "店里的常客推荐 {n}", "雨天适合听的专辑"],
}
TAGS = ["做饭", "旅行", "周末", "收纳", "灵感", "想去", "健身"]
COLLECTIONS = [("col-1", "想去的地方"), ("col-2", "有用的收藏"), ("col-3", "家居设计")]


async def main(root: Path) -> None:
    random.seed(42)
    now = int(time.time())
    database = await Database(root / "data" / "archive.sqlite3").open()
    try:
        for creator_id, nickname, unique_id in CREATORS:
            await database.execute(
                "INSERT OR IGNORE INTO creators (remote_id, nickname, unique_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (creator_id, nickname, unique_id, now - 90 * 86_400, now),
            )
        for remote_id, name in COLLECTIONS:
            await database.execute(
                "INSERT OR IGNORE INTO collections (remote_id, name, name_history_json, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (remote_id, name, json.dumps([name], ensure_ascii=False), now - 80 * 86_400, now),
            )
            await database.execute(
                "INSERT OR IGNORE INTO library_sources (id, kind, remote_id, name, sync_status, first_seen_at, last_seen_at) "
                "VALUES (?, 'favorite_collection', ?, ?, 'complete', ?, ?)",
                (f"favorite_collection:{remote_id}", remote_id, name, now - 80 * 86_400, now),
            )
        await database.execute(
            "INSERT OR IGNORE INTO library_sources (id, kind, remote_id, name, sync_status, first_seen_at, last_seen_at) "
            "VALUES ('account:likes', 'like', 'self', '喜欢', 'complete', ?, ?)",
            (now - 80 * 86_400, now),
        )
        item_ids: list[str] = []
        for index in range(240):
            creator_id, nickname, _ = CREATORS[index % len(CREATORS)]
            description = random.choice(TOPICS[creator_id]).replace("{n}", str(index % 30 + 1))
            seen = now - random.randint(0, 85) * 86_400 - random.randint(0, 86_400)
            remote_id = f"7{index:018d}"
            item_ids.append(remote_id)
            kind = "gallery" if index % 5 == 0 else "video"
            await database.execute(
                "INSERT OR IGNORE INTO items (remote_id, author_name, description, item_type, published_at, first_seen_at, "
                "last_seen_at, creator_id, duration_ms, statistics_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    remote_id, nickname, description, kind, seen - 3 * 86_400, seen, seen, creator_id,
                    None if kind == "gallery" else random.randint(12_000, 420_000),
                    json.dumps({"diggCount": random.randint(200, 90_000), "commentCount": random.randint(5, 2_000)}),
                    json.dumps({"hashtags": random.sample(TAGS, 2)}, ensure_ascii=False),
                ),
            )
            collection = COLLECTIONS[index % len(COLLECTIONS)][0] if index % 3 else None
            if collection:
                await database.execute(
                    "INSERT OR IGNORE INTO collection_items (collection_id, item_id, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
                    (collection, remote_id, seen, seen),
                )
                await database.execute(
                    "INSERT OR IGNORE INTO source_items (source_id, item_id, remote_order, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                    (f"favorite_collection:{collection}", remote_id, f"{index:06d}", seen, seen),
                )
            await database.execute(
                "INSERT OR IGNORE INTO source_items (source_id, item_id, remote_order, first_seen_at, last_seen_at) VALUES ('account:likes', ?, ?, ?, ?)",
                (remote_id, f"{index:06d}", seen, seen),
            )
            if index % 7 == 0:
                await database.execute("INSERT OR IGNORE INTO item_stars (item_id, starred_at) VALUES (?, ?)", (remote_id, seen))
            if index % 11 == 0:
                await database.execute(
                    "INSERT OR IGNORE INTO remote_checks (item_id, status, checked_at, evidence_code, updated_at) VALUES (?, 'deleted', ?, 'ITEM_NOT_FOUND', ?)",
                    (remote_id, now - 86_400, now),
                )
            for tag in random.sample(TAGS, 1 if index % 2 else 0):
                await database.execute("INSERT OR IGNORE INTO item_tags (item_id, tag, created_at) VALUES (?, ?, ?)", (remote_id, tag, seen))
        for name, picks in (("下次旅行参考", item_ids[::9]), ("晚饭灵感", item_ids[1::13])):
            row = await database.fetchone(
                "INSERT INTO albums (name, position, created_at, updated_at) VALUES (?, 1, ?, ?) RETURNING id", (name, now, now)
            )
            for item_id in picks:
                await database.execute("INSERT OR IGNORE INTO album_items (album_id, item_id, added_at) VALUES (?, ?, ?)", (row["id"], item_id, now))
        await database.execute(
            "INSERT INTO sync_runs (mode, phase, status, discovered_count, enqueued_count, started_at, finished_at) VALUES ('incremental', 'finished', 'completed', 84, 3, ?, ?)",
            (now - 400, now - 300),
        )
        await database.execute(
            "INSERT OR REPLACE INTO auth_sessions (provider, encrypted_cookies, status, updated_at) VALUES ('douyin', 'demo', 'authenticated', ?)", (now,)
        )
    finally:
        await database.close()
    print(f"seeded demo archive at {root}")


if __name__ == "__main__":
    target = Path(os.environ.get("ARCHIVE_ROOT", "./demo-archive")).resolve()
    (target / "data").mkdir(parents=True, exist_ok=True)
    asyncio.run(main(target))

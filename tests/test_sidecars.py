import asyncio
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from douyin_archive import sidecars
from douyin_archive.db import Database
from douyin_archive.sidecars import SidecarWriter, build_nfo, display_title
from douyin_archive.storage import CollectionProjector

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32


async def saved_video(database: Database, root: Path, item: str, **fields: object) -> Path:
    relative = f"objects/{item}/000.mp4"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"video " + item.encode())
    values = {
        "author_name": "测试博主",
        "description": f"作品 {item}",
        "item_type": "video",
        "published_at": 1_750_000_000,
        "duration_ms": 95_000,
        "source_url": f"https://www.douyin.com/video/{item}",
        "metadata_json": json.dumps({"hashtags": ["旅行"]}, ensure_ascii=False),
        **fields,
    }
    await database.execute(
        "INSERT INTO items (remote_id, author_name, description, item_type, published_at, first_seen_at, "
        "last_seen_at, duration_ms, source_url, metadata_json) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?)",
        (
            item,
            values["author_name"],
            values["description"],
            values["item_type"],
            values["published_at"],
            values["duration_ms"],
            values["source_url"],
            values["metadata_json"],
        ),
    )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, status, "
        "created_at, updated_at) VALUES (?, 0, ?, ?, ?, 'ready', 1, 1)",
        (item, "video" if values["item_type"] == "video" else "image", relative, path.stat().st_size),
    )
    return path


def test_nfo_is_valid_xml_even_with_markup_emoji_and_control_characters() -> None:
    """Catches descriptions that would break the XML and hide the video's metadata."""
    body = build_nfo(
        {
            "remote_id": "42",
            "author_name": "A&B <工作室>",
            "description": "猫 & 狗 <3 🐱\x07\x00 #萌宠 #日常 @朋友\n第二行",
            "published_at": 1_750_000_000,
            "first_seen_at": 1_750_000_100,
            "duration_ms": 30_000,
            "source_url": "https://www.douyin.com/video/42?a=1&b=2",
            "note": "收藏 <重要>",
            "tags": ["萌宠", "萌宠", "我的标签"],
            "genres": ["我的相册"],
        }
    )
    movie = ET.fromstring(body)
    assert movie.tag == "movie"
    assert movie.findtext("title") == "猫 & 狗 <3 🐱"
    assert "\x07" not in body.decode() and "\x00" not in body.decode()
    assert movie.findtext("director") == "A&B <工作室>"
    assert movie.findtext("premiered") == "2025-06-15" and movie.findtext("year") == "2025"
    assert movie.findtext("runtime") == "1"
    assert movie.findtext("dateadded") == "2025-06-15 23:08:20"
    unique = movie.find("uniqueid")
    assert unique is not None and unique.text == "42" and unique.get("type") == "douyin"
    assert [tag.text for tag in movie.findall("tag")] == ["萌宠", "我的标签"]
    assert [genre.text for genre in movie.findall("genre")] == ["我的相册"]
    plot = movie.findtext("plot") or ""
    assert "我的备注：收藏 <重要>" in plot and "a=1&b=2" in plot


def test_title_falls_back_when_the_description_is_only_hashtags_or_empty() -> None:
    assert display_title("#旅行 #海边", "博主") == "#旅行 #海边"
    assert display_title("", "博主") == "博主 的作品"
    long = display_title("长" * 200, "博主")
    assert len(long) == sidecars.TITLE_MAX_CHARS and long.endswith("…")


def test_walk_writes_sidecars_beside_videos_and_projections_and_resumes(tmp_path: Path, monkeypatch) -> None:
    """Catches media servers seeing bare 000.mp4 files with no title or poster."""
    root = tmp_path / "archive"
    monkeypatch.setattr(sidecars, "BATCH_SIZE", 2)

    async def scenario() -> None:
        database = await Database(tmp_path / "archive.sqlite3").open()
        first = await saved_video(database, root, "101", description="海边日落 #旅行")
        second = await saved_video(database, root, "102")
        third = await saved_video(database, root, "103")
        gallery = await saved_video(database, root, "104", item_type="gallery")
        await database.execute(
            "INSERT INTO collections (remote_id, name, name_history_json, first_seen_at, last_seen_at) "
            "VALUES ('c1', '风景', '[]', 1, 1)"
        )
        await database.execute(
            "INSERT INTO collection_items (collection_id, item_id, first_seen_at, last_seen_at) "
            "VALUES ('c1', '101', 1, 1)"
        )
        projected = await CollectionProjector(root).project("风景", "海边日落 #旅行", "101", first)
        await database.execute("INSERT INTO item_tags (item_id, tag, created_at) VALUES ('101', '收藏', 1)")
        # Grid poster for 102 only.
        poster = root / "cache" / "posters" / "2.jpg"
        poster.parent.mkdir(parents=True)
        poster.write_bytes(JPEG)

        clock = [2_000_000_000.0]
        writer = SidecarWriter(database, root, clock=lambda: clock[0])
        # Batch of two: 101 and 102, then the cursor resumes at 103.
        assert await writer.run_batch() == 4  # 101 nfo + projection nfo, 102 nfo + poster
        assert not third.with_suffix(".nfo").exists()
        assert await writer.run_batch() == 1  # 103; the gallery is skipped
        assert not gallery.with_suffix(".nfo").exists()

        movie = ET.fromstring(first.with_suffix(".nfo").read_bytes())
        assert movie.findtext("title") == "海边日落"
        assert [tag.text for tag in movie.findall("tag")] == ["旅行", "收藏"]
        assert [genre.text for genre in movie.findall("genre")] == ["风景"]
        assert projected.with_suffix(".nfo").read_bytes() == first.with_suffix(".nfo").read_bytes()
        assert (second.parent / "000-poster.jpg").read_bytes() == JPEG
        assert not list(root.rglob(".*.writing"))

        # Finished: nothing until a day later, then unchanged files are left alone...
        assert await writer.run_batch() == 0
        clock[0] += sidecars.REWALK_AFTER_SECONDS + 1
        assert await writer.run_batch() == 0
        assert await writer.run_batch() == 0
        # ...and a new note shows up on the next pass.
        await database.execute("INSERT INTO item_notes (item_id, note, updated_at) VALUES ('103', '再看一遍', 1)")
        clock[0] += sidecars.REWALK_AFTER_SECONDS + 1
        assert await writer.run_batch() == 0
        assert await writer.run_batch() == 1
        assert "我的备注：再看一遍" in third.with_suffix(".nfo").read_text(encoding="utf-8")
        await database.close()

    asyncio.run(scenario())


def test_write_for_item_covers_a_fresh_download_right_away(tmp_path: Path) -> None:
    root = tmp_path / "archive"

    async def scenario() -> None:
        database = await Database(tmp_path / "archive.sqlite3").open()
        video = await saved_video(database, root, "201")
        assert await SidecarWriter(database, root).write_for_item("201") == 1
        assert ET.fromstring(video.with_suffix(".nfo").read_bytes()).findtext("studio") == "抖音"
        assert await SidecarWriter(database, root).write_for_item("201") == 0
        await database.close()

    asyncio.run(scenario())

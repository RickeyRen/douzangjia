import errno
import os
import time
from pathlib import Path

import pytest

from douyin_archive.storage import CollectionProjector, ObjectStore


async def test_finalize_is_atomic_and_rejects_empty_files(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    empty = store.part_path("734", "000.mp4")
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_bytes(b"")

    with pytest.raises(ValueError, match="empty"):
        await store.finalize(empty, "734", "000.mp4")
    assert not store.object_path("734", "000.mp4").exists()


async def test_same_item_in_two_collections_uses_hardlinks(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    projector = CollectionProjector(tmp_path)
    part = store.part_path("734", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"media")
    object_file = await store.finalize(part, "734", "000.mp4")

    first = await projector.project("想去的地方", "海边日落", "734", object_file)
    second = await projector.project("好看的美女", "海边日落", "734", object_file)

    assert first.stat().st_ino == second.stat().st_ino == object_file.stat().st_ino


async def test_collection_rename_keeps_old_projection(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    projector = CollectionProjector(tmp_path)
    part = store.part_path("734", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"media")
    object_file = await store.finalize(part, "734", "000.mp4")

    old_path = await projector.project("想去的地方", "海边", "734", object_file)
    new_path = await projector.project("周末想去", "海边", "734", object_file)

    assert old_path.exists()
    assert new_path.exists()


async def test_long_chinese_title_projects_within_filesystem_filename_limit(
    tmp_path: Path,
) -> None:
    store = ObjectStore(tmp_path)
    projector = CollectionProjector(tmp_path)
    part = store.part_path("7673431909393682914", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"media")
    object_file = await store.finalize(part, "7673431909393682914", "000.mp4")

    projected = await projector.project(
        "想去的地方",
        "这是一个很长的中文标题" * 80,
        "7673431909393682914",
        object_file,
    )

    assert projected.exists()
    assert len(projected.name.encode("utf-8")) <= 255
    assert "7673431909393682914" in projected.name


async def test_cross_device_hardlink_falls_back_to_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ObjectStore(tmp_path)
    projector = CollectionProjector(tmp_path)
    part = store.part_path("734", "000.mp4")
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"media")
    object_file = await store.finalize(part, "734", "000.mp4")

    def raise_cross_device(_: Path, __: Path) -> None:
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(os, "link", raise_cross_device)
    projected = await projector.project("想去的地方", "海边", "734", object_file)
    assert projected.read_bytes() == b"media"


async def test_cleanup_only_removes_old_parts(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    old = store.part_path("old", "000.mp4")
    recent = store.part_path("recent", "000.mp4")
    old.parent.mkdir(parents=True, exist_ok=True)
    recent.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"old")
    recent.write_bytes(b"recent")
    old_time = time.time() - 25 * 60 * 60
    os.utime(old, (old_time, old_time))

    removed = await store.cleanup_orphan_parts(older_than_seconds=24 * 60 * 60)
    assert removed == 1
    assert not old.exists()
    assert recent.exists()

import csv
import io
import json
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.routes.export import _zip_stream


def seed(root: Path) -> None:
    def save(relative: str, body: bytes) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    save("objects/301/000.mp4", b"video-301")
    save("objects/302/000.webp", b"img-a")
    save("objects/302/001.webp", b"img-b")
    poster = root / "cache" / "posters" / "1.jpg"
    poster.parent.mkdir(parents=True, exist_ok=True)
    poster.write_bytes(b"\xff\xd8\xff\xe0poster")
    with sqlite3.connect(root / "data" / "archive.sqlite3") as database:
        for item, kind, description in (
            ("301", "video", "山里的清晨 #露营 #自然"),
            ("302", "gallery", "周末做饭记录"),
            ("303", "video", "还没下载的作品"),
        ):
            database.execute(
                "INSERT INTO items (remote_id, item_type, author_name, description, published_at, duration_ms, "
                "source_url, metadata_json, first_seen_at, last_seen_at) VALUES (?, ?, '示例博主', ?, "
                "1750000000, 61000, ?, ?, 1, 1)",
                (
                    item,
                    kind,
                    description,
                    f"https://www.douyin.com/video/{item}",
                    json.dumps({"hashtags": ["露营", "自然"]} if item == "301" else {}, ensure_ascii=False),
                ),
            )
        files = [
            ("301", 0, "video", "objects/301/000.mp4", "ready"),
            ("302", 0, "image", "objects/302/000.webp", "ready"),
            ("302", 1, "image", "objects/302/001.webp", "ready"),
            ("303", 0, "video", None, "pending"),
        ]
        for item, index, kind, relative, status in files:
            database.execute(
                "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, status, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, 1)",
                (item, index, kind, relative, status),
            )
        database.execute("INSERT INTO albums (id, name, created_at, updated_at) VALUES (7, '周末/灵感', 1, 1)")
        for item, added in (("301", 5), ("302", 9), ("303", 7)):
            database.execute(
                "INSERT INTO album_items (album_id, item_id, added_at) VALUES (7, ?, ?)", (item, added)
            )
        database.execute("INSERT INTO item_tags (item_id, tag, created_at) VALUES ('301', '想去', 1)")
        database.execute("INSERT INTO item_notes (item_id, note, updated_at) VALUES ('301', '秋天再去一次', 1)")


def test_album_exports_files_metadata_and_a_listing(tmp_path: Path, master_key: str) -> None:
    """Catches an export that loses titles, metadata or the owner's own notes."""
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        seed(tmp_path)
        response = client.get("/api/export?albumId=7")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert unquote(response.headers["content-disposition"]).endswith("周末_灵感.zip")
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.testzip() is None
    names = archive.namelist()
    video = "周末_灵感/示例博主 - 山里的清晨 [301].mp4"
    assert archive.read(video) == b"video-301"
    assert archive.read("周末_灵感/示例博主 - 山里的清晨 [301]-poster.jpg").startswith(b"\xff\xd8")
    nfo = ET.fromstring(archive.read("周末_灵感/示例博主 - 山里的清晨 [301].nfo"))
    assert nfo.findtext("title") == "山里的清晨"
    assert archive.read("周末_灵感/示例博主 - 周末做饭记录 [302]/001.webp") == b"img-b"
    assert "周末_灵感/示例博主 - 周末做饭记录 [302]/示例博主 - 周末做饭记录 [302].nfo" in names
    # Not on the NAS yet: left out rather than an empty file.
    assert not any("[303]" in name for name in names)

    listing = archive.read("周末_灵感/作品清单.csv").decode("utf-8")
    assert listing.startswith("﻿")
    rows = list(csv.reader(io.StringIO(listing.lstrip("﻿"))))
    assert rows[0][0] == "标题" and len(rows) == 3
    # Album order: most recently added first.
    assert [row[0] for row in rows[1:]] == ["周末做饭记录", "山里的清晨"]
    camp = rows[2]
    assert camp[2] == "2025-06-15 23:06" and camp[3] == "61"
    assert camp[4] == "#露营 #自然" and camp[5] == "想去" and camp[6] == "周末/灵感"
    assert camp[7] == "秋天再去一次" and camp[9] == "示例博主 - 山里的清晨 [301].mp4"


def test_selection_export_and_errors(tmp_path: Path, master_key: str) -> None:
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        seed(tmp_path)
        picked = client.get("/api/export?items=301,301,303")
        assert client.get("/api/export?items=303").json()["code"] == "NOTHING_SAVED"
        assert client.get("/api/export").json()["code"] == "NOTHING_SELECTED"
        assert client.get("/api/export?albumId=99").status_code == 404
        client.cookies.clear()
        assert client.get("/api/export?items=301").status_code == 401

    names = zipfile.ZipFile(io.BytesIO(picked.content)).namelist()
    assert sum(name.endswith("[301].mp4") for name in names) == 1
    assert all(name.startswith("抖藏家导出-") for name in names)


def test_zip_stream_opens_cleanly_and_skips_files_that_vanished(tmp_path: Path) -> None:
    """Streamed ZIPs must still open, including when a file disappeared mid-way."""
    present = tmp_path / "a.mp4"
    present.write_bytes(b"x" * 3_000_000)
    gone = tmp_path / "gone.mp4"
    body = b"".join(_zip_stream([("d/a.mp4", present), ("d/gone.mp4", gone), ("d/list.csv", b"ok")]))
    archive = zipfile.ZipFile(io.BytesIO(body))
    assert archive.namelist() == ["d/a.mp4", "d/list.csv"]
    assert archive.read("d/a.mp4") == b"x" * 3_000_000 and archive.testzip() is None

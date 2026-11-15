import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def test_database_backup_streams_a_consistent_copy(tmp_path: Path, master_key: str) -> None:
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        response = client.get("/api/backup/database")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.sqlite3"
    assert 'filename="douzangjia-' in response.headers["content-disposition"]
    copy = tmp_path / "copy.sqlite3"
    copy.write_bytes(response.content)
    with sqlite3.connect(copy) as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert database.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] > 0
    assert not list((tmp_path / "tmp").glob("backup-*.sqlite3"))


def test_backup_requires_login(tmp_path: Path, master_key: str) -> None:
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        client.cookies.clear()
        assert client.get("/api/backup/database").status_code == 401


def test_storage_usage_splits_media_database_backups_and_quarantine(tmp_path: Path, master_key: str) -> None:
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        with sqlite3.connect(tmp_path / "data" / "archive.sqlite3") as database:
            database.execute(
                "INSERT INTO items (remote_id, item_type, author_name, description, first_seen_at, last_seen_at) "
                "VALUES ('1', 'video', 'a', 'd', 1, 1)"
            )
            for index, (kind, size, status) in enumerate(
                [("video", 1000, "ready"), ("image", 200, "ready"), ("image", 50, "pending")]
            ):
                database.execute(
                    "INSERT INTO media_files (item_id, asset_index, media_type, byte_size, status, "
                    "created_at, updated_at) VALUES ('1', ?, ?, ?, ?, 1, 1)",
                    (index, kind, size, status),
                )
        (tmp_path / "data" / "backups").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "backups" / "auto-20261114-000000.sqlite3").write_bytes(b"x" * 300)
        (tmp_path / "quarantine" / "objects").mkdir(parents=True)
        (tmp_path / "quarantine" / "objects" / "0.mp4.1").write_bytes(b"y" * 70)

        body = client.get("/api/storage").json()

    assert body["media"] == {"files": 2, "bytes": 1200, "videoBytes": 1000, "imageBytes": 200, "otherBytes": 0}
    assert body["backups"] == {"bytes": 300, "count": 1}
    assert body["quarantine"] == {"bytes": 70, "files": 1}
    assert body["database"]["bytes"] > 0
    assert body["disk"]["totalBytes"] >= body["disk"]["freeBytes"] > 0
    assert isinstance(body["disk"]["low"], bool)

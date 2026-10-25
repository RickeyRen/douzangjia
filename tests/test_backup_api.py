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

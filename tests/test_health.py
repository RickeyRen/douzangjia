from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def test_liveness_is_independent_of_setup(tmp_path: Path, master_key: str) -> None:
    app = create_app(Settings(archive_root=tmp_path, master_key=master_key))
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_archive_directory(tmp_path: Path, master_key: str) -> None:
    root = tmp_path / "archive"
    app = create_app(Settings(archive_root=root, master_key=master_key))
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["archiveRoot"] == "ok"


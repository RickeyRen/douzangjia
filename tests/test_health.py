import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.browser_coordinator import BrowserCoordinator
from douyin_archive.config import Settings


def test_application_uses_douzangjia_product_name(
    tmp_path: Path, master_key: str
) -> None:
    app = create_app(Settings(archive_root=tmp_path, master_key=master_key))

    assert app.title == "DouZangJia"


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
    assert response.json()["checks"]["browserProfile"] == "ok"
    assert response.json()["checks"]["browserConnection"] == "not_started"
    profile = root / "data" / "chromium-profile"
    assert stat.S_IMODE(profile.stat().st_mode) == 0o700


@pytest.mark.parametrize("connection", ["disconnected", "unresponsive"])
def test_readiness_fails_when_browser_connection_is_broken(
    tmp_path: Path,
    master_key: str,
    monkeypatch: pytest.MonkeyPatch,
    connection: str,
) -> None:
    """Catches Docker reporting healthy while every sync fails on a dead browser."""

    async def broken_probe(_self: BrowserCoordinator) -> str:
        return connection

    monkeypatch.setattr(BrowserCoordinator, "probe", broken_probe)
    app = create_app(Settings(archive_root=tmp_path, master_key=master_key))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["checks"]["browserConnection"] == connection

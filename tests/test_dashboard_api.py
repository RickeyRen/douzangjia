import sqlite3

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def test_dashboard_exposes_professional_nas_and_library_metrics(
    tmp_path, master_key: str
) -> None:
    with TestClient(
        create_app(Settings(archive_root=tmp_path, master_key=master_key))
    ) as client:
        setup = client.post(
            "/api/setup", json={"password": "a secure local passphrase"}
        )
        response = client.get("/api/dashboard")

    assert setup.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["storage"]["totalBytes"] > 0
    assert payload["storage"]["freeBytes"] >= 0
    assert payload["storage"]["archiveBytes"] == 0
    assert payload["system"]["cpuCount"] >= 1
    assert payload["system"]["memoryTotalBytes"] >= 0
    assert payload["system"]["processMemoryBytes"] >= 0
    assert payload["library"] == {
        "items": 0,
        "archivedItems": 0,
        "mediaFiles": 0,
        "creators": 0,
        "sources": 11,
        "completeSources": 0,
        "incompleteSources": 0,
        "neverSyncedSources": 11,
        "discoveredLinks": 0,
        "archivedBytes": 0,
    }
    assert payload["queue"]["pending"] == 0
    assert payload["queue"]["speedBps"] == 0
    assert payload["health"]["recentErrors"] == 0
    assert payload["account"]["status"] == "unknown"
    assert len(payload["sources"]) == 11
    assert payload["sources"][0]["autoDownloadEnabled"] is False
    assert payload["generatedAt"] > 0


def test_dashboard_series_returns_persisted_real_samples(
    tmp_path, master_key: str
) -> None:
    """Catches the history endpoint fabricating or omitting stored telemetry."""
    with TestClient(
        create_app(Settings(archive_root=tmp_path, master_key=master_key))
    ) as client:
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        connection = sqlite3.connect(tmp_path / "data" / "archive.sqlite3")
        connection.execute(
            "INSERT INTO metric_samples "
            "(sampled_at, download_speed_bps, archive_bytes) "
            "VALUES (unixepoch(), 2048, 4096)"
        )
        connection.commit()
        connection.close()
        response = client.get("/api/dashboard/series?window=15m")

    assert response.status_code == 200
    point = response.json()["items"][-1]
    assert point["downloadSpeedBps"] == 2048.0
    assert point["archiveBytes"] == 4096

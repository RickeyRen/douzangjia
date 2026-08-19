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
        "creators": 0,
        "sources": 10,
        "completeSources": 0,
        "incompleteSources": 0,
        "neverSyncedSources": 10,
        "discoveredLinks": 0,
        "archivedBytes": 0,
    }
    assert payload["queue"]["pending"] == 0
    assert payload["queue"]["speedBps"] == 0
    assert payload["health"]["recentErrors"] == 0
    assert payload["generatedAt"] > 0

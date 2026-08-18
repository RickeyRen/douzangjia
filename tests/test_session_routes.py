from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def build_client(tmp_path: Path, master_key: str) -> TestClient:
    return TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key)))


def test_first_run_setup_creates_admin_and_session(tmp_path: Path, master_key: str) -> None:
    with build_client(tmp_path, master_key) as client:
        response = client.post("/api/setup", json={"password": "a secure local passphrase"})
    assert response.status_code == 201
    assert response.json()["configured"] is True
    assert response.cookies.get("archive_session")


def test_second_setup_is_rejected(tmp_path: Path, master_key: str) -> None:
    with build_client(tmp_path, master_key) as client:
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        response = client.post("/api/setup", json={"password": "another secure passphrase"})
    assert response.status_code == 409
    assert response.json()["code"] == "ALREADY_CONFIGURED"


def test_mutation_requires_csrf_after_setup(tmp_path: Path, master_key: str) -> None:
    with build_client(tmp_path, master_key) as client:
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        response = client.post("/api/protected-test")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REQUIRED"


def test_public_status_reports_only_setup_and_session_booleans(
    tmp_path: Path, master_key: str
) -> None:
    with build_client(tmp_path, master_key) as client:
        before = client.get("/api/status")
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        authenticated = client.get("/api/status")
        client.cookies.clear()
        signed_out = client.get("/api/status")

    assert before.json() == {
        "configured": False,
        "authenticated": False,
        "douyinAuthenticated": False,
    }
    assert authenticated.json() == {
        "configured": True,
        "authenticated": True,
        "douyinAuthenticated": False,
    }
    assert signed_out.status_code == 200
    assert signed_out.json()["authenticated"] is False

from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def build_client(tmp_path: Path, master_key: str) -> TestClient:
    return TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key)))


def test_default_auth_browser_uses_app_persistent_coordinator(
    tmp_path: Path, master_key: str
) -> None:
    app = create_app(Settings(archive_root=tmp_path, master_key=master_key))

    with TestClient(app):
        coordinator = app.state.browser_coordinator
        browser = app.state.auth_service.browser
        assert browser.coordinator is coordinator
        assert coordinator.profile_store.profile_path == (tmp_path / "data" / "chromium-profile")


def test_first_run_setup_creates_admin_and_session(tmp_path: Path, master_key: str) -> None:
    with build_client(tmp_path, master_key) as client:
        response = client.post(
            "/api/setup",
            json={"username": "RENJIAWEI", "password": "a secure local passphrase"},
        )
    assert response.status_code == 201
    assert response.json()["configured"] is True
    assert response.json()["username"] == "RENJIAWEI"
    assert response.cookies.get("archive_session")


def test_login_requires_matching_username_and_is_case_insensitive(
    tmp_path: Path, master_key: str
) -> None:
    with build_client(tmp_path, master_key) as client:
        client.post(
            "/api/setup",
            json={"username": "RenJiaWei", "password": "a secure local passphrase"},
        )
        client.cookies.clear()
        wrong_username = client.post(
            "/api/session",
            json={"username": "somebody-else", "password": "a secure local passphrase"},
        )
        response = client.post(
            "/api/session",
            json={"username": "RENJIAWEI", "password": "a secure local passphrase"},
        )

    assert wrong_username.status_code == 401
    assert wrong_username.json()["message"] == "用户名或密码不正确"
    assert response.status_code == 200
    assert response.cookies.get("archive_session")


def test_legacy_admin_requires_current_password_to_claim_owner_identity(
    tmp_path: Path, master_key: str
) -> None:
    from douyin_archive.security import PasswordHasher

    data = tmp_path / "data"
    data.mkdir(parents=True)
    legacy_hash = PasswordHasher().hash("the original secure password")
    (data / "admin.json").write_text(
        f'{{"passwordHash":"{legacy_hash}"}}', encoding="utf-8"
    )

    with build_client(tmp_path, master_key) as client:
        status = client.get("/api/status")
        rejected = client.post(
            "/api/admin/migrate-owner",
            json={"username": "RENJIAWEI", "currentPassword": "the wrong secure password"},
        )
        migrated = client.post(
            "/api/admin/migrate-owner",
            json={"username": "RENJIAWEI", "currentPassword": "the original secure password"},
        )
        client.cookies.clear()
        login = client.post(
            "/api/session",
            json={"username": "renjiawei", "password": "the original secure password"},
        )

    assert status.json()["ownerSetupRequired"] is True
    assert rejected.status_code == 401
    assert migrated.status_code == 200
    assert migrated.json()["username"] == "RENJIAWEI"
    assert login.status_code == 200


def test_second_setup_is_rejected(tmp_path: Path, master_key: str) -> None:
    with build_client(tmp_path, master_key) as client:
        client.post(
            "/api/setup",
            json={"username": "RENJIAWEI", "password": "a secure local passphrase"},
        )
        response = client.post(
            "/api/setup",
            json={"username": "RENJIAWEI", "password": "another secure passphrase"},
        )
    assert response.status_code == 409
    assert response.json()["code"] == "ALREADY_CONFIGURED"


def test_mutation_requires_csrf_after_setup(tmp_path: Path, master_key: str) -> None:
    with build_client(tmp_path, master_key) as client:
        client.post(
            "/api/setup",
            json={"username": "RENJIAWEI", "password": "a secure local passphrase"},
        )
        response = client.post("/api/protected-test")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REQUIRED"


def test_public_status_reports_only_setup_and_session_booleans(
    tmp_path: Path, master_key: str
) -> None:
    with build_client(tmp_path, master_key) as client:
        before = client.get("/api/status")
        client.post(
            "/api/setup",
            json={"username": "RENJIAWEI", "password": "a secure local passphrase"},
        )
        authenticated = client.get("/api/status")
        client.cookies.clear()
        signed_out = client.get("/api/status")

    assert before.json() == {
        "configured": False,
        "ownerSetupRequired": False,
        "authenticated": False,
        "douyinAuthenticated": False,
        "version": "0.2.0",
        "commit": "unknown",
    }
    assert {
        key: authenticated.json()[key]
        for key in ("configured", "authenticated", "douyinAuthenticated")
    } == {
        "configured": True,
        "authenticated": True,
        "douyinAuthenticated": False,
    }
    assert "douyinHealth" in authenticated.json()
    assert signed_out.status_code == 200
    assert signed_out.json()["authenticated"] is False
    assert "douyinHealth" not in signed_out.json()


def test_manual_sync_is_handed_to_the_runtime(tmp_path: Path, master_key: str) -> None:
    class FakeRuntime:
        def __init__(self, *_args) -> None:
            self.full_scan: bool | None = None

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def trigger_sync(self, *, full_scan: bool) -> int:
            self.full_scan = full_scan
            return 42

    runtime = FakeRuntime()
    app = create_app(
        Settings(archive_root=tmp_path, master_key=master_key),
        runtime_factory=lambda *_args: runtime,
    )
    with TestClient(app) as client:
        client.post(
            "/api/setup",
            json={"username": "RENJIAWEI", "password": "a secure local passphrase"},
        )
        csrf = client.cookies.get("archive_csrf")
        response = client.post(
            "/api/sync",
            headers={"X-CSRF-Token": csrf or ""},
            json={"fullScan": True},
        )

    assert response.status_code == 202
    assert response.json() == {"runId": 42}
    assert runtime.full_scan is True

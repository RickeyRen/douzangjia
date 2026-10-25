from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.login_guard import MAX_FAILURES, LoginGuard


def test_guard_locks_after_repeated_failures_with_growing_waits() -> None:
    now = [1000.0]
    guard = LoginGuard(clock=lambda: now[0])

    for _ in range(MAX_FAILURES - 1):
        guard.record_failure("ip:1")
    assert guard.retry_after("ip:1") == 0
    guard.record_failure("ip:1")
    assert 0 < guard.retry_after("ip:1") <= 31

    now[0] += 31
    assert guard.retry_after("ip:1") == 0
    for _ in range(MAX_FAILURES):
        guard.record_failure("ip:1")
    assert guard.retry_after("ip:1") > 31  # second lockout is longer

    guard.record_success("ip:1")
    assert guard.retry_after("ip:1") == 0


def test_login_endpoint_rate_limits_password_guessing(tmp_path: Path, master_key: str) -> None:
    """Catches the single admin account being brute-forced from the LAN."""
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        client.delete("/api/session")
        for _ in range(MAX_FAILURES):
            wrong = client.post("/api/session", json={"username": "owner", "password": "nope-nope-nope"})
            assert wrong.status_code == 401
        blocked = client.post("/api/session", json={"username": "owner", "password": "a secure local passphrase"})
        other_user = client.post("/api/session", json={"username": "someone", "password": "x"})

    assert blocked.status_code == 429
    assert blocked.json()["code"] == "TOO_MANY_ATTEMPTS"
    assert int(blocked.headers["Retry-After"]) >= 1
    # The client address is locked too, so switching usernames does not help.
    assert other_user.status_code == 429


def test_status_reports_version(tmp_path: Path, master_key: str) -> None:
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        body = client.get("/api/status").json()

    assert body["version"] == "0.2.0"
    assert "commit" in body

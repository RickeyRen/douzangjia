from pathlib import Path

import pytest
from pydantic import ValidationError

from douyin_archive.config import Settings


def test_settings_reject_filesystem_root(master_key: str) -> None:
    with pytest.raises(ValidationError, match="filesystem root"):
        Settings(archive_root=Path("/"), master_key=master_key)


def test_settings_resolve_archive_root(tmp_path: Path, master_key: str) -> None:
    settings = Settings(archive_root=tmp_path / "archive", master_key=master_key)
    assert settings.archive_root == (tmp_path / "archive").resolve()
    assert settings.browser_profile_path == (
        tmp_path / "archive" / "data" / "chromium-profile"
    ).resolve()
    assert settings.sync_interval_seconds == 300


def test_settings_use_documented_environment_names(
    tmp_path: Path, master_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setenv("ARCHIVE_MASTER_KEY", master_key)
    monkeypatch.setenv("APP_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_PORT", "8123")
    monkeypatch.setenv("WEB_DIST", str(tmp_path / "web"))
    settings = Settings()
    assert settings.archive_root == (tmp_path / "archive").resolve()
    assert settings.bind_host == "127.0.0.1"
    assert settings.port == 8123
    assert settings.web_dist == (tmp_path / "web").resolve()

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
    assert settings.sync_interval_seconds == 300


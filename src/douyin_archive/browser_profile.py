import os
import stat
from datetime import UTC, datetime
from pathlib import Path


class BrowserProfileStore:
    """Own the private Chromium profile directory below the archive root."""

    def __init__(self, archive_root: Path) -> None:
        self.profile_path = archive_root / "data" / "chromium-profile"

    def prepare(self) -> Path:
        self.profile_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.profile_path, 0o700)
        if stat.S_IMODE(self.profile_path.stat().st_mode) != 0o700:
            raise PermissionError("browser profile must have mode 0700")
        return self.profile_path

    def quarantine(self, reason: str) -> Path:
        suffix = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        target = self.profile_path.with_name(f"chromium-profile.{reason}.{suffix}")
        self.profile_path.rename(target)
        return target

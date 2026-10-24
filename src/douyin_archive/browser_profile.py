import os
import socket
import stat
from datetime import UTC, datetime
from pathlib import Path

SINGLETON_FILES = ("SingletonLock", "SingletonSocket", "SingletonCookie")


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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

    def clear_stale_singleton(self, *, hostname: str | None = None) -> bool:
        """Drop a Chromium profile lock left behind by a previous container.

        Chromium records ``<hostname>-<pid>`` in SingletonLock and refuses a
        profile locked by "another computer". A recreated container gets a new
        hostname, so a browser killed during shutdown would otherwise block
        every later start. One container owns this archive, so a foreign
        hostname, or our own hostname with a dead pid, means the lock is stale.
        """
        lock = self.profile_path / "SingletonLock"
        try:
            owner = os.readlink(lock)
        except OSError:
            return False
        host, _, pid = owner.rpartition("-")
        if host == (hostname or socket.gethostname()) and (not pid.isdigit() or _process_alive(int(pid))):
            return False
        for name in SINGLETON_FILES:
            (self.profile_path / name).unlink(missing_ok=True)
        return True

    def quarantine(self, reason: str) -> Path:
        suffix = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        target = self.profile_path.with_name(f"chromium-profile.{reason}.{suffix}")
        self.profile_path.rename(target)
        return target

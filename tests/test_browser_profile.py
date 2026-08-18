import stat
from pathlib import Path

from douyin_archive.browser_profile import BrowserProfileStore


def test_prepare_creates_private_profile_directory(tmp_path: Path) -> None:
    store = BrowserProfileStore(tmp_path)

    path = store.prepare()

    assert path == tmp_path / "data" / "chromium-profile"
    assert stat.S_IMODE(path.stat().st_mode) == 0o700


def test_prepare_repairs_permissive_profile_mode(tmp_path: Path) -> None:
    profile = tmp_path / "data" / "chromium-profile"
    profile.mkdir(parents=True, mode=0o755)
    profile.chmod(0o755)

    BrowserProfileStore(tmp_path).prepare()

    assert stat.S_IMODE(profile.stat().st_mode) == 0o700


def test_quarantine_preserves_corrupt_profile(tmp_path: Path) -> None:
    store = BrowserProfileStore(tmp_path)
    store.prepare()
    (store.profile_path / "marker").write_text("keep", encoding="utf-8")

    quarantined = store.quarantine("corrupt")

    assert quarantined.parent == store.profile_path.parent
    assert quarantined.name.startswith("chromium-profile.corrupt.")
    assert (quarantined / "marker").read_text(encoding="utf-8") == "keep"
    assert not store.profile_path.exists()

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


def lock_profile(store: BrowserProfileStore, owner: str) -> None:
    store.prepare()
    (store.profile_path / "SingletonLock").symlink_to(owner)
    (store.profile_path / "SingletonCookie").symlink_to("12345")
    (store.profile_path / "SingletonSocket").symlink_to("/tmp/org.chromium.Chromium.x/SingletonSocket")
    (store.profile_path / "Cookies").write_text("session", encoding="utf-8")


def remaining(store: BrowserProfileStore) -> set[str]:
    return {path.name for path in store.profile_path.iterdir()}


def test_lock_from_a_previous_container_is_cleared(tmp_path: Path) -> None:
    """Catches a recreated container failing to start on the old one's lock."""
    store = BrowserProfileStore(tmp_path)
    lock_profile(store, "42965adc7656-5612")

    assert store.clear_stale_singleton(hostname="96d4bc8ff618") is True
    assert remaining(store) == {"Cookies"}


def test_live_lock_on_this_host_is_kept(tmp_path: Path) -> None:
    import os

    store = BrowserProfileStore(tmp_path)
    lock_profile(store, f"96d4bc8ff618-{os.getpid()}")

    assert store.clear_stale_singleton(hostname="96d4bc8ff618") is False
    assert "SingletonLock" in remaining(store)


def test_dead_lock_on_this_host_is_cleared(tmp_path: Path) -> None:
    store = BrowserProfileStore(tmp_path)
    lock_profile(store, "96d4bc8ff618-999999")

    assert store.clear_stale_singleton(hostname="96d4bc8ff618") is True
    assert remaining(store) == {"Cookies"}


def test_unlocked_profile_is_left_alone(tmp_path: Path) -> None:
    store = BrowserProfileStore(tmp_path)
    store.prepare()

    assert store.clear_stale_singleton(hostname="any") is False

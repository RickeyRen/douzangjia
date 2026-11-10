import io
from pathlib import Path

from douyin_archive import admin_cli
from douyin_archive.admin_store import AdminStore
from douyin_archive.security import PasswordHasher


def test_add_debug_account_reads_password_from_stdin_without_printing_it(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    store = AdminStore(tmp_path / "data" / "admin.json")
    store.create_owner("owner", PasswordHasher().hash("owner secure password"))
    monkeypatch.setattr(admin_cli.sys, "stdin", io.StringIO("debug secret from stdin"))

    assert admin_cli.main(
        ["add", "--archive-root", str(tmp_path), "--username", "codex-debug", "--kind", "debug"]
    ) == 0

    account = store.account("codex-debug")
    assert account is not None
    assert PasswordHasher().verify(account.password_hash, "debug secret from stdin")
    assert "debug secret from stdin" not in capsys.readouterr().out


def test_remove_debug_account_is_explicit_and_reversible_at_store_level(tmp_path: Path) -> None:
    store = AdminStore(tmp_path / "data" / "admin.json")
    store.create_owner("owner", PasswordHasher().hash("owner secure password"))
    store.upsert_account("codex-debug", PasswordHasher().hash("debug password"), kind="debug")

    assert admin_cli.main(
        ["remove", "--archive-root", str(tmp_path), "--username", "codex-debug"]
    ) == 0
    assert store.account("codex-debug") is None


def test_reset_password_replaces_only_that_accounts_hash(tmp_path: Path, monkeypatch, capsys) -> None:
    store = AdminStore(tmp_path / "data" / "admin.json")
    store.create_owner("RENJIAWEI", PasswordHasher().hash("forgotten old password"))
    store.upsert_account("codex-debug", PasswordHasher().hash("debug password"), kind="debug")
    monkeypatch.setattr(admin_cli.sys, "stdin", io.StringIO("brand new owner password\n"))

    assert admin_cli.main(
        ["reset-password", "--archive-root", str(tmp_path), "--username", "renjiawei"]
    ) == 0

    owner = store.account("RENJIAWEI")
    assert owner is not None and owner.kind == "owner" and owner.username == "RENJIAWEI"
    assert PasswordHasher().verify(owner.password_hash, "brand new owner password")
    assert not PasswordHasher().verify(owner.password_hash, "forgotten old password")
    debug = store.account("codex-debug")
    assert debug is not None and PasswordHasher().verify(debug.password_hash, "debug password")
    assert "brand new owner password" not in capsys.readouterr().out


def test_reset_password_rejects_short_password_and_unknown_user(tmp_path: Path, monkeypatch) -> None:
    store = AdminStore(tmp_path / "data" / "admin.json")
    store.create_owner("owner", PasswordHasher().hash("owner secure password"))
    monkeypatch.setattr(admin_cli.sys, "stdin", io.StringIO("short\n"))
    assert admin_cli.main(["reset-password", "--archive-root", str(tmp_path), "--username", "owner"]) == 1
    account = store.account("owner")
    assert account is not None and PasswordHasher().verify(account.password_hash, "owner secure password")
    assert admin_cli.main(["reset-password", "--archive-root", str(tmp_path), "--username", "nobody"]) == 1

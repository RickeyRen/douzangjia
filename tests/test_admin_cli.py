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

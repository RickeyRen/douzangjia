import json
import stat
from pathlib import Path

import pytest

from douyin_archive.admin_store import AdminStore


def test_create_owner_stores_normalized_account_without_plaintext_password(tmp_path: Path) -> None:
    path = tmp_path / "data" / "admin.json"
    store = AdminStore(path)

    store.create_owner("  RenJiaWei  ", "$argon2id$owner-hash")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "version": 2,
        "accounts": [
            {
                "username": "RenJiaWei",
                "usernameKey": "renjiawei",
                "passwordHash": "$argon2id$owner-hash",
                "kind": "owner",
            }
        ],
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "plain-password" not in path.read_text(encoding="utf-8")


def test_legacy_password_file_requires_owner_identity_migration(tmp_path: Path) -> None:
    path = tmp_path / "admin.json"
    path.write_text('{"passwordHash":"$argon2id$legacy-hash"}', encoding="utf-8")
    store = AdminStore(path)

    assert store.configured is True
    assert store.owner_setup_required is True
    assert store.legacy_password_hash() == "$argon2id$legacy-hash"
    assert store.account("anyone") is None


def test_migrate_owner_replaces_legacy_hash_and_preserves_secondary_accounts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "admin.json"
    path.write_text('{"passwordHash":"$argon2id$legacy-hash"}', encoding="utf-8")
    store = AdminStore(path)
    store.upsert_account("codex-debug", "$argon2id$debug-hash", kind="debug")

    store.migrate_owner("RENJIAWEI", "$argon2id$legacy-hash")

    assert store.owner_setup_required is False
    assert store.account("renjiawei").kind == "owner"
    assert store.account("CODEX-DEBUG").kind == "debug"
    assert store.legacy_password_hash() is None


def test_normalized_duplicate_usernames_are_rejected(tmp_path: Path) -> None:
    store = AdminStore(tmp_path / "admin.json")
    store.create_owner("RenJiaWei", "$argon2id$owner-hash")

    with pytest.raises(FileExistsError):
        store.upsert_account(" renjiawei ", "$argon2id$other-hash", kind="debug")


def test_debug_account_can_be_revoked_without_removing_owner(tmp_path: Path) -> None:
    store = AdminStore(tmp_path / "admin.json")
    store.create_owner("RENJIAWEI", "$argon2id$owner-hash")
    store.upsert_account("codex-debug", "$argon2id$debug-hash", kind="debug")

    assert store.remove_account("CODEX-DEBUG") is True
    assert store.account("codex-debug") is None
    assert store.account("renjiawei") is not None


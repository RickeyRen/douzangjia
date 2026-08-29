from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AccountKind = Literal["owner", "debug"]


def normalize_username(value: str) -> tuple[str, str]:
    username = value.strip()
    if not 2 <= len(username) <= 32:
        raise ValueError("用户名长度必须为 2 到 32 个字符")
    if any(unicodedata.category(character).startswith("C") for character in username):
        raise ValueError("用户名不能包含控制字符")
    return username, username.casefold()


@dataclass(frozen=True, slots=True)
class AdminAccount:
    username: str
    username_key: str
    password_hash: str
    kind: AccountKind


class AdminStore:
    """Atomic, backwards-compatible local administrator credential store."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    @property
    def owner_setup_required(self) -> bool:
        payload = self._read()
        return bool(payload and self._legacy_hash(payload) and not self._owner(payload))

    def create_owner(self, username: str, password_hash: str) -> AdminAccount:
        if self.configured:
            raise FileExistsError(self.path)
        account = self._account_value(username, password_hash, "owner")
        self._write({"version": 2, "accounts": [self._serialize(account)]})
        return account

    def account(self, username: str) -> AdminAccount | None:
        try:
            _, username_key = normalize_username(username)
        except ValueError:
            return None
        payload = self._read()
        if payload is None:
            return None
        for value in self._accounts(payload):
            if value.username_key == username_key:
                return value
        return None

    def legacy_password_hash(self) -> str | None:
        payload = self._read()
        return self._legacy_hash(payload) if payload else None

    def migrate_owner(self, username: str, password_hash: str) -> AdminAccount:
        payload = self._read()
        if payload is None or not self._legacy_hash(payload) or self._owner(payload):
            raise RuntimeError("owner identity migration is not required")
        account = self._account_value(username, password_hash, "owner")
        accounts = self._accounts(payload)
        if any(value.username_key == account.username_key for value in accounts):
            raise FileExistsError(account.username)
        accounts.insert(0, account)
        self._write(
            {
                "version": 2,
                "accounts": [self._serialize(value) for value in accounts],
            }
        )
        return account

    def upsert_account(
        self,
        username: str,
        password_hash: str,
        *,
        kind: AccountKind,
    ) -> AdminAccount:
        account = self._account_value(username, password_hash, kind)
        payload = self._read() or {}
        accounts = self._accounts(payload)
        if any(value.username_key == account.username_key for value in accounts):
            raise FileExistsError(account.username)
        accounts.append(account)
        next_payload: dict[str, object] = {
            "version": 2,
            "accounts": [self._serialize(value) for value in accounts],
        }
        legacy_hash = self._legacy_hash(payload)
        if legacy_hash and not self._owner(payload):
            next_payload["legacyPasswordHash"] = legacy_hash
        self._write(next_payload)
        return account

    def remove_account(self, username: str) -> bool:
        payload = self._read()
        if payload is None:
            return False
        try:
            _, username_key = normalize_username(username)
        except ValueError:
            return False
        accounts = self._accounts(payload)
        remaining = [value for value in accounts if value.username_key != username_key]
        if len(remaining) == len(accounts):
            return False
        if not any(value.kind == "owner" for value in remaining) and not self._legacy_hash(payload):
            raise ValueError("不能删除唯一的所有者账户")
        next_payload: dict[str, object] = {
            "version": 2,
            "accounts": [self._serialize(value) for value in remaining],
        }
        legacy_hash = self._legacy_hash(payload)
        if legacy_hash:
            next_payload["legacyPasswordHash"] = legacy_hash
        self._write(next_payload)
        return True

    def _read(self) -> dict[str, object] | None:
        if not self.configured:
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _legacy_hash(payload: dict[str, object]) -> str | None:
        value = payload.get("legacyPasswordHash", payload.get("passwordHash"))
        return str(value) if value else None

    @staticmethod
    def _accounts(payload: dict[str, object]) -> list[AdminAccount]:
        values = payload.get("accounts")
        if not isinstance(values, list):
            return []
        accounts: list[AdminAccount] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            try:
                username = str(value["username"])
                username_key = str(value["usernameKey"])
                password_hash = str(value["passwordHash"])
                kind = value["kind"]
                if kind not in ("owner", "debug"):
                    continue
                accounts.append(
                    AdminAccount(username, username_key, password_hash, kind)
                )
            except KeyError:
                continue
        return accounts

    @staticmethod
    def _owner(payload: dict[str, object]) -> AdminAccount | None:
        return next((value for value in AdminStore._accounts(payload) if value.kind == "owner"), None)

    @staticmethod
    def _account_value(
        username: str,
        password_hash: str,
        kind: AccountKind,
    ) -> AdminAccount:
        display_name, username_key = normalize_username(username)
        return AdminAccount(display_name, username_key, password_hash, kind)

    @staticmethod
    def _serialize(account: AdminAccount) -> dict[str, str]:
        return {
            "username": account.username,
            "usernameKey": account.username_key,
            "passwordHash": account.password_hash,
            "kind": account.kind,
        }

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)
        os.chmod(self.path, 0o600)

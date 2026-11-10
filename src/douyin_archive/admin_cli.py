from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .admin_store import AdminStore
from .security import PasswordHasher


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local DouZangJia administrator accounts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", help="Add a local account; reads its password from stdin")
    add.add_argument("--archive-root", type=Path, required=True)
    add.add_argument("--username", required=True)
    add.add_argument("--kind", choices=("owner", "debug"), default="debug")

    reset = subparsers.add_parser(
        "reset-password",
        help="Set a new password for an existing account; prompts twice without echo",
    )
    reset.add_argument("--archive-root", type=Path, required=True)
    reset.add_argument("--username", required=True)

    remove = subparsers.add_parser("remove", help="Remove a local account")
    remove.add_argument("--archive-root", type=Path, required=True)
    remove.add_argument("--username", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    store = AdminStore(arguments.archive_root / "data" / "admin.json")
    if arguments.command == "add":
        password = sys.stdin.read().rstrip("\r\n")
        if len(password) < 12:
            raise ValueError("password from stdin must contain at least 12 characters")
        account = store.upsert_account(
            arguments.username,
            PasswordHasher().hash(password),
            kind=arguments.kind,
        )
        print(f"account added: {account.username} ({account.kind})")
        return 0
    if arguments.command == "reset-password":
        return _reset_password(store, arguments.username)
    removed = store.remove_account(arguments.username)
    if not removed:
        print(f"account not found: {arguments.username}", file=sys.stderr)
        return 1
    print(f"account removed: {arguments.username}")
    return 0


def _read_new_password() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read().rstrip("\r\n")
    first = getpass.getpass("新密码（至少 12 位，输入时不显示）: ")
    second = getpass.getpass("再输入一次: ")
    if first != second:
        raise ValueError("两次输入的密码不一致")
    return first


def _reset_password(store: AdminStore, username: str) -> int:
    if store.account(username) is None:
        print(f"account not found: {username}", file=sys.stderr)
        return 1
    password = _read_new_password()
    if len(password) < 12:
        print("密码至少需要 12 个字符", file=sys.stderr)
        return 1
    account = store.set_password(username, PasswordHasher().hash(password))
    print(f"password reset: {account.username} ({account.kind})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

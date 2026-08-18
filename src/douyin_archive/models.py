from __future__ import annotations

import json
from dataclasses import dataclass
from sqlite3 import Row
from typing import Any


@dataclass(frozen=True, slots=True)
class Collection:
    remote_id: str
    name: str
    name_history: list[str]
    first_seen_at: int
    last_seen_at: int

    @classmethod
    def from_row(cls, row: Row) -> Collection:
        return cls(
            remote_id=row["remote_id"],
            name=row["name"],
            name_history=json.loads(row["name_history_json"]),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
        )


@dataclass(frozen=True, slots=True)
class DownloadJob:
    id: int
    kind: str
    remote_id: str
    payload: dict[str, Any]
    status: str
    attempts: int
    next_attempt_at: int
    claimed_by: str | None
    last_error_code: str | None

    @classmethod
    def from_row(cls, row: Row) -> DownloadJob:
        return cls(
            id=row["id"],
            kind=row["kind"],
            remote_id=row["remote_id"],
            payload=json.loads(row["payload_json"]),
            status=row["status"],
            attempts=row["attempts"],
            next_attempt_at=row["next_attempt_at"],
            claimed_by=row["claimed_by"],
            last_error_code=row["last_error_code"],
        )


@dataclass(frozen=True, slots=True)
class MediaAsset:
    remote_id: str
    asset_index: int
    media_type: str
    url: str
    mime_type: str | None = None
    expected_size: int | None = None


@dataclass(frozen=True, slots=True)
class RemoteItem:
    remote_id: str
    author_name: str
    description: str
    item_type: str
    published_at: int | None = None
    assets: tuple[MediaAsset, ...] = ()

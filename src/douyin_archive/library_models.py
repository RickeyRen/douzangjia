from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LibrarySourceKind(str, Enum):
    POST = "post"
    RECOMMEND = "recommend"
    LIKE = "like"
    FAVORITE_COLLECTION = "favorite_collection"
    FAVORITE_VIDEO = "favorite_video"
    FAVORITE_MUSIC = "favorite_music"
    FAVORITE_SERIES = "favorite_series"
    FAVORITE_DRAMA = "favorite_drama"
    WATCH_HISTORY = "watch_history"
    WATCH_LATER = "watch_later"
    RESERVATION = "reservation"
    FOLLOWING = "following"


class LibrarySyncStatus(str, Enum):
    NEVER = "never"
    RUNNING = "running"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LibrarySource:
    id: str
    kind: LibrarySourceKind
    remote_id: str
    name: str
    declared_count: int | None = None
    sync_cursor: str | None = None
    sync_status: LibrarySyncStatus = LibrarySyncStatus.NEVER
    last_full_scan_at: int | None = None
    last_incremental_scan_at: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CreatorRecord:
    remote_id: str
    nickname: str
    unique_id: str | None = None
    avatar_url: str | None = None
    follower_count: int | None = None
    post_count: int | None = None


@dataclass(frozen=True, slots=True)
class SourceIntegrity:
    source_id: str
    declared_count: int | None
    discovered_count: int
    archived_count: int
    missing_count: int
    sync_status: LibrarySyncStatus
    complete: bool


@dataclass(frozen=True, slots=True)
class SourceEntityRecord:
    source_id: str
    remote_id: str
    entity_type: str
    title: str
    subtitle: str | None
    cover_url: str | None
    source_url: str | None
    remote_order: str | None
    metadata: dict[str, object] | None = None

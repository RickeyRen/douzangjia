"""Keep a creator's identity after Douyin bans, resets or closes the account.

Douyin rewrites such profiles in place: a reset account's nickname becomes
its numeric 抖音号 and its avatar the default one, a closed account reads
"该用户已注销". Every identity we see is therefore stored as a snapshot, the
last healthy one is what the archive shows, and a slow background check
classifies the creators the library holds.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .db import Database
from .library_models import CreatorRecord
from .library_scope import library_item_sql
from .provider.base import ProviderChanged, ProviderError

logger = logging.getLogger(__name__)

ACTIVE = "active"
RESET = "reset"
DEACTIVATED = "deactivated"
BANNED = "banned"
VANISHED = "vanished"
ARCHIVE_STATUSES = (RESET, DEACTIVATED, BANNED, VANISHED)

DEACTIVATED_NAMES = frozenset({"该用户已注销", "用户已注销", "账号已注销", "已注销"})
DEFAULT_AVATAR_MARK = "aweme_default_avatar"

CHECK_EVERY_SECONDS = 60
MEDIA_EVERY_SECONDS = 45
ACTIVE_RECHECK_SECONDS = 14 * 86_400
ARCHIVED_RECHECK_SECONDS = 3 * 86_400
PENDING_RECHECK_SECONDS = 6 * 3_600
FAILED_RECHECK_SECONDS = 3_600
CANDIDATE_REFRESH_SECONDS = 30 * 60
MEDIA_BATCH_SIZE = 12
MAX_MEDIA_ATTEMPTS = 5
MAX_MEDIA_BYTES = 8 * 1024 * 1024

_SIZE_PREFIX = re.compile(r"^(?:aweme/\d+x\d+/|img/|obj/)")
_IMAGE_SUFFIX = re.compile(r"(?:\.(?:jpe?g|png|webp|heic|image|awebp))+$", re.IGNORECASE)


def avatar_key(url: str | None) -> str | None:
    """The stable part of a Douyin image URL; the query and size change per fetch."""
    if not url:
        return None
    path = urlparse(url).path.lstrip("/")
    path = _SIZE_PREFIX.sub("", path)
    path = path.split("~", 1)[0]
    path = _IMAGE_SUFFIX.sub("", path)
    return path or None


def is_default_avatar(url: str | None) -> bool:
    return bool(url) and DEFAULT_AVATAR_MARK in str(url)


def degraded_kind(nickname: str, unique_id: str | None, avatar_url: str | None) -> str | None:
    """Recognise Douyin's placeholder identities, never a name a person chose."""
    name = nickname.strip()
    if name in DEACTIVATED_NAMES:
        return DEACTIVATED
    handle = (unique_id or "").strip()
    # A real numeric nickname ("29", "667") is common; the reset placeholder is
    # the 抖音号 itself, paired with the default avatar.
    if name and name == handle and name.isdigit() and (avatar_url is None or is_default_avatar(avatar_url)):
        return RESET
    return None


def _fingerprint(nickname: str, unique_id: str | None, key: str | None) -> str:
    raw = "\x1f".join((nickname.strip(), (unique_id or "").strip(), key or ""))
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


async def record_snapshot(
    database: Database, creator: CreatorRecord, *, source: str, seen_at: int | None = None
) -> None:
    """Store this identity once; later sightings only refresh its details."""
    nickname = creator.nickname.strip()
    if not nickname:
        return
    now = seen_at or int(time.time())
    key = avatar_key(creator.avatar_url)
    kind = degraded_kind(nickname, creator.unique_id, creator.avatar_url)
    await database.execute(
        "INSERT INTO creator_snapshots "
        "(creator_id, fingerprint, nickname, unique_id, signature, avatar_url, avatar_key, "
        "cover_url, follower_count, following_count, total_favorited, post_count, ip_location, "
        "degraded, source, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(creator_id, fingerprint) DO UPDATE SET "
        "signature=COALESCE(excluded.signature, creator_snapshots.signature), "
        "avatar_url=COALESCE(excluded.avatar_url, creator_snapshots.avatar_url), "
        "cover_url=COALESCE(excluded.cover_url, creator_snapshots.cover_url), "
        "follower_count=COALESCE(excluded.follower_count, creator_snapshots.follower_count), "
        "following_count=COALESCE(excluded.following_count, creator_snapshots.following_count), "
        "total_favorited=COALESCE(excluded.total_favorited, creator_snapshots.total_favorited), "
        "post_count=COALESCE(excluded.post_count, creator_snapshots.post_count), "
        "ip_location=COALESCE(excluded.ip_location, creator_snapshots.ip_location), "
        "last_seen_at=MAX(creator_snapshots.last_seen_at, excluded.last_seen_at)",
        (
            creator.remote_id,
            _fingerprint(nickname, creator.unique_id, key),
            nickname,
            creator.unique_id,
            creator.signature,
            creator.avatar_url,
            key,
            creator.cover_url,
            creator.follower_count,
            creator.following_count,
            creator.total_favorited,
            creator.post_count,
            creator.ip_location,
            int(kind is not None),
            source,
            now,
            now,
        ),
    )
    if kind == DEACTIVATED:
        # Douyin's own wording; no second look is needed to believe it.
        await database.execute(
            "UPDATE creators SET archive_status=?, archive_status_since=?, archive_evidence=?, "
            "archive_pending_status=NULL, archive_pending_count=0 "
            "WHERE remote_id=? AND archive_status IN ('active', 'reset')",
            (DEACTIVATED, now, "nickname", creator.remote_id),
        )
    elif kind == RESET:
        # Only a hint; the status check confirms it from the profile itself.
        await database.execute(
            "UPDATE creators SET archive_checked_at=NULL "
            "WHERE remote_id=? AND archive_status='active' AND EXISTS ("
            "SELECT 1 FROM creator_snapshots s WHERE s.creator_id=creators.remote_id AND s.degraded=0)",
            (creator.remote_id,),
        )


async def preserved_identity(database: Database, creator_id: str) -> Any:
    """The last identity the creator chose themselves, preferring one with a stored avatar."""
    return await database.fetchone(
        "SELECT * FROM creator_snapshots WHERE creator_id=? AND degraded=0 "
        "ORDER BY (avatar_path IS NOT NULL) DESC, last_seen_at DESC, id DESC LIMIT 1",
        (creator_id,),
    )


async def backfill_snapshots(database: Database, archive_root: Path) -> int:
    """Seed snapshots from what the archive already knows, once per creator."""
    rows = await database.fetchall(
        "SELECT * FROM creators c WHERE NOT EXISTS ("
        "SELECT 1 FROM creator_snapshots s WHERE s.creator_id=c.remote_id AND s.source<>'download_job')"
    )
    for row in rows:
        await record_snapshot(
            database,
            CreatorRecord(
                remote_id=row["remote_id"],
                nickname=row["nickname"],
                unique_id=row["unique_id"],
                avatar_url=row["avatar_url"],
                follower_count=row["follower_count"],
                post_count=row["post_count"],
            ),
            source="current",
            seen_at=int(row["last_seen_at"]),
        )
    await _adopt_legacy_avatars(database, archive_root)
    return len(rows)


async def _adopt_legacy_avatars(database: Database, archive_root: Path) -> None:
    """The old per-creator cache may still hold an avatar from before a reset."""
    legacy = archive_root.resolve() / "cache" / "avatars"
    if not legacy.is_dir():
        return
    store = CreatorMediaStore(archive_root)
    creators = await database.fetchall("SELECT remote_id, nickname, unique_id FROM creators")
    for creator in creators:
        digest = hashlib.sha256(str(creator["remote_id"]).encode()).hexdigest()[:24]
        image, marker = legacy / f"{digest}.img", legacy / f"{digest}.url"
        if not image.is_file() or not marker.is_file() or image.stat().st_size == 0:
            continue
        url = marker.read_text(encoding="utf-8").strip()
        key = avatar_key(url)
        if not key or is_default_avatar(url):
            continue
        stored = store.adopt(key, image)
        updated = await database.execute(
            "UPDATE creator_snapshots SET avatar_path=? "
            "WHERE creator_id=? AND avatar_key=? AND avatar_path IS NULL",
            (stored, creator["remote_id"], key),
        )
        if updated.rowcount or await database.fetchone(
            "SELECT 1 FROM creator_snapshots WHERE creator_id=? AND avatar_key=?",
            (creator["remote_id"], key),
        ):
            continue
        # The avatar outlived the name it belonged to; pair it with the newest
        # chosen name we have, which is the best record of who posted it.
        named = await database.fetchone(
            "SELECT nickname, unique_id FROM creator_snapshots WHERE creator_id=? AND degraded=0 "
            "ORDER BY last_seen_at DESC LIMIT 1",
            (creator["remote_id"],),
        )
        if named is None:
            continue
        seen = int(image.stat().st_mtime)
        await database.execute(
            "INSERT OR IGNORE INTO creator_snapshots "
            "(creator_id, fingerprint, nickname, unique_id, avatar_url, avatar_key, avatar_path, "
            "source, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'avatar_cache', ?, ?)",
            (
                creator["remote_id"],
                _fingerprint(named["nickname"], named["unique_id"], key),
                named["nickname"],
                named["unique_id"],
                url,
                key,
                stored,
                seen,
                seen,
            ),
        )


class CreatorMediaStore:
    """Avatars and profile banners, one file per image version, never overwritten."""

    def __init__(self, archive_root: Path) -> None:
        self.root = archive_root.resolve()
        self.directory = self.root / "cache" / "creators"

    def relative_for(self, key: str) -> str:
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return f"cache/creators/{digest[:2]}/{digest}.img"

    def resolve(self, relative: str | None) -> Path | None:
        if not relative:
            return None
        path = (self.root / relative).resolve()
        if self.directory not in path.parents or not path.is_file():
            return None
        return path

    def adopt(self, key: str, source: Path) -> str:
        relative = self.relative_for(key)
        target = self.root / relative
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return relative

    async def fetch(self, client: httpx.AsyncClient, key: str, urls: list[str]) -> str | None:
        relative = self.relative_for(key)
        target = self.root / relative
        if target.is_file() and target.stat().st_size > 0:
            return relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".part")
        for url in urls:
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200 or not response.headers.get(
                        "content-type", ""
                    ).startswith("image/"):
                        continue
                    written = 0
                    with temporary.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            written += len(chunk)
                            if written > MAX_MEDIA_BYTES:
                                break
                            handle.write(chunk)
                if 0 < written <= MAX_MEDIA_BYTES:
                    temporary.replace(target)
                    return relative
            except (httpx.HTTPError, OSError) as error:
                logger.info("creator image fetch failed for %s: %s", url, error)
            finally:
                temporary.unlink(missing_ok=True)
        return None


def _larger_avatar(url: str) -> list[str]:
    # Item records carry a 100px thumbnail; the same object is served larger.
    larger = re.sub(r"/aweme/\d+x\d+/", "/aweme/720x720/", url, count=1)
    return [larger, url] if larger != url else [url]


class CreatorMediaPreserver:
    """Download every chosen avatar and banner while Douyin still serves them."""

    def __init__(self, database: Database, archive_root: Path, client: httpx.AsyncClient | None = None) -> None:
        self.database = database
        self.store = CreatorMediaStore(archive_root)
        self._client = client

    async def run_batch(self) -> int:
        now = int(time.time())
        rows = await self.database.fetchall(
            "SELECT s.* FROM creator_snapshots s JOIN creators c ON c.remote_id=s.creator_id "
            "WHERE s.degraded=0 AND s.media_attempts<? "
            "AND ((s.avatar_url IS NOT NULL AND s.avatar_path IS NULL) "
            "OR (s.cover_url IS NOT NULL AND s.cover_path IS NULL)) "
            "AND (s.media_attempted_at IS NULL OR s.media_attempted_at <= ? - (3600 << s.media_attempts)) "
            "AND (c.archive_status<>'active' OR EXISTS (SELECT 1 FROM items i JOIN media_files mf "
            "ON mf.item_id=i.remote_id AND mf.status='ready' WHERE i.creator_id=c.remote_id)) "
            "ORDER BY (c.archive_status<>'active') DESC, s.last_seen_at DESC LIMIT ?",
            (MAX_MEDIA_ATTEMPTS, now, MEDIA_BATCH_SIZE),
        )
        if not rows:
            return 0
        client = self._client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(20, connect=10),
            headers={"Referer": "https://www.douyin.com/", "User-Agent": "Mozilla/5.0"},
        )
        saved = 0
        try:
            for row in rows:
                avatar_path = row["avatar_path"]
                if avatar_path is None and row["avatar_url"] and not is_default_avatar(row["avatar_url"]):
                    avatar_path = await self.store.fetch(
                        client, row["avatar_key"] or row["avatar_url"], _larger_avatar(str(row["avatar_url"]))
                    )
                cover_path = row["cover_path"]
                if cover_path is None and row["cover_url"]:
                    cover_path = await self.store.fetch(
                        client, "cover:" + (avatar_key(row["cover_url"]) or row["cover_url"]), [row["cover_url"]]
                    )
                saved += int(avatar_path != row["avatar_path"]) + int(cover_path != row["cover_path"])
                await self.database.execute(
                    "UPDATE creator_snapshots SET avatar_path=?, cover_path=?, "
                    "media_attempts=media_attempts+1, media_attempted_at=? WHERE id=?",
                    (avatar_path, cover_path, now, row["id"]),
                )
        finally:
            if self._client is None:
                await client.aclose()
        return saved


@dataclass(frozen=True, slots=True)
class ProfileProbe:
    status_code: int | None
    status_message: str | None
    user: dict[str, Any] | None


def _first_url(value: object) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        urls = value.get("url_list")
        if isinstance(urls, list) and urls:
            return str(urls[0])
    return None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def creator_from_profile(creator_id: str, user: dict[str, Any]) -> CreatorRecord | None:
    nickname = str(user.get("nickname") or "").strip()
    if not nickname:
        return None
    unique_id = str(user.get("unique_id") or "").strip() or str(user.get("short_id") or "").strip()
    location = str(user.get("ip_location") or "").strip().removeprefix("IP属地：") or None
    return CreatorRecord(
        remote_id=creator_id,
        nickname=nickname,
        unique_id=unique_id if unique_id and unique_id != "0" else None,
        avatar_url=_first_url(user.get("avatar_larger")) or _first_url(user.get("avatar_thumb")),
        follower_count=_optional_int(user.get("follower_count")),
        post_count=_optional_int(user.get("aweme_count")),
        signature=str(user.get("signature") or "").strip() or None,
        following_count=_optional_int(user.get("following_count")),
        total_favorited=_optional_int(user.get("total_favorited")),
        ip_location=location,
        cover_url=_first_url(user.get("cover_url")),
    )


# A verdict is hard when Douyin states it outright, soft when it is inferred.
HARD, SOFT = "hard", "soft"


def classify_profile(probe: ProfileProbe, *, deleted_items: int) -> tuple[str, str, str] | None:
    """Map one profile response to (status, strength, evidence); None means no verdict."""
    user = probe.user or {}
    if probe.status_code not in (0, None) or not user:
        message = (probe.status_message or "").strip()
        # Douyin answers an id it no longer recognises with status 2; anything
        # else (throttling, login) says nothing about the creator.
        if probe.status_code == 2 or any(word in message for word in ("不存在", "封禁", "不合法")):
            return BANNED, SOFT, f"status:{probe.status_code}:{message}"[:200]
        return None
    if user.get("is_ban") is True:
        return BANNED, HARD, "is_ban"
    nickname = str(user.get("nickname") or "")
    avatar = _first_url(user.get("avatar_thumb")) or _first_url(user.get("avatar_larger"))
    kind = degraded_kind(nickname, str(user.get("unique_id") or ""), avatar)
    if kind == DEACTIVATED:
        return DEACTIVATED, HARD, "nickname"
    if kind == RESET:
        return RESET, SOFT, "nickname_and_avatar_reset"
    if _optional_int(user.get("aweme_count")) == 0 and deleted_items > 0:
        return VANISHED, SOFT, f"no_posts_and_{deleted_items}_deleted"
    return ACTIVE, SOFT, "profile_ok"


class CreatorStatusChecker:
    """Look at one library creator's profile per tick and keep its status honest."""

    def __init__(
        self,
        database: Database,
        probe: Callable[[str], Awaitable[ProfileProbe]],
        *,
        rescue: Callable[[str], Awaitable[Any]] | None = None,
    ) -> None:
        self.database = database
        self.probe = probe
        self.rescue = rescue
        self._candidates: list[str] = []
        self._candidates_at = 0

    async def _next_candidate(self) -> str | None:
        now = int(time.time())
        if not self._candidates or now - self._candidates_at > CANDIDATE_REFRESH_SECONDS:
            deactivated = ",".join(f"'{name}'" for name in sorted(DEACTIVATED_NAMES))
            rows = await self.database.fetchall(
                "SELECT c.remote_id FROM creators c "
                "WHERE (c.archive_checked_at IS NULL "
                "OR (c.archive_pending_status IS NOT NULL AND c.archive_checked_at <= ?) "
                "OR (c.archive_status<>'active' AND c.archive_checked_at <= ?) "
                "OR c.archive_checked_at <= ?) "
                "AND (c.archive_status<>'active' OR EXISTS (SELECT 1 FROM items i WHERE "
                f"i.creator_id=c.remote_id AND {library_item_sql('i')})) "
                "ORDER BY CASE WHEN c.archive_pending_status IS NOT NULL THEN 0 "
                f"WHEN c.nickname=c.unique_id OR c.nickname IN ({deactivated}) THEN 1 "
                "WHEN c.archive_checked_at IS NULL THEN 2 ELSE 3 END, "
                "COALESCE(c.archive_checked_at, 0), c.last_seen_at DESC LIMIT 200",
                (now - PENDING_RECHECK_SECONDS, now - ARCHIVED_RECHECK_SECONDS, now - ACTIVE_RECHECK_SECONDS),
            )
            self._candidates = [str(row["remote_id"]) for row in rows]
            self._candidates.reverse()
            self._candidates_at = now
        return self._candidates.pop() if self._candidates else None

    async def run_tick(self) -> str | None:
        creator_id = await self._next_candidate()
        if creator_id is None:
            return None
        try:
            return await self.check(creator_id)
        except Exception:
            logger.exception("creator status check failed for %s", creator_id)
            return None

    async def check(self, creator_id: str) -> str | None:
        now = int(time.time())
        current = await self.database.fetchone("SELECT * FROM creators WHERE remote_id=?", (creator_id,))
        if current is None:
            return None
        try:
            probe = await self.probe(creator_id)
        except ProviderError as error:
            # An unreachable Douyin is no evidence; look again in an hour.
            await self.database.execute(
                "UPDATE creators SET archive_checked_at=? WHERE remote_id=?",
                (now - _recheck_after(current) + FAILED_RECHECK_SECONDS, creator_id),
            )
            logger.info("creator status probe skipped for %s: %s", creator_id, error.code)
            return None
        if probe.user:
            record = creator_from_profile(creator_id, probe.user)
            if record is not None:
                await _store_profile(self.database, record)
        deleted = await self.database.fetchone(
            "SELECT COUNT(*) AS n FROM remote_checks rc JOIN items i ON i.remote_id=rc.item_id "
            "WHERE i.creator_id=? AND rc.status='deleted'",
            (creator_id,),
        )
        verdict = classify_profile(probe, deleted_items=int(deleted["n"]) if deleted else 0)
        if verdict is None:
            await self.database.execute(
                "UPDATE creators SET archive_checked_at=? WHERE remote_id=?",
                (now - _recheck_after(current) + FAILED_RECHECK_SECONDS, creator_id),
            )
            return None
        status, strength, evidence = verdict
        previous = str(current["archive_status"])
        first_look = current["archive_checked_at"] is None and previous == ACTIVE
        if status == previous:
            await self.database.execute(
                "UPDATE creators SET archive_checked_at=?, archive_evidence=?, "
                "archive_pending_status=NULL, archive_pending_count=0 WHERE remote_id=?",
                (now, evidence, creator_id),
            )
            return status
        pending = current["archive_pending_status"]
        count = int(current["archive_pending_count"] or 0) + 1 if pending == status else 1
        if strength == SOFT and count < 2:
            await self.database.execute(
                "UPDATE creators SET archive_checked_at=?, archive_pending_status=?, "
                "archive_pending_count=? WHERE remote_id=?",
                (now, status, count, creator_id),
            )
            return previous
        await self.database.execute(
            "UPDATE creators SET archive_status=?, archive_status_since=?, archive_evidence=?, "
            "archive_checked_at=?, archive_pending_status=NULL, archive_pending_count=0 "
            "WHERE remote_id=?",
            (status, None if status == ACTIVE else now, evidence, now, creator_id),
        )
        logger.warning("creator %s archive status %s -> %s (%s)", creator_id, previous, status, evidence)
        # A reset profile still lists its works for a while: save them all now.
        # Creators first classified on the very first look are an old backlog,
        # not a fresh emergency, so they are left to the user.
        if status == RESET and previous == ACTIVE and not first_look and self.rescue is not None:
            try:
                await self.rescue(creator_id)
            except Exception:
                logger.exception("could not queue rescue archive for %s", creator_id)
        return status


def _recheck_after(row: Any) -> int:
    if row["archive_pending_status"] is not None:
        return PENDING_RECHECK_SECONDS
    return ACTIVE_RECHECK_SECONDS if row["archive_status"] == ACTIVE else ARCHIVED_RECHECK_SECONDS


async def _store_profile(database: Database, record: CreatorRecord) -> None:
    from .library_repository import LibraryRepository

    await LibraryRepository(database).upsert_creator(record, source="profile")


def serialize_snapshot(row: Any) -> dict[str, object]:
    creator_id, snapshot_id = str(row["creator_id"]), int(row["id"])
    return {
        "id": snapshot_id,
        "nickname": row["nickname"],
        "uniqueId": row["unique_id"],
        "signature": row["signature"],
        "avatarUrl": (
            f"/api/creators/{creator_id}/snapshots/{snapshot_id}/avatar" if row["avatar_path"] else None
        ),
        "coverUrl": (
            f"/api/creators/{creator_id}/snapshots/{snapshot_id}/cover" if row["cover_path"] else None
        ),
        "followerCount": row["follower_count"],
        "followingCount": row["following_count"],
        "totalFavorited": row["total_favorited"],
        "postCount": row["post_count"],
        "ipLocation": row["ip_location"],
        "degraded": bool(row["degraded"]),
        "source": row["source"],
        "firstSeenAt": row["first_seen_at"],
        "lastSeenAt": row["last_seen_at"],
    }


def probe_from_payload(payload: object) -> ProfileProbe:
    if not isinstance(payload, dict):
        raise ProviderChanged("profile response was not an object")
    raw_status = payload.get("statusCode")
    user = payload.get("user")
    return ProfileProbe(
        status_code=_optional_int(raw_status),
        status_message=str(payload.get("statusMessage") or "") or None,
        user=user if isinstance(user, dict) and user else None,
    )


__all__ = [
    "ARCHIVE_STATUSES",
    "CreatorMediaPreserver",
    "CreatorMediaStore",
    "CreatorStatusChecker",
    "ProfileProbe",
    "avatar_key",
    "backfill_snapshots",
    "classify_profile",
    "creator_from_profile",
    "degraded_kind",
    "preserved_identity",
    "probe_from_payload",
    "record_snapshot",
    "serialize_snapshot",
]

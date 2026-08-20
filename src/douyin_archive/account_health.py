from __future__ import annotations

import time
from dataclasses import dataclass

from .db import Database


@dataclass(frozen=True, slots=True)
class DouyinAccountProfile:
    remote_id: str
    nickname: str
    unique_id: str | None = None
    avatar_url: str | None = None


class AccountHealthService:
    """Store identity and evidence from real Douyin verification attempts."""

    def __init__(self, database: Database) -> None:
        self.db = database

    async def snapshot(self) -> dict[str, object]:
        session = await self.db.fetchone(
            "SELECT status FROM auth_sessions WHERE provider='douyin'"
        )
        row = await self.db.fetchone(
            "SELECT * FROM douyin_account WHERE provider='douyin'"
        )
        if row is None:
            return {
                "sessionStored": bool(
                    session is not None and session["status"] == "authenticated"
                ),
                "status": "unknown",
                "lastVerifiedAt": None,
                "lastSyncAt": None,
                "lastFailureAt": None,
                "errorCode": None,
                "consecutiveFailures": 0,
                "account": None,
            }
        account = None
        if row["remote_id"] and row["nickname"]:
            account = {
                "id": row["remote_id"],
                "nickname": row["nickname"],
                "uniqueId": row["unique_id"],
                "avatarUrl": row["avatar_url"],
            }
        return {
            "sessionStored": bool(
                session is not None and session["status"] == "authenticated"
            ),
            "status": row["health_status"],
            "lastVerifiedAt": row["last_verified_at"],
            "lastSyncAt": row["last_sync_at"],
            "lastFailureAt": row["last_failure_at"],
            "errorCode": row["last_error_code"],
            "consecutiveFailures": row["consecutive_failures"],
            "account": account,
        }

    async def record_checking(self, *, checked_at: int | None = None) -> None:
        now = checked_at or int(time.time())
        await self.db.execute(
            "INSERT INTO douyin_account (provider, health_status, updated_at) "
            "VALUES ('douyin', 'checking', ?) "
            "ON CONFLICT(provider) DO UPDATE SET "
            "health_status='checking', updated_at=excluded.updated_at",
            (now,),
        )

    async def record_success(
        self,
        profile: DouyinAccountProfile | None,
        *,
        verified_at: int,
        sync_completed_at: int | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO douyin_account "
            "(provider, remote_id, nickname, unique_id, avatar_url, health_status, "
            "last_verified_at, last_sync_at, consecutive_failures, profile_updated_at, "
            "updated_at) VALUES ('douyin', ?, ?, ?, ?, 'healthy', ?, ?, 0, ?, ?) "
            "ON CONFLICT(provider) DO UPDATE SET "
            "remote_id=COALESCE(excluded.remote_id, douyin_account.remote_id), "
            "nickname=COALESCE(excluded.nickname, douyin_account.nickname), "
            "unique_id=COALESCE(excluded.unique_id, douyin_account.unique_id), "
            "avatar_url=COALESCE(excluded.avatar_url, douyin_account.avatar_url), "
            "health_status='healthy', last_verified_at=excluded.last_verified_at, "
            "last_sync_at=COALESCE(excluded.last_sync_at, douyin_account.last_sync_at), "
            "last_failure_at=NULL, last_error_code=NULL, consecutive_failures=0, "
            "profile_updated_at=CASE WHEN excluded.remote_id IS NOT NULL "
            "THEN excluded.profile_updated_at ELSE douyin_account.profile_updated_at END, "
            "updated_at=excluded.updated_at",
            (
                profile.remote_id if profile else None,
                profile.nickname if profile else None,
                profile.unique_id if profile else None,
                profile.avatar_url if profile else None,
                verified_at,
                sync_completed_at,
                verified_at if profile else None,
                verified_at,
            ),
        )

    async def record_failure(self, error_code: str, *, checked_at: int) -> None:
        status = "expired" if error_code == "DOUYIN_SESSION_EXPIRED" else "degraded"
        await self.db.execute(
            "INSERT INTO douyin_account "
            "(provider, health_status, last_failure_at, last_error_code, "
            "consecutive_failures, updated_at) "
            "VALUES ('douyin', ?, ?, ?, 1, ?) "
            "ON CONFLICT(provider) DO UPDATE SET health_status=excluded.health_status, "
            "last_failure_at=excluded.last_failure_at, "
            "last_error_code=excluded.last_error_code, "
            "consecutive_failures=douyin_account.consecutive_failures+1, "
            "updated_at=excluded.updated_at",
            (status, checked_at, error_code, checked_at),
        )

    async def infer_self_profile(self) -> DouyinAccountProfile | None:
        row = await self.db.fetchone(
            "SELECT c.remote_id, c.nickname, c.unique_id, c.avatar_url "
            "FROM source_items si "
            "JOIN items i ON i.remote_id=si.item_id "
            "JOIN creators c ON c.remote_id=i.creator_id "
            "WHERE si.source_id='account:posts' "
            "ORDER BY si.remote_order DESC, si.item_id DESC LIMIT 1"
        )
        if row is None:
            return None
        return DouyinAccountProfile(
            remote_id=str(row["remote_id"]),
            nickname=str(row["nickname"]),
            unique_id=(str(row["unique_id"]) if row["unique_id"] else None),
            avatar_url=(str(row["avatar_url"]) if row["avatar_url"] else None),
        )

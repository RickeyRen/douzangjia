from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.creator_archive import (
    BANNED,
    DEACTIVATED,
    RESET,
    VANISHED,
    CreatorStatusChecker,
    ProfileProbe,
    avatar_key,
    backfill_snapshots,
    classify_profile,
    creator_from_profile,
    degraded_kind,
    preserved_identity,
)
from douyin_archive.db import Database
from douyin_archive.library_models import CreatorRecord
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.provider.base import ProviderUnavailable

AVATAR = "https://p3-pc.douyinpic.com/aweme/100x100/aweme-avatar/tos-cn-avt-0015_abc.jpeg?from=327834062"
DEFAULT = "https://p3-pc.douyinpic.com/aweme/100x100/aweme-avatar/aweme_default_avatar.png.jpeg?from=1"


def run(coroutine):
    return asyncio.run(coroutine)


async def open_db(root: Path) -> Database:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    return database


def test_avatar_key_ignores_size_and_signature() -> None:
    small = AVATAR
    large = "https://p26-pc.douyinpic.com/aweme/720x720/aweme-avatar/tos-cn-avt-0015_abc.jpeg?from=9&x=1"
    assert avatar_key(small) == avatar_key(large) == "aweme-avatar/tos-cn-avt-0015_abc"
    assert avatar_key(None) is None


def test_only_douyin_placeholders_count_as_degraded() -> None:
    # Real people pick numeric names; only the 抖音号 with the default avatar is a reset.
    assert degraded_kind("29", "mm070701", AVATAR) is None
    assert degraded_kind("49855631198", "49855631198", AVATAR) is None
    assert degraded_kind("49855631198", "49855631198", DEFAULT) == RESET
    assert degraded_kind("该用户已注销", "10pn3Qz02Ut", AVATAR) == DEACTIVATED
    assert degraded_kind("用户9001114431803", "64729633653", DEFAULT) is None


def test_rename_keeps_the_chosen_identity_as_the_preserved_one(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        library = LibraryRepository(database)
        await library.upsert_creator(CreatorRecord("c1", "乐酷", "49855631198", AVATAR, 100, 5))
        await library.upsert_creator(CreatorRecord("c1", "乐酷", "49855631198", AVATAR, 120, 6))
        await library.upsert_creator(CreatorRecord("c1", "49855631198", "49855631198", DEFAULT, 0, 0))
        snapshots = await database.fetchall(
            "SELECT nickname, degraded, follower_count FROM creator_snapshots WHERE creator_id='c1' ORDER BY id"
        )
        kept = await preserved_identity(database, "c1")
        current = await database.fetchone("SELECT nickname, archive_checked_at FROM creators WHERE remote_id='c1'")
        await database.close()
        return snapshots, kept, current

    snapshots, kept, current = run(scenario())

    assert [(row["nickname"], row["degraded"], row["follower_count"]) for row in snapshots] == [
        ("乐酷", 0, 120),
        ("49855631198", 1, 0),
    ]
    assert kept["nickname"] == "乐酷"
    assert current["nickname"] == "49855631198"


def test_deactivated_name_marks_the_creator_at_once(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        library = LibraryRepository(database)
        await library.upsert_creator(CreatorRecord("c2", "小水", "xiaoshui", AVATAR))
        await library.upsert_creator(CreatorRecord("c2", "该用户已注销", "xiaoshui", AVATAR))
        row = await database.fetchone("SELECT archive_status FROM creators WHERE remote_id='c2'")
        await database.close()
        return row["archive_status"]

    assert run(scenario()) == DEACTIVATED


def test_migration_recovers_names_from_queued_downloads(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        await database.execute(
            "INSERT INTO creators (remote_id, nickname, unique_id, first_seen_at, last_seen_at) "
            "VALUES ('c3', '64191114109', '64191114109', 1, 1)"
        )
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at, "
            "creator_id) VALUES ('i3', '64191114109', 'd', 'video', 1, 1, 'c3')"
        )
        await database.execute(
            "INSERT INTO download_jobs (kind, remote_id, payload_json, status, next_attempt_at, created_at, updated_at) "
            "VALUES ('download', 'i3', '{\"author_name\": \"乂氼\"}', 'completed', 5, 5, 5)"
        )
        # Re-run the migration's backfill statement the way a fresh upgrade would.
        script = (Path(__file__).parents[1] / "src/douyin_archive/migrations/015_creator_archive.sql").read_text()
        await database.connection.executescript(script[script.index("INSERT OR IGNORE"):])
        await backfill_snapshots(database, tmp_path)
        rows = await database.fetchall(
            "SELECT nickname, source FROM creator_snapshots WHERE creator_id='c3' ORDER BY first_seen_at"
        )
        kept = await preserved_identity(database, "c3")
        await database.close()
        return rows, kept

    rows, kept = run(scenario())

    assert {(row["nickname"], row["source"]) for row in rows} == {("乂氼", "download_job"), ("64191114109", "current")}
    # The queued name is newer than the stale row, so it is what the archive shows.
    assert kept["nickname"] == "乂氼"


def test_backfill_adopts_an_avatar_cached_before_the_reset(tmp_path: Path) -> None:
    async def scenario():
        database = await open_db(tmp_path)
        await database.execute(
            "INSERT INTO creators (remote_id, nickname, unique_id, avatar_url, first_seen_at, last_seen_at) "
            "VALUES ('c4', '乐酷', 'leku', ?, 1, 1)",
            (AVATAR,),
        )
        legacy = tmp_path / "cache" / "avatars"
        legacy.mkdir(parents=True)
        digest = hashlib.sha256(b"c4").hexdigest()[:24]
        (legacy / f"{digest}.img").write_bytes(b"jpeg")
        (legacy / f"{digest}.url").write_text(AVATAR.replace("100x100", "168x168"))
        await backfill_snapshots(database, tmp_path)
        kept = await preserved_identity(database, "c4")
        await database.close()
        return kept

    kept = run(scenario())

    assert kept["avatar_path"].startswith("cache/creators/")
    assert (tmp_path / kept["avatar_path"]).read_bytes() == b"jpeg"


def user(**fields):
    base = {
        "nickname": "乐酷",
        "unique_id": "leku",
        "avatar_thumb": {"url_list": [AVATAR]},
        "aweme_count": 10,
        "follower_count": 17470,
        "is_ban": False,
    }
    base.update(fields)
    return base


def test_classify_profile_reads_douyin_states() -> None:
    reset = user(nickname="49855631198", unique_id="49855631198", avatar_thumb={"url_list": [DEFAULT]})
    assert classify_profile(ProfileProbe(0, None, reset), deleted_items=0)[:2] == (RESET, "soft")
    assert classify_profile(ProfileProbe(0, None, user(nickname="该用户已注销")), deleted_items=0)[:2] == (
        DEACTIVATED,
        "hard",
    )
    assert classify_profile(ProfileProbe(0, None, user(is_ban=True)), deleted_items=0)[:2] == (BANNED, "hard")
    assert classify_profile(ProfileProbe(2, "UserId不合法", None), deleted_items=0)[:2] == (BANNED, "soft")
    assert classify_profile(ProfileProbe(0, None, user(aweme_count=0)), deleted_items=3)[:2] == (VANISHED, "soft")
    assert classify_profile(ProfileProbe(8, "请登录", None), deleted_items=0) is None
    assert classify_profile(ProfileProbe(0, None, user()), deleted_items=0)[0] == "active"


def test_creator_from_profile_keeps_bio_banner_and_counts() -> None:
    record = creator_from_profile(
        "c1",
        user(
            signature="天天开心",
            following_count=30,
            total_favorited=98531,
            ip_location="IP属地：江苏",
            avatar_larger={"url_list": ["https://x/aweme/1080x1080/aweme-avatar/a.jpeg"]},
            cover_url=[{"url_list": ["https://x/obj/cover"]}],
        ),
    )
    assert record.signature == "天天开心"
    assert record.ip_location == "江苏"
    assert record.total_favorited == 98531
    assert record.cover_url == "https://x/obj/cover"
    assert record.avatar_url.endswith("a.jpeg")


def test_checker_confirms_soft_verdicts_and_rescues_new_resets(tmp_path: Path) -> None:
    reset = user(nickname="49855631198", unique_id="49855631198", avatar_thumb={"url_list": [DEFAULT]})
    answers = [ProfileProbe(0, None, user()), ProfileProbe(0, None, reset), ProfileProbe(0, None, reset)]
    rescued: list[str] = []

    async def probe(creator_id: str) -> ProfileProbe:
        return answers.pop(0)

    async def rescue(creator_id: str) -> None:
        rescued.append(creator_id)

    async def scenario():
        database = await open_db(tmp_path)
        await LibraryRepository(database).upsert_creator(CreatorRecord("c5", "乐酷", "leku", AVATAR))
        checker = CreatorStatusChecker(database, probe, rescue=rescue)
        statuses = [await checker.check("c5") for _ in range(3)]
        row = await database.fetchone("SELECT archive_status, archive_status_since FROM creators WHERE remote_id='c5'")
        kept = await preserved_identity(database, "c5")
        await database.close()
        return statuses, row, kept

    statuses, row, kept = run(scenario())

    # One odd look is not enough; the second matching one flips the status.
    assert statuses == ["active", "active", RESET]
    assert row["archive_status"] == RESET and row["archive_status_since"]
    assert rescued == ["c5"]
    assert kept["nickname"] == "乐酷"


def test_checker_leaves_creators_reset_before_the_first_look_to_the_user(tmp_path: Path) -> None:
    reset = user(nickname="49855631198", unique_id="49855631198", avatar_thumb={"url_list": [DEFAULT]})
    rescued: list[str] = []

    async def probe(creator_id: str) -> ProfileProbe:
        return ProfileProbe(0, None, reset)

    async def rescue(creator_id: str) -> None:
        rescued.append(creator_id)

    async def scenario():
        database = await open_db(tmp_path)
        await LibraryRepository(database).upsert_creator(CreatorRecord("c7", "乐酷", "leku", AVATAR))
        checker = CreatorStatusChecker(database, probe, rescue=rescue)
        statuses = [await checker.check("c7") for _ in range(3)]
        await database.close()
        return statuses

    # An old reset is archived but not mass-downloaded; that stays the user's call.
    assert run(scenario())[-1] == RESET
    assert rescued == []


def test_checker_treats_unreachable_douyin_as_no_evidence(tmp_path: Path) -> None:
    async def probe(creator_id: str) -> ProfileProbe:
        raise ProviderUnavailable("offline")

    async def scenario():
        database = await open_db(tmp_path)
        await LibraryRepository(database).upsert_creator(CreatorRecord("c6", "作者", "author", AVATAR))
        result = await CreatorStatusChecker(database, probe).check("c6")
        row = await database.fetchone("SELECT archive_status, archive_checked_at FROM creators WHERE remote_id='c6'")
        await database.close()
        return result, row

    result, row = run(scenario())

    assert result is None
    assert row["archive_status"] == "active"
    assert row["archive_checked_at"] is not None


async def seed_vanished(root: Path) -> None:
    database = await open_db(root)
    library = LibraryRepository(database)
    await library.upsert_creator(CreatorRecord("gone-1", "乐酷", "49855631198", AVATAR, 17470, 311))
    await library.upsert_creator(CreatorRecord("gone-1", "49855631198", "49855631198", DEFAULT, 0, 0))
    await database.execute(
        "UPDATE creators SET archive_status='reset', archive_status_since=100 WHERE remote_id='gone-1'"
    )
    # Neither item is downloaded or in a kept source; the archive still lists both.
    for item_id in ("g1", "g2"):
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at, "
            "creator_id) VALUES (?, '49855631198', '海边', 'video', 2, 2, 'gone-1')",
            (item_id,),
        )
    await database.close()


def test_vanished_endpoints_show_the_creator_as_they_were(tmp_path: Path, master_key: str) -> None:
    run(seed_vanished(tmp_path))
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
        listing = client.get("/api/creators/vanished").json()
        detail = client.get("/api/creators/gone-1").json()
        feed = client.get("/api/feed", params={"creatorId": "gone-1", "limit": 10}).json()
        home = client.get("/api/home").json()

    assert listing["counts"] == {"reset": 1}
    assert listing["monitor"]["consecutiveFailures"] == 0
    assert listing["monitor"]["catalogPausedUntil"] is None
    entry = listing["items"][0]
    assert entry["nickname"] == "乐酷"
    assert entry["knownItemCount"] == 2
    assert entry["archive"]["status"] == "reset"
    assert entry["archive"]["currentNickname"] == "49855631198"
    assert [snap["nickname"] for snap in detail["archive"]["history"]] == ["乐酷", "49855631198"]
    assert {item["awemeId"] for item in feed["items"]} == {"g1", "g2"}
    assert {item["author"] for item in feed["items"]} == {"乐酷"}
    assert home["stats"]["vanishedCreators"] == 1
    assert home["vanishedCreators"][0]["nickname"] == "乐酷"


def test_vanished_list_searches_former_names_and_sorts_by_saved_works(tmp_path: Path, master_key: str) -> None:
    async def seed() -> None:
        await seed_vanished(tmp_path)
        database = await open_db(tmp_path)
        # Never had a chosen name on record.
        await LibraryRepository(database).upsert_creator(CreatorRecord("gone-2", "该用户已注销", "closed"))
        await database.execute("UPDATE creators SET archive_status_since=200 WHERE remote_id='gone-2'")
        await database.execute(
            "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, status, created_at, updated_at) "
            "VALUES ('g1', 0, 'video', 'objects/g1/0.mp4', 'ready', 1, 1)"
        )
        await database.close()

    run(seed())
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
        recent = client.get("/api/creators/vanished").json()
        saved = client.get("/api/creators/vanished", params={"sort": "saved"}).json()
        found = client.get("/api/creators/vanished", params={"search": "乐酷"}).json()
        first = client.get("/api/creators/vanished", params={"sort": "saved", "limit": 1}).json()
        rest = client.get(
            "/api/creators/vanished", params={"sort": "saved", "limit": 1, "cursor": first["nextCursor"]}
        ).json()

    assert [entry["id"] for entry in recent["items"]] == ["gone-2", "gone-1"]
    assert recent["items"][0]["nickname"] == "原名未知"
    assert recent["items"][0]["archive"]["currentNickname"] == "该用户已注销"
    assert [entry["id"] for entry in saved["items"]] == ["gone-1", "gone-2"]
    assert [entry["id"] for entry in found["items"]] == ["gone-1"]
    assert [entry["id"] for entry in first["items"] + rest["items"]] == ["gone-1", "gone-2"]



def test_checker_counts_looks_that_told_it_nothing_until_one_does(tmp_path: Path) -> None:
    answers: list = [ProviderUnavailable("offline"), ProfileProbe(8, "请登录", None), ProfileProbe(0, None, user())]

    async def probe(creator_id: str) -> ProfileProbe:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def scenario():
        database = await open_db(tmp_path)
        await LibraryRepository(database).upsert_creator(CreatorRecord("c8", "作者", "author", AVATAR))
        checker = CreatorStatusChecker(database, probe)
        counts = []
        for _ in range(3):
            await checker.check("c8")
            counts.append(checker.consecutive_failures)
        await database.close()
        return counts

    assert run(scenario()) == [1, 2, 0]


def test_creator_search_finds_a_creator_by_a_former_name(tmp_path: Path, master_key: str) -> None:
    run(seed_vanished(tmp_path))
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "test-admin", "password": "a secure local passphrase"})
        by_former = client.get("/api/creators", params={"search": "乐酷"}).json()
        by_current = client.get("/api/creators", params={"search": "49855631198"}).json()
        miss = client.get("/api/creators", params={"search": "不存在的人"}).json()

    assert [entry["id"] for entry in by_former["items"]] == ["gone-1"]
    assert [entry["id"] for entry in by_current["items"]] == ["gone-1"]
    assert miss["items"] == []

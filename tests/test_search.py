import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.search import fts_query


async def seed(root: Path) -> None:
    database = await Database(root / "data" / "archive.sqlite3").open()
    await database.execute(
        "INSERT INTO creators (remote_id, nickname, unique_id, first_seen_at, last_seen_at) VALUES ('c1', '旅行家小鹿', 'deer2026', 1, 1)"
    )
    rows = [
        ("801", "杭州西湖边的咖啡馆，秋天真好看", "作者甲", None, 10, '{"hashtags": ["杭州", "咖啡"]}', 45_000),
        ("802", "一个女生的房车旅行记录", "作者乙", "c1", 20, '{"hashtags": ["旅行", "vlog"]}', 600_000),
        ("803", "番茄炒蛋的正确做法", "作者丙", None, 30, "{}", 90_000),
        ("804", "ab", "作者丁", None, 40, "{}", None),
    ]
    for remote_id, description, author, creator, seen, metadata, duration in rows:
        await database.execute(
            "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at, "
            "creator_id, metadata_json, duration_ms) VALUES (?, ?, ?, 'video', ?, ?, ?, ?, ?)",
            (remote_id, author, description, seen, seen, creator, metadata, duration),
        )
    await database.close()


def client_for(root: Path, master_key: str) -> TestClient:
    asyncio.run(seed(root))
    client = TestClient(create_app(Settings(archive_root=root, master_key=master_key)))
    client.__enter__()
    client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
    client.headers["X-CSRF-Token"] = client.cookies["archive_csrf"]
    return client


def ids(response) -> list[str]:
    return [item["awemeId"] for item in response.json()["items"]]


def test_fts_query_builder() -> None:
    assert fts_query("西湖边 咖啡馆") == '"西湖边" AND "咖啡馆"'
    assert fts_query('say "hi" there') == '"say" AND """hi""" AND "there"'
    assert fts_query("ab cde") is None  # a 2-char token cannot use trigrams
    assert fts_query("   ") is None


def test_search_matches_chinese_substrings_across_fields(tmp_path: Path, master_key: str) -> None:
    """Catches search needing exact words: trigram FTS finds 西湖边 inside the sentence."""
    client = client_for(tmp_path, master_key)
    try:
        by_description = client.get("/api/feed?search=西湖边")
        two_terms = client.get("/api/feed?search=杭州 咖啡馆")
        two_terms_miss = client.get("/api/feed?search=杭州 房车")
        by_hashtag = client.get("/api/feed?search=vlog")
        by_creator = client.get("/api/feed?search=deer2026")
        client.put("/api/items/803/tags", json={"tags": ["晚饭灵感"]})
        client.put("/api/items/803/note", json={"note": "周三试试看"})
        by_tag = client.get("/api/feed?search=晚饭灵感")
        by_note = client.get("/api/feed?search=周三试试")
        short_term = client.get("/api/feed?search=ab")
        client.put("/api/items/803/tags", json={"tags": []})
        tag_removed = client.get("/api/feed?search=晚饭灵感")
    finally:
        client.__exit__(None, None, None)

    assert ids(by_description) == ["801"]
    assert ids(two_terms) == ["801"] and ids(two_terms_miss) == []
    assert ids(by_hashtag) == ["802"]
    assert ids(by_creator) == ["802"]
    assert ids(by_tag) == ["803"] and ids(by_note) == ["803"]
    assert ids(short_term) == ["804"]  # LIKE fallback for < 3 characters
    assert ids(tag_removed) == []


def test_relevance_sort_pages_without_duplicates(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        client.put("/api/items/804/note", json={"note": "旅行 旅行 旅行"})
        first = client.get("/api/feed?search=旅行&limit=1")
        second = client.get(f"/api/feed?search=旅行&limit=1&cursor={first.json()['nextCursor']}")
        explicit = client.get("/api/feed?search=旅行&sort=archived")
        relevance_without_fts = client.get("/api/feed?search=ab&sort=relevance")
    finally:
        client.__exit__(None, None, None)

    assert first.status_code == 200 and second.status_code == 200
    assert set(ids(first) + ids(second)) == {"802", "804"}
    assert ids(first) != ids(second)
    assert ids(explicit) == ["804", "802"]
    assert relevance_without_fts.status_code == 200


def test_duration_and_date_filters(tmp_path: Path, master_key: str) -> None:
    client = client_for(tmp_path, master_key)
    try:
        short = client.get("/api/feed?maxDuration=60")
        long = client.get("/api/feed?minDuration=300")
        window = client.get("/api/feed?since=20&until=40")
    finally:
        client.__exit__(None, None, None)

    assert ids(short) == ["801"]
    assert ids(long) == ["802"]
    assert ids(window) == ["803", "802"]

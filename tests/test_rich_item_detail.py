from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database
from douyin_archive.provider.normalizers import normalize_page


def test_normalizer_preserves_available_douyin_metadata() -> None:
    """Catches rich Douyin fields being discarded during discovery."""
    page = normalize_page(
        {
            "status_code": 0,
            "aweme_list": [
                {
                    "aweme_id": "734",
                    "desc": "海边日落 #旅行",
                    "create_time": 100,
                    "author": {
                        "sec_uid": "creator-1",
                        "nickname": "旅行作者",
                        "unique_id": "travel-user",
                    },
                    "video": {
                        "duration": 15_200,
                        "width": 1080,
                        "height": 1920,
                        "play_addr": {
                            "url_list": ["https://media.test/734.mp4"],
                            "data_size": 1234,
                        },
                        "cover": {"url_list": ["https://media.test/cover.jpg"]},
                    },
                    "statistics": {
                        "play_count": 1000,
                        "digg_count": 50,
                        "comment_count": 4,
                        "collect_count": 8,
                        "share_count": 2,
                    },
                    "text_extra": [{"hashtag_name": "旅行"}],
                    "music": {"mid": "music-1", "title": "海风", "author": "音乐人"},
                }
            ],
        }
    )

    item = page.items[0]
    assert item.cover_url == "https://media.test/cover.jpg"
    assert item.duration_ms == 15_200
    assert item.width == 1080
    assert item.height == 1920
    assert item.statistics == {
        "playCount": 1000,
        "diggCount": 50,
        "commentCount": 4,
        "collectCount": 8,
        "shareCount": 2,
    }
    assert item.hashtags == ("旅行",)
    assert item.music == {"id": "music-1", "title": "海风", "author": "音乐人"}
    assert item.source_url == "https://www.douyin.com/video/734"


async def _seed_rich_item(root: Path) -> None:
    database = await Database(root / "data" / "archive.sqlite3").open()
    await database.execute(
        "INSERT INTO creators "
        "(remote_id, nickname, unique_id, avatar_url, first_seen_at, last_seen_at) "
        "VALUES ('creator-1', '旅行作者', 'travel-user', "
        "'https://media.test/avatar.jpg', 1, 1)"
    )
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, published_at, first_seen_at, "
        "last_seen_at, creator_id, cover_url, duration_ms, statistics_json, source_url, "
        "metadata_json) VALUES "
        "('734', '旅行作者', '海边日落', 'video', 100, 1, 1, 'creator-1', "
        "'https://media.test/cover.jpg', 15200, ?, "
        "'https://www.douyin.com/video/734', ?)",
        (
            json.dumps({"playCount": 1000, "diggCount": 50}),
            json.dumps({"hashtags": ["旅行"], "music": {"title": "海风"}}),
        ),
    )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, relative_path, byte_size, checksum_sha256, "
        "mime_type, status, created_at, updated_at, downloaded_bytes, total_bytes, "
        "width, height, codec, fps, bit_rate, duration_ms, probe_status, probed_at, "
        "completed_at) VALUES "
        "('734', 0, 'video', 'objects/734/000-video.mp4', 1234, 'abc123', "
        "'video/mp4', 'ready', 1, 1, 1234, 1234, 1080, 1920, 'h264', 30, "
        "4500000, 15200, 'ready', 2, 2)"
    )
    await database.execute(
        "INSERT INTO remote_checks "
        "(item_id, status, checked_at, evidence_code, consecutive_matches, "
        "last_available_at, updated_at) VALUES "
        "('734', 'available', 200, 'OK', 1, 200, 200)"
    )
    await database.close()


def test_item_detail_exposes_douyin_creator_file_and_remote_information(
    tmp_path: Path, master_key: str
) -> None:
    """Catches the details UI receiving only a title and generic local badge."""
    asyncio.run(_seed_rich_item(tmp_path))
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        response = client.get("/api/items/734")

    assert response.status_code == 200
    payload = response.json()
    assert payload["creator"] == {
        "id": "creator-1",
        "nickname": "旅行作者",
        "uniqueId": "travel-user",
        "avatarUrl": "https://media.test/avatar.jpg",
    }
    assert payload["douyin"]["statistics"]["playCount"] == 1000
    assert payload["douyin"]["durationMs"] == 15_200
    assert payload["douyin"]["hashtags"] == ["旅行"]
    assert payload["media"][0]["byteSize"] == 1234
    assert payload["media"][0]["checksumSha256"] == "abc123"
    assert payload["media"][0]["technical"] == {
        "width": 1080,
        "height": 1920,
        "codec": "h264",
        "fps": 30.0,
        "bitRate": 4500000,
        "durationMs": 15200,
        "probeStatus": "ready",
        "probedAt": 2,
    }
    assert payload["remoteAvailability"] == {
        "status": "available",
        "checkedAt": 200,
        "evidenceCode": "OK",
        "lastAvailableAt": 200,
    }
    assert "media.test/734.mp4" not in response.text


def test_remote_check_endpoint_persists_runtime_evidence(tmp_path: Path, master_key: str) -> None:
    asyncio.run(_seed_rich_item(tmp_path))

    class Runtime:
        async def check_item_availability(self, remote_id: str) -> str:
            assert remote_id == "734"
            return "ITEM_NOT_FOUND"

    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.app.state.runtime = Runtime()
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        response = client.post(
            "/api/items/734/remote-check",
            headers={"X-CSRF-Token": client.cookies.get("archive_csrf") or ""},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert response.json()["evidenceCode"] == "ITEM_NOT_FOUND"

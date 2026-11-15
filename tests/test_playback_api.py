import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def test_long_videos_resume_and_finished_or_short_ones_start_over(tmp_path: Path, master_key: str) -> None:
    """Catches a long video restarting from zero on the next device."""
    with TestClient(create_app(Settings(archive_root=tmp_path, master_key=master_key))) as client:
        client.post("/api/setup", json={"username": "owner", "password": "a secure local passphrase"})
        client.headers["X-CSRF-Token"] = client.cookies["archive_csrf"]
        with sqlite3.connect(tmp_path / "data" / "archive.sqlite3") as database:
            database.execute(
                "INSERT INTO items (remote_id, item_type, author_name, description, first_seen_at, last_seen_at) "
                "VALUES ('401', 'video', 'a', 'd', 1, 1)"
            )
        url = "/api/items/401/playback"
        assert client.get(url).json() == {"positionMs": None}

        assert client.put(url, json={"positionMs": 95_000, "durationMs": 600_000}).json() == {"positionMs": 95_000}
        saved = client.get(url).json()
        assert saved["positionMs"] == 95_000 and saved["durationMs"] == 600_000

        # Near the end counts as finished; the next open starts over.
        assert client.put(url, json={"positionMs": 590_000, "durationMs": 600_000}).json() == {"positionMs": None}
        assert client.get(url).json() == {"positionMs": None}
        # Short clips and the first seconds are never remembered.
        assert client.put(url, json={"positionMs": 50_000, "durationMs": 90_000}).json() == {"positionMs": None}
        assert client.put(url, json={"positionMs": 4_000, "durationMs": 600_000}).json() == {"positionMs": None}

        assert client.put("/api/items/missing/playback", json={"positionMs": 95_000, "durationMs": 600_000}).status_code == 404
        assert client.put(url, json={"positionMs": -1, "durationMs": 600_000}).status_code == 422
        client.cookies.clear()
        assert client.get(url).status_code == 401

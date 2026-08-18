import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings
from douyin_archive.db import Database


async def _seed_job(root: Path) -> None:
    database = Database(root / "data" / "archive.sqlite3")
    await database.open()
    await database.execute(
        "INSERT INTO items "
        "(remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES ('734', '旅行家', '海边日落', 'video', 1, 1)"
    )
    payload = json.dumps(
        {
            "assets": [
                {
                    "remote_id": "734",
                    "asset_index": 0,
                    "media_type": "video",
                    "url": "https://media.test/734",
                    "mime_type": "video/mp4",
                    "expected_size": 10,
                }
            ]
        }
    )
    await database.execute(
        "INSERT INTO download_jobs "
        "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "created_at, updated_at) VALUES ('download', '734', ?, 'running', 1, 0, 1, 2)",
        (payload,),
    )
    await database.close()


def test_jobs_route_returns_summary_and_asset_details(
    tmp_path: Path, master_key: str
) -> None:
    asyncio.run(_seed_job(tmp_path))
    app = create_app(Settings(archive_root=tmp_path, master_key=master_key))

    with TestClient(app) as client:
        client.post("/api/setup", json={"password": "a secure local passphrase"})
        response = client.get("/api/jobs?limit=50")

    assert response.status_code == 200
    assert response.json()["summary"]["running"] == 1
    assert response.json()["items"][0]["description"] == "海边日落"
    assert response.json()["items"][0]["assets"][0]["fileName"] == "000.mp4"

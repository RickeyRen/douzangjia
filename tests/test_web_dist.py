from pathlib import Path

from fastapi.testclient import TestClient

from douyin_archive.api import create_app
from douyin_archive.config import Settings


def build_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name":"抖藏家"}', encoding="utf-8")
    (dist / "icon-192.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return dist


def test_shell_revalidates_while_hashed_assets_and_icons_cache(tmp_path: Path, master_key: str) -> None:
    """Catches browsers keeping an old bundle after a deploy, and the PWA manifest 404ing."""
    dist = build_dist(tmp_path)
    app = create_app(Settings(archive_root=tmp_path / "archive", master_key=master_key, web_dist=dist))
    with TestClient(app) as client:
        shell = client.get("/")
        deep = client.get("/library/account%3Alikes")
        asset = client.get("/assets/index-abc123.js")
        manifest = client.get("/manifest.webmanifest")
        icon = client.get("/icon-192.png")
        escape = client.get("/..%2Fsecret")
        api_missing = client.get("/api/nope")

    assert shell.status_code == 200 and shell.headers["cache-control"] == "no-cache"
    assert deep.text == shell.text
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert manifest.status_code == 200 and manifest.headers["cache-control"] == "public, max-age=86400"
    assert manifest.json()["name"] == "抖藏家"
    assert icon.headers["content-type"] == "image/png"
    assert escape.status_code == 200 and escape.text == shell.text  # falls back to the shell, never a file outside dist
    assert api_missing.status_code == 404

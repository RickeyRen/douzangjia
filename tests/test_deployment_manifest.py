from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_compose_keeps_archive_outside_the_container_and_stays_unprivileged() -> None:
    manifest = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = manifest["services"]["archive"]

    assert service["restart"] == "unless-stopped"
    assert service["user"] == "${PUID:-1000}:${PGID:-1000}"
    assert service.get("privileged", False) is False
    assert "${ARCHIVE_PATH:-./archive-data}:/archive" in service["volumes"]
    assert service["environment"]["ARCHIVE_MASTER_KEY"] == "${ARCHIVE_MASTER_KEY:?required}"
    assert service["healthcheck"]["test"][-1].endswith("/health/ready')")


def test_docker_context_excludes_secrets_and_local_archives() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored
    assert "archive-data" in ignored
    assert ".git" in ignored


def test_docker_image_exposes_the_installed_full_chromium() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/local/bin/douyin-chromium" in dockerfile
    assert "chrome-linux*/chrome" in dockerfile


def test_docker_image_bypasses_the_broken_nas_hub_mirror() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM docker.m.daocloud.io/library/node:22-bookworm-slim" in dockerfile
    assert "FROM docker.m.daocloud.io/library/python:3.13-slim-bookworm" in dockerfile

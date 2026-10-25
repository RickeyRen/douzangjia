from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_compose_keeps_archive_outside_the_container_and_stays_unprivileged() -> None:
    manifest = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = manifest["services"]["archive"]

    assert service["restart"] == "unless-stopped"
    assert service["user"] == "${PUID:-1000}:${PGID:-1000}"
    assert service.get("privileged", False) is False
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["volumes"] == ["${ARCHIVE_PATH:-./archive-data}:/archive"]
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


def test_docker_image_defaults_to_official_registries_with_mirror_overrides() -> None:
    """Catches hard-coded China mirrors breaking builds for everyone else."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    manifest = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    build_args = manifest["services"]["archive"]["build"]["args"]

    assert "daocloud" not in dockerfile and "aliyun" not in dockerfile and "npmmirror" not in dockerfile
    assert "ARG NODE_IMAGE=node:22-bookworm-slim" in dockerfile
    assert "ARG PYTHON_IMAGE=python:3.13-slim-bookworm" in dockerfile
    for name in ("NODE_IMAGE", "PYTHON_IMAGE", "NPM_REGISTRY", "PIP_INDEX_URL", "DEBIAN_MIRROR", "PLAYWRIGHT_DOWNLOAD_HOST", "APP_COMMIT"):
        assert name in build_args, name
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "# NPM_REGISTRY=https://registry.npmmirror.com/" in example


def test_release_metadata_is_in_place() -> None:
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    assert (ROOT / ".github" / "workflows" / "ci.yml").is_file()
    package = (ROOT / "web" / "package.json").read_text(encoding="utf-8")
    assert '"latest"' not in package


def test_chromium_shared_memory_and_sqlite_temp_files_do_not_compete() -> None:
    """Catches the 1g /tmp filling with Chromium shm, crashing pages and SQLite writes."""
    manifest = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    tmpfs = manifest["services"]["archive"]["tmpfs"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert any(entry.startswith("/tmp:") and "size=4g" in entry for entry in tmpfs)
    assert "SQLITE_TMPDIR=/archive/tmp" in dockerfile

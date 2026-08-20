from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from douyin_archive.db import Database
from douyin_archive.library_models import LibrarySource, LibrarySourceKind
from douyin_archive.library_repository import LibraryRepository
from douyin_archive.repositories import ArchiveRepository


@pytest.fixture
async def dashboard_components(tmp_path: Path):
    database = await Database(tmp_path / "archive.sqlite3").open()
    dashboard_module = importlib.import_module("douyin_archive.dashboard_service")
    telemetry_module = importlib.import_module("douyin_archive.telemetry")
    service = dashboard_module.DashboardService(database, tmp_path, clock=lambda: 10_000)
    telemetry = telemetry_module.TelemetrySampler(
        database, tmp_path, clock=lambda: 10_000
    )
    yield database, dashboard_module, telemetry_module, service, telemetry
    await database.close()


async def _seed_ready_media(
    database: Database, archive: ArchiveRepository, item_id: str, byte_size: int
) -> None:
    await archive.upsert_item(
        remote_id=item_id,
        author_name="作者",
        description=item_id,
        item_type="video",
    )
    await database.execute(
        "INSERT INTO media_files "
        "(item_id, asset_index, media_type, byte_size, status, downloaded_bytes, "
        "total_bytes, speed_bps, created_at, updated_at, completed_at) "
        "VALUES (?, 0, 'video', ?, 'ready', ?, ?, 0, 1, 1, 1)",
        (item_id, byte_size, byte_size, byte_size),
    )


async def test_source_progress_is_logical_while_global_storage_is_deduplicated(
    dashboard_components,
) -> None:
    """Catches shared media being double-counted as physical NAS usage."""
    database, _dashboard_module, _telemetry_module, service, _telemetry = (
        dashboard_components
    )
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    for source_id in ("favorite_collection:one", "favorite_collection:two"):
        await library.upsert_source(
            LibrarySource(
                id=source_id,
                kind=LibrarySourceKind.FAVORITE_COLLECTION,
                remote_id=source_id.rsplit(":", 1)[-1],
                name=source_id,
            )
        )
    await _seed_ready_media(database, archive, "shared", 100)
    await _seed_ready_media(database, archive, "only-one", 50)
    await library.link_source_item("favorite_collection:one", "shared", "2")
    await library.link_source_item("favorite_collection:one", "only-one", "1")
    await library.link_source_item("favorite_collection:two", "shared", "1")

    snapshot = await service.snapshot()
    sources = {entry["id"]: entry for entry in snapshot["sources"]}

    assert snapshot["storage"]["archiveBytes"] == 150
    assert sources["favorite_collection:one"]["archivedBytes"] == 150
    assert sources["favorite_collection:two"]["archivedBytes"] == 100
    assert sources["favorite_collection:one"]["discovered"] == 2
    assert sources["favorite_collection:one"]["archived"] == 2
    assert sources["favorite_collection:one"]["coveragePercent"] == 100.0


async def test_source_progress_reports_queue_states_and_unknown_totals(
    dashboard_components,
) -> None:
    """Catches an unknown remote total being presented as a completed full archive."""
    database, _dashboard_module, _telemetry_module, service, _telemetry = (
        dashboard_components
    )
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="account:likes",
            kind=LibrarySourceKind.LIKE,
            remote_id="self",
            name="喜欢",
            declared_count=None,
        )
    )
    await archive.upsert_item(
        remote_id="waiting",
        author_name="作者",
        description="等待",
        item_type="video",
    )
    await library.link_source_item("account:likes", "waiting", "1")
    await database.execute(
        "INSERT INTO download_jobs "
        "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "created_at, updated_at) VALUES "
        "('download', 'waiting', '{}', 'pending', 0, 1, 1, 1)"
    )

    source = (await service.source_progress())[0]

    assert source["pending"] == 1
    assert source["archived"] == 0
    assert source["remoteTotal"] is None
    assert source["remoteComplete"] is False
    assert source["coveragePercent"] == 0.0


async def test_metric_series_filters_windows_and_keeps_real_values(
    dashboard_components,
) -> None:
    """Catches charts inventing points outside the selected time window."""
    _database, _dashboard_module, telemetry_module, service, telemetry = (
        dashboard_components
    )
    sample_type = telemetry_module.MetricSample
    await telemetry.record(sample_type(sampled_at=8_000, download_speed_bps=10))
    await telemetry.record(sample_type(sampled_at=9_500, download_speed_bps=25))

    short = await service.series("15m")
    day = await service.series("24h")

    assert [(point["sampledAt"], point["downloadSpeedBps"]) for point in short] == [
        (9_500, 25.0)
    ]
    assert [(point["sampledAt"], point["downloadSpeedBps"]) for point in day] == [
        (8_000, 10.0),
        (9_500, 25.0),
    ]


async def test_empty_metric_history_returns_an_empty_series(
    dashboard_components,
) -> None:
    """Catches a dashboard drawing fabricated baseline history."""
    _database, _dashboard_module, _telemetry_module, service, _telemetry = (
        dashboard_components
    )

    assert await service.series("24h") == []


async def test_live_snapshot_matches_full_home_contract(dashboard_components) -> None:
    """Catches SSE replacing the REST snapshot with a reduced data shape."""
    _database, _dashboard_module, _telemetry_module, service, _telemetry = (
        dashboard_components
    )

    snapshot = await service.snapshot()

    assert set(snapshot["library"]) == {
        "items",
        "archivedItems",
        "mediaFiles",
        "creators",
        "sources",
        "completeSources",
        "incompleteSources",
        "neverSyncedSources",
        "discoveredLinks",
        "archivedBytes",
    }
    assert set(snapshot["health"]) == {
        "recentErrors",
        "uptimeSeconds",
        "latestSync",
    }
    assert "account" in snapshot
    assert "sources" in snapshot


async def test_prune_compacts_old_raw_samples_before_deleting_them(
    dashboard_components,
) -> None:
    """Catches the 7-day chart losing all history after the raw retention window."""
    database, _dashboard_module, telemetry_module, service, telemetry = (
        dashboard_components
    )
    old_time = 10_000 - 25 * 60 * 60
    await telemetry.record(
        telemetry_module.MetricSample(
            sampled_at=old_time,
            download_speed_bps=50,
            archive_bytes=1_000,
        )
    )

    await telemetry.prune()

    raw = await database.fetchone(
        "SELECT 1 FROM metric_samples WHERE resolution='raw' AND sampled_at=?",
        (old_time,),
    )
    compacted = await database.fetchone(
        "SELECT resolution, download_speed_bps, archive_bytes FROM metric_samples "
        "WHERE resolution='minute'"
    )
    week = await service.series("7d")
    assert raw is None
    assert compacted is not None
    assert compacted["download_speed_bps"] == 50
    assert compacted["archive_bytes"] == 1_000
    assert week[-1]["archiveBytes"] == 1_000

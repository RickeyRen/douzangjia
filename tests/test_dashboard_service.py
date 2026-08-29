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
    database: Database,
    archive: ArchiveRepository,
    item_id: str,
    byte_size: int,
    *,
    completed_at: int = 1,
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
        "VALUES (?, 0, 'video', ?, 'ready', ?, ?, 0, 1, 1, ?)",
        (item_id, byte_size, byte_size, byte_size, completed_at),
    )


async def test_throughput_uses_completed_media_and_only_compares_full_history(
    tmp_path: Path,
) -> None:
    """Catches the dashboard inventing time-window traffic or comparisons."""
    database = await Database(tmp_path / "throughput.sqlite3").open()
    try:
        archive = ArchiveRepository(database)
        service = importlib.import_module("douyin_archive.dashboard_service").DashboardService(
            database,
            tmp_path,
            clock=lambda: 964_800,
        )
        await _seed_ready_media(
            database, archive, "historical", 50, completed_at=1
        )
        await _seed_ready_media(
            database, archive, "yesterday", 100, completed_at=840_000
        )
        await _seed_ready_media(
            database, archive, "today", 300, completed_at=922_000
        )

        throughput = (await service.snapshot())["throughput"]

        assert throughput["today"] == {
            "bytes": 300,
            "previousBytes": 100,
            "deltaBytes": 200,
            "comparisonAvailable": True,
        }
        assert throughput["lifetime"] == {"bytes": 450}
        assert throughput["historyStartedAt"] == 1
    finally:
        await database.close()


async def test_throughput_marks_comparison_unavailable_without_prior_coverage(
    tmp_path: Path,
) -> None:
    """Catches a partial telemetry history being labeled as a real comparison."""
    database = await Database(tmp_path / "partial-throughput.sqlite3").open()
    try:
        archive = ArchiveRepository(database)
        service = importlib.import_module("douyin_archive.dashboard_service").DashboardService(
            database,
            tmp_path,
            clock=lambda: 964_800,
        )
        await _seed_ready_media(
            database, archive, "today-only", 300, completed_at=922_000
        )

        today = (await service.snapshot())["throughput"]["today"]

        assert today["bytes"] == 300
        assert today["previousBytes"] == 0
        assert today["comparisonAvailable"] is False
    finally:
        await database.close()


def test_process_tree_snapshot_counts_only_real_chromium_descendants(
    tmp_path: Path,
) -> None:
    """Catches unrelated child RSS being presented as browser memory."""
    proc_root = tmp_path / "proc"
    for pid, children, command, rss_kib in (
        (100, "101 102", "python api", 100),
        (101, "103", "chromium --type=browser", 10),
        (102, "", "ffmpeg probe", 5),
        (103, "", "chrome --type=renderer", 20),
    ):
        task = proc_root / str(pid) / "task" / str(pid)
        task.mkdir(parents=True)
        (task / "children").write_text(children, encoding="utf-8")
        (proc_root / str(pid) / "cmdline").write_bytes(command.replace(" ", "\0").encode())
        (proc_root / str(pid) / "status").write_text(
            f"Name:\tprocess\nVmRSS:\t{rss_kib} kB\n",
            encoding="utf-8",
        )

    snapshot = importlib.import_module("douyin_archive.telemetry").process_tree_snapshot(
        root_pid=100,
        proc_root=proc_root,
    )

    assert snapshot == {
        "browserProcessCount": 2,
        "browserMemoryBytes": 30 * 1024,
    }


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


async def test_source_progress_uses_declared_remote_total_for_archive_coverage(
    dashboard_components,
) -> None:
    """Catches a partially discovered collection being shown as fully archived."""
    database, _dashboard_module, _telemetry_module, service, _telemetry = (
        dashboard_components
    )
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    await library.upsert_source(
        LibrarySource(
            id="favorite_collection:partial",
            kind=LibrarySourceKind.FAVORITE_COLLECTION,
            remote_id="partial",
            name="未发现完的收藏夹",
            declared_count=10,
        )
    )
    for index in range(4):
        item_id = f"partial-{index}"
        await _seed_ready_media(database, archive, item_id, 100)
        await library.link_source_item("favorite_collection:partial", item_id, str(index))

    source = (await service.source_progress())[0]

    assert source["discovered"] == 4
    assert source["archived"] == 4
    assert source["remoteTotal"] == 10
    assert source["coveragePercent"] == 40.0


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


async def test_runtime_cards_report_real_logical_service_boundaries(
    dashboard_components,
) -> None:
    """Catches async workers being mislabeled as fabricated OS processes."""
    database, _dashboard_module, _telemetry_module, service, _telemetry = (
        dashboard_components
    )
    await database.execute(
        "INSERT INTO download_jobs "
        "(kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "created_at, updated_at) VALUES "
        "('download', 'active', '{}', 'running', 0, 1, 9, 9)"
    )

    snapshot = await service.snapshot(
        runtime={
            "workerCount": 2,
            "activeWorkers": 2,
            "browser": {"started": True, "busy": True},
        }
    )

    assert snapshot["runtime"]["serviceCount"] == 3
    assert snapshot["runtime"]["application"]["memoryBytes"] >= 0
    assert snapshot["runtime"]["downloader"] == {
        "status": "running",
        "workerCount": 2,
        "activeWorkers": 2,
        "activeDownloads": 1,
        "pendingDownloads": 0,
        "speedBps": 0.0,
        "lastActivityAt": 9,
    }
    assert snapshot["runtime"]["browser"]["status"] == "busy"
    assert snapshot["runtime"]["browser"]["started"] is True
    assert snapshot["runtime"]["browser"]["busy"] is True


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

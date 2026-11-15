import asyncio
import hashlib
import json
from pathlib import Path

from douyin_archive.db import Database
from douyin_archive.integrity import RECHECK_AFTER_SECONDS, ArchiveVerifier


async def saved(database: Database, root: Path, item: str, body: bytes) -> Path:
    relative = f"objects/{item}/0.mp4"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    await database.execute(
        "INSERT INTO items (remote_id, author_name, description, item_type, first_seen_at, last_seen_at) "
        "VALUES (?, 'a', 'd', 'video', 1, 1)",
        (item,),
    )
    await database.execute(
        "INSERT INTO media_files (item_id, asset_index, media_type, relative_path, byte_size, "
        "checksum_sha256, status, created_at, updated_at) VALUES (?, 0, 'video', ?, ?, ?, 'ready', 1, 1)",
        (item, relative, len(body), hashlib.sha256(body).hexdigest()),
    )
    await database.execute(
        "INSERT INTO download_jobs (kind, remote_id, payload_json, status, attempts, next_attempt_at, "
        "created_at, updated_at) VALUES ('download', ?, ?, 'completed', 2, 0, 1, 1)",
        (item, json.dumps({"remote_id": item, "assets": []})),
    )
    return path


def test_self_check_finds_missing_and_damaged_files_and_downloads_them_again(tmp_path: Path) -> None:
    """Catches a backup that silently lost or damaged files after saving them."""
    root = tmp_path / "archive"

    async def scenario() -> None:
        database = await Database(tmp_path / "archive.sqlite3").open()
        await saved(database, root, "1", b"good video")
        gone = await saved(database, root, "2", b"lost video")
        damaged = await saved(database, root, "3", b"damaged!!!")
        clock = [1_800_000_000.0]
        verifier = ArchiveVerifier(database, root, clock=lambda: clock[0])

        assert (await verifier.summary())["verifiedFiles"] == 0
        gone.unlink()
        damaged.write_bytes(b"flipped!!!")  # same size, different bytes
        # The fast pass notices the missing file; only hashing catches the flipped bytes.
        assert await verifier.run_presence_pass() == 3
        assert (await verifier.summary())["presentFiles"] == 2
        assert await verifier.run_checksum_pass() == 2

        files = {
            row["item_id"]: dict(row)
            for row in await database.fetchall("SELECT item_id, status, verify_status FROM media_files")
        }
        assert files["1"]["status"] == "ready" and files["1"]["verify_status"] == "ok"
        assert (files["2"]["status"], files["2"]["verify_status"]) == ("pending", "missing")
        assert (files["3"]["status"], files["3"]["verify_status"]) == ("pending", "corrupt")
        # The damaged copy is kept aside, never deleted, so the re-download replaces it.
        assert not damaged.exists()
        assert [p.read_bytes() for p in (root / "quarantine").rglob("*.mp4.*")] == [b"flipped!!!"]
        jobs = {
            row["remote_id"]: dict(row)
            for row in await database.fetchall(
                "SELECT remote_id, status, attempts, last_error_code FROM download_jobs"
            )
        }
        assert jobs["1"]["status"] == "completed"
        for item in ("2", "3"):
            assert (jobs[item]["status"], jobs[item]["attempts"], jobs[item]["last_error_code"]) == (
                "retry",
                0,
                "MEDIA_URL_EXPIRED",
            )

        summary = await verifier.summary()
        assert summary["totalFiles"] == 1 and summary["verifiedFiles"] == 1
        assert summary["repairingFiles"] == 2
        assert summary["allCheckedSince"] == int(clock[0])
        assert summary["allPresentSince"] == int(clock[0])

        # Once re-downloaded the file counts as repaired, and everything is checked again a month later.
        await database.execute("UPDATE media_files SET status='ready' WHERE item_id IN ('2', '3')")
        (root / "objects/2/0.mp4").write_bytes(b"lost video")
        (root / "objects/3/0.mp4").write_bytes(b"damaged!!!")
        summary = await verifier.summary()
        assert summary["repairedFiles"] == 2 and summary["repairingFiles"] == 0
        assert await verifier.run_checksum_pass() == 2  # the fresh copies are checked right away
        assert await verifier.run_checksum_pass() == 0
        clock[0] += RECHECK_AFTER_SECONDS + 1
        assert await verifier.run_checksum_pass() == 3
        await database.close()

    asyncio.run(scenario())


def test_fast_pass_covers_the_whole_archive_before_hashing_catches_up(tmp_path: Path) -> None:
    """Catches a self-check that needs weeks before it can say anything about most files."""
    from douyin_archive.integrity import MAX_FILES_PER_RUN

    root = tmp_path / "archive"

    async def scenario() -> None:
        database = await Database(tmp_path / "archive.sqlite3").open()
        for index in range(MAX_FILES_PER_RUN * 3):
            await saved(database, root, str(100 + index), b"v" * 10)
        truncated = root / "objects/150/0.mp4"
        truncated.write_bytes(b"v" * 4)
        verifier = ArchiveVerifier(database, root, clock=lambda: 1_800_000_000.0)
        await verifier.run_batch()
        summary = await verifier.summary()
        total = MAX_FILES_PER_RUN * 3 - 1
        # One run: every file has been seen, a third has been hashed, the short one is queued again.
        assert summary["totalFiles"] == total and summary["presentFiles"] == total
        assert summary["allPresentSince"] == 1_800_000_000
        assert summary["verifiedFiles"] == MAX_FILES_PER_RUN
        assert summary["allCheckedSince"] is None
        assert summary["repairingFiles"] == 1
        await database.close()

    asyncio.run(scenario())

from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database


@dataclass(frozen=True, slots=True)
class MediaTechnical:
    status: str
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    fps: float | None = None
    bit_rate: int | None = None
    duration_ms: int | None = None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _frame_rate(value: object) -> float | None:
    text = str(value or "")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        top = _optional_float(numerator)
        bottom = _optional_float(denominator)
        return top / bottom if top is not None and bottom else None
    return _optional_float(value)


def parse_ffprobe(payload: dict[str, Any]) -> MediaTechnical:
    streams = payload.get("streams")
    video = (
        next(
            (
                stream
                for stream in streams
                if isinstance(stream, dict) and stream.get("codec_type") == "video"
            ),
            {},
        )
        if isinstance(streams, list)
        else {}
    )
    format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = _optional_float(video.get("duration"))
    if duration is None:
        duration = _optional_float(format_info.get("duration"))
    return MediaTechnical(
        status="ready",
        width=_optional_int(video.get("width")),
        height=_optional_int(video.get("height")),
        codec=str(video["codec_name"]) if video.get("codec_name") else None,
        fps=_frame_rate(video.get("avg_frame_rate", video.get("r_frame_rate"))),
        bit_rate=_optional_int(video.get("bit_rate", format_info.get("bit_rate"))),
        duration_ms=round(duration * 1000) if duration is not None else None,
    )


class MediaProbe:
    def __init__(
        self,
        executable: str | None = None,
        *,
        discover_executable: bool = True,
        timeout_seconds: float = 20,
    ) -> None:
        self.executable = executable or (shutil.which("ffprobe") if discover_executable else None)
        self.timeout_seconds = timeout_seconds

    async def probe(self, path: Path) -> MediaTechnical:
        if self.executable is None:
            return MediaTechnical(status="unavailable")
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            if process.returncode != 0:
                return MediaTechnical(status="failed")
            payload = json.loads(stdout)
            if not isinstance(payload, dict):
                return MediaTechnical(status="failed")
            return parse_ffprobe(payload)
        except (TimeoutError, OSError, json.JSONDecodeError):
            return MediaTechnical(status="failed")


class MediaProbeBackfill:
    def __init__(self, database: Database, archive_root: Path, probe: Any) -> None:
        self.db = database
        self.archive_root = archive_root.resolve()
        self.probe = probe

    async def run_batch(self, *, limit: int = 25) -> int:
        rows = await self.db.fetchall(
            "SELECT id, relative_path FROM media_files "
            "WHERE status='ready' AND probe_status='pending' "
            "AND relative_path IS NOT NULL ORDER BY id LIMIT ?",
            (max(1, limit),),
        )
        for row in rows:
            path = (self.archive_root / str(row["relative_path"])).resolve()
            technical = (
                await self.probe.probe(path)
                if path.is_relative_to(self.archive_root) and path.is_file()
                else MediaTechnical(status="failed")
            )
            now = int(time.time())
            await self.db.execute(
                "UPDATE media_files SET width=?, height=?, codec=?, fps=?, bit_rate=?, "
                "duration_ms=?, probe_status=?, probed_at=?, updated_at=? WHERE id=?",
                (
                    technical.width,
                    technical.height,
                    technical.codec,
                    technical.fps,
                    technical.bit_rate,
                    technical.duration_ms,
                    technical.status,
                    now,
                    now,
                    row["id"],
                ),
            )
        return len(rows)

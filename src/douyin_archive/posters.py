from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

POSTER_WIDTH = 540


class PosterCache:
    """Render small JPEG posters for archived media once and keep them on disk."""

    def __init__(
        self,
        archive_root: Path,
        *,
        executable: str | None = None,
        discover_executable: bool = True,
        concurrency: int = 2,
        timeout_seconds: float = 30,
    ) -> None:
        self.directory = archive_root.resolve() / "cache" / "posters"
        self.executable = executable or (shutil.which("ffmpeg") if discover_executable else None)
        self.timeout_seconds = timeout_seconds
        self._slots = asyncio.Semaphore(concurrency)
        self._locks: dict[int, asyncio.Lock] = {}
        # Undecodable sources stay undecodable; retrying them on every grid scroll
        # would keep ffmpeg busy for nothing.
        self._failed: set[int] = set()

    def path_for(self, media_id: int) -> Path:
        return self.directory / f"{media_id}.jpg"

    async def poster(self, media_id: int, source: Path, media_type: str) -> Path | None:
        target = self.path_for(media_id)
        if _usable(target):
            return target
        if self.executable is None or media_id in self._failed:
            return None
        lock = self._locks.setdefault(media_id, asyncio.Lock())
        async with lock:
            if _usable(target):
                return target
            async with self._slots:
                rendered = await self._render(source, target, media_type)
            if not rendered:
                self._failed.add(media_id)
            self._locks.pop(media_id, None)
            return target if rendered else None

    async def _render(self, source: Path, target: Path, media_type: str) -> bool:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{os.getpid()}.part.jpg")
        attempts = [["-ss", "1"], []] if media_type == "video" else [[]]
        try:
            for seek in attempts:
                if await self._run([*seek, "-i", str(source)], temporary) and _usable(temporary):
                    temporary.replace(target)
                    return True
            return False
        finally:
            temporary.unlink(missing_ok=True)

    async def _run(self, input_arguments: list[str], output: Path) -> bool:
        assert self.executable is not None
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-hide_banner",
                "-loglevel",
                "error",
                *input_arguments,
                "-frames:v",
                "1",
                "-vf",
                f"scale='min({POSTER_WIDTH},iw)':-2",
                "-q:v",
                "5",
                "-y",
                str(output),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return False
        try:
            await asyncio.wait_for(process.wait(), timeout=self.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            return False
        return process.returncode == 0


def _usable(path: Path) -> bool:
    try:
        return path.stat().st_size > 0
    except OSError:
        return False

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
LOCKOUT_SECONDS = (30, 60, 300, 900, 3600)


class LoginGuard:
    """Slow down password guessing against the single local admin account.

    Failures are counted per client address and per username; after
    MAX_FAILURES within the window the key is locked for a growing interval.
    State lives in memory, which is enough for one NAS container, and a
    restart simply clears it.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._locked_until: dict[str, float] = {}
        self._lockouts: dict[str, int] = defaultdict(int)

    def retry_after(self, *keys: str) -> int:
        """Seconds the caller must wait, or 0 when an attempt is allowed."""
        now = self._clock()
        waits = [self._locked_until.get(key, 0.0) - now for key in keys]
        longest = max(waits, default=0.0)
        return int(longest) + 1 if longest > 0 else 0

    def record_failure(self, *keys: str) -> None:
        now = self._clock()
        for key in keys:
            recent = [stamp for stamp in self._failures[key] if now - stamp < WINDOW_SECONDS]
            recent.append(now)
            self._failures[key] = recent
            if len(recent) >= MAX_FAILURES:
                step = min(self._lockouts[key], len(LOCKOUT_SECONDS) - 1)
                self._locked_until[key] = now + LOCKOUT_SECONDS[step]
                self._lockouts[key] += 1
                self._failures[key] = []

    def record_success(self, *keys: str) -> None:
        for key in keys:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)
            self._lockouts.pop(key, None)

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

# The NAS disk is often saturated and the page cache gets evicted, so the first
# visit after a quiet spell read everything from disk (home ~6 s, vanished
# creators ~6.5 s on the phone). Rebuilding those answers in the background
# keeps their pages in memory; the result is thrown away, so nothing goes stale.
WARM_EVERY_SECONDS = 60


async def warm_once(app: Any) -> None:
    from .routes.creators import vanished_creators
    from .routes.home import home

    request = SimpleNamespace(app=app)
    await home(request)
    await vanished_creators(request, limit=60, cursor=None, search=None, sort="recent")


async def keep_pages_warm(app: Any, *, interval: float = WARM_EVERY_SECONDS) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await warm_once(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("keeping pages warm failed", exc_info=True)

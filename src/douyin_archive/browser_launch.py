from __future__ import annotations

import os
from typing import Any


def chromium_launch_options() -> dict[str, Any]:
    """Return Chromium launch options shared by login and archive sessions."""

    options: dict[str, Any] = {
        "headless": True,
        "args": ["--disable-dev-shm-usage", "--no-sandbox"],
    }
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if executable:
        options["executable_path"] = executable
    return options

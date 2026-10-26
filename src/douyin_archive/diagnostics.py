"""Operator diagnostics: dump every asyncio task's stack on SIGUSR1.

A hung await never shows up in a thread dump (py-spy saw only idle threads
while a sync sat on ``page.close()`` for a day). ``docker kill -s USR1`` on the
container writes where each coroutine is waiting to the application log.
"""

from __future__ import annotations

import asyncio
import io
import logging
import signal
from contextlib import suppress

logger = logging.getLogger(__name__)


def format_asyncio_tasks(loop: asyncio.AbstractEventLoop | None = None) -> str:
    tasks = asyncio.all_tasks(loop) if loop is not None else asyncio.all_tasks()
    buffer = io.StringIO()
    buffer.write(f"{len(tasks)} asyncio tasks\n")
    for task in sorted(tasks, key=lambda item: item.get_name()):
        buffer.write(f"--- task {task.get_name()} done={task.done()}\n")
        with suppress(Exception):
            task.print_stack(limit=12, file=buffer)
    return buffer.getvalue()


def log_asyncio_tasks() -> None:
    logger.warning("Task dump requested\n%s", format_asyncio_tasks())


def install_task_dump_signal(loop: asyncio.AbstractEventLoop) -> bool:
    """Register SIGUSR1 as the task-dump trigger; False where signals are unsupported."""
    usr1 = getattr(signal, "SIGUSR1", None)
    if usr1 is None:
        return False
    try:
        loop.add_signal_handler(usr1, log_asyncio_tasks)
    except (NotImplementedError, RuntimeError, ValueError):
        return False
    return True

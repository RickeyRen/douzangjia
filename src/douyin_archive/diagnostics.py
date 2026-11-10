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
            for line in await_chain(task.get_coro()):
                buffer.write(f"  {line}\n")
    return buffer.getvalue()


def await_chain(coro: object, limit: int = 40) -> list[str]:
    """Follow cr_await from a task's coroutine down to where it is suspended.

    Task.print_stack shows only the outermost frame of a suspended coroutine,
    which hides the line that actually waits (a lock, a query, a page call).
    """
    lines: list[str] = []
    current = coro
    while current is not None and len(lines) < limit:
        frame = getattr(current, "cr_frame", None) or getattr(current, "ag_frame", None)
        if frame is None:
            frame = getattr(current, "gi_frame", None)
        if frame is not None:
            code = frame.f_code
            lines.append(f"{code.co_filename}:{frame.f_lineno} in {code.co_name}")
        nxt = (
            getattr(current, "cr_await", None)
            or getattr(current, "ag_await", None)
            or getattr(current, "gi_yieldfrom", None)
        )
        if nxt is None:
            if not hasattr(current, "cr_frame") and not hasattr(current, "gi_frame"):
                lines.append(f"awaiting {type(current).__name__}")
            break
        current = nxt
    return lines


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

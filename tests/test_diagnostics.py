import asyncio
import logging

from douyin_archive.diagnostics import (
    format_asyncio_tasks,
    install_task_dump_signal,
    log_asyncio_tasks,
)


async def test_task_dump_names_waiting_tasks_and_where_they_wait(caplog) -> None:
    gate = asyncio.Event()

    async def stuck_page_close() -> None:
        await gate.wait()

    task = asyncio.create_task(stuck_page_close(), name="sync:page-close")
    await asyncio.sleep(0)
    try:
        dump = format_asyncio_tasks()
        assert "task sync:page-close done=False" in dump
        assert "stuck_page_close" in dump
        with caplog.at_level(logging.WARNING):
            log_asyncio_tasks()
        assert "Task dump requested" in caplog.text
    finally:
        gate.set()
        await task


async def test_signal_handler_installs_on_posix_loops() -> None:
    loop = asyncio.get_running_loop()
    assert install_task_dump_signal(loop) is True
    import signal

    loop.remove_signal_handler(signal.SIGUSR1)

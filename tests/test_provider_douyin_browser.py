from douyin_archive.provider.douyin import PlaywrightDouyinSource


class FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler: object) -> None:
        if self.handlers.get(event) == handler:
            self.handlers.pop(event)


class FakeLease:
    def __init__(self) -> None:
        self.page = FakePage()
        self.released = False

    async def release(self) -> None:
        self.released = True


class FakeCoordinator:
    def __init__(self) -> None:
        self.lease = FakeLease()
        self.requested_viewports: list[tuple[int, int]] = []
        self.closed = False

    async def acquire_page(self, *, viewport: tuple[int, int]) -> FakeLease:
        self.requested_viewports.append(viewport)
        return self.lease


async def test_source_uses_coordinator_page_without_launching_browser() -> None:
    coordinator = FakeCoordinator()
    source = PlaywrightDouyinSource(coordinator)

    await source.open()

    assert coordinator.requested_viewports == [(1440, 1000)]
    assert "response" in coordinator.lease.page.handlers

    await source.close()

    assert coordinator.lease.released is True
    assert coordinator.lease.page.handlers == {}
    assert coordinator.closed is False

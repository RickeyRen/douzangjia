from douyin_archive.auth_browser import replay_drag


class RecordingMouse:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def move(self, x: float, y: float, *, steps: int = 1) -> None:
        self.events.append(("move", x, y, steps))

    async def down(self) -> None:
        self.events.append(("down",))

    async def up(self) -> None:
        self.events.append(("up",))


class RecordingPage:
    def __init__(self) -> None:
        self.mouse = RecordingMouse()
        self.waits: list[int] = []

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


async def test_replay_drag_maps_normalized_points_to_the_login_viewport() -> None:
    page = RecordingPage()

    await replay_drag(page, [(0.1, 0.2), (0.5, 0.2), (0.9, 0.2)])

    assert page.mouse.events == [
        ("move", 52.0, 136.0, 1),
        ("down",),
        ("move", 260.0, 136.0, 1),
        ("move", 468.0, 136.0, 1),
        ("up",),
    ]
    assert page.waits == [16, 16, 700]

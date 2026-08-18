from __future__ import annotations

import time
from types import SimpleNamespace

from douyin_archive.auth_browser import (
    LOGIN_VIEWPORT_HEIGHT,
    LOGIN_VIEWPORT_WIDTH,
    AuthBrowser,
    PointerGesture,
    replay_drag,
    replay_pointer,
)


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
    def __init__(
        self,
        *,
        nested_frame: RecordingPage | None = None,
        frame_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.mouse = RecordingMouse()
        self.waits: list[int] = []
        self.element_clicks: list[tuple[float, float]] = []
        self.hit_tests: list[tuple[float, float]] = []
        self.nested_frame = nested_frame
        self.frame_offset = frame_offset

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)

    async def evaluate_handle(self, _script: str, point: dict[str, float]):
        self.hit_tests.append((point["x"], point["y"]))
        return RecordingHandle(self, point["x"], point["y"])


class RecordingElement:
    def __init__(self, page: RecordingPage, x: float, y: float) -> None:
        self.page = page
        self.x = x
        self.y = y

    async def click(self, *, timeout: int) -> None:
        assert timeout == 2_000
        self.page.element_clicks.append((self.x, self.y))

    async def content_frame(self) -> RecordingPage | None:
        return self.page.nested_frame

    async def evaluate(self, _script: str) -> dict[str, float]:
        return {"x": self.page.frame_offset[0], "y": self.page.frame_offset[1]}


class RecordingHandle:
    def __init__(self, page: RecordingPage, x: float, y: float) -> None:
        self.element = RecordingElement(page, x, y)

    def as_element(self) -> RecordingElement:
        return self.element

    async def dispose(self) -> None:
        return None


class EmptyCookieContext:
    async def cookies(self) -> list[dict[str, object]]:
        return []


class ExpiredQrLocator:
    def __init__(self, page: ExpiredQrPage, selector: str) -> None:
        self.page = page
        self.selector = selector
        self.first = self

    async def is_visible(self, *, timeout: int) -> bool:
        assert timeout == 300
        return "刷新" in self.selector

    async def click(self, *, timeout: int) -> None:
        assert timeout == 2_000
        self.page.clicked.append(self.selector)


class ExpiredQrPage:
    def __init__(self) -> None:
        self.clicked: list[str] = []

    async def evaluate(self, _script: str) -> bool:
        return True

    def locator(self, selector: str) -> ExpiredQrLocator:
        return ExpiredQrLocator(self, selector)


def test_login_viewport_uses_full_douyin_desktop_layout() -> None:
    assert LOGIN_VIEWPORT_WIDTH == 1280
    assert LOGIN_VIEWPORT_HEIGHT == 800


async def test_poll_refreshes_an_expired_qr_inside_the_existing_browser() -> None:
    browser = AuthBrowser()
    page = ExpiredQrPage()
    browser._sessions["login-1"] = SimpleNamespace(
        deadline=time.monotonic() + 60,
        context=EmptyCookieContext(),
        page=page,
    )

    status = await browser.poll("login-1", capture_screenshot=False)

    assert status.state == "awaiting_scan"
    assert page.clicked == ["button:has-text('刷新')"]


async def test_replay_pointer_clicks_the_dom_element_instead_of_splitting_mouse_events() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "up", 0.5, 0.5)

    assert page.mouse.events == []
    assert page.element_clicks == [(640.0, 400.0)]
    assert page.waits == [120]


async def test_replay_pointer_clicks_through_a_nested_verification_frame() -> None:
    verification_frame = RecordingPage()
    page = RecordingPage(nested_frame=verification_frame, frame_offset=(40.0, 80.0))
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "up", 0.5, 0.5)

    assert page.element_clicks == []
    assert page.hit_tests == [(640.0, 400.0)]
    assert verification_frame.hit_tests == [(600.0, 320.0)]
    assert verification_frame.element_clicks == [(600.0, 320.0)]


async def test_replay_pointer_starts_a_native_drag_after_real_movement() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.1, 0.4)
    await replay_pointer(page, gesture, "move", 0.5, 0.4)
    await replay_pointer(page, gesture, "up", 0.9, 0.4)

    assert page.mouse.events == [
        ("move", 128.0, 320.0, 1),
        ("down",),
        ("move", 640.0, 320.0, 12),
        ("move", 1152.0, 320.0, 12),
        ("up",),
    ]
    assert page.element_clicks == []
    assert page.waits == [48, 16, 64, 120]


async def test_replay_pointer_paces_long_drag_before_releasing() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.1, 0.4)
    await replay_pointer(page, gesture, "move", 0.5, 0.4)
    await replay_pointer(page, gesture, "up", 0.9, 0.4)

    drag_moves = [event for event in page.mouse.events if event[0] == "move"]
    assert drag_moves[1][3] > 1
    assert drag_moves[2][3] > 1
    assert len(page.waits) > 1
    assert page.waits[-1] == 120


async def test_replay_pointer_keeps_small_cursor_jitter_as_a_click() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "move", 0.502, 0.502)
    await replay_pointer(page, gesture, "up", 0.502, 0.502)

    assert page.mouse.events == []
    assert page.element_clicks == [(642.56, 401.6)]


async def test_replay_pointer_forwards_hover_moves_without_a_pressed_pointer() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "move", 0.75, 0.25)

    assert page.mouse.events == [("move", 960.0, 200.0, 1)]
    assert page.element_clicks == []
    assert page.waits == []


async def test_replay_pointer_down_resets_an_unfinished_drag() -> None:
    page = RecordingPage()
    gesture = PointerGesture(origin=(10.0, 20.0), pressed=True)

    await replay_pointer(page, gesture, "down", 0.5, 0.5)

    assert page.mouse.events == [
        ("up",),
    ]
    assert gesture.origin == (640.0, 400.0)
    assert gesture.pressed is False


async def test_replay_drag_maps_normalized_points_to_the_login_viewport() -> None:
    page = RecordingPage()

    await replay_drag(page, [(0.1, 0.2), (0.5, 0.2), (0.9, 0.2)])

    assert page.mouse.events == [
        ("move", 128.0, 160.0, 1),
        ("down",),
        ("move", 640.0, 160.0, 1),
        ("move", 1152.0, 160.0, 1),
        ("up",),
    ]
    assert page.waits == [16, 16, 700]

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

try:
    from playwright.async_api import Error as SimulatedPlaywrightError
except ModuleNotFoundError:
    SimulatedPlaywrightError = RuntimeError

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

    async def click(self, x: float, y: float) -> None:
        self.events.append(("click", x, y))


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
        self.playwright_clicks: list[tuple[float, float]] = []
        self.hit_tests: list[tuple[float, float]] = []
        self.hit_test_scripts: list[str] = []
        self.nested_frame = nested_frame
        self.frame_offset = frame_offset

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)

    async def evaluate_handle(self, _script: str, point: dict[str, float]):
        self.hit_test_scripts.append(_script)
        self.hit_tests.append((point["x"], point["y"]))
        return RecordingHandle(self, point["x"], point["y"])


class RecordingElement:
    def __init__(self, page: RecordingPage, x: float, y: float) -> None:
        self.page = page
        self.x = x
        self.y = y

    async def click(self, *, timeout: int) -> None:
        assert timeout == 2_000
        if getattr(self.page, "intercept_element_click", False):
            raise RuntimeError("pointer events were intercepted")
        self.page.playwright_clicks.append((self.x, self.y))

    async def dispatch_event(self, event: str) -> None:
        assert event == "click"
        if getattr(self.page, "intercept_direct_click", False):
            raise SimulatedPlaywrightError("direct click dispatch failed")
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


class SessionCookieContext:
    async def cookies(self) -> list[dict[str, object]]:
        return [{"name": "sessionid", "domain": ".douyin.com", "value": "stale"}]


class CollectionStatusPage:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def evaluate(self, _script: str) -> dict[str, object]:
        return {
            "status_code": self.status_code,
            "collects_list": [] if self.status_code == 0 else None,
        }


class HiddenLocator:
    first: HiddenLocator

    def __init__(self) -> None:
        self.first = self

    async def is_visible(self, *, timeout: int) -> bool:
        assert timeout == 1_500
        return False


class LoginPage:
    def __init__(self) -> None:
        self.visited: list[str] = []
        self.context = LoginCdpContext()

    async def goto(self, url: str, **_options: object) -> None:
        self.visited.append(url)

    def locator(self, _selector: str) -> HiddenLocator:
        return HiddenLocator()

    async def screenshot(self, **_options: object) -> bytes:
        return b"login-image"


class LoginCdp:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.handlers: dict[str, object] = {}

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler: object) -> None:
        if self.handlers.get(event) == handler:
            self.handlers.pop(event)

    async def send(self, command: str, _params: object = None) -> None:
        self.commands.append(command)

    async def detach(self) -> None:
        return None


class LoginCdpContext:
    def __init__(self) -> None:
        self.cdp = LoginCdp()

    async def new_cdp_session(self, _page: object) -> LoginCdp:
        return self.cdp


class LoginLease:
    def __init__(self) -> None:
        self.page = LoginPage()
        self.context = EmptyCookieContext()
        self.released = False

    async def release(self) -> None:
        self.released = True


class LoginCoordinator:
    def __init__(self) -> None:
        self.lease = LoginLease()
        self.requested_viewports: list[tuple[int, int]] = []
        self.closed = False

    async def acquire_page(self, *, viewport: tuple[int, int]) -> LoginLease:
        self.requested_viewports.append(viewport)
        return self.lease


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


async def test_login_releases_its_page_without_closing_persistent_browser() -> None:
    coordinator = LoginCoordinator()
    browser = AuthBrowser(coordinator)

    login = await browser.start(timeout_seconds=60)
    await browser.close(login.id)

    assert login.state == "awaiting_scan"
    assert coordinator.requested_viewports == [(1280, 800)]
    assert coordinator.lease.released is True
    assert coordinator.closed is False


async def test_login_screencast_stops_before_its_page_is_released() -> None:
    coordinator = LoginCoordinator()
    browser = AuthBrowser(coordinator)
    login = await browser.start(timeout_seconds=60)

    first = await browser.screencast(login.id)
    second = await browser.screencast(login.id)
    await browser.close(login.id)

    assert first is second
    assert coordinator.lease.page.context.cdp.commands == [
        "Page.startScreencast",
        "Page.stopScreencast",
    ]
    assert coordinator.lease.released is True


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


@pytest.mark.parametrize("status_code, expected", [(0, True), (8, False)])
async def test_login_requires_live_collection_api_not_just_session_cookie(
    status_code: int,
    expected: bool,
) -> None:
    browser = AuthBrowser()
    session = SimpleNamespace(
        context=SessionCookieContext(),
        page=CollectionStatusPage(status_code),
    )

    assert await browser._session_is_authenticated(session) is expected


async def test_replay_pointer_clicks_the_dom_element_instead_of_splitting_mouse_events() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "up", 0.5, 0.5)

    assert page.mouse.events == []
    assert page.element_clicks == [(640.0, 400.0)]
    assert page.playwright_clicks == []
    assert page.waits == [120]


async def test_click_hit_testing_finds_interactive_elements_below_transparent_overlays() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "up", 0.5, 0.5)

    hit_test_script = page.hit_test_scripts[0]
    assert "elementsFromPoint" in hit_test_script
    assert "cursor === 'pointer'" in hit_test_script
    assert "__reactProps$" in hit_test_script


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
    assert verification_frame.playwright_clicks == []


async def test_replay_pointer_dispatches_click_without_actionability_checks() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "up", 0.5, 0.5)

    assert page.element_clicks == [(640.0, 400.0)]
    assert page.playwright_clicks == []
    assert page.mouse.events == []
    assert gesture.origin is None
    assert gesture.pressed is False


async def test_replay_pointer_falls_back_to_native_click_when_direct_dispatch_fails() -> None:
    page = RecordingPage()
    page.intercept_direct_click = True
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "up", 0.5, 0.5)

    assert page.element_clicks == []
    assert page.mouse.events == [("click", 640.0, 400.0)]
    assert gesture.origin is None
    assert gesture.pressed is False


async def test_replay_pointer_starts_a_native_drag_after_real_movement() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.1, 0.4)
    await replay_pointer(page, gesture, "move", 0.5, 0.4)
    await replay_pointer(page, gesture, "up", 0.9, 0.4)

    assert page.mouse.events == [
        ("move", 128.0, 320.0, 1),
        ("down",),
        ("move", 640.0, 320.0, 1),
        ("move", 1152.0, 320.0, 1),
        ("up",),
    ]
    assert page.element_clicks == []
    assert page.waits == [48, 64, 120]


async def test_replay_pointer_live_moves_follow_the_hand_without_pacing() -> None:
    """Catches the slider trailing seconds behind the cursor during a drag."""
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.1, 0.4)
    for step in range(1, 31):
        await replay_pointer(page, gesture, "move", 0.1 + step * 0.02, 0.4)
    await replay_pointer(page, gesture, "up", 0.7, 0.4)

    drag_moves = [event for event in page.mouse.events if event[0] == "move"]
    assert len(drag_moves) == 32  # press origin + 30 live moves + release point
    assert all(event[3] == 1 for event in drag_moves)
    # One pause when the press lands, one before release, one after: no
    # per-move pauses that would pile up while the hand keeps moving.
    assert page.waits == [48, 64, 120]


async def test_replay_pointer_keeps_small_cursor_jitter_as_a_click() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "move", 0.502, 0.502)
    await replay_pointer(page, gesture, "up", 0.502, 0.502)

    assert page.mouse.events == []
    assert page.element_clicks == [(642.56, 401.6)]


async def test_replay_pointer_keeps_normal_hand_jitter_as_a_click() -> None:
    page = RecordingPage()
    gesture = PointerGesture()

    await replay_pointer(page, gesture, "down", 0.5, 0.5)
    await replay_pointer(page, gesture, "move", 0.506, 0.505)
    await replay_pointer(page, gesture, "up", 0.506, 0.505)

    assert page.mouse.events == []
    assert len(page.element_clicks) == 1
    x, y = page.element_clicks[0]
    assert round(x, 2) == 647.68
    assert y == 404.0


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


class PhasePage:
    """Douyin page double whose text decides the login phase."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.clicked: list[str] = []

    async def evaluate(self, script: str, *args: object) -> object:
        if "二维码已失效" in script:
            return False
        if "verification" in script:
            markers = args[0]
            return {
                "verification": any(m in self.text for m in markers["verification"]),
                "dialog": any(m in self.text for m in markers["dialog"]),
            }
        return {}

    def locator(self, selector: str) -> PhaseLocator:
        return PhaseLocator(self, selector)


class PhaseLocator:
    def __init__(self, page: PhasePage, selector: str) -> None:
        self.page = page
        self.selector = selector
        self.first = self

    async def is_visible(self, *, timeout: int) -> bool:
        return "登录" in self.selector

    async def click(self, *, timeout: int) -> None:
        self.page.clicked.append(self.selector)

    # wait_for_timeout lives on the page in Playwright; the dialog opener
    # calls it after clicking, so the double provides it too.


async def _poll_phase(text: str) -> tuple[object, PhasePage]:
    browser = AuthBrowser()
    page = PhasePage(text)
    page.wait_for_timeout = lambda _ms: _noop()  # type: ignore[attr-defined]
    browser._sessions["login-1"] = SimpleNamespace(
        deadline=time.monotonic() + 60,
        context=EmptyCookieContext(),
        page=page,
    )
    status = await browser.poll("login-1", capture_screenshot=False)
    return status, page


async def _noop() -> None:
    return None


async def test_poll_reports_a_slider_check_so_people_know_to_act() -> None:
    status, page = await _poll_phase("请完成下列验证后继续 按住左边按钮拖动完成上方拼图")

    assert status.state == "awaiting_scan"
    assert status.verification_required is True
    assert page.clicked == []


async def test_poll_reopens_the_login_dialog_after_a_passed_check() -> None:
    """Catches the QR never appearing after someone completes the slider."""
    status, page = await _poll_phase("推荐 关注 朋友 我的 登录")

    assert status.verification_required is False
    assert page.clicked == ["button:has-text('登录')"]


async def test_poll_leaves_an_open_qr_dialog_alone() -> None:
    status, page = await _poll_phase("扫码登录 使用抖音APP扫一扫")

    assert status.verification_required is False
    assert page.clicked == []


class NavigatingPage:
    """The page Douyin navigates away from right after a confirmed scan."""

    def __init__(self) -> None:
        self.clicked: list[str] = []

    async def evaluate(self, *_args: object) -> object:
        from playwright.async_api import Error as PlaywrightError

        raise PlaywrightError(
            "Page.evaluate: Execution context was destroyed, most likely because of a navigation"
        )

    def locator(self, selector: str) -> PhaseLocator:
        return PhaseLocator(self, selector)  # type: ignore[arg-type]


async def test_poll_survives_the_navigation_after_a_confirmed_scan() -> None:
    """Catches a 500 on the status poll at the instant the phone confirms."""
    browser = AuthBrowser()
    page = NavigatingPage()
    page.wait_for_timeout = lambda _ms: _noop()  # type: ignore[attr-defined]
    browser._sessions["login-1"] = SimpleNamespace(
        deadline=time.monotonic() + 60,
        context=EmptyCookieContext(),
        page=page,
    )

    status = await browser.poll("login-1", capture_screenshot=False)

    assert status.state == "awaiting_scan"

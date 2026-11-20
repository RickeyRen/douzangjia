import pytest

from douyin_archive.provider.base import RateLimited
from douyin_archive.provider.douyin import PlaywrightDouyinSource

HTTP_ERROR = RuntimeError(
    "Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at https://www.douyin.com/user/self"
)


class GotoPage:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = list(failures)
        self.visits = 0
        self.waits: list[int] = []

    async def goto(self, url: str, **_kwargs) -> None:
        self.visits += 1
        if self.failures:
            raise self.failures.pop(0)

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


def source_on(page: GotoPage) -> PlaywrightDouyinSource:
    source = PlaywrightDouyinSource.__new__(PlaywrightDouyinSource)
    source._page = page
    return source


async def test_error_page_is_retried_once_after_a_pause() -> None:
    page = GotoPage([HTTP_ERROR])
    await source_on(page)._goto("https://www.douyin.com/user/self", timeout=1)
    assert page.visits == 2
    assert page.waits == [PlaywrightDouyinSource.HTTP_ERROR_RETRY_DELAY_MS]


async def test_repeated_error_page_counts_as_rate_limiting() -> None:
    page = GotoPage([HTTP_ERROR, HTTP_ERROR])
    with pytest.raises(RateLimited):
        await source_on(page)._goto("https://www.douyin.com/user/self")
    assert page.visits == 2


async def test_other_navigation_errors_are_not_retried() -> None:
    page = GotoPage([TimeoutError("Page.goto: Timeout 45000ms exceeded")])
    with pytest.raises(TimeoutError):
        await source_on(page)._goto("https://www.douyin.com/user/self")
    assert page.visits == 1

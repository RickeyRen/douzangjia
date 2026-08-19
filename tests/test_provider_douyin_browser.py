import asyncio
import logging

import pytest

from douyin_archive.provider import douyin as douyin_module
from douyin_archive.provider.base import ProviderChanged
from douyin_archive.provider.douyin import (
    ALL_FAVORITES_REMOTE_ID,
    PlaywrightDouyinSource,
    _merge_collection_counts,
    _parse_collection_counts,
    _payload_shape,
)


class FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.url = "https://www.douyin.com/user/self?private=page-token"

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


async def test_source_captures_current_listcollection_endpoint() -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.url = (
                "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
                "?device_platform=webapp"
            )
            self.headers = {"content-type": "application/json; charset=utf-8"}

        async def json(self) -> dict:
            return {"mix_list": [{"mix_id": "1001", "mix_name": "想去的地方"}]}

    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()
    await source._capture_response(FakeResponse())

    assert source._responses.qsize() == 1
    await source.close()


async def test_response_capture_ignores_bodies_lost_during_navigation() -> None:
    class NavigatedResponse:
        def __init__(self) -> None:
            self.url = "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
            self.headers = {"content-type": "application/json"}

        async def json(self) -> dict:
            raise RuntimeError("response body disappeared after navigation")

    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()

    await source._capture_response(NavigatedResponse())

    assert source._responses.empty()
    await source.close()


async def test_collection_wait_skips_flat_favorite_video_response() -> None:
    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()
    url = "https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
    await source._responses.put((url, {"aweme_list": [{"aweme_id": "734"}]}))
    expected = {"mix_list": [{"mix_id": "1001", "mix_name": "想去的地方"}]}
    await source._responses.put((url, expected))

    payload = await source._wait_for_collections()

    assert payload == expected
    await source.close()


async def test_direct_collects_api_uses_browser_session_and_paginates() -> None:
    class DirectApiPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[dict] = []
            self.scripts: list[str] = []

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.scripts.append(script)
            self.calls.append(arguments)
            if arguments["path"].endswith("/collects/list/"):
                return {
                    "status_code": 0,
                    "collects_list": [
                        {
                            "collects_id_str": "2001",
                            "collects_name": "想去的地方",
                        }
                    ],
                    "has_more": 0,
                }
            cursor = arguments["params"]["cursor"]
            return {
                "status_code": 0,
                "aweme_list": [{"aweme_id": f"item-{cursor}"}],
                "cursor": 20,
                "has_more": int(cursor == 0),
            }

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = DirectApiPage()

    collections = await source._fetch_collections_api()
    pages = [page async for page in source._iter_collection_api("2001")]

    assert collections["collects_list"][0]["collects_id_str"] == "2001"
    assert collections["collects_list"][-1] == {
        "collects_id_str": ALL_FAVORITES_REMOTE_ID,
        "collects_name": "抖音全部收藏",
    }
    assert [page["aweme_list"][0]["aweme_id"] for page in pages] == [
        "item-0",
        "item-20",
    ]
    assert source._page.calls[0]["path"].endswith("/collects/list/")
    assert source._page.calls[1]["params"]["collects_id"] == "2001"
    assert "AbortController" in source._page.scripts[0]


def test_collection_counts_are_recovered_from_the_official_folder_view() -> None:
    counts = _parse_collection_counts(
        """
        新建收藏夹
        ✈️
        共2390作品
        有用的收藏
        共 33 作品
        想去的地方
        共1.2万作品
        """,
        ("✈️", "有用的收藏", "想去的地方", "不存在"),
    )

    assert counts == {"✈️": 2390, "有用的收藏": 33, "想去的地方": 12_000}


def test_dom_counts_fill_missing_api_counts_without_overwriting_api_values() -> None:
    payload = {
        "status_code": 0,
        "collects_list": [
            {
                "collects_id_str": "2001",
                "collects_name": "想去的地方",
            },
            {
                "collects_id_str": "2002",
                "collects_name": "家居设计",
                "aweme_count": 2,
            },
        ],
    }

    enriched = _merge_collection_counts(payload, {"想去的地方": 19, "家居设计": 99})

    assert enriched["collects_list"][0]["aweme_count"] == 19
    assert enriched["collects_list"][1]["aweme_count"] == 2


async def test_collection_count_fallback_waits_for_the_folder_view_to_render() -> None:
    class BodyLocator:
        def __init__(self) -> None:
            self.reads = 0

        async def inner_text(self, *, timeout: int) -> str:
            assert timeout == 5_000
            self.reads += 1
            if self.reads == 1:
                return "收藏夹加载中"
            return "想去的地方\n共19作品"

    class DelayedFolderPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.body = BodyLocator()
            self.waits: list[int] = []

        async def wait_for_timeout(self, milliseconds: int) -> None:
            self.waits.append(milliseconds)

        def locator(self, selector: str) -> BodyLocator:
            assert selector == "body"
            return self.body

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = DelayedFolderPage()
    source._page = page
    click_attempts = 0

    async def record_clicks(labels: tuple[str, ...]) -> None:
        nonlocal click_attempts
        assert labels == ("收藏", "收藏夹")
        click_attempts += 1

    source._click_text_candidates = record_clicks  # type: ignore[method-assign]

    counts = await source._read_collection_counts_from_page(("想去的地方",))

    assert counts == {"想去的地方": 19}
    assert click_attempts == 2
    assert page.waits == [800, 800]


async def test_all_favorites_use_the_flat_favorites_endpoint() -> None:
    class FlatFavoritesPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.paths: list[str] = []

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.paths.append(arguments["path"])
            return {
                "status_code": 0,
                "aweme_list": [{"aweme_id": "all-1"}],
                "cursor": 20,
                "has_more": 0,
            }

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = FlatFavoritesPage()

    pages = [page async for page in source._iter_collection_api(ALL_FAVORITES_REMOTE_ID)]

    assert pages[0]["aweme_list"][0]["aweme_id"] == "all-1"
    assert source._page.paths == ["/aweme/v1/web/aweme/listcollection/"]


async def test_account_source_uses_visible_tab_ids_and_fetches_item_details() -> None:
    class Candidate:
        async def count(self) -> int:
            return 1

        def nth(self, index: int):
            assert index == 0
            return self

        async def is_visible(self, *, timeout: int) -> bool:
            return True

        async def click(self, *, timeout: int) -> None:
            return None

    class AccountPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.goto_urls: list[str] = []
            self.id_reads = 0
            self.detail_ids: list[list[str]] = []

        async def goto(self, url: str, **kwargs) -> None:
            self.goto_urls.append(url)

        def get_by_text(self, label: str, *, exact: bool) -> Candidate:
            assert label == "作品"
            assert exact is True
            return Candidate()

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        async def evaluate(self, script: str, arguments=None):
            if "__yingcangVisibleAccountIds" in script:
                assert "closest('footer')" in script
                assert "img, picture, video" in script
                assert "data-e2e-aweme-id" in script
                self.id_reads += 1
                return ["734", "735"]
            if "__yingcangScrollAccountPanel" in script:
                assert "scrollHeight > element.clientHeight" in script
                assert "overflowY" in script
                return True
            if "__yingcangFetchDetails" in script:
                ids = list(arguments["ids"])
                self.detail_ids.append(ids)
                return {
                    "status_code": 0,
                    "aweme_list": [
                        {
                            "aweme_id": remote_id,
                            "desc": f"作品 {remote_id}",
                            "author": {"uid": "creator-1", "nickname": "作者"},
                            "video": {
                                "play_addr": {
                                    "url_list": [f"https://media.test/{remote_id}.mp4"]
                                }
                            },
                        }
                        for remote_id in ids
                    ],
                    "has_more": 0,
                }
            raise AssertionError("unexpected browser evaluation")

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = AccountPage()
    source._page = page

    pages = [page async for page in source.iter_account_raw_pages("post")]

    assert page.goto_urls == [f"{source.SELF_URL}&showTab=post"]
    assert page.detail_ids == [["734", "735"]]
    assert [item["aweme_id"] for item in pages[0]["aweme_list"]] == ["734", "735"]
    assert pages[0]["has_more"] is False
    assert page.id_reads >= 3


async def test_following_source_uses_official_follow_feed() -> None:
    class FollowingPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.goto_urls: list[str] = []
            self.id_reads = 0

        async def goto(self, url: str, **kwargs) -> None:
            self.goto_urls.append(url)

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        async def evaluate(self, script: str, arguments=None):
            if "__yingcangVisibleAccountIds" in script:
                self.id_reads += 1
                return ["767"]
            if "__yingcangScrollAccountPanel" in script:
                return True
            if "__yingcangFetchDetails" in script:
                return {
                    "status_code": 0,
                    "aweme_list": [
                        {
                            "aweme_id": item_id,
                            "author": {"uid": "creator-1", "nickname": "作者"},
                            "video": {
                                "play_addr": {
                                    "url_list": [f"https://media.test/{item_id}.mp4"]
                                }
                            },
                        }
                        for item_id in arguments["ids"]
                    ],
                }
            raise AssertionError("unexpected browser evaluation")

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = FollowingPage()
    source._page = page

    pages = [page async for page in source.iter_account_raw_pages("following")]

    assert "following" in source.SUPPORTED_ACCOUNT_SOURCES
    assert page.goto_urls == [source.FOLLOWING_URL]
    assert [item["aweme_id"] for item in pages[0]["aweme_list"]] == ["767"]
    assert page.id_reads >= 3


@pytest.mark.parametrize(
    ("kind", "expected_url"),
    [
        (
            "favorite_series",
            (
                "https://www.douyin.com/user/self?from_tab_name=main"
                "&showTab=favorite_collection&showSubTab=compilation"
            ),
        ),
        (
            "favorite_drama",
            (
                "https://www.douyin.com/user/self?from_tab_name=main"
                "&showTab=favorite_collection&showSubTab=playlet"
            ),
        ),
        (
            "reservation",
            (
                "https://www.douyin.com/user/self?from_tab_name=main"
                "&showTab=my_appointment"
            ),
        ),
    ],
)
async def test_additional_account_sources_use_stable_official_urls(
    kind: str, expected_url: str
) -> None:
    class EmptySourcePage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.goto_urls: list[str] = []

        async def goto(self, url: str, **kwargs) -> None:
            self.goto_urls.append(url)

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        async def evaluate(self, script: str, arguments=None):
            if "__yingcangVisibleNestedLinks" in script:
                return []
            if "__yingcangVisibleAccountIds" in script:
                return []
            if "__yingcangScrollAccountPanel" in script:
                return True
            raise AssertionError("unexpected browser evaluation")

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = EmptySourcePage()
    source._page = page

    pages = [page async for page in source.iter_account_raw_pages(kind)]

    assert kind in source.SUPPORTED_ACCOUNT_SOURCES
    assert page.goto_urls == [expected_url]
    assert pages == []


async def test_favorite_music_source_emits_stable_browsable_entities() -> None:
    class MusicCandidate:
        async def count(self) -> int:
            return 1

        def nth(self, index: int):
            assert index == 0
            return self

        async def is_visible(self, *, timeout: int) -> bool:
            return True

        async def click(self, *, timeout: int) -> None:
            return None

    class MusicPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.goto_urls: list[str] = []
            self.reads = 0
            self.music_click_queries = 0

        async def goto(self, url: str, **kwargs) -> None:
            self.goto_urls.append(url)

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        def get_by_text(self, label: str, *, exact: bool) -> MusicCandidate:
            assert label == "音乐"
            assert exact is True
            self.music_click_queries += 1
            return MusicCandidate()

        async def evaluate(self, script: str, arguments=None):
            if "__yingcangVisibleMusicEntities" in script:
                assert r"split(/\n+/)" in script
                self.reads += 1
                return [
                    {
                        "title": "收藏音乐",
                        "subtitle": "创作者",
                        "duration": "00:15",
                        "coverUrl": "https://media.test/music.jpg?size=100",
                    }
                ]
            if "__yingcangScrollSourceEntities" in script:
                return True
            raise AssertionError("unexpected browser evaluation")

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = MusicPage()
    source._page = page
    provider = douyin_module.DouyinProvider(source, known_ids=set())

    pages = [
        page async for page in provider.iter_account_entity_pages(
            "favorite_music", full_scan=True
        )
    ]

    assert provider.supported_account_entity_sources() == ("favorite_music",)
    assert page.goto_urls == [source.FAVORITE_MUSIC_URL]
    assert page.music_click_queries == 1
    assert len(pages) == 1
    assert len(pages[0].entities) == 1
    entity = pages[0].entities[0]
    assert entity.remote_id.startswith("music:")
    assert (entity.title, entity.subtitle, entity.entity_type) == (
        "收藏音乐",
        "创作者",
        "music",
    )
    assert page.reads >= 3


async def test_item_detail_fetch_retries_a_truncated_json_response() -> None:
    class FlakyDetailPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0
            self.waits: list[int] = []

        async def evaluate(self, script: str, arguments=None):
            assert "__yingcangFetchDetails" in script
            assert "JSON.parse(await response.text())" in script
            assert "for (let attempt = 0; attempt < 3; attempt += 1)" in script
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("Unexpected end of JSON input")
            return {
                "status_code": 0,
                "aweme_list": [{"aweme_id": arguments["ids"][0]}],
            }

        async def wait_for_timeout(self, milliseconds: int) -> None:
            self.waits.append(milliseconds)

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = FlakyDetailPage()
    source._page = page

    payload = await source._fetch_aweme_details(["734"])

    assert payload["aweme_list"][0]["aweme_id"] == "734"
    assert page.calls == 3
    assert page.waits == [500, 1_000]


async def test_provider_incremental_account_source_stops_at_known_streak() -> None:
    class RawAccountSource:
        async def fetch_collections(self) -> dict:
            return {"status_code": 0, "collects_list": []}

        async def iter_raw_pages(self, remote_id: str):
            if False:
                yield remote_id

        async def iter_account_raw_pages(
            self, kind: str, *, known_ids: set[str], full_scan: bool
        ):
            assert kind == "like"
            assert full_scan is False
            yield {
                "status_code": 0,
                "aweme_list": [
                    {
                        "aweme_id": str(index),
                        "author": {"nickname": "作者"},
                        "video": {
                            "play_addr": {
                                "url_list": [f"https://media.test/{index}.mp4"]
                            }
                        },
                    }
                    for index in range(35)
                ],
                "has_more": 1,
                "cursor": 35,
            }

    provider = douyin_module.DouyinProvider(
        RawAccountSource(), known_ids={str(index) for index in range(30)}
    )

    pages = [
        page async for page in provider.iter_account_pages("like", full_scan=False)
    ]

    assert pages == []


async def test_creator_source_opens_stable_creator_url_and_fetches_details() -> None:
    class CreatorPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.goto_urls: list[str] = []
            self.id_reads = 0

        async def goto(self, url: str, **kwargs) -> None:
            self.goto_urls.append(url)

        async def wait_for_timeout(self, milliseconds: int) -> None:
            return None

        async def evaluate(self, script: str, arguments=None):
            if "__yingcangVisibleAccountIds" in script:
                self.id_reads += 1
                return ["9001"]
            if "__yingcangScrollAccountPanel" in script:
                return True
            if "__yingcangFetchDetails" in script:
                return {
                    "status_code": 0,
                    "aweme_list": [
                        {
                            "aweme_id": "9001",
                            "author": {
                                "sec_uid": "creator-sec-uid",
                                "nickname": "旅行博主",
                            },
                            "video": {
                                "play_addr": {
                                    "url_list": ["https://media.test/9001.mp4"]
                                }
                            },
                        }
                    ],
                }
            raise AssertionError("unexpected browser evaluation")

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = CreatorPage()
    source._page = page

    pages = [
        page async for page in source.iter_creator_raw_pages("creator-sec-uid")
    ]

    assert page.goto_urls == ["https://www.douyin.com/user/creator-sec-uid"]
    assert pages[0]["aweme_list"][0]["aweme_id"] == "9001"


async def test_browser_api_timeout_is_a_stable_provider_error() -> None:
    class TimedOutPage(FakePage):
        async def evaluate(self, script: str, arguments: dict) -> dict:
            return {"__browser_error": "timeout"}

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = TimedOutPage()

    with pytest.raises(ProviderChanged):
        await source._browser_json(source.COLLECTS_LIST_PATH, {"cursor": 0})


async def test_cancelled_browser_child_is_a_stable_provider_error() -> None:
    class CancelledPage(FakePage):
        async def evaluate(self, script: str, arguments: dict) -> dict:
            raise asyncio.CancelledError

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = CancelledPage()

    with pytest.raises(ProviderChanged):
        await source._browser_json(source.COLLECTS_LIST_PATH, {"cursor": 0})


async def test_browser_api_evaluate_has_an_outer_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ResponsivePage(FakePage):
        async def evaluate(self, script: str, arguments: dict) -> dict:
            return {"status_code": 0, "collects_list": []}

    async def timeout_immediately(awaitables, *, timeout):
        assert timeout == 25
        return set(), set(awaitables)

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = ResponsivePage()
    monkeypatch.setattr(douyin_module.asyncio, "wait", timeout_immediately)

    with pytest.raises(ProviderChanged):
        await source._browser_json(source.COLLECTS_LIST_PATH, {"cursor": 0})


async def test_collection_page_retries_a_transient_browser_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TransientPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.attempts += 1
            if self.attempts == 1:
                return {"__browser_error": "timeout"}
            return {
                "status_code": 0,
                "aweme_list": [{"aweme_id": "recovered"}],
                "cursor": 20,
                "has_more": 0,
            }

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = TransientPage()
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(douyin_module.asyncio, "sleep", record_sleep)

    pages = [page async for page in source._iter_collection_api("2001")]

    assert pages[0]["aweme_list"][0]["aweme_id"] == "recovered"
    assert source._page.attempts == 2
    assert sleeps == [1]


async def test_collection_api_retries_empty_transient_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TransientPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def evaluate(self, script: str, arguments: dict) -> dict:
            self.attempts += 1
            if self.attempts == 1:
                return {"status_code": 0}
            return {"status_code": 0, "collects_list": [], "has_more": False}

    source = PlaywrightDouyinSource(FakeCoordinator())
    source._page = TransientPage()
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(douyin_module.asyncio, "sleep", record_sleep)

    payload = await source._fetch_collections_api()

    assert "collects_list" in payload
    assert source._page.attempts == 2
    assert sleeps == [1]


def test_payload_shape_never_contains_response_values() -> None:
    shape = _payload_shape(
        {
            "status_code": 0,
            "data": {"secret_field": "private-value", "items": [{"id": "private-id"}]},
            "cursor": "private-cursor",
        }
    )

    assert shape == {
        "cursor": "str",
        "data": {"items": "list[1]", "secret_field": "str"},
        "status_code": "int",
    }
    assert "private-value" not in repr(shape)
    assert "private-id" not in repr(shape)
    assert "private-cursor" not in repr(shape)


async def test_click_candidates_uses_visible_duplicate_instead_of_hidden_first() -> None:
    class Candidate:
        def __init__(self, index: int, clicks: list[int]) -> None:
            self.index = index
            self.clicks = clicks

        async def is_visible(self, *, timeout: int) -> bool:
            return self.index == 1

        async def click(self, *, timeout: int) -> None:
            self.clicks.append(self.index)

    class TextLocator:
        def __init__(self, clicks: list[int]) -> None:
            self.candidates = [Candidate(0, clicks), Candidate(1, clicks)]
            self.first = self.candidates[0]

        async def count(self) -> int:
            return len(self.candidates)

        def nth(self, index: int) -> Candidate:
            return self.candidates[index]

    class TextPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.clicks: list[int] = []

        def get_by_text(self, label: str, *, exact: bool) -> TextLocator:
            assert label == "收藏夹"
            assert exact is True
            return TextLocator(self.clicks)

        async def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 800

    source = PlaywrightDouyinSource(FakeCoordinator())
    page = TextPage()
    source._page = page

    await source._click_text_candidates(("收藏夹",))

    assert page.clicks == [1]


async def test_response_timeout_logs_only_sanitized_paths(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.url = "https://www.douyin.com/aweme/v1/web/tab/feed/?msToken=secret"
            self.headers = {"content-type": "text/html"}

    async def timeout_immediately(awaitable, *, timeout):
        awaitable.close()
        raise TimeoutError

    source = PlaywrightDouyinSource(FakeCoordinator())
    await source.open()
    await source._capture_response(FakeResponse())
    monkeypatch.setattr(douyin_module.asyncio, "wait_for", timeout_immediately)

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderChanged):
        await source._wait_for(source.COLLECTION_PATH_MARKERS)

    assert "/user/self" in caplog.text
    assert "/aweme/v1/web/tab/feed/" in caplog.text
    assert "page-token" not in caplog.text
    assert "msToken" not in caplog.text
    assert "secret" not in caplog.text
    await source.close()

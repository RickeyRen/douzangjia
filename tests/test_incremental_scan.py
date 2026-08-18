from collections.abc import AsyncIterator

from douyin_archive.provider.base import RawPageSource, RemoteCollection
from douyin_archive.provider.douyin import DouyinProvider


def raw_item(remote_id: str) -> dict:
    return {
        "aweme_id": remote_id,
        "desc": f"作品 {remote_id}",
        "author": {"nickname": "作者"},
        "video": {"play_addr": {"url_list": [f"https://media.test/{remote_id}"]}},
    }


class FakeSource(RawPageSource):
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages
        self.requested_pages = 0

    async def fetch_collections(self) -> dict:
        return {"mix_infos": [{"mix_id": "1001", "mix_name": "想去的地方"}]}

    async def iter_raw_pages(self, remote_id: str) -> AsyncIterator[dict]:
        assert remote_id == "1001"
        for page in self.pages:
            self.requested_pages += 1
            yield page


async def test_list_collections_uses_normalized_contract() -> None:
    provider = DouyinProvider(FakeSource([]), known_ids=set())
    assert await provider.list_collections() == [RemoteCollection("1001", "想去的地方", None)]


async def test_incremental_scan_stops_after_thirty_consecutive_known_items() -> None:
    known_ids = {str(index) for index in range(1, 31)}
    source = FakeSource(
        [
            {"aweme_list": [raw_item("new"), *[raw_item(str(i)) for i in range(1, 21)]], "has_more": 1, "cursor": "2"},
            {"aweme_list": [*[raw_item(str(i)) for i in range(21, 31)], raw_item("too-old")], "has_more": 1, "cursor": "3"},
            {"aweme_list": [raw_item("never-requested")], "has_more": 0},
        ]
    )
    provider = DouyinProvider(source, known_ids=known_ids)

    pages = [page async for page in provider.iter_collection_pages("1001", full_scan=False)]
    items = [item.remote_id for page in pages for item in page.items]

    assert items == ["new"]
    assert source.requested_pages == 2


async def test_new_item_resets_consecutive_known_counter() -> None:
    known_ids = {str(index) for index in range(1, 41)}
    source = FakeSource(
        [
            {
                "aweme_list": [
                    *[raw_item(str(i)) for i in range(1, 21)],
                    raw_item("new"),
                    *[raw_item(str(i)) for i in range(21, 31)],
                ],
                "has_more": 0,
            }
        ]
    )
    provider = DouyinProvider(source, known_ids=known_ids)
    items = [
        item.remote_id
        async for page in provider.iter_collection_pages("1001", full_scan=False)
        for item in page.items
    ]
    assert items == ["new"]


async def test_full_scan_yields_known_items() -> None:
    source = FakeSource([{"aweme_list": [raw_item("1")], "has_more": 0}])
    provider = DouyinProvider(source, known_ids={"1"})
    items = [
        item.remote_id
        async for page in provider.iter_collection_pages("1001", full_scan=True)
        for item in page.items
    ]
    assert items == ["1"]


async def test_repeated_cursor_stops_instead_of_looping() -> None:
    source = FakeSource(
        [
            {"aweme_list": [raw_item("1")], "has_more": 1, "cursor": "same"},
            {"aweme_list": [raw_item("2")], "has_more": 1, "cursor": "same"},
            {"aweme_list": [raw_item("3")], "has_more": 1, "cursor": "same"},
        ]
    )
    provider = DouyinProvider(source, known_ids=set())
    items = [
        item.remote_id
        async for page in provider.iter_collection_pages("1001", full_scan=True)
        for item in page.items
    ]
    assert items == ["1", "2"]
    assert source.requested_pages == 2

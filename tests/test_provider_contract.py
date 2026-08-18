import json
from pathlib import Path

import pytest

from douyin_archive.provider.base import RateLimited, SessionExpired
from douyin_archive.provider.normalizers import normalize_collections, normalize_page

FIXTURES = Path(__file__).parent / "fixtures" / "douyin"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_collection_names_ids_and_counts_are_normalized() -> None:
    collections = normalize_collections(load_fixture("collections.json"))
    assert [(item.remote_id, item.name, item.item_count) for item in collections] == [
        ("1001", "想去的地方", 42),
        ("1002", "好看的美女", 8),
    ]


def test_video_and_gallery_assets_are_normalized() -> None:
    page = normalize_page(load_fixture("collection_items.json"))
    video, gallery = page.items

    assert video.remote_id == "734"
    assert video.item_type == "video"
    assert video.assets[0].media_type == "video"
    assert video.assets[0].expected_size == 12345
    assert gallery.remote_id == "735"
    assert gallery.item_type == "gallery"
    assert [asset.media_type for asset in gallery.assets] == ["image", "image"]
    assert page.next_cursor == "page-2"
    assert page.has_more is True


def test_nested_data_envelope_and_missing_author_are_tolerated() -> None:
    page = normalize_page(
        {
            "data": {
                "items": [
                    {
                        "id": "900",
                        "description": "无作者字段",
                        "video": {"play_addr": {"url_list": ["https://media.test/a"]}},
                    }
                ],
                "hasMore": False,
            }
        }
    )
    assert page.items[0].author_name == "未知作者"
    assert page.items[0].remote_id == "900"


@pytest.mark.parametrize("payload", [{"status_code": 8}, {"status_code": 1009}])
def test_session_expiry_is_a_stable_error(payload: dict) -> None:
    with pytest.raises(SessionExpired):
        normalize_page(payload)


def test_rate_limit_is_a_stable_error() -> None:
    with pytest.raises(RateLimited):
        normalize_page({"status_code": 429})

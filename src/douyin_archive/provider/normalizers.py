from __future__ import annotations

import mimetypes
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from ..models import MediaAsset, RemoteItem
from .base import RateLimited, RemoteCollection, RemotePage, SessionExpired

SESSION_EXPIRED_CODES = {8, 1009}


def _status_code(payload: dict[str, Any]) -> int:
    raw = payload.get("status_code", payload.get("statusCode", 0))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _check_status(payload: dict[str, Any]) -> None:
    status = _status_code(payload)
    if status in SESSION_EXPIRED_CODES:
        raise SessionExpired("Douyin session is no longer valid")
    if status == 429:
        raise RateLimited("Douyin requested a cooldown")


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("data")
    return nested if isinstance(nested, dict) else payload


def _first_list(payload: dict[str, Any], keys: Iterable[str]) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def normalize_collections(payload: dict[str, Any]) -> list[RemoteCollection]:
    _check_status(payload)
    data = _envelope(payload)
    records = _first_list(
        data, ("collects_list", "mix_infos", "mix_list", "collections", "items")
    )
    result: list[RemoteCollection] = []
    for record in records:
        remote_id = record.get(
            "collects_id_str",
            record.get(
                "collects_id",
                record.get("mix_id", record.get("id", record.get("collection_id"))),
            ),
        )
        name = record.get(
            "collects_name",
            record.get("mix_name", record.get("name", record.get("title"))),
        )
        if remote_id is None or not str(name or "").strip():
            continue
        statistics = record.get("statis") if isinstance(record.get("statis"), dict) else {}
        raw_count = statistics.get(
            "aweme_count", record.get("aweme_count", record.get("item_count"))
        )
        try:
            count = int(raw_count) if raw_count is not None else None
        except (TypeError, ValueError):
            count = None
        result.append(RemoteCollection(str(remote_id), str(name).strip(), count))
    return result


def _asset_url(container: Any) -> tuple[str | None, int | None]:
    if not isinstance(container, dict):
        return None, None
    urls = container.get("url_list", container.get("urlList", []))
    url = next((str(value) for value in urls if value), None) if isinstance(urls, list) else None
    raw_size = container.get("data_size", container.get("size"))
    try:
        size = int(raw_size) if raw_size is not None else None
    except (TypeError, ValueError):
        size = None
    return url, size


def _guess_mime(url: str, fallback: str) -> str:
    suffix = PurePosixPath(urlparse(url).path).suffix.lower()
    guessed = mimetypes.types_map.get(suffix)
    return guessed or fallback


def _normalize_item(record: dict[str, Any]) -> RemoteItem | None:
    remote_id = record.get("aweme_id", record.get("id"))
    if remote_id is None:
        return None
    remote_id = str(remote_id)
    author = record.get("author") if isinstance(record.get("author"), dict) else {}
    author_name = str(author.get("nickname", author.get("name", "未知作者"))).strip()
    creator_id = author.get("sec_uid", author.get("secUid", author.get("uid")))
    creator_unique_id = author.get("unique_id", author.get("uniqueId"))
    avatar = author.get("avatar_thumb", author.get("avatarThumb"))
    creator_avatar_url, _ = _asset_url(avatar)

    def optional_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    description = str(record.get("desc", record.get("description", ""))).strip()
    raw_published = record.get("create_time", record.get("published_at"))
    try:
        published_at = int(raw_published) if raw_published is not None else None
    except (TypeError, ValueError):
        published_at = None

    assets: list[MediaAsset] = []
    images = record.get("images")
    if isinstance(images, list) and images:
        item_type = "gallery"
        for index, image in enumerate(images):
            url, size = _asset_url(image)
            if url:
                assets.append(
                    MediaAsset(
                        remote_id,
                        index,
                        "image",
                        url,
                        _guess_mime(url, "image/jpeg"),
                        size,
                    )
                )
    else:
        item_type = "video"
        video = record.get("video") if isinstance(record.get("video"), dict) else {}
        address = video.get("play_addr", video.get("playAddr"))
        url, size = _asset_url(address)
        if url:
            assets.append(MediaAsset(remote_id, 0, "video", url, "video/mp4", size))

    return RemoteItem(
        remote_id=remote_id,
        author_name=author_name or "未知作者",
        description=description,
        item_type=item_type,
        published_at=published_at,
        assets=tuple(assets),
        creator_id=str(creator_id) if creator_id else None,
        creator_unique_id=str(creator_unique_id) if creator_unique_id else None,
        creator_avatar_url=creator_avatar_url,
        creator_follower_count=optional_int(
            author.get("follower_count", author.get("followerCount"))
        ),
        creator_post_count=optional_int(
            author.get("aweme_count", author.get("awemeCount"))
        ),
    )


def normalize_page(payload: dict[str, Any]) -> RemotePage:
    _check_status(payload)
    data = _envelope(payload)
    records = _first_list(data, ("aweme_list", "items", "awemes"))
    items = tuple(item for record in records if (item := _normalize_item(record)) is not None)
    cursor = data.get("cursor", data.get("max_cursor", data.get("nextCursor")))
    raw_more = data.get("has_more", data.get("hasMore", False))
    return RemotePage(
        items=items,
        next_cursor=str(cursor) if cursor is not None else None,
        has_more=bool(raw_more),
    )

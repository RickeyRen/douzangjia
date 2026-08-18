from douyin_archive.paths import asset_filename, sanitize_segment


def test_sanitize_segment_preserves_chinese_and_blocks_traversal() -> None:
    assert sanitize_segment("../想去的/地方\x00") == "想去的_地方"


def test_sanitize_segment_has_stable_empty_fallback() -> None:
    assert sanitize_segment("../\x00") == "未命名"


def test_asset_filename_does_not_use_remote_url_path() -> None:
    assert asset_filename(0, "video", "video/mp4") == "000.mp4"
    assert asset_filename(12, "image", "image/jpeg") == "012.jpg"

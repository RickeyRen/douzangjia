import mimetypes
import re
import unicodedata

_UNSAFE_SEGMENT = re.compile(r"[\x00-\x1f\x7f/\\]+")
_REPEATED_UNDERSCORE = re.compile(r"_+")
_MIME_EXTENSIONS = {
    "video/mp4": ".mp4",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


def sanitize_segment(value: str, *, max_length: int = 120) -> str:
    """Return a single safe NFC path segment while preserving Chinese text."""

    normalized = unicodedata.normalize("NFC", value)
    cleaned = _UNSAFE_SEGMENT.sub("_", normalized)
    cleaned = _REPEATED_UNDERSCORE.sub("_", cleaned).strip(" ._")
    return cleaned[:max_length].rstrip(" ._") or "未命名"


def asset_filename(index: int, media_type: str, mime_type: str | None) -> str:
    extension = _MIME_EXTENSIONS.get(mime_type or "")
    if extension is None and mime_type:
        extension = mimetypes.guess_extension(mime_type, strict=False)
    if not extension:
        extension = ".mp4" if media_type == "video" else ".jpg"
    return f"{index:03d}{extension}"

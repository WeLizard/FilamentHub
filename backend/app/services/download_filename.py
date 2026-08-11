"""Safe filenames and HTTP attachment headers for generated downloads."""

from urllib.parse import quote


def safe_download_stem(value: str | None, fallback: str = "download") -> str:
    """Keep readable Unicode while removing characters forbidden in filenames."""
    safe = value or ""
    for character in '<>:"/\\|?*':
        safe = safe.replace(character, "_")
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip(" _") or fallback


def attachment_content_disposition(filename: str) -> str:
    """Return an ASCII fallback plus an RFC 5987 UTF-8 filename."""
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"

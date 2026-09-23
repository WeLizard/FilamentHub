"""Bounded validation and preparation of outgoing email attachments."""

import base64
import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import status
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.errors import (
    ERR_EMAIL_ATTACHMENT_EMPTY,
    ERR_EMAIL_ATTACHMENT_LIMIT,
    ERR_EMAIL_ATTACHMENT_TYPE,
    ERR_EMAIL_ATTACHMENTS_TOO_LARGE,
    raise_error,
)

MAX_EMAIL_ATTACHMENTS = 10
MAX_EMAIL_ATTACHMENTS_BYTES = 15 * 1024 * 1024

_ALLOWED_CONTENT_TYPES = {
    ".zip": "application/zip",
    ".json": "application/json",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".csv": "text/csv",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".htm": "text/html",
    ".html": "text/html",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".webp": "image/webp",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class PreparedEmailAttachment:
    filename: str
    content_type: str
    content: bytes

    def provider_payload(self) -> dict[str, str]:
        return {
            "filename": self.filename,
            "content": base64.b64encode(self.content).decode("ascii"),
            "content_type": self.content_type,
        }

    def metadata(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "size": len(self.content),
            # Kept server-side so the same idempotency key cannot silently be
            # reused for another file with an identical name and size.
            "sha256": hashlib.sha256(self.content).hexdigest(),
        }


def _safe_filename(value: str | None) -> str:
    normalized = _CONTROL_CHARS.sub("", (value or "").replace("\\", "/"))
    filename = normalized.rsplit("/", 1)[-1].strip().strip(".")
    return filename[:180]


def _valid_office_zip(content: bytes, expected_folder: str) -> bool:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (BadZipFile, OSError):
        return False
    return "[Content_Types].xml" in names and any(
        name.startswith(f"{expected_folder}/") for name in names
    )


def _content_matches(extension: str, content: bytes) -> bool:
    if extension == ".pdf":
        return content.startswith(b"%PDF-")
    if _ALLOWED_CONTENT_TYPES.get(extension, "").startswith("image/"):
        try:
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > 40_000_000:
                    return False
                actual_type = Image.MIME.get(image.format)
                if actual_type != _ALLOWED_CONTENT_TYPES[extension]:
                    return False
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
            return True
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombError,
        ):
            return False
    if extension == ".zip":
        try:
            with ZipFile(BytesIO(content)) as archive:
                archive.infolist()
            return True
        except (BadZipFile, OSError, ValueError):
            return False
    if extension in {".doc", ".xls"}:
        return content.startswith(_OLE_SIGNATURE)
    if extension == ".docx":
        return _valid_office_zip(content, "word")
    if extension == ".xlsx":
        return _valid_office_zip(content, "xl")
    if extension == ".pptx":
        return _valid_office_zip(content, "ppt")
    if extension in {".htm", ".html", ".txt", ".csv", ".json"}:
        if b"\x00" in content:
            return False
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return False
        return True
    return False


def email_image_preview(content: bytes) -> bytes | None:
    """Decode bounded raster input and return a browser-compatible thumbnail."""
    if len(content) > MAX_EMAIL_ATTACHMENTS_BYTES:
        return None
    try:
        with Image.open(
            BytesIO(content),
            formats=["PNG", "JPEG", "GIF", "WEBP", "BMP", "TIFF", "AVIF", "ICO", "JPEG2000"],
        ) as image:
            if image.width * image.height > 40_000_000:
                return None
            image.thumbnail((1600, 1600))
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


async def prepare_email_attachments(
    uploads: list[UploadFile],
) -> list[PreparedEmailAttachment]:
    """Read at most 15 MiB and verify every attachment against an explicit allowlist."""
    if len(uploads) > MAX_EMAIL_ATTACHMENTS:
        raise_error(400, ERR_EMAIL_ATTACHMENT_LIMIT, {"max": MAX_EMAIL_ATTACHMENTS})

    prepared: list[PreparedEmailAttachment] = []
    total_size = 0
    for upload in uploads:
        filename = _safe_filename(upload.filename)
        extension = Path(filename).suffix.casefold()
        content_type = _ALLOWED_CONTENT_TYPES.get(extension)
        if not filename or content_type is None:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ERR_EMAIL_ATTACHMENT_TYPE,
                {"filename": filename or "attachment"},
            )

        remaining = MAX_EMAIL_ATTACHMENTS_BYTES - total_size
        content = await upload.read(remaining + 1)
        if not content:
            raise_error(400, ERR_EMAIL_ATTACHMENT_EMPTY, {"filename": filename})
        total_size += len(content)
        if total_size > MAX_EMAIL_ATTACHMENTS_BYTES:
            raise_error(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                ERR_EMAIL_ATTACHMENTS_TOO_LARGE,
                {"max_mb": MAX_EMAIL_ATTACHMENTS_BYTES // (1024 * 1024)},
            )
        if not await run_in_threadpool(_content_matches, extension, content):
            raise_error(400, ERR_EMAIL_ATTACHMENT_TYPE, {"filename": filename})
        prepared.append(
            PreparedEmailAttachment(
                filename=filename,
                content_type=content_type,
                content=content,
            )
        )
    return prepared

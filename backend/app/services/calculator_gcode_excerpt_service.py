"""Receive the parts of a sliced file that the browser cut out locally.

A quote needs the slicer's summary and configuration, which sit at the start and
at the end of a G-code file and in a handful of metadata entries of a sliced 3MF.
The browser sends only those, so the server never holds the whole file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import python_multipart as multipart
from fastapi import Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from app.services.calculator_gcode_parser import (
    MAX_GCODE_3MF_ENTRIES,
    MAX_GCODE_3MF_PLATES,
    MAX_GCODE_3MF_SLICE_INFO_BYTES,
    MAX_GCODE_3MF_THUMBNAIL_BYTES,
    ToolpathEvidence,
    is_supported_gcode_filename,
    parse_gcode_3mf_excerpt,
    parse_gcode_excerpt,
)

MAX_EXCERPT_BODY_BYTES = 24 * 1024 * 1024
MAX_EXCERPT_HEAD_BYTES = 1024 * 1024
MAX_EXCERPT_TAIL_BYTES = 4 * 1024 * 1024
MAX_EXCERPT_FILE_SIZE_BYTES = 2147483648
MAX_EXCERPT_TOOLPATH_BYTES = 256 * 1024
_MAX_FIELD_BYTES = 4096
_MAX_FIELDS = 16
_MAX_PROJECT_SETTINGS_BYTES = 4 * 1024 * 1024
_MAX_SMALL_ENTRY_BYTES = 1024 * 1024

_FIELD_NAMES = frozenset({"file_name", "file_size_bytes", "container", "toolpath"})
_FIELD_LIMITS = {"toolpath": MAX_EXCERPT_TOOLPATH_BYTES}
_FILE_SIZE_RE = re.compile(r"\d{1,10}")
_PLATE_KEY_RE = re.compile(r"[1-9][0-9]{0,5}")
# Matched against the lower-cased, forward-slash archive path.
_ENTRY_LIMITS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"metadata/slice_info\.config"), MAX_GCODE_3MF_SLICE_INFO_BYTES),
    (re.compile(r"metadata/project_settings\.config"), _MAX_PROJECT_SETTINGS_BYTES),
    (re.compile(r"metadata/model_settings\.config"), _MAX_SMALL_ENTRY_BYTES),
    (re.compile(r"metadata/plate_\d{1,6}\.json"), _MAX_SMALL_ENTRY_BYTES),
    (re.compile(r"metadata/plate_\d{1,6}(?:_small)?\.png"), MAX_GCODE_3MF_THUMBNAIL_BYTES),
)


class GcodeExcerptTooLargeError(Exception):
    """The request or one of its parts is bigger than the contract allows."""


class GcodeExcerptInvalidError(Exception):
    """The request does not follow the excerpt contract."""


@dataclass(frozen=True, slots=True)
class GcodeExcerptUpload:
    file_name: str
    file_size_bytes: int
    container: Literal["plain_gcode", "gcode_3mf"]
    head: bytes | None
    tail: bytes | None
    entries: dict[str, bytes]
    # The browser's walk of every move: one for plain G-code, one per plate for a 3MF.
    toolpath: ToolpathEvidence | None = None
    plate_toolpaths: dict[int, ToolpathEvidence] | None = None


class _Part:
    __slots__ = ("data", "kind", "limit", "name", "path")

    def __init__(
        self,
        kind: Literal["field", "head", "tail", "entry"],
        limit: int,
        *,
        name: str = "",
        path: str | None = None,
    ) -> None:
        self.kind = kind
        self.limit = limit
        self.name = name
        self.path = path
        self.data = bytearray()


class _ExcerptFormReader:
    """Collect one multipart body, refusing a part the moment it outgrows its cap."""

    def __init__(self) -> None:
        self.fields: dict[str, str] = {}
        self.head: bytes | None = None
        self.tail: bytes | None = None
        self.entries: dict[str, bytes] = {}
        self.ended = False
        self._part: _Part | None = None
        self._field_count = 0
        self._disposition = b""
        self._header_name = b""
        self._header_value = b""

    def on_part_begin(self) -> None:
        self._part = None
        self._disposition = b""

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        if self._header_name.lower() == b"content-disposition":
            self._disposition = self._header_value
        self._header_name = b""
        self._header_value = b""

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._disposition)
        raw_name = options.get(b"name")
        if raw_name is None:
            raise GcodeExcerptInvalidError
        name = _decode_header_text(raw_name)
        raw_filename = options.get(b"filename")

        if raw_filename is None:
            self._field_count += 1
            if self._field_count > _MAX_FIELDS or name in self.fields:
                raise GcodeExcerptInvalidError
            self._part = _Part("field", _FIELD_LIMITS.get(name, _MAX_FIELD_BYTES), name=name)
            return

        if name == "head" and self.head is None:
            self._part = _Part("head", MAX_EXCERPT_HEAD_BYTES)
        elif name == "tail" and self.tail is None:
            self._part = _Part("tail", MAX_EXCERPT_TAIL_BYTES)
        elif name == "entry":
            # The File API lets a browser replace "/" in a name with ":".
            path = _decode_header_text(raw_filename).replace("\\", "/").replace(":", "/").lower()
            limit = _entry_limit(path)
            if (
                limit is None
                or path in self.entries
                or len(self.entries) >= MAX_GCODE_3MF_ENTRIES
            ):
                raise GcodeExcerptInvalidError
            self._part = _Part("entry", limit, path=path)
            # Reserved now so a repeated path is refused before its data is read.
            self.entries[path] = b""
        else:
            raise GcodeExcerptInvalidError

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        part = self._part
        if part is None:
            return
        if len(part.data) + (end - start) > part.limit:
            raise GcodeExcerptTooLargeError
        part.data.extend(data[start:end])

    def on_part_end(self) -> None:
        part = self._part
        self._part = None
        if part is None:
            return
        data = bytes(part.data)
        if part.kind == "head":
            self.head = data
        elif part.kind == "tail":
            self.tail = data
        elif part.kind == "entry" and part.path is not None:
            self.entries[part.path] = data
        else:
            self.fields[part.name] = data.decode("utf-8", errors="replace")

    def on_end(self) -> None:
        self.ended = True


def _decode_header_text(value: bytes | bytearray) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("latin-1")


def _entry_limit(path: str) -> int | None:
    for pattern, limit in _ENTRY_LIMITS:
        if pattern.fullmatch(path):
            return limit
    return None


async def read_gcode_excerpt_upload(request: Request) -> GcodeExcerptUpload:
    """Stream the multipart body into bounded buffers and validate it."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_EXCERPT_BODY_BYTES:
        raise GcodeExcerptTooLargeError

    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise GcodeExcerptInvalidError

    reader = _ExcerptFormReader()
    parser = multipart.MultipartParser(
        boundary,
        {
            "on_part_begin": reader.on_part_begin,
            "on_part_data": reader.on_part_data,
            "on_part_end": reader.on_part_end,
            "on_header_field": reader.on_header_field,
            "on_header_value": reader.on_header_value,
            "on_header_end": reader.on_header_end,
            "on_headers_finished": reader.on_headers_finished,
            "on_end": reader.on_end,
        },
    )
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_EXCERPT_BODY_BYTES:
                raise GcodeExcerptTooLargeError
            parser.write(chunk)
        parser.finalize()
    except MultipartParseError as exc:
        raise GcodeExcerptInvalidError from exc
    if not reader.ended:
        raise GcodeExcerptInvalidError
    return _validated_upload(reader)


def _display_file_name(file_name: str) -> str:
    """Keep the display name while refusing paths and control characters."""
    normalized = file_name.replace("\\", "/").split("/")[-1].strip()
    if not normalized or len(normalized) > 255 or any(ord(char) < 32 for char in normalized):
        raise GcodeExcerptInvalidError
    return normalized


def _validated_upload(reader: _ExcerptFormReader) -> GcodeExcerptUpload:
    fields = {name: value for name, value in reader.fields.items() if name in _FIELD_NAMES}
    file_name = _display_file_name(fields.get("file_name", ""))
    if not is_supported_gcode_filename(file_name):
        raise GcodeExcerptInvalidError

    raw_size = fields.get("file_size_bytes", "").strip()
    if _FILE_SIZE_RE.fullmatch(raw_size) is None:
        raise GcodeExcerptInvalidError
    file_size_bytes = int(raw_size)
    if not 1 <= file_size_bytes <= MAX_EXCERPT_FILE_SIZE_BYTES:
        raise GcodeExcerptInvalidError

    container = fields.get("container")
    is_3mf_name = file_name.lower().endswith(".gcode.3mf")
    if container == "plain_gcode":
        if is_3mf_name or reader.head is None or reader.entries:
            raise GcodeExcerptInvalidError
    elif container == "gcode_3mf":
        if (
            not is_3mf_name
            or reader.head is not None
            or reader.tail is not None
            or "metadata/slice_info.config" not in reader.entries
        ):
            raise GcodeExcerptInvalidError
    else:
        raise GcodeExcerptInvalidError

    toolpath, plate_toolpaths = _read_toolpath(fields.get("toolpath"), is_3mf_name)
    return GcodeExcerptUpload(
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        container=container,
        head=reader.head,
        tail=reader.tail,
        entries=reader.entries,
        toolpath=toolpath,
        plate_toolpaths=plate_toolpaths,
    )


def _read_toolpath(
    raw: str | None,
    per_plate: bool,
) -> tuple[ToolpathEvidence | None, dict[int, ToolpathEvidence] | None]:
    """Decode the browser's toolpath summary; any deviation from the contract refuses the request."""
    if raw is None:
        return None, None
    try:
        decoded = json.loads(raw)
        if not per_plate:
            return ToolpathEvidence.from_payload(decoded), None
        if not isinstance(decoded, dict) or len(decoded) > MAX_GCODE_3MF_PLATES:
            raise GcodeExcerptInvalidError
        plates: dict[int, ToolpathEvidence] = {}
        for plate_key, payload in decoded.items():
            if _PLATE_KEY_RE.fullmatch(plate_key) is None:
                raise GcodeExcerptInvalidError
            plates[int(plate_key)] = ToolpathEvidence.from_payload(payload)
    except (ValueError, RecursionError) as exc:
        raise GcodeExcerptInvalidError from exc
    return None, plates


def parse_gcode_excerpt_upload(upload: GcodeExcerptUpload) -> list[dict[str, Any]]:
    """One job per plate for a sliced 3MF, a single job for plain G-code."""
    if upload.container == "gcode_3mf":
        return parse_gcode_3mf_excerpt(
            upload.file_name,
            upload.file_size_bytes,
            upload.entries,
            upload.plate_toolpaths,
        )
    return [
        parse_gcode_excerpt(
            upload.file_name,
            upload.file_size_bytes,
            upload.head or b"",
            upload.tail,
            upload.toolpath,
        )
    ]

"""Provider-neutral NFC/RFID tag identity helpers."""

from __future__ import annotations

import json
import re

TAG_UID_MAX_LENGTH = 64
TAG_FORMAT_MAX_LENGTH = 32
TAG_TECHNOLOGIES = ("unknown", "nfc", "uhf_rfid")

_UID_SEPARATORS = re.compile(r"[\s:_.-]+")
_HEX_UID = re.compile(r"^[0-9A-F]+$")


def normalize_tag_uid(value: str) -> str:
    """Return one canonical uppercase hexadecimal UID."""
    normalized = _UID_SEPARATORS.sub("", value).strip().upper().removeprefix("0X")
    if not normalized:
        raise ValueError("A tag UID must not be empty.")
    if not _HEX_UID.fullmatch(normalized):
        raise ValueError("A tag UID must be hexadecimal.")
    if len(normalized) % 2:
        raise ValueError("A tag UID must contain complete hexadecimal bytes.")
    if len(normalized) > TAG_UID_MAX_LENGTH:
        raise ValueError(f"A tag UID can be at most {TAG_UID_MAX_LENGTH} hex characters.")
    return normalized


def normalize_tag_format(value: str | None) -> str | None:
    """Normalize an informational tag format without restricting future formats."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if len(normalized) > TAG_FORMAT_MAX_LENGTH:
        raise ValueError(f"A tag format can be at most {TAG_FORMAT_MAX_LENGTH} characters.")
    return normalized


def parse_happy_hare_tag_list(value: object) -> list[str]:
    """Decode Happy Hare's JSON-string, comma-separated RFID compatibility field."""
    if value is None or value == "":
        return []
    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            decoded = value
    if isinstance(decoded, str):
        candidates = decoded.split(",")
    elif isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
        candidates = decoded
    else:
        raise ValueError("RFID tag data must be a string or a list of strings.")

    normalized: list[str] = []
    for candidate in candidates:
        if not candidate.strip():
            continue
        uid = normalize_tag_uid(candidate)
        if uid not in normalized:
            normalized.append(uid)
    return normalized


def happy_hare_tag_value(uids: list[str]) -> str:
    """Encode canonical UIDs in the exact Spoolman extra-field shape HH consumes."""
    return json.dumps(",".join(uids))

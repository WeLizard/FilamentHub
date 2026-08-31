"""Canonical tag identity normalization is shared by every adapter."""

import pytest

from app.core.tag_identity import (
    happy_hare_tag_value,
    normalize_tag_format,
    normalize_tag_uid,
    parse_happy_hare_tag_list,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("04:a1-b2 c3", "04A1B2C3"),
        ("0x01020304", "01020304"),
        ("AA_BB.CC-DD", "AABBCCDD"),
    ],
)
def test_uid_normalization_is_provider_neutral(raw: str, expected: str) -> None:
    assert normalize_tag_uid(raw) == expected


@pytest.mark.parametrize("raw", ["", "ABC", "tag-1", "00" * 33])
def test_uid_normalization_rejects_ambiguous_or_malformed_values(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_tag_uid(raw)


def test_happy_hare_compatibility_projection_round_trips_without_becoming_authority() -> None:
    decoded = parse_happy_hare_tag_list('"04A1B2C3, 01020304,04:a1:b2:c3"')
    assert decoded == ["04A1B2C3", "01020304"]
    assert happy_hare_tag_value(decoded) == '"04A1B2C3,01020304"'
    assert normalize_tag_format(" NTAG-215 ") == "ntag-215"


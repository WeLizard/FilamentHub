"""Text normalization and matching for verifying quoted manufacturer statements."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_PUNCTUATION = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "′": "'",
        "´": "'",
        "`": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "″": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "­": None,
        "​": None,
        "‌": None,
        "‍": None,
        "﻿": None,
    }
)
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d{1,2}(?!\d))")
MIN_QUOTE_CHARS = 20
_NUMBER = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\d)")
_WORD = re.compile(r"[^\W\d_]{3,}")
_LEADING_QUOTE = re.compile(r"^\s*(?:\"([^\"]+)\"|“([^”]+)”|«([^»]+)»)")


def normalize_text(text: str) -> str:
    """Fold case, whitespace (including NBSP), compatibility forms, quotes, dashes and
    decimal commas (``1,75`` reads as ``1.75``; ``1,000`` is left alone)."""
    text = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION).casefold()
    return _DECIMAL_COMMA.sub(".", " ".join(text.split()))


def squash(normalized: str) -> str:
    """Drop all whitespace, for pages whose inline markup splits words and numbers."""
    return "".join(normalized.split())


def _bounded_find(haystack: str, needle: str) -> bool:
    """Substring search that never cuts a number: ``75`` is not inside ``175`` or ``1.75``."""
    start = 0
    while (index := haystack.find(needle, start)) != -1:
        end = index + len(needle)
        left_ok = True
        if needle[0].isdigit() and index > 0:
            before = haystack[index - 1]
            left_ok = not before.isdigit() and not (
                before in ".," and index > 1 and haystack[index - 2].isdigit()
            )
        right_ok = True
        if needle[-1].isdigit() and end < len(haystack):
            after = haystack[end]
            right_ok = not after.isdigit() and not (
                after in ".," and end + 1 < len(haystack) and haystack[end + 1].isdigit()
            )
        if left_ok and right_ok:
            return True
        start = index + 1
    return False


def contains_text(page_normalized: str, page_squashed: str, fragment: str) -> bool:
    needle = normalize_text(fragment)
    if not needle:
        return False
    return _bounded_find(page_normalized, needle) or _bounded_find(page_squashed, squash(needle))


def quote_long_enough(quote: str) -> bool:
    return len(normalize_text(quote)) >= MIN_QUOTE_CHARS


def canonical_number(token: str) -> str | None:
    """``1.75`` and ``1.750`` are the same number; ``200.0`` equals ``200``."""
    try:
        return format(Decimal(token).normalize(), "f")
    except InvalidOperation:
        return None


def _readings(token: str) -> set[str]:
    """Every plausible value of a written number.

    ``2,300`` groups thousands (2300); a single group could also be a decimal comma
    (2.3), and a list written without spaces (``200,210``) holds both parts, so
    every reading is accepted.
    """
    if "," not in token:
        number = canonical_number(token)
        return {number} if number else set()
    candidates = [token.replace(",", "")]
    if token.count(",") == 1:
        candidates += [token.replace(",", "."), *token.split(",")]
    return {number for item in candidates if (number := canonical_number(item))}


def number_alternatives(normalized: str) -> list[set[str]]:
    return [
        readings
        for token in _NUMBER.findall(normalized)
        if (readings := _readings(token))
    ]


def numbers_in(normalized: str) -> set[str]:
    return {number for readings in number_alternatives(normalized) for number in readings}


def numbers_present(claimed: str, quote: str) -> bool:
    """Every number written in ``claimed`` appears as a whole number in ``quote``.

    A claim without numbers has nothing to compare and passes; callers that need a
    comparison for text use ``words_present``.
    """
    available = numbers_in(normalize_text(quote))
    return all(readings & available for readings in number_alternatives(normalize_text(claimed)))


def has_numbers(text: str) -> bool:
    return bool(number_alternatives(normalize_text(text)))


def number_present(value: int | float, quote: str) -> bool:
    number = canonical_number(str(value))
    return number is not None and number in numbers_in(normalize_text(quote))


def _words(normalized: str) -> set[str]:
    return set(_WORD.findall(normalized))


def words_present(claimed: str, quote: str) -> bool:
    """At least half of the claim's words (3+ letters) occur in the quote."""
    wanted = _words(normalize_text(claimed))
    if not wanted:
        return False
    found = wanted & _words(normalize_text(quote))
    return len(found) * 2 >= len(wanted)


def text_present(value: str, quote: str) -> bool:
    quote_normalized = normalize_text(quote)
    return contains_text(quote_normalized, squash(quote_normalized), value)


def leading_quote(explanation: str | None) -> str | None:
    """The quoted fragment that legacy proposals put at the start of ``explanation``."""
    if not explanation:
        return None
    match = _LEADING_QUOTE.match(explanation)
    if match is None:
        return None
    fragment = next(group for group in match.groups() if group is not None).strip()
    return fragment[:500] or None

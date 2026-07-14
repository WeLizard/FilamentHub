"""Utilities for generating and ensuring unique slugs."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeMeta

_CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "і": "i",
        "ї": "yi",
        "є": "ye",
        "ґ": "g",
        "ў": "u",
    }
)


def _slugify(value: str, fallback: str) -> str:
    """
    Convert text to a filesystem/web friendly slug.

    Args:
        value: Source text.
        fallback: Fallback slug when value becomes empty after normalization.

    Returns:
        Slug string composed of lowercase latin chars, numbers and dashes.
    """
    transliterated = value.casefold().translate(_CYRILLIC_TRANSLITERATION)
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_encoded = normalized.encode("ascii", "ignore").decode("ascii")
    value_ascii = ascii_encoded.lower()
    value_ascii = re.sub(r"[^a-z0-9]+", "-", value_ascii)
    value_ascii = value_ascii.strip("-")
    if not value_ascii:
        return fallback
    return value_ascii


async def generate_unique_slug(
    *,
    db: AsyncSession,
    model: DeclarativeMeta,
    source: str,
    fallback: str,
    exclude_id: int | None = None,
) -> str:
    """
    Generate a unique slug for the specified SQLAlchemy model.

    Args:
        db: AsyncSession for DB interaction.
        model: SQLAlchemy model having ``slug`` column.
        source: Source text used to derive slug.
        fallback: Fallback slug if source becomes empty after normalization.
        exclude_id: Optional primary key to exclude from uniqueness check (updates).

    Returns:
        Unique slug string.
    """
    base_slug = _slugify(source, fallback)
    slug_candidate = base_slug
    counter = 1

    while True:
        stmt: Select = select(model).where(model.slug == slug_candidate)
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            return slug_candidate
        counter += 1
        slug_candidate = f"{base_slug}-{counter}"

"""Recognise catalog records that describe the same brand or product."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_slug_redirect import BrandSlugRedirect

# One typo is a duplicate only when the name is long enough for a single
# changed letter not to produce a different real brand ("U3" vs "U4").
_TYPO_MIN_KEY_LENGTH = 5


def comparable_name(value: str | None) -> str:
    """Name reduced to letters and digits.

    Catches the same product written differently: `PLA-Black`, `PLA Black` and
    `pla  black` are one product, and a spelling difference must not be enough
    to create a second catalog record.
    """
    if not value:
        return ""
    return "".join(char for char in value.lower() if char.isalnum())


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def same_filament_color(
    existing_color_name: str | None,
    existing_color_hex: str | None,
    new_color_name: str | None,
    new_color_hex: str | None,
) -> bool:
    # Цвет — часть идентичности материала.
    # Приоритет: текстовое имя цвета; HEX используется только когда name отсутствует с обеих сторон.
    existing_name = _normalize_text(existing_color_name)
    incoming_name = _normalize_text(new_color_name)
    if existing_name or incoming_name:
        return existing_name == incoming_name

    existing_hex = _normalize_text(existing_color_hex)
    incoming_hex = _normalize_text(new_color_hex)
    if existing_hex or incoming_hex:
        return existing_hex == incoming_hex

    return True


def same_filament_kind(
    left_material_type: str,
    left_diameter: float,
    right_material_type: str,
    right_diameter: float,
) -> bool:
    """Whether two records could be one product at all."""
    return (
        left_material_type.strip().casefold() == right_material_type.strip().casefold()
        and left_diameter == right_diameter
    )


def brand_name_key(value: str) -> str:
    """Spelling-insensitive brand key: `Bambu Lab` and `BambuLabs` match."""
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    key = "".join(char for char in normalized if char.isalnum())
    if len(key) > _TYPO_MIN_KEY_LENGTH and key.endswith("s"):
        key = key[:-1]
    return key


def _within_one_edit(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    index = 0
    while index < len(left) and left[index] == right[index]:
        index += 1
    # "SeedBrand 0001" and "SeedBrand 0002" are numbered siblings, not typos.
    if right[index].isdigit() or (index < len(left) and left[index].isdigit()):
        return False
    if len(left) == len(right):
        return left[index + 1 :] == right[index + 1 :]
    return left[index:] == right[index + 1 :]


def brand_keys_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) < _TYPO_MIN_KEY_LENGTH:
        return False
    return _within_one_edit(left, right)


def _neighbourhood(key: str) -> set[str]:
    """Keys within one deletion; two keys one edit apart always share one."""
    variants = {key}
    if len(key) >= _TYPO_MIN_KEY_LENGTH:
        variants.update(key[:index] + key[index + 1 :] for index in range(len(key)))
    return variants


@dataclass(frozen=True)
class BrandIdentity:
    id: int
    name: str
    slug: str
    verified: bool


async def _brand_identities(db: AsyncSession) -> tuple[list[BrandIdentity], dict[str, set[int]]]:
    rows = await db.execute(select(Brand.id, Brand.name, Brand.slug, Brand.verified))
    brands = [BrandIdentity(*row) for row in rows]
    keys: dict[str, set[int]] = {}
    for brand in brands:
        keys.setdefault(brand_name_key(brand.name), set()).add(brand.id)
        keys.setdefault(brand_name_key(brand.slug), set()).add(brand.id)
    aliases = await db.execute(select(BrandSlugRedirect.old_slug, BrandSlugRedirect.brand_id))
    for old_slug, brand_id in aliases:
        if not old_slug.isdecimal():
            keys.setdefault(brand_name_key(old_slug), set()).add(brand_id)
    return brands, keys


async def find_similar_brands(
    db: AsyncSession,
    name: str,
    *,
    exclude_brand_id: int | None = None,
) -> list[BrandIdentity]:
    """Existing brands whose name, slug or former slug looks like ``name``."""
    wanted = brand_name_key(name)
    if not wanted:
        return []
    brands, keys = await _brand_identities(db)
    matched: set[int] = set()
    for key, brand_ids in keys.items():
        if brand_keys_similar(wanted, key):
            matched.update(brand_ids)
    if exclude_brand_id is not None:
        matched.discard(exclude_brand_id)
    return sorted(
        (brand for brand in brands if brand.id in matched),
        key=lambda brand: (not brand.verified, brand.name.casefold()),
    )


async def find_duplicate_brand_pairs(db: AsyncSession) -> list[tuple[BrandIdentity, BrandIdentity]]:
    """Pairs of current brands that look like one brand spelled differently."""
    brands = (await _brand_identities(db))[0]
    by_id = {brand.id: brand for brand in brands}
    brand_key = {brand.id: brand_name_key(brand.name) for brand in brands}
    buckets: dict[str, set[int]] = {}
    for brand_id, key in brand_key.items():
        for variant in _neighbourhood(key):
            buckets.setdefault(variant, set()).add(brand_id)

    pairs: set[tuple[int, int]] = set()
    for brand_ids in buckets.values():
        ordered = sorted(brand_ids)
        for position, left in enumerate(ordered):
            for right in ordered[position + 1 :]:
                if brand_keys_similar(brand_key[left], brand_key[right]):
                    pairs.add((left, right))
    return [(by_id[left], by_id[right]) for left, right in sorted(pairs)]

"""Canonical creation, lookup and rename rules for public brand slugs."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_slug_redirect import BrandSlugRedirect
from app.services.slug_service import slugify

BRAND_SLUG_MAX_LENGTH = 100
_BRAND_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def canonicalize_brand_slug(value: str) -> str | None:
    """Normalize a requested slug and reject unusable or ambiguous results."""
    raw = value.strip()
    if not raw:
        return None
    canonical = slugify(raw, "")
    if (
        not canonical
        or len(canonical) > BRAND_SLUG_MAX_LENGTH
        or canonical.isdecimal()
        or not _BRAND_SLUG_PATTERN.fullmatch(canonical)
    ):
        return None
    return canonical


async def brand_slug_available(
    db: AsyncSession,
    slug: str,
    *,
    exclude_brand_id: int | None = None,
) -> bool:
    """Return whether a current or historical slug can be assigned."""
    current_stmt = select(Brand.id).where(Brand.slug == slug)
    if exclude_brand_id is not None:
        current_stmt = current_stmt.where(Brand.id != exclude_brand_id)
    if await db.scalar(current_stmt) is not None:
        return False

    alias = await db.scalar(
        select(BrandSlugRedirect).where(BrandSlugRedirect.old_slug == slug)
    )
    return alias is None or alias.brand_id == exclude_brand_id


async def suggest_brand_slug(
    db: AsyncSession,
    source: str,
    *,
    exclude_brand_id: int | None = None,
) -> str:
    """Generate a unique brand slug while reserving historical aliases."""
    base = slugify(source, "brand")[:BRAND_SLUG_MAX_LENGTH].strip("-") or "brand"
    if base.isdecimal():
        base = f"brand-{base}"
    candidate = base
    counter = 1
    while not await brand_slug_available(
        db, candidate, exclude_brand_id=exclude_brand_id
    ):
        counter += 1
        suffix = f"-{counter}"
        candidate = f"{base[: BRAND_SLUG_MAX_LENGTH - len(suffix)].rstrip('-')}{suffix}"
    return candidate


async def choose_brand_slug(
    db: AsyncSession,
    *,
    name: str,
    requested_slug: str | None,
    exclude_brand_id: int | None = None,
) -> tuple[str | None, bool]:
    """Return ``(slug, available)`` for a custom slug or a server suggestion."""
    if requested_slug and requested_slug.strip():
        canonical = canonicalize_brand_slug(requested_slug)
        if canonical is None:
            return None, False
        return canonical, await brand_slug_available(
            db, canonical, exclude_brand_id=exclude_brand_id
        )
    return await suggest_brand_slug(
        db, name, exclude_brand_id=exclude_brand_id
    ), True


async def resolve_brand_identifier(
    db: AsyncSession,
    identifier: str,
) -> tuple[Brand | None, str | None]:
    """Resolve an ID, current slug or old slug; return the alias used, if any."""
    normalized = identifier.strip().casefold()
    if not normalized:
        return None, None

    if normalized.isdecimal():
        brand = await db.get(Brand, int(normalized))
        if brand is not None:
            return brand, None

    brand = await db.scalar(select(Brand).where(Brand.slug == normalized))
    if brand is not None:
        return brand, None

    alias = await db.scalar(
        select(BrandSlugRedirect).where(BrandSlugRedirect.old_slug == normalized)
    )
    if alias is None:
        return None, None
    return await db.get(Brand, alias.brand_id), alias.old_slug


async def apply_brand_slug_rename(
    db: AsyncSession,
    *,
    brand: Brand,
    new_slug: str,
) -> None:
    """Change a slug while preserving every previously published URL."""
    if new_slug == brand.slug:
        return

    reusable_alias = await db.scalar(
        select(BrandSlugRedirect).where(BrandSlugRedirect.old_slug == new_slug)
    )
    if reusable_alias is not None and reusable_alias.brand_id == brand.id:
        await db.delete(reusable_alias)

    existing_old_alias = await db.scalar(
        select(BrandSlugRedirect).where(BrandSlugRedirect.old_slug == brand.slug)
    )
    if existing_old_alias is None:
        db.add(BrandSlugRedirect(brand_id=brand.id, old_slug=brand.slug))
    elif existing_old_alias.brand_id != brand.id:
        # Defensive cleanup is intentionally not attempted: inconsistent
        # historical ownership must fail loudly rather than redirect elsewhere.
        raise ValueError("Current brand slug is reserved by another redirect")

    brand.slug = new_slug

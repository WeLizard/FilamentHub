"""Stable public URL rules for brands and exact catalog filament variants."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_slug_redirect import FilamentSlugRedirect
from app.services.brand_slug_service import resolve_brand_identifier
from app.services.slug_service import slugify

FILAMENT_SLUG_MAX_LENGTH = 200


@dataclass(frozen=True)
class ResolvedFilament:
    filament: Filament
    brand: Brand
    used_legacy_identifier: bool


def filament_slug_source(name: str, color_name: str | None) -> str:
    """Describe an exact variant without deriving identity from its HEX colour."""
    clean_name = name.strip()
    clean_color = (color_name or "").strip()
    if not clean_color:
        return clean_name

    name_slug = slugify(clean_name, "")
    color_slug = slugify(clean_color, "")
    if color_slug and color_slug in name_slug.split("-"):
        return clean_name
    if color_slug and name_slug.endswith(f"-{color_slug}"):
        return clean_name
    return f"{clean_name} {clean_color}"


async def filament_slug_available(
    db: AsyncSession,
    *,
    brand_id: int,
    slug: str,
    exclude_filament_id: int | None = None,
) -> bool:
    """Return whether a current or historical per-brand slug is free."""
    current = select(Filament.id).where(
        Filament.brand_id == brand_id,
        Filament.slug == slug,
    )
    if exclude_filament_id is not None:
        current = current.where(Filament.id != exclude_filament_id)
    if await db.scalar(current) is not None:
        return False

    alias = await db.scalar(
        select(FilamentSlugRedirect).where(
            FilamentSlugRedirect.brand_id == brand_id,
            FilamentSlugRedirect.old_slug == slug,
        )
    )
    return alias is None or alias.filament_id == exclude_filament_id


async def choose_filament_slug(
    db: AsyncSession,
    *,
    brand_id: int,
    name: str,
    color_name: str | None,
    ral_code: str | None = None,
) -> str | None:
    """Choose an unambiguous stable slug; never invent an opaque numeric suffix."""
    base = slugify(filament_slug_source(name, color_name), "filament")
    base = base[:FILAMENT_SLUG_MAX_LENGTH].strip("-") or "filament"
    if await filament_slug_available(db, brand_id=brand_id, slug=base):
        return base

    clean_ral = (ral_code or "").strip()
    if clean_ral and f"ral-{clean_ral}" not in base:
        suffix = f"-ral-{clean_ral}"
        candidate = f"{base[: FILAMENT_SLUG_MAX_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        if await filament_slug_available(db, brand_id=brand_id, slug=candidate):
            return candidate
    return None


async def resolve_filament_identifier(
    db: AsyncSession,
    *,
    brand_identifier: str,
    filament_identifier: str,
) -> ResolvedFilament | None:
    """Resolve current or historical brand/filament identifiers."""
    brand, brand_alias = await resolve_brand_identifier(db, brand_identifier)
    if brand is None:
        return None

    normalized = filament_identifier.strip().casefold()
    if not normalized:
        return None

    if normalized.isdecimal():
        filament = await db.get(Filament, int(normalized))
        if filament is not None and filament.brand_id == brand.id:
            return ResolvedFilament(filament, brand, True)

    filament = await db.scalar(
        select(Filament).where(
            Filament.brand_id == brand.id,
            Filament.slug == normalized,
        )
    )
    if filament is not None:
        return ResolvedFilament(filament, brand, brand_alias is not None)

    alias = await db.scalar(
        select(FilamentSlugRedirect).where(
            FilamentSlugRedirect.brand_id == brand.id,
            FilamentSlugRedirect.old_slug == normalized,
        )
    )
    if alias is None:
        return None
    filament = await db.get(Filament, alias.filament_id)
    if filament is None or filament.brand_id != brand.id:
        return None
    return ResolvedFilament(filament, brand, True)


async def apply_filament_slug_rename(
    db: AsyncSession,
    *,
    filament: Filament,
    new_slug: str,
) -> None:
    """Rename a published slug while preserving every previous public URL."""
    if new_slug == filament.slug:
        return
    if not await filament_slug_available(
        db,
        brand_id=filament.brand_id,
        slug=new_slug,
        exclude_filament_id=filament.id,
    ):
        raise ValueError("Filament slug is already reserved")

    reusable = await db.scalar(
        select(FilamentSlugRedirect).where(
            FilamentSlugRedirect.brand_id == filament.brand_id,
            FilamentSlugRedirect.old_slug == new_slug,
        )
    )
    if reusable is not None and reusable.filament_id == filament.id:
        await db.delete(reusable)

    old_alias = await db.scalar(
        select(FilamentSlugRedirect).where(
            FilamentSlugRedirect.brand_id == filament.brand_id,
            FilamentSlugRedirect.old_slug == filament.slug,
        )
    )
    if old_alias is None:
        db.add(
            FilamentSlugRedirect(
                filament_id=filament.id,
                brand_id=filament.brand_id,
                old_slug=filament.slug,
                reason="rename",
            )
        )
    elif old_alias.filament_id != filament.id:
        raise ValueError("Current filament slug is reserved by another redirect")
    filament.slug = new_slug


def brand_public_path(brand: Brand) -> str:
    return f"/brands/{brand.slug}"


def filament_public_path(filament: Filament, brand: Brand) -> str:
    return f"{brand_public_path(brand)}/filaments/{filament.slug}"


def localized_public_path(path: str, locale: str | None) -> str:
    """English is unprefixed; Russian and Chinese use stable prefixes."""
    return f"/{locale}{path}" if locale in {"ru", "zh"} else path

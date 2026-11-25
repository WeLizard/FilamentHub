"""Colour variants of one catalogue material.

A catalogue material is sold in colours, and every colour is its own Filament
row. Two rows are colours of one material when they share the brand, material
type and diameter and either belong to the same FilamentLine or, where a line
is not set, carry the same product name. One SQL condition is the only
definition, so the list a person picks from and the check of their choice
cannot disagree.
"""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.filament import Filament

# Diameters are typed by hand; 1.75 and 1.750001 are one diameter.
_DIAMETER_TOLERANCE_MM = 0.01
COLOR_VARIANTS_LIMIT = 200


def _product_name(value: str | None) -> str:
    return (value or "").strip().lower()


def color_variant_condition(filament: Filament) -> ColumnElement[bool]:
    """Rows that are another colour of ``filament``'s material."""
    same_name = func.lower(func.trim(Filament.name)) == _product_name(filament.name)
    if filament.line_id is not None:
        same_product = or_(
            Filament.line_id == filament.line_id,
            and_(Filament.line_id.is_(None), same_name),
        )
    else:
        same_product = same_name
    return and_(
        Filament.id != filament.id,
        Filament.brand_id == filament.brand_id,
        Filament.material_type == filament.material_type,
        func.abs(Filament.diameter - filament.diameter) < _DIAMETER_TOLERANCE_MM,
        same_product,
    )


async def list_color_variants(
    db: AsyncSession, filament: Filament, *, limit: int = COLOR_VARIANTS_LIMIT
) -> list[Filament]:
    """Other active colours of the material, in colour-name order."""
    rows = await db.scalars(
        select(Filament)
        .where(color_variant_condition(filament), Filament.active.is_(True))
        .order_by(
            Filament.color_name.is_(None),
            func.lower(Filament.color_name),
            Filament.id,
        )
        .limit(limit)
    )
    return list(rows)


async def is_color_variant(db: AsyncSession, filament: Filament, candidate_id: int) -> bool:
    """Whether ``candidate_id`` is another colour of ``filament``'s material."""
    return await is_color_variant_of_any(db, [filament], candidate_id)


async def is_color_variant_of_any(
    db: AsyncSession, filaments: list[Filament], candidate_id: int
) -> bool:
    """Whether ``candidate_id`` is another colour of any of these materials."""
    if not filaments:
        return False
    found = await db.scalar(
        select(Filament.id).where(
            or_(*(color_variant_condition(filament) for filament in filaments)),
            Filament.id == candidate_id,
        )
    )
    return found is not None

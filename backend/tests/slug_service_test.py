"""Tests for shared slug generation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.services.slug_service import generate_unique_slug


@pytest.mark.asyncio
async def test_generate_unique_slug_transliterates_cyrillic(db_session: AsyncSession) -> None:
    slug = await generate_unique_slug(
        db=db_session,
        model=Brand,
        source="НИТ",
        fallback="brand",
    )

    assert slug == "nit"


@pytest.mark.asyncio
async def test_generate_unique_slug_transliterates_mixed_brand_name(
    db_session: AsyncSession,
) -> None:
    slug = await generate_unique_slug(
        db=db_session,
        model=Brand,
        source="ООО «ПК НИТ»",
        fallback="brand",
    )

    assert slug == "ooo-pk-nit"


@pytest.mark.asyncio
async def test_generate_unique_slug_suffixes_transliterated_collision(
    db_session: AsyncSession,
) -> None:
    db_session.add(Brand(name="NIT", slug="nit", active=True))
    await db_session.commit()

    slug = await generate_unique_slug(
        db=db_session,
        model=Brand,
        source="НИТ",
        fallback="brand",
    )

    assert slug == "nit-2"

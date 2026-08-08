"""Выдача территориального права по одобренной заявке или приглашению.

Оба входа ведут к одной сущности: источник хранится для аудита и никаких
дополнительных возможностей не даёт.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.organization import OrganizationMembership
from app.models.user import User


async def _organization_of(db: AsyncSession, user: User, brand: Brand) -> int | None:
    """Организация, от имени которой человек работает с этим брендом."""
    if brand.organization_id is not None:
        own = await db.scalar(
            select(OrganizationMembership.organization_id).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == brand.organization_id,
                OrganizationMembership.active.is_(True),
            )
        )
        if own is not None:
            return own

    return await db.scalar(
        select(OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.active.is_(True),
        )
        .order_by(OrganizationMembership.id.desc())
        .limit(1)
    )


async def issue_territorial_grant(
    db: AsyncSession,
    *,
    brand: Brand,
    user: User,
    country: str | None,
    source: GrantSource,
    approved_by_id: int | None,
    organization_id: int | None = None,
) -> BrandTerritorialGrant | None:
    """Дать организации человека право вести бренд в стране.

    Повторное одобрение той же пары не плодит второе право, а оживляет прежнее:
    отозванное когда-то представительство возвращается тем же решением.

    Организацию можно назвать прямо: человек может состоять и в организации
    головного офиса, и тогда угадывание привязало бы право к ней.
    """
    if organization_id is None:
        organization_id = await _organization_of(db, user, brand)
    if organization_id is None:
        return None

    normalized = country.upper() if country else None
    existing = await db.scalar(
        select(BrandTerritorialGrant).where(
            BrandTerritorialGrant.brand_id == brand.id,
            BrandTerritorialGrant.organization_id == organization_id,
            BrandTerritorialGrant.country.is_(None)
            if normalized is None
            else BrandTerritorialGrant.country == normalized,
        )
    )

    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.status = GrantStatus.active
        existing.revoked_at = None
        existing.approved_by_id = approved_by_id
        existing.approved_at = now
        return existing

    grant = BrandTerritorialGrant(
        brand_id=brand.id,
        organization_id=organization_id,
        country=normalized,
        status=GrantStatus.active,
        source=source,
        approved_by_id=approved_by_id,
        approved_at=now,
    )
    db.add(grant)
    return grant

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
from app.models.organization import (
    Organization,
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.user import User, UserRole
from app.services.slug_service import generate_unique_slug


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


async def _organization_of_own(db: AsyncSession, user: User) -> Organization | None:
    """Организация, которой человек владеет сам."""
    return await db.scalar(
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.active.is_(True),
            OrganizationMembership.role == OrganizationMemberRole.OWNER,
            Organization.active.is_(True),
        )
        .order_by(Organization.id)
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


async def settle_territorial_application(
    db: AsyncSession,
    *,
    brand: Brand,
    user: User,
    country: str,
    organization_name: str | None,
    approved_by_id: int | None,
) -> BrandTerritorialGrant | None:
    """Одобрить заявку организации на одну страну существующего бренда.

    Заявитель получает своё рабочее пространство, а не членство в организации,
    уже работающей с этим брендом: организации вокруг бренда независимы, и
    занятость бренда чужой компанией на заявку не влияет.
    """
    organization = await _organization_of_own(db, user)
    if organization is None:
        organization = Organization(
            name=(organization_name or f"{brand.name} {country.upper()}").strip(),
            slug=await generate_unique_slug(
                db=db,
                model=Organization,
                source=organization_name or f"{brand.name}-{country}",
                fallback="organization",
            ),
            created_by_id=user.id,
            active=True,
        )
        db.add(organization)
        await db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationMemberRole.OWNER,
                all_brands=False,
                active=True,
            )
        )
        await db.flush()

    access = await db.scalar(
        select(OrganizationBrandAccess)
        .join(
            OrganizationMembership,
            OrganizationMembership.id == OrganizationBrandAccess.membership_id,
        )
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
            OrganizationBrandAccess.brand_id == brand.id,
        )
    )
    if access is None:
        membership_id = await db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
        )
        if membership_id is not None:
            db.add(OrganizationBrandAccess(membership_id=membership_id, brand_id=brand.id))

    # Тот же паритет, что и у остальных входов: без активного бренда и роли
    # человеку некуда прийти работать.
    user.brand_id = brand.id
    user.active_organization_id = organization.id
    if user.role == UserRole.USER:
        user.role = UserRole.BRAND

    return await issue_territorial_grant(
        db,
        brand=brand,
        user=user,
        country=country,
        source=GrantSource.application,
        approved_by_id=approved_by_id,
        organization_id=organization.id,
    )

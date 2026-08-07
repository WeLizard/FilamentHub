"""Кто и что может менять в бренде по своей территории.

Один бренд, одни и те же филаменты, несколько официальных представителей: у
каждого своя страна и своя часть данных. Правило простое и проверяется на
сервере: править можно ячейку своей области, чужую нельзя, общий слой закрыт,
пока его не открыли отдельно.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_territorial_grant import BrandTerritorialGrant, GrantStatus
from app.models.organization import OrganizationMembership
from app.models.user import User, UserRole


async def active_grants_for(
    db: AsyncSession, user: User, brand_id: int
) -> list[BrandTerritorialGrant]:
    """Действующие права человека на бренд — через его организации."""
    grants = await db.scalars(
        select(BrandTerritorialGrant)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == BrandTerritorialGrant.organization_id,
        )
        .where(
            BrandTerritorialGrant.brand_id == brand_id,
            BrandTerritorialGrant.status == GrantStatus.active,
            BrandTerritorialGrant.revoked_at.is_(None),
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.active.is_(True),
        )
    )
    return list(grants)


def _covers(grant: BrandTerritorialGrant, country: str | None) -> bool:
    """Глобальное право покрывает любую страну, страновое — только свою."""
    if grant.country is None:
        return True
    if country is None:
        return False
    return grant.country == country.upper()


async def can_manage_brand_country(
    db: AsyncSession, user: User, brand_id: int, country: str
) -> bool:
    """Вести региональную витрину бренда в этой стране."""
    if user.role == UserRole.ADMIN:
        return True
    return any(
        grant.manage_brand_country and _covers(grant, country)
        for grant in await active_grants_for(db, user, brand_id)
    )


async def can_manage_filament_country(
    db: AsyncSession, user: User, brand_id: int, country: str
) -> bool:
    """Вести рыночные сведения о товаре в этой стране."""
    if user.role == UserRole.ADMIN:
        return True
    return any(
        grant.manage_filament_country and _covers(grant, country)
        for grant in await active_grants_for(db, user, brand_id)
    )


async def can_edit_brand_common(db: AsyncSession, user: User, brand_id: int) -> bool:
    """Менять общие данные бренда — имя, логотип, сайт.

    Региональному представителю это закрыто: бренд один на все страны, и
    переписывать его из одной страны нельзя.
    """
    if user.role == UserRole.ADMIN:
        return True
    return any(
        grant.edit_brand_common for grant in await active_grants_for(db, user, brand_id)
    )


async def can_edit_filament_common(
    db: AsyncSession, user: User, brand_id: int, created_by_id: int | None = None
) -> bool:
    """Менять общие свойства товара — те, что одинаковы во всех странах.

    Создатель правит созданное им; всё остальное требует отдельного права.
    """
    if user.role == UserRole.ADMIN:
        return True

    grants = await active_grants_for(db, user, brand_id)
    if any(grant.edit_all_filaments_common for grant in grants):
        return True
    if created_by_id is not None and created_by_id == user.id:
        return any(grant.edit_own_created_filaments for grant in grants)
    return False


async def countries_user_manages(db: AsyncSession, user: User, brand_id: int) -> list[str | None]:
    """Области, которые человек ведёт. `None` в списке означает глобальную."""
    return [grant.country for grant in await active_grants_for(db, user, brand_id)]


async def organizations_with_grant(
    db: AsyncSession, brand_id: int, country: str | None
) -> list[int]:
    """Организации, ведущие бренд в этой стране, включая глобальных."""
    scope = BrandTerritorialGrant.country.is_(None)
    if country is not None:
        scope = or_(scope, BrandTerritorialGrant.country == country.upper())

    rows = await db.scalars(
        select(BrandTerritorialGrant.organization_id).where(
            BrandTerritorialGrant.brand_id == brand_id,
            BrandTerritorialGrant.status == GrantStatus.active,
            BrandTerritorialGrant.revoked_at.is_(None),
            scope,
        )
    )
    return sorted(set(rows))

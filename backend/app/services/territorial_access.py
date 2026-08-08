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
    """Действующие права человека на бренд.

    Один бренд бывает доступен через несколько организаций сразу. Если человек
    выбрал, от какой действует, берутся права только этой: иначе он получил бы
    объединение полномочий разных компаний, не действуя ни от одной.
    """
    query = (
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
    if user.active_organization_id is None:
        return []
    query = query.where(
        BrandTerritorialGrant.organization_id == user.active_organization_id
    )
    return list(await db.scalars(query))


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
    db: AsyncSession,
    user: User,
    brand_id: int,
    contributed_by_organization_id: int | None = None,
) -> bool:
    """Менять общие свойства товара — те, что одинаковы во всех странах.

    Provenance explains who contributed a catalog record but does not own it.
    Common technical data is managed through an explicit global capability;
    territorial organizations enrich their country cell instead.
    """
    del contributed_by_organization_id
    if user.role == UserRole.ADMIN:
        return True

    grants = await active_grants_for(db, user, brand_id)
    return any(grant.edit_all_filaments_common for grant in grants)


async def can_create_for_brand(db: AsyncSession, user: User, brand_id: int) -> bool:
    """Заводить записи каталога от имени организации.

    Обычное пользовательское добавление недостающей позиции этим правом не
    ограничено: каталог открыт. Здесь речь о работе от имени компании —
    импорте, линейках с палитрами и синхронизации.
    """
    if user.role == UserRole.ADMIN:
        return True
    return any(
        grant.create_filaments for grant in await active_grants_for(db, user, brand_id)
    )


async def _draft_scope(
    db: AsyncSession, user: User | None, brand_id: int, capability: str
) -> tuple[bool, set[str]]:
    if user is None:
        return False, set()
    if user.role == UserRole.ADMIN:
        return True, set()

    grants = [
        grant
        for grant in await active_grants_for(db, user, brand_id)
        if getattr(grant, capability)
    ]
    if any(grant.country is None for grant in grants):
        return True, set()
    return False, {grant.country for grant in grants if grant.country}


async def brand_drafts_visible_to(
    db: AsyncSession, user: User | None, brand_id: int
) -> tuple[bool, set[str]]:
    """Чьи неопубликованные витрины бренда человек вправе видеть.

    Свою ячейку нужно читать и до публикации, иначе её нельзя ни доделать, ни
    опубликовать позже. Первое значение означает «все страны».
    """
    return await _draft_scope(db, user, brand_id, "manage_brand_country")


async def filament_drafts_visible_to(
    db: AsyncSession, user: User | None, brand_id: int
) -> tuple[bool, set[str]]:
    """То же для рыночных сведений о товаре."""
    return await _draft_scope(db, user, brand_id, "manage_filament_country")


async def can_invite_representative(db: AsyncSession, user: User, brand_id: int) -> bool:
    """Позвать независимую организацию получить право на страну.

    Приглашает организация с глобальным правом либо администратор площадки.
    Региональная организация территориальных прав другим не выдаёт: она ведёт
    только свою команду. Родства между организациями это не создаёт.
    """
    if user.role == UserRole.ADMIN:
        return True
    return any(
        grant.country is None for grant in await active_grants_for(db, user, brand_id)
    )


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

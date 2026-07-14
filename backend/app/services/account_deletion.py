"""Сервис для удаления аккаунта пользователя с обработкой связанных данных."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_OWNERSHIP_TRANSFER_REQUIRED,
    ERR_REPRESENTATION_RELEASE_REQUIRED,
    raise_error,
)
from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus
from app.models.filament_review import FilamentReview
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User, UserRole
from app.models.user_saved_preset import UserSavedPreset


async def get_deletion_stats(user_id: int, db: AsyncSession) -> dict:
    """
    Получить статистику данных пользователя перед удалением аккаунта.

    Returns:
        dict: Статистика данных пользователя
    """
    # Количество пресетов пользователя
    presets_result = await db.execute(
        select(func.count(Preset.id)).where(Preset.user_id == user_id)
    )
    presets_count = presets_result.scalar() or 0

    # Количество официальных пресетов
    official_result = await db.execute(
        select(func.count(Preset.id)).where(
            and_(Preset.user_id == user_id, Preset.is_official == True)
        )
    )
    official_presets_count = official_result.scalar() or 0

    # Количество одобренных пресетов
    approved_result = await db.execute(
        select(func.count(Preset.id)).where(
            and_(
                Preset.user_id == user_id,
                Preset.moderation_status == PresetModerationStatus.APPROVED
            )
        )
    )
    approved_presets_count = approved_result.scalar() or 0

    # Количество пресетов, сохраненных другими пользователями
    presets_used_result = await db.execute(
        select(func.count(func.distinct(UserSavedPreset.preset_id)))
        .join(Preset, UserSavedPreset.preset_id == Preset.id)
        .where(
            and_(
                Preset.user_id == user_id,
                UserSavedPreset.user_id != user_id
            )
        )
    )
    presets_used_by_others_count = presets_used_result.scalar() or 0

    # Количество отзывов
    reviews_result = await db.execute(
        select(func.count(FilamentReview.id)).where(FilamentReview.user_id == user_id)
    )
    reviews_count = reviews_result.scalar() or 0

    # Количество сохраненных пресетов (личные закладки)
    saved_presets_result = await db.execute(
        select(func.count(UserSavedPreset.id)).where(UserSavedPreset.user_id == user_id)
    )
    saved_presets_count = saved_presets_result.scalar() or 0

    # Количество заявок на верификацию бренда
    brand_requests_result = await db.execute(
        select(func.count(BrandRequest.id)).where(BrandRequest.user_id == user_id)
    )
    brand_requests_count = brand_requests_result.scalar() or 0

    memberships = (
        await db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.active.is_(True),
            )
        )
    ).all()
    is_brand_representative = bool(memberships)
    organization_memberships_count = len(memberships)
    owned_organizations_count = sum(
        membership.role == OrganizationMemberRole.OWNER for membership in memberships
    )
    sole_owner_organizations_count = 0
    transfer_required = False
    brand_other_representatives_count = 0
    for membership in memberships:
        other_members = int(
            await db.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.active.is_(True),
                    OrganizationMembership.id != membership.id,
                )
            )
            or 0
        )
        brand_other_representatives_count += other_members
        if membership.role == OrganizationMemberRole.OWNER:
            other_owners = int(
                await db.scalar(
                    select(func.count(OrganizationMembership.id)).where(
                        OrganizationMembership.organization_id == membership.organization_id,
                        OrganizationMembership.active.is_(True),
                        OrganizationMembership.role == OrganizationMemberRole.OWNER,
                        OrganizationMembership.id != membership.id,
                    )
                )
                or 0
            )
            if other_owners == 0:
                sole_owner_organizations_count += 1
                transfer_required = transfer_required or other_members > 0

    return {
        "presets_count": presets_count,
        "official_presets_count": official_presets_count,
        "approved_presets_count": approved_presets_count,
        "presets_used_by_others_count": presets_used_by_others_count,
        "reviews_count": reviews_count,
        "saved_presets_count": saved_presets_count,
        "brand_requests_count": brand_requests_count,
        "is_brand_representative": is_brand_representative,
        "brand_other_representatives_count": brand_other_representatives_count,
        "organization_memberships_count": organization_memberships_count,
        "owned_organizations_count": owned_organizations_count,
        "sole_owner_organizations_count": sole_owner_organizations_count,
        "ownership_transfer_required": transfer_required,
        "representation_release_available": (
            sole_owner_organizations_count > 0 and not transfer_required
        ),
    }


async def delete_user_account(
    user: User,
    delete_reviews: bool,
    release_brand_representation: bool,
    db: AsyncSession,
) -> None:
    """
    Удалить аккаунт пользователя с обработкой связанных данных.

    Args:
        user: Пользователь для удаления
        delete_reviews: True - удалить отзывы полностью, False - анонимизировать
        release_brand_representation: снять официальное представительство у организаций,
            где пользователь является единственным участником-owner
        db: Сессия базы данных
    """
    user_id = user.id

    memberships = (
        await db.scalars(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.active.is_(True),
            )
        )
    ).all()
    organization_ids = sorted({membership.organization_id for membership in memberships})
    if organization_ids:
        # Serialize deletion with role changes/transfers so two owners cannot
        # concurrently leave the same organization without a successor.
        await db.execute(
            select(Organization.id)
            .where(Organization.id.in_(organization_ids))
            .order_by(Organization.id)
            .with_for_update()
        )
        memberships = (
            await db.scalars(
                select(OrganizationMembership)
                .where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.active.is_(True),
                )
                .order_by(OrganizationMembership.organization_id)
                .with_for_update()
            )
        ).all()
    release_organization_ids: set[int] = set()
    for membership in memberships:
        if membership.role != OrganizationMemberRole.OWNER:
            continue
        other_owners = int(
            await db.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.active.is_(True),
                    OrganizationMembership.role == OrganizationMemberRole.OWNER,
                    OrganizationMembership.id != membership.id,
                )
            )
            or 0
        )
        if other_owners > 0:
            continue
        other_members = int(
            await db.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.active.is_(True),
                    OrganizationMembership.id != membership.id,
                )
            )
            or 0
        )
        if other_members > 0:
            raise_error(409, ERR_OWNERSHIP_TRANSFER_REQUIRED)
        if not release_brand_representation:
            raise_error(409, ERR_REPRESENTATION_RELEASE_REQUIRED)
        release_organization_ids.add(membership.organization_id)

    # 1. Обработка пресетов
    presets_result = await db.execute(
        select(Preset)
        .where(Preset.user_id == user_id)
        .options(selectinload(Preset.saved_by_users))
    )
    presets = presets_result.scalars().all()

    for preset in presets:
        # Всегда сохраняем официальные пресеты - анонимизируем
        if preset.is_official:
            preset.user_id = None

        # Одобренные пресеты, используемые другими - анонимизируем
        elif preset.moderation_status == PresetModerationStatus.APPROVED:
            # Проверяем, используется ли пресет другими
            saved_count = len([sp for sp in preset.saved_by_users if sp.user_id != user_id])
            if saved_count > 0 or preset.usage_count > 0:
                preset.user_id = None
            else:
                # Можно удалить, если не используется - анонимизируем для безопасности
                preset.user_id = None

        # Неодобренные/отклоненные пресеты - помечаем как неактивные и анонимизируем
        else:
            preset.active = False
            preset.user_id = None

    # 2. Обработка отзывов
    reviews_result = await db.execute(
        select(FilamentReview).where(FilamentReview.user_id == user_id)
    )
    reviews = reviews_result.scalars().all()

    if delete_reviews:
        # Полностью удаляем отзывы
        for review in reviews:
            review.active = False
            # Можно полностью удалить через delete, но лучше пометить как неактивный
            # для возможного восстановления
            await db.delete(review)
    else:
        # Анонимизируем отзывы - помечаем как неактивные и скрываем пользователя
        # user_id оставляем (NOT NULL constraint), но помечаем review.active = False
        # И можно изменить comment на "Отзыв от удалённого пользователя"
        for review in reviews:
            review.active = False
            if review.comment:
                review.comment = f"[Отзыв от удалённого пользователя] {review.comment}"

    # 3. Удаление личных закладок (UserSavedPresets)
    saved_presets_result = await db.execute(
        select(UserSavedPreset).where(UserSavedPreset.user_id == user_id)
    )
    saved_presets = saved_presets_result.scalars().all()
    for saved_preset in saved_presets:
        await db.delete(saved_preset)

    # 4. Обработка заявок на верификацию бренда
    brand_requests_result = await db.execute(
        select(BrandRequest).where(BrandRequest.user_id == user_id)
    )
    brand_requests = brand_requests_result.scalars().all()
    for request in brand_requests:
        # Удаляем pending/rejected заявки
        if request.status in [BrandRequestStatus.PENDING, BrandRequestStatus.REJECTED]:
            await db.delete(request)
        # Одобренные заявки оставляем для истории (можно добавить флаг archived)

    # 5. Membership lifecycle. Public brands and their catalog content are
    # never deleted with an account. Explicit release only removes the
    # official verified status; existing QR identifiers stay untouched.
    if release_organization_ids:
        release_brands = (
            await db.scalars(
                select(Brand).where(Brand.organization_id.in_(release_organization_ids))
            )
        ).all()
        for brand in release_brands:
            brand.verified = False
    for membership in memberships:
        membership.active = False
    user.brand_id = None
    if user.role == UserRole.BRAND:
        user.role = UserRole.USER

    # 6. Деактивация аккаунта (мягкое удаление)
    # Устанавливаем active=False вместо полного удаления
    # Это позволит восстановить аккаунт при необходимости
    user.active = False
    # Очищаем чувствительные данные
    user.email = f"deleted_{user_id}_{user.email}"
    user.username = f"deleted_{user_id}_{user.username}"
    user.api_key = None
    user.password_hash = ""  # Очищаем пароль

    await db.commit()

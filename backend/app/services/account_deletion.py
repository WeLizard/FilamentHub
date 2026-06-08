"""Сервис для удаления аккаунта пользователя с обработкой связанных данных."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus
from app.models.filament_review import FilamentReview
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
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

    # Проверка, является ли пользователь представителем бренда
    user_result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.presets))
    )
    user = user_result.scalar_one_or_none()

    is_brand_representative = user.brand_id is not None if user else False
    brand_other_representatives_count = 0

    if is_brand_representative and user:
        # Подсчет других представителей бренда
        other_reps_result = await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.brand_id == user.brand_id,
                    User.id != user_id,
                    User.active == True
                )
            )
        )
        brand_other_representatives_count = other_reps_result.scalar() or 0

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
    }


async def delete_user_account(
    user: User,
    delete_reviews: bool,
    delete_brand_if_sole_representative: bool,
    db: AsyncSession,
) -> None:
    """
    Удалить аккаунт пользователя с обработкой связанных данных.

    Args:
        user: Пользователь для удаления
        delete_reviews: True - удалить отзывы полностью, False - анонимизировать
        delete_brand_if_sole_representative: True - удалить бренд, если единственный представитель,
            False - передать админу
        db: Сессия базы данных
    """
    user_id = user.id

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

    # 5. Обработка связи с брендом
    if user.brand_id:
        # Проверяем, есть ли другие активные представители
        other_reps_result = await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.brand_id == user.brand_id,
                    User.id != user_id,
                    User.active == True
                )
            )
        )
        other_reps_count = other_reps_result.scalar() or 0

        if other_reps_count == 0:
            # Единственный представитель
            if delete_brand_if_sole_representative:
                # Удаляем бренд (cascade удалит все связанные филаменты)
                brand_result = await db.execute(
                    select(Brand).where(Brand.id == user.brand_id)
                )
                brand = brand_result.scalar_one_or_none()
                if brand:
                    await db.delete(brand)
            else:
                # Передаем админу - оставляем бренд, но отвязываем пользователя
                # Можно добавить флаг в Brand: managed_by_admin
                pass

        # Отвязываем пользователя от бренда (роль не меняем)
        user.brand_id = None

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


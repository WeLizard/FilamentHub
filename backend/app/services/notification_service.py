"""Сервис для создания и управления уведомлениями."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.user_saved_preset import UserSavedPreset


async def create_notification(
    user_id: int,
    notification_type: NotificationType,
    title: str,
    message: str,
    db: AsyncSession,
    link: str | None = None,
    extra_data: dict | None = None,
) -> Notification:
    """
    Создать уведомление для пользователя.
    
    Args:
        user_id: ID пользователя
        notification_type: Тип уведомления
        title: Заголовок уведомления
        message: Текст уведомления
        db: Database session
        link: Ссылка на связанную сущность (опционально)
        extra_data: Дополнительные данные в формате JSON (опционально)
    
    Returns:
        Созданное уведомление
    """
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        link=link,
        extra_data=extra_data,
        read=False,
    )
    
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    
    return notification


async def notify_preset_updated(
    preset_id: int,
    preset_name: str,
    filament_id: int,
    db: AsyncSession,
) -> None:
    """
    Создать уведомления для всех пользователей, у которых сохранен этот пресет.
    
    Args:
        preset_id: ID пресета
        preset_name: Название пресета
        filament_id: ID филамента
        db: Database session
    """
    # Находим всех пользователей, у которых сохранен этот пресет
    result = await db.execute(
        select(UserSavedPreset.user_id)
        .where(UserSavedPreset.preset_id == preset_id)
        .distinct()
    )
    user_ids = result.scalars().all()
    
    # Создаем уведомления для каждого пользователя
    for user_id in user_ids:
        await create_notification(
            user_id=user_id,
            notification_type=NotificationType.PRESET_UPDATED,
            title="Пресет обновлен",
            message=f'Пресет "{preset_name}" был обновлен. Проверьте новые настройки.',
            db=db,
            link=f"/filaments/{filament_id}",
            extra_data={"preset_id": preset_id, "filament_id": filament_id},
        )


async def notify_preset_deleted(
    preset_id: int,
    preset_name: str,
    filament_id: int,
    db: AsyncSession,
) -> None:
    """
    Создать уведомления для всех пользователей, у которых сохранен этот пресет.
    
    Args:
        preset_id: ID пресета
        preset_name: Название пресета
        filament_id: ID филамента
        db: Database session
    """
    # Находим всех пользователей, у которых сохранен этот пресет
    result = await db.execute(
        select(UserSavedPreset.user_id)
        .where(UserSavedPreset.preset_id == preset_id)
        .distinct()
    )
    user_ids = result.scalars().all()
    
    # Создаем уведомления для каждого пользователя
    for user_id in user_ids:
        await create_notification(
            user_id=user_id,
            notification_type=NotificationType.PRESET_DELETED,
            title="Пресет удален",
            message=f'Пресет "{preset_name}" был удален из каталога.',
            db=db,
            link=f"/filaments/{filament_id}",
            extra_data={"preset_id": preset_id, "filament_id": filament_id},
        )


async def notify_brand_verified(
    user_id: int,
    brand_name: str,
    brand_id: int,
    db: AsyncSession,
) -> None:
    """
    Создать уведомление об одобрении верификации бренда.
    
    Args:
        user_id: ID пользователя (владельца бренда)
        brand_name: Название бренда
        brand_id: ID бренда
        db: Database session
    """
    await create_notification(
        user_id=user_id,
        notification_type=NotificationType.BRAND_VERIFIED,
        title="Бренд верифицирован",
        message=f'Ваш бренд "{brand_name}" успешно верифицирован! Теперь вы можете создавать официальные пресеты и генерировать QR-коды.',
        db=db,
        link=f"/brands/{brand_id}",
        extra_data={"brand_id": brand_id},
    )


async def notify_brand_request_approved(
    user_id: int,
    brand_name: str,
    brand_id: int,
    db: AsyncSession,
) -> None:
    """
    Создать уведомление об одобрении заявки на бренд.
    
    Args:
        user_id: ID пользователя
        brand_name: Название бренда
        brand_id: ID бренда
        db: Database session
    """
    await create_notification(
        user_id=user_id,
        notification_type=NotificationType.BRAND_REQUEST_APPROVED,
        title="Заявка на бренд одобрена",
        message=f'Ваша заявка на присоединение к бренду "{brand_name}" была одобрена.',
        db=db,
        link=f"/brands/{brand_id}",
        extra_data={"brand_id": brand_id},
    )


async def notify_brand_request_rejected(
    user_id: int,
    brand_name: str,
    reason: str | None,
    db: AsyncSession,
) -> None:
    """
    Создать уведомление об отклонении заявки на бренд.
    
    Args:
        user_id: ID пользователя
        brand_name: Название бренда
        reason: Причина отклонения (опционально)
        db: Database session
    """
    message = f'Ваша заявка на присоединение к бренду "{brand_name}" была отклонена.'
    if reason:
        message += f" Причина: {reason}"
    
    await create_notification(
        user_id=user_id,
        notification_type=NotificationType.BRAND_REQUEST_REJECTED,
        title="Заявка на бренд отклонена",
        message=message,
        db=db,
        extra_data={"brand_name": brand_name, "reason": reason},
    )


async def create_bulk_notifications(
    user_ids: list[int],
    notification_type: NotificationType,
    title: str,
    message: str,
    db: AsyncSession,
    link: str | None = None,
    extra_data: dict | None = None,
) -> int:
    """
    Создать массовые уведомления для списка пользователей.
    
    Args:
        user_ids: Список ID пользователей
        notification_type: Тип уведомления
        title: Заголовок уведомления
        message: Текст уведомления
        db: Database session
        link: Ссылка на связанную сущность (опционально)
        extra_data: Дополнительные данные в формате JSON (опционально)
    
    Returns:
        Количество созданных уведомлений
    """
    if not user_ids:
        return 0
    
    notifications = []
    for user_id in user_ids:
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            link=link,
            extra_data=extra_data,
            read=False,
        )
        notifications.append(notification)
    
    db.add_all(notifications)
    await db.commit()
    
    return len(notifications)


async def notify_all_users(
    notification_type: NotificationType,
    title: str,
    message: str,
    db: AsyncSession,
    link: str | None = None,
    extra_data: dict | None = None,
    active_only: bool = True,
) -> int:
    """
    Создать уведомления для всех пользователей (массовая рассылка).
    
    Args:
        notification_type: Тип уведомления
        title: Заголовок уведомления
        message: Текст уведомления
        db: Database session
        link: Ссылка на связанную сущность (опционально)
        extra_data: Дополнительные данные в формате JSON (опционально)
        active_only: Отправлять только активным пользователям (по умолчанию True)
    
    Returns:
        Количество созданных уведомлений
    """
    from app.models.user import User
    
    query = select(User.id)
    if active_only:
        query = query.where(User.active == True)
    
    result = await db.execute(query)
    user_ids = result.scalars().all()
    
    if not user_ids:
        return 0
    
    return await create_bulk_notifications(
        user_ids=list(user_ids),
        notification_type=notification_type,
        title=title,
        message=message,
        db=db,
        link=link,
        extra_data=extra_data,
    )

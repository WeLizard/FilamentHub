"""Сервис для работы с OrcaSlicer интеграцией (удалённые пресеты, правила пользователя)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.preset import Preset
from app.models.user_saved_preset import UserSavedPreset


async def get_user_deleted_preset_rule(
    user_id: int,
    db: AsyncSession,
) -> str:
    """
    Получить правило обработки удалённых пресетов для пользователя.
    
    Args:
        user_id: ID пользователя
        db: Database session
    
    Returns:
        Правило обработки удалённых пресетов ("always_restore", "always_delete", "always_ask", etc.)
        По умолчанию возвращает "always_ask"
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return "always_ask"  # По умолчанию
    
    return user.deleted_preset_rule or "always_ask"


async def save_user_deleted_preset_rule(
    user_id: int,
    rule: str,
    db: AsyncSession,
) -> None:
    """
    Сохранить правило обработки удалённых пресетов для пользователя.
    
    Args:
        user_id: ID пользователя
        rule: Правило обработки ("always_restore", "always_delete", "always_ask", etc.)
        db: Database session
    
    Raises:
        ValueError: Если пользователь не найден
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    # Валидация правила
    valid_rules = [
        "always_restore",
        "always_delete",
        "always_ask",
        "restore_created_delete_saved",
        "restore_created_ask_saved",
    ]
    if rule not in valid_rules:
        raise ValueError(f"Invalid rule: {rule}. Valid rules: {valid_rules}")
    
    user.deleted_preset_rule = rule
    await db.commit()
    await db.refresh(user)


async def remove_saved_preset(
    user_id: int,
    preset_id: int,
    db: AsyncSession,
) -> None:
    """
    Удалить сохранённый пресет из "Мои пресеты" (убрать из избранного).
    
    Args:
        user_id: ID пользователя
        preset_id: ID пресета
        db: Database session
    """
    result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user_id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()
    
    if saved_preset:
        await db.delete(saved_preset)
        await db.commit()


async def is_preset_created_by_user(
    user_id: int,
    preset_id: int,
    db: AsyncSession,
) -> bool:
    """
    Проверить, создан ли пресет пользователем.
    
    Args:
        user_id: ID пользователя
        preset_id: ID пресета
        db: Database session
    
    Returns:
        True, если пресет создан пользователем, False иначе
    """
    result = await db.execute(
        select(Preset).where(
            Preset.id == preset_id,
            Preset.user_id == user_id,
        )
    )
    preset = result.scalar_one_or_none()
    
    return preset is not None


async def is_preset_saved_by_user(
    user_id: int,
    preset_id: int,
    db: AsyncSession,
) -> bool:
    """
    Проверить, сохранён ли пресет пользователем (добавлен в избранное).
    
    Args:
        user_id: ID пользователя
        preset_id: ID пресета
        db: Database session
    
    Returns:
        True, если пресет сохранён пользователем, False иначе
    """
    result = await db.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user_id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_preset = result.scalar_one_or_none()
    
    return saved_preset is not None


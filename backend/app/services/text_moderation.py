"""Универсальный сервис модерации текстовых полей."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.preset_moderation import validate_text_field


async def validate_multiple_text_fields(
    db: AsyncSession, **fields: str | None
) -> tuple[bool, str | None]:
    """
    Проверить несколько текстовых полей одновременно.

    Args:
        db: Сессия БД
        **fields: Словарь {field_name: value} - название поля и его значение

    Returns:
        (is_valid, error_message): (True, None) если всё ок, (False, message) если найдены проблемы

    Example:
        is_valid, error = await validate_multiple_text_fields(
            db,
            name="Название материала",
            description="Описание материала",
            color_name="Красный"
        )
    """
    for field_name, field_value in fields.items():
        if field_value is not None:
            is_valid, reason = await validate_text_field(field_value, db, field_name)
            if not is_valid:
                return False, reason

    return True, None


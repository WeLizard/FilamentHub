"""Service for managing maintenance mode."""

from typing import Optional

# In-memory storage for maintenance mode
# В production можно заменить на Redis
_maintenance_mode: bool = False
_maintenance_message: Optional[str] = None


def get_maintenance_mode() -> bool:
    """Получить текущее состояние режима технических работ."""
    return _maintenance_mode


def set_maintenance_mode(enabled: bool, message: Optional[str] = None) -> None:
    """
    Установить режим технических работ.
    
    Args:
        enabled: Включить или выключить технические работы
        message: Сообщение для пользователей (опционально)
    """
    global _maintenance_mode, _maintenance_message
    _maintenance_mode = enabled
    _maintenance_message = message


def get_maintenance_message() -> Optional[str]:
    """Получить сообщение о технических работах."""
    return _maintenance_message


def get_maintenance_info() -> dict:
    """Получить полную информацию о режиме технических работ."""
    return {
        "enabled": _maintenance_mode,
        "message": _maintenance_message or "Сайт временно недоступен. Ведутся технические работы.",
    }


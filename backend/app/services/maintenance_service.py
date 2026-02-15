"""Service for managing maintenance mode."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Файл для хранения состояния технических работ (доступен всем воркерам)
# Используем директорию uploads, которая монтируется как volume
MAINTENANCE_FILE = Path("/app/uploads/.maintenance.json")


def _read_maintenance_file() -> tuple[bool, Optional[str]]:
    """Читает состояние технических работ из файла."""
    try:
        if MAINTENANCE_FILE.exists():
            with open(MAINTENANCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("enabled", False), data.get("message")
    except Exception:
        logger.warning("Failed to read maintenance file", exc_info=True)
    return False, None


def _write_maintenance_file(enabled: bool, message: Optional[str] = None) -> None:
    """Записывает состояние технических работ в файл."""
    try:
        MAINTENANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MAINTENANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled, "message": message}, f, ensure_ascii=False)
    except Exception:
        logger.warning("Failed to write maintenance file", exc_info=True)


def get_maintenance_mode() -> bool:
    """Получить текущее состояние режима технических работ."""
    enabled, _ = _read_maintenance_file()
    return enabled


def set_maintenance_mode(enabled: bool, message: Optional[str] = None) -> None:
    """
    Установить режим технических работ.
    
    Args:
        enabled: Включить или выключить технические работы
        message: Сообщение для пользователей (опционально)
    """
    _write_maintenance_file(enabled, message)


def get_maintenance_message() -> Optional[str]:
    """Получить сообщение о технических работах."""
    _, message = _read_maintenance_file()
    return message


def get_maintenance_info() -> dict:
    """Получить полную информацию о режиме технических работ."""
    enabled, message = _read_maintenance_file()
    return {
        "enabled": enabled,
        "message": message or "Сайт временно недоступен. Ведутся технические работы.",
    }


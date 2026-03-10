"""File upload service for brand requests."""

import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import UploadFile, HTTPException, status

from app.core.config import settings
from app.core.errors import (
    ERR_FILE_EXT_NOT_ALLOWED,
    ERR_FILE_SAVE_FAILED,
    ERR_FILE_SIZE_EXCEEDED,
    ERR_INVALID_FILE_PATH,
    ERR_MAX_FILES_EXCEEDED,
    raise_error,
)

logger = logging.getLogger(__name__)


def get_upload_root_dir() -> Path:
    """Canonical uploads root directory mounted by FastAPI StaticFiles."""
    return Path(__file__).resolve().parents[2] / settings.UPLOAD_DIR


def get_legacy_app_upload_root_dir() -> Path:
    """Legacy uploads root accidentally used by some endpoints."""
    return Path(__file__).resolve().parents[1] / settings.UPLOAD_DIR


def ensure_upload_dir_compatibility() -> None:
    """
    Copy files from the legacy app-local uploads directory into the canonical uploads
    directory if they are missing there.

    This keeps already uploaded files accessible after path fixes without deleting
    anything from the legacy location.
    """
    canonical_dir = get_upload_root_dir()
    canonical_dir.mkdir(parents=True, exist_ok=True)

    legacy_dir = get_legacy_app_upload_root_dir()
    if not legacy_dir.exists():
        return

    try:
        if canonical_dir.resolve() == legacy_dir.resolve():
            return
    except OSError:
        return

    copied_files = 0

    for source_path in legacy_dir.rglob("*"):
        if not source_path.is_file():
            continue

        relative_path = source_path.relative_to(legacy_dir)
        destination_path = canonical_dir / relative_path
        if destination_path.exists():
            continue

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        copied_files += 1

    if copied_files > 0:
        logger.info(
            "Copied %s legacy upload files from %s to %s",
            copied_files,
            legacy_dir,
            canonical_dir,
        )


def get_allowed_extensions() -> list[str]:
    """Получить список разрешенных расширений файлов."""
    return settings.ALLOWED_PROOF_FILE_EXTENSIONS


def validate_file(file: UploadFile) -> None:
    """Валидация загружаемого файла."""
    if not file.filename:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_FILE_EXT_NOT_ALLOWED, {"ext": "", "allowed": ", ".join(get_allowed_extensions())})

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in get_allowed_extensions():
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_FILE_EXT_NOT_ALLOWED, {"ext": file_ext, "allowed": ", ".join(get_allowed_extensions())})


async def save_proof_file(
    file: UploadFile,
    request_id: int,
    user_id: int,
    request_type: str = "brand",  # "brand" или "printer"
    existing_files: list[dict[str, str]] | None = None,  # Существующие файлы для проверки лимита
) -> dict[str, str]:
    """
    Сохранить файл подтверждающего документа для заявки на бренд или принтер.
    
    Args:
        file: Файл для загрузки
        request_id: ID заявки
        user_id: ID пользователя
        request_type: Тип заявки ("brand" или "printer")
        existing_files: Список существующих файлов для проверки лимита
    
    Returns:
        Путь к сохраненному файлу относительно корня проекта
    """
    validate_file(file)
    
    # Получаем оригинальное имя файла
    original_filename = file.filename or "unknown"
    
    # Проверяем количество файлов
    if existing_files is not None and len(existing_files) >= settings.MAX_FILES_PER_REQUEST:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_MAX_FILES_EXCEEDED, {"max": settings.MAX_FILES_PER_REQUEST})
    
    # Читаем содержимое файла
    file_content = await file.read()
    file_size_mb = len(file_content) / (1024 * 1024)
    
    # Проверяем размер файла
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_FILE_SIZE_EXCEEDED, {"size_mb": f"{file_size_mb:.2f}", "max_mb": str(settings.MAX_UPLOAD_SIZE_MB)})
    
    # Определяем директорию в зависимости от типа заявки
    if request_type == "printer":
        folder = "printer_requests"
    else:
        folder = "brand_requests"
    
    # Создаем директорию для заявки
    # Определяем базовую директорию: из app/services/ поднимаемся на 2 уровня вверх (к backend/)
    base_upload_dir = get_upload_root_dir()
    upload_dir = base_upload_dir / folder / str(request_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем уникальное имя файла
    file_ext = Path(file.filename).suffix.lower()
    file_name = f"{uuid.uuid4().hex}{file_ext}"
    file_path = (upload_dir / file_name).resolve()

    # Path traversal protection: убеждаемся, что файл остаётся внутри upload_dir
    if not str(file_path).startswith(str(upload_dir.resolve())):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILE_PATH)

    # Сохраняем файл (используем уже прочитанное содержимое)
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Проверяем, что файл действительно сохранился
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_FILE_SAVE_FAILED)
    
    # Возвращаем объект с путем и оригинальным именем
    relative_path = f"{folder}/{request_id}/{file_name}"
    return {
        "path": relative_path,
        "name": original_filename,
    }


def parse_proof_files(proof_files_str: str | None) -> list[dict[str, str]]:
    """
    Парсить JSON строку с файлами.
    Поддерживает как старый формат (массив строк) так и новый (массив объектов).
    Убирает дубликаты по пути файла.
    """
    if not proof_files_str:
        return []
    try:
        parsed = json.loads(proof_files_str)
        # Если это массив строк (старый формат), конвертируем в объекты
        if isinstance(parsed, list):
            result = []
            seen_paths = set()  # Для отслеживания уже добавленных путей
            for item in parsed:
                if isinstance(item, str):
                    # Старый формат: строка с путем
                    if item not in seen_paths:
                        seen_paths.add(item)
                        result.append({"path": item, "name": item.split("/")[-1]})
                elif isinstance(item, dict) and "path" in item:
                    # Новый формат: объект с путем и именем
                    path = item["path"]
                    if path not in seen_paths:
                        seen_paths.add(path)
                        result.append({"path": path, "name": item.get("name", path.split("/")[-1])})
            return result
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_proof_files(proof_files: list[dict[str, str]] | None) -> str | None:
    """Сериализовать список файлов (объектов с path и name) в JSON строку."""
    if not proof_files:
        return None
    return json.dumps(proof_files)


async def delete_proof_file(file_path: str) -> None:
    """Удалить файл подтверждающего документа."""
    # file_path может быть в формате "brand_requests/123/file.pdf" или объектом
    if isinstance(file_path, dict):
        file_path = file_path.get("path", "")
    
    # Используем абсолютный путь относительно корня проекта
    base_upload_dir = get_upload_root_dir()
    full_path = (base_upload_dir / file_path).resolve()

    # Path traversal protection
    if not str(full_path).startswith(str(base_upload_dir.resolve())):
        return

    if full_path.exists():
        full_path.unlink()
        
        # Удаляем пустые директории
        parent_dir = full_path.parent
        if parent_dir.exists() and not any(parent_dir.iterdir()):
            parent_dir.rmdir()


async def delete_proof_files(proof_files_str: str | None) -> None:
    """Удалить все файлы подтверждающих документов заявки."""
    files = parse_proof_files(proof_files_str)
    for file_info in files:
        await delete_proof_file(file_info.get("path", ""))


async def cleanup_old_files(
    cutoff_date: datetime | None = None,
    request_type: str | None = None,  # "brand", "printer" или None (оба)
) -> dict[str, int]:
    """
    Очистить старые файлы из директории uploads.
    
    Args:
        cutoff_date: Дата, до которой удалять файлы (по умолчанию: CLEANUP_FILES_AFTER_DAYS дней назад)
        request_type: Тип заявки для очистки ("brand", "printer" или None для обоих)
    
    Returns:
        Словарь с количеством удаленных файлов и освобожденным местом
    """
    if cutoff_date is None:
        cutoff_date = datetime.now() - timedelta(days=settings.CLEANUP_FILES_AFTER_DAYS)
    
    base_upload_dir = get_upload_root_dir()
    if not base_upload_dir.exists():
        return {"files_deleted": 0, "space_freed_mb": 0}
    
    folders_to_clean = []
    if request_type is None:
        folders_to_clean = ["brand_requests", "printer_requests"]
    elif request_type in ["brand", "printer"]:
        folders_to_clean = [f"{request_type}_requests"]
    
    files_deleted = 0
    space_freed_bytes = 0
    
    for folder_name in folders_to_clean:
        folder_path = base_upload_dir / folder_name
        if not folder_path.exists():
            continue
        
        # Проходим по всем поддиректориям (request_id)
        for request_dir in folder_path.iterdir():
            if not request_dir.is_dir():
                continue
            
            # Проходим по всем файлам в директории заявки
            for file_path in request_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                # Проверяем дату модификации файла
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_date:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    files_deleted += 1
                    space_freed_bytes += file_size
                    
                    # Удаляем пустые директории
                    if not any(request_dir.iterdir()):
                        request_dir.rmdir()
    
    space_freed_mb = round(space_freed_bytes / (1024 * 1024), 2)
    return {
        "files_deleted": files_deleted,
        "space_freed_mb": space_freed_mb,
    }

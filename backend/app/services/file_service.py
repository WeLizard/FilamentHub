"""File upload service for brand requests."""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import UploadFile, HTTPException, status

from app.core.config import settings


def get_allowed_extensions() -> list[str]:
    """Получить список разрешенных расширений файлов."""
    return settings.ALLOWED_PROOF_FILE_EXTENSIONS


def validate_file(file: UploadFile) -> None:
    """Валидация загружаемого файла."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in get_allowed_extensions():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension {file_ext} not allowed. Allowed extensions: {', '.join(get_allowed_extensions())}",
        )


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.MAX_FILES_PER_REQUEST} files per request allowed. Current: {len(existing_files)}",
        )
    
    # Читаем содержимое файла
    file_content = await file.read()
    file_size_mb = len(file_content) / (1024 * 1024)
    
    # Проверяем размер файла
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size {file_size_mb:.2f} MB exceeds maximum allowed size {settings.MAX_UPLOAD_SIZE_MB} MB",
        )
    
    # Определяем директорию в зависимости от типа заявки
    if request_type == "printer":
        folder = "printer_requests"
    else:
        folder = "brand_requests"
    
    # Создаем директорию для заявки
    # Определяем базовую директорию: из app/services/ поднимаемся на 2 уровня вверх (к backend/)
    base_upload_dir = Path(__file__).parent.parent.parent / settings.UPLOAD_DIR
    upload_dir = base_upload_dir / folder / str(request_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем уникальное имя файла
    file_ext = Path(file.filename).suffix.lower()
    file_name = f"{uuid.uuid4().hex}{file_ext}"
    file_path = (upload_dir / file_name).resolve()

    # Path traversal protection: убеждаемся, что файл остаётся внутри upload_dir
    if not str(file_path).startswith(str(upload_dir.resolve())):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
        )

    # Сохраняем файл (используем уже прочитанное содержимое)
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Проверяем, что файл действительно сохранился
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        )
    
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
    base_upload_dir = Path(__file__).parent.parent.parent / settings.UPLOAD_DIR
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
    
    base_upload_dir = Path(__file__).parent.parent.parent / settings.UPLOAD_DIR
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


"""Schemas for database management and migrations."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class MigrationStatus(BaseModel):
    """Статус одной миграции."""

    revision: str = Field(..., description="Ревизия миграции")
    down_revision: Optional[str] = Field(None, description="Предыдущая ревизия")
    branch_labels: Optional[str] = Field(None, description="Метки веток")
    is_head: bool = Field(False, description="Является ли головной миграцией")
    is_applied: bool = Field(False, description="Применена ли миграция")
    applied_at: Optional[str] = Field(None, description="Дата применения (ISO строка)")
    description: Optional[str] = Field(None, description="Описание миграции")


class MigrationHistoryResponse(BaseModel):
    """История миграций."""

    current_revision: Optional[str] = Field(None, description="Текущая применённая ревизия")
    heads: list[str] = Field(default_factory=list, description="Головные ревизии")
    migrations: list[MigrationStatus] = Field(default_factory=list, description="Список всех миграций")


class MigrationApplyRequest(BaseModel):
    """Запрос на применение миграции."""

    revision: str = Field(..., description="Ревизия для применения (например, 'head', '+1', '-1')")


class MigrationApplyResponse(BaseModel):
    """Ответ на применение миграции."""

    success: bool = Field(..., description="Успешно ли применена миграция")
    message: str = Field(..., description="Сообщение о результате")
    current_revision: Optional[str] = Field(None, description="Текущая ревизия после применения")
    validation_errors: Optional[list[str]] = Field(None, description="Ошибки валидации после применения (отсутствующие таблицы)")


class DatabaseIntegrityResponse(BaseModel):
    """Ответ на проверку целостности БД."""

    is_valid: bool = Field(..., description="Валидна ли структура БД")
    missing_tables: list[str] = Field(default_factory=list, description="Отсутствующие таблицы")
    message: str = Field(..., description="Сообщение о результате проверки")


class RecreateTablesResponse(BaseModel):
    """Ответ на восстановление таблиц."""

    success: bool = Field(..., description="Успешно ли восстановлены таблицы")
    message: str = Field(..., description="Сообщение о результате")
    created_tables: list[str] = Field(default_factory=list, description="Список созданных таблиц")


class DatabaseStatsResponse(BaseModel):
    """Статистика базы данных."""

    database_name: str = Field(..., description="Имя базы данных")
    database_size: str = Field(..., description="Размер базы данных (форматированный)")
    database_size_bytes: int = Field(..., description="Размер базы данных в байтах")
    table_stats: list[dict[str, Any]] = Field(default_factory=list, description="Статистика по таблицам")


class DatabaseExportRequest(BaseModel):
    """Запрос на экспорт базы данных."""

    format: str = Field("custom", description="Формат экспорта: custom, plain, tar (default: custom)")
    include_data: bool = Field(True, description="Включать ли данные (True) или только схему (False)")
    tables: Optional[list[str]] = Field(None, description="Список таблиц для экспорта (None = все)")


class DatabaseExportResponse(BaseModel):
    """Ответ на экспорт базы данных."""

    success: bool = Field(..., description="Успешно ли выполнен экспорт")
    filename: Optional[str] = Field(None, description="Имя файла дампа")
    download_url: Optional[str] = Field(None, description="URL для скачивания")
    size: Optional[int] = Field(None, description="Размер файла в байтах")
    message: str = Field(..., description="Сообщение о результате")


class DatabaseImportRequest(BaseModel):
    """Запрос на импорт базы данных."""

    format: str = Field("custom", description="Формат импорта: custom, plain, tar (default: custom)")
    clean: bool = Field(False, description="Очистить базу перед импортом (--clean)")
    create: bool = Field(False, description="Создать базу если не существует (--create)")


class DatabaseImportResponse(BaseModel):
    """Ответ на импорт базы данных."""

    success: bool = Field(..., description="Успешно ли выполнен импорт")
    message: str = Field(..., description="Сообщение о результате")


class DatabaseDumpInfo(BaseModel):
    """Информация о дампе базы данных."""

    filename: str = Field(..., description="Имя файла")
    size: int = Field(..., description="Размер файла в байтах")
    created_at: str = Field(..., description="Дата создания (ISO format)")
    modified_at: str = Field(..., description="Дата изменения (ISO format)")
    format: str = Field(..., description="Формат дампа: custom, plain, tar")


class DatabaseDumpListResponse(BaseModel):
    """Список дампов базы данных."""

    dumps: list[DatabaseDumpInfo] = Field(default_factory=list, description="Список дампов")


class DatabaseDumpDeleteResponse(BaseModel):
    """Ответ на удаление дампа."""

    success: bool = Field(..., description="Успешно ли удалён дамп")
    message: str = Field(..., description="Сообщение о результате")


class TableColumnInfo(BaseModel):
    """Информация о колонке таблицы."""

    column_name: str = Field(..., description="Имя колонки")
    data_type: str = Field(..., description="Тип данных")
    is_nullable: bool = Field(..., description="Может ли быть NULL")
    column_default: Optional[str] = Field(None, description="Значение по умолчанию")
    character_maximum_length: Optional[int] = Field(None, description="Максимальная длина для строковых типов")


class TableStructureResponse(BaseModel):
    """Структура таблицы."""

    table_name: str = Field(..., description="Имя таблицы")
    schema_name: str = Field(..., description="Имя схемы")
    columns: list[TableColumnInfo] = Field(default_factory=list, description="Список колонок")
    indexes: list[dict[str, Any]] = Field(default_factory=list, description="Список индексов")
    constraints: list[dict[str, Any]] = Field(default_factory=list, description="Список ограничений")


class TableDataRequest(BaseModel):
    """Запрос на получение данных таблицы."""

    table_name: str = Field(..., description="Имя таблицы")
    schema_name: str = Field("public", description="Имя схемы")
    page: int = Field(1, ge=1, description="Номер страницы")
    size: int = Field(50, ge=1, le=1000, description="Размер страницы")
    order_by: Optional[str] = Field(None, description="Колонка для сортировки")
    order_desc: bool = Field(False, description="Сортировка по убыванию")
    search: Optional[str] = Field(None, description="Поиск по всем колонкам")


class TableDataResponse(BaseModel):
    """Данные таблицы."""

    table_name: str = Field(..., description="Имя таблицы")
    schema_name: str = Field(..., description="Имя схемы")
    columns: list[str] = Field(default_factory=list, description="Список колонок")
    rows: list[dict[str, Any]] = Field(default_factory=list, description="Строки данных")
    total: int = Field(..., description="Всего строк")
    page: int = Field(..., description="Текущая страница")
    size: int = Field(..., description="Размер страницы")
    pages: int = Field(..., description="Всего страниц")


class TableDataUpdateRequest(BaseModel):
    """Запрос на обновление данных таблицы."""

    primary_key: dict[str, Any] = Field(..., description="Значения первичного ключа для идентификации строки")
    data: dict[str, Any] = Field(..., description="Новые значения полей")


class MigrationStampRequest(BaseModel):
    """Запрос на пометку миграции как применённой (без выполнения)."""

    revision: str = Field(..., description="Ревизия для пометки (например, 'head' или конкретная ревизия)")


class MigrationStampResponse(BaseModel):
    """Ответ на пометку миграции."""

    success: bool = Field(..., description="Успешно ли помечена миграция")
    message: str = Field(..., description="Сообщение о результате")
    current_revision: Optional[str] = Field(None, description="Текущая ревизия после пометки")


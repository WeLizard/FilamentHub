"""Pydantic schemas for BrandRequest."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.brand_request import BrandRequestStatus, BrandRequestType


class BrandRequestBase(BaseModel):
    """Base schema for BrandRequest."""

    request_type: BrandRequestType
    message: str | None = Field(None, max_length=1000)
    proof_text: str | None = Field(None, max_length=2000, description="Описание подтверждающих документов для заявки (ссылки, документы, описание)")


class BrandRequestCreate(BaseModel):
    """Schema for creating BrandRequest."""

    request_type: BrandRequestType = Field(..., description="Тип заявки: join или create")
    brand_id: int | None = Field(None, gt=0, description="ID бренда (для JOIN заявок)")

    # Для CREATE заявок
    new_brand_name: str | None = Field(None, max_length=100)
    new_brand_slug: str | None = Field(None, max_length=100)
    new_brand_description: str | None = None
    new_brand_website: str | None = Field(None, max_length=255)

    message: str | None = Field(None, max_length=1000, description="Дополнительное сообщение")

    # Структурированные поля для доказательств
    company_email: str | None = Field(None, max_length=255, description="Email от компании (например: info@company.ru, manager@company.ru)")
    company_website: str | None = Field(None, max_length=500, description="Сайт компании/бренда (для проверки email на сайте)")
    social_media_urls: list[str] | None = Field(None, description="Ссылки на соцсети бренда (Instagram, VK, Facebook и т.д.)")

    proof_text: str | None = Field(
        None,
        max_length=2000,
        description="Описание подтверждающих документов (общее описание, дополнительные детали). Обязательно для CREATE заявок, необязательно для JOIN заявок."
    )
    proof_files: list[dict[str, str]] | None = Field(
        None,
        description="Список файлов с путем и оригинальным именем: [{'path': 'brand_requests/123/file.jpg', 'name': 'снимок.jpg'}]"
    )


class BrandRequestResponse(BaseModel):
    """Schema for BrandRequest response."""

    id: int
    user_id: int
    user_email: str | None = None  # Email пользователя для админки
    request_type: BrandRequestType
    brand_id: int | None = None
    brand_name: str | None = None  # Название бренда для JOIN заявок
    new_brand_name: str | None = None
    new_brand_slug: str | None = None
    new_brand_description: str | None = None
    new_brand_website: str | None = None
    message: str | None = None

    # Структурированные поля для доказательств
    company_email: str | None = None
    company_website: str | None = None
    social_media_urls: list[str] | None = None

    proof_text: str | None = None
    proof_files: list[dict[str, str]] | None = None
    status: BrandRequestStatus
    processed_by_id: int | None = None
    processed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator('proof_files', mode='before')
    @classmethod
    def parse_proof_files(cls, v):
        """
        Парсит JSON строку в список для proof_files.
        Конвертирует старый формат (массив строк) в новый (массив объектов).
        """
        if v is None:
            return None
        if isinstance(v, str):
            if not v.strip():
                return None
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    # Конвертируем старый формат (строки) в новый (объекты)
                    result = []
                    for item in parsed:
                        if isinstance(item, str):
                            # Старый формат: строка с путем
                            result.append({"path": item, "name": item.split("/")[-1]})
                        elif isinstance(item, dict) and "path" in item:
                            # Новый формат: объект с путем и именем
                            result.append({"path": item["path"], "name": item.get("name", item["path"].split("/")[-1])})
                    return result if result else None
                return None
            except (json.JSONDecodeError, TypeError):
                # Если не JSON, возвращаем None (некорректный формат)
                return None
        if isinstance(v, list):
            # Если уже список, конвертируем если нужно
            result = []
            for item in v:
                if isinstance(item, str):
                    # Старый формат: строка с путем
                    result.append({"path": item, "name": item.split("/")[-1]})
                elif isinstance(item, dict) and "path" in item:
                    # Новый формат: объект с путем и именем
                    result.append({"path": item["path"], "name": item.get("name", item["path"].split("/")[-1])})
            return result if result else None
        return None

    @field_validator('social_media_urls', mode='before')
    @classmethod
    def parse_social_media_urls(cls, v):
        """Парсит JSON строку в список для social_media_urls."""
        if v is None:
            return None
        if isinstance(v, str):
            if not v.strip():
                return None
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                return [parsed] if parsed else None
            except (json.JSONDecodeError, TypeError):
                # Если не JSON, возвращаем как есть (для обратной совместимости)
                return [v] if v else None
        if isinstance(v, list):
            return v
        return None


class BrandRequestListResponse(BaseModel):
    """Schema for list of BrandRequests."""

    items: list[BrandRequestResponse]
    total: int


class BrandRequestUpdate(BaseModel):
    """Schema for updating BrandRequest (admin only)."""

    status: BrandRequestStatus
    rejection_reason: str | None = None


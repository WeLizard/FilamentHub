"""Pydantic schemas for PrinterRequest."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.printer_request import PrinterRequestStatus


class PrinterRequestCreate(BaseModel):
    """Schema for creating PrinterRequest."""

    name: str = Field(..., min_length=1, max_length=200)
    manufacturer: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    
    # Optional printer specs
    build_volume_x: float | None = Field(None, ge=0)
    build_volume_y: float | None = Field(None, ge=0)
    build_volume_z: float | None = Field(None, ge=0)
    nozzle_diameter: float | None = Field(None, ge=0.1, le=2.0)
    max_extruder_temp: int | None = Field(None, ge=0, le=500)
    max_bed_temp: int | None = Field(None, ge=0, le=200)
    image_url: str | None = Field(None, max_length=500)
    
    message: str | None = Field(None, max_length=1000, description="Дополнительная информация о принтере")
    proof_files: list[str] | None = Field(
        None,
        description="Пути к загруженным файлам (скриншоты, изображения принтера) - заполняется автоматически после загрузки через отдельный эндпоинт"
    )


class PrinterRequestResponse(BaseModel):
    """Schema for PrinterRequest response."""

    id: int
    user_id: int
    user_email: str | None = None  # Email пользователя для админки
    name: str
    manufacturer: str
    model: str
    slug: str
    description: str | None = None
    build_volume_x: float | None = None
    build_volume_y: float | None = None
    build_volume_z: float | None = None
    nozzle_diameter: float | None = None
    max_extruder_temp: int | None = None
    max_bed_temp: int | None = None
    image_url: str | None = None
    message: str | None = None
    proof_files: list[str] | None = None
    status: PrinterRequestStatus
    processed_by_id: int | None = None
    processed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator('proof_files', mode='before')
    @classmethod
    def parse_proof_files(cls, v):
        """Парсит JSON строку в список для proof_files."""
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


class PrinterRequestListResponse(BaseModel):
    """Schema for list of PrinterRequests."""

    items: list[PrinterRequestResponse]
    total: int


class PrinterRequestUpdate(BaseModel):
    """Schema for updating PrinterRequest (admin only)."""

    status: PrinterRequestStatus
    rejection_reason: str | None = None


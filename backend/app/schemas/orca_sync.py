"""Schemas for OrcaSlicer synchronisation endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class OrcaSyncResult(BaseModel):
    """Single item sync result."""

    external_id: str | None = Field(
        default=None,
        description="Идентификатор профиля на стороне OrcaSlicer (если есть).",
    )
    fhub_id: int | None = Field(
        default=None,
        description="ID созданного или обновленного объекта в FilamentHub.",
    )
    status: Literal["created", "updated", "skipped", "error"]
    message: str | None = Field(default=None, description="Дополнительные детали по элементу.")


class OrcaPrinterProfilePayload(BaseModel):
    """Payload для импорта профилей принтера из OrcaSlicer."""

    external_id: str | None = Field(
        default=None, description="Уникальный ID профиля в OrcaSlicer (полезно для сопоставления)."
    )
    fhub_id: int | None = Field(
        default=None, ge=1, description="ID существующего профиля в FilamentHub (если обновляем)."
    )
    name: str = Field(..., max_length=200)
    slug: str | None = Field(
        default=None,
        max_length=200,
        description="Slug профиля. Если не передан, будет сгенерирован автоматически.",
    )
    description: str | None = Field(default=None, max_length=10_000)
    printer_id: int | None = Field(
        default=None, ge=1, description="ID принтера в FilamentHub, если уже существует."
    )
    printer_slug: str | None = Field(
        default=None,
        description="Slug принтера для автоматического сопоставления, если printer_id не указан.",
    )
    active: bool | None = Field(
        default=None,
        description="Включен ли профиль после импорта. По умолчанию черновик (False).",
    )
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    start_gcode: str | None = None
    end_gcode: str | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class PrinterProfileSyncRequest(BaseModel):
    """Запрос с профилями принтера для импорта/обновления."""

    profiles: list[OrcaPrinterProfilePayload]


class PrinterProfileSyncResponse(BaseModel):
    """Результат импорта профилей принтера."""

    results: list[OrcaSyncResult]


class OrcaPrintProfilePayload(BaseModel):
    """Payload для импорта профилей печати."""

    external_id: str | None = Field(default=None)
    fhub_id: int | None = Field(default=None, ge=1)
    name: str = Field(..., max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    category: str | None = Field(default=None, max_length=100)
    active: bool | None = Field(
        default=None,
        description="Флаг активности. По умолчанию импортируется как черновик (False).",
    )
    compatible_printers: list[str] | None = Field(
        default=None,
        description="Список slug или внутренних ID принтеров, совместимых с профилем.",
    )
    compatible_filaments: list[str] | None = Field(
        default=None,
        description="Список slug или внутренних ID материалов, совместимых с профилем.",
    )
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=10_000)


class PrintProfileSyncRequest(BaseModel):
    """Запрос на импорт профилей печати."""

    profiles: list[OrcaPrintProfilePayload]


class PrintProfileSyncResponse(BaseModel):
    """Результат импорта профилей печати."""

    results: list[OrcaSyncResult]



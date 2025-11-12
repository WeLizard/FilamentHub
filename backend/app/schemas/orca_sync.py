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
    source: str | None = Field(default=None, max_length=50)
    vendor: str | None = Field(default=None, max_length=100)
    setting_id: str | None = Field(default=None, max_length=100)
    default_print_profile_slug: str | None = Field(default=None, max_length=200)
    nozzle_diameters: list[float] | None = Field(default=None)
    printable_area: dict[str, Any] | None = Field(default=None)
    printable_height_mm: float | None = Field(default=None)
    extra_metadata: dict[str, Any] | None = Field(default=None)
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
    source: str | None = Field(default=None, max_length=50)
    vendor: str | None = Field(default=None, max_length=100)
    setting_id: str | None = Field(default=None, max_length=100)
    quality_tier: str | None = Field(default=None, max_length=50)
    default_nozzle: str | None = Field(default=None, max_length=20)
    layer_height_mm: float | None = Field(default=None)
    compatible_printers: list[str] | None = Field(
        default=None,
        description="Список slug или внутренних ID принтеров, совместимых с профилем.",
    )
    compatible_filaments: list[str] | None = Field(
        default=None,
        description="Список slug или внутренних ID материалов, совместимых с профилем.",
    )
    compatible_printers_condition: str | None = Field(default=None, description="Логические условия совместимости.")
    orcaslicer_settings: dict[str, Any] = Field(default_factory=dict)
    extra_metadata: dict[str, Any] | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=10_000)


class PrintProfileSyncRequest(BaseModel):
    """Запрос на импорт профилей печати."""

    profiles: list[OrcaPrintProfilePayload]


class PrintProfileSyncResponse(BaseModel):
    """Результат импорта профилей печати."""

    results: list[OrcaSyncResult]


class DeletedPresetData(BaseModel):
    """Данные об удалённом пресете."""

    preset_id: int = Field(..., description="ID пресета в FilamentHub")
    preset_name: str = Field(..., description="Название пресета")
    bundle_preset_name: str | None = Field(
        default=None, description="Название пресета в OrcaSlicer bundle (если было)"
    )


class DeletedPresetsRequest(BaseModel):
    """Запрос на сообщение об удалённых пресетах."""

    deleted_presets: list[DeletedPresetData] = Field(..., description="Список удалённых пресетов")


class DeletedPresetAction(BaseModel):
    """Действие пользователя для удалённого пресета."""

    action: Literal["restore", "delete", "skip"] = Field(..., description="Действие: восстановить, удалить, пропустить")
    preset_ids: list[int] | None = Field(
        default=None, description="ID пресетов для обработки (если не указано, применяется ко всем)"
    )
    apply_to_all: bool = Field(
        default=False, description="Применить действие ко всем пресетам в уведомлении"
    )
    save_rule: bool = Field(
        default=False, description="Сохранить это действие как правило для будущих удалений"
    )


class DeletedPresetsResponse(BaseModel):
    """Ответ на сообщение об удалённых пресетах."""

    message: str
    notification_id: int | None = Field(default=None, description="ID созданного уведомления")
    preset_count: int | None = Field(default=None, description="Количество удалённых пресетов")
    created_count: int | None = Field(default=None, description="Количество созданных пользователем пресетов")
    saved_count: int | None = Field(default=None, description="Количество сохранённых пресетов")
    rule: str | None = Field(default=None, description="Применённое правило пользователя")


class DeletedPresetActionResponse(BaseModel):
    """Ответ на обработку действия пользователя."""

    message: str
    action: str
    processed_count: int
    total_count: int



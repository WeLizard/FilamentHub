"""Schemas for OrcaSlicer synchronisation endpoints."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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
    review_state: str | None = Field(
        default=None,
        description="Состояние review для приватной заготовки после импорта.",
    )
    important_decisions: int | None = Field(
        default=None,
        ge=0,
        description="Сколько действительно важных решений осталось пользователю.",
    )
    preset_readiness_percent: int | None = Field(default=None, ge=0, le=100)
    catalog_readiness_percent: int | None = Field(default=None, ge=0, le=100)


class OrcaPrinterProfilePayload(BaseModel):
    """Payload для импорта профилей принтера из OrcaSlicer."""

    external_id: str | None = Field(
        default=None,
        max_length=200,
        description="Уникальный ID профиля в OrcaSlicer (полезно для сопоставления).",
    )
    fhub_id: int | None = Field(
        default=None, ge=1, description="ID существующего профиля в FilamentHub (если обновляем)."
    )
    local_profile_id: str | None = Field(
        default=None,
        min_length=36,
        max_length=36,
        pattern=_UUID_PATTERN,
        description="Непрозрачный устойчивый UUID локального профиля из реестра плагина.",
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

    profiles: list[OrcaPrinterProfilePayload] = Field(..., max_length=50)
    source_instance_id: str | None = Field(default=None, min_length=16, max_length=100)
    account_id: str | None = Field(
        default=None, min_length=36, max_length=36, pattern=_UUID_PATTERN
    )
    snapshot_id: str | None = Field(
        default=None, min_length=36, max_length=36, pattern=_UUID_PATTERN
    )


class PrinterProfileSyncResponse(BaseModel):
    """Результат импорта профилей принтера."""

    results: list[OrcaSyncResult]


class OrcaPrintProfilePayload(BaseModel):
    """Payload для импорта профилей печати."""

    external_id: str | None = Field(default=None, max_length=200)
    fhub_id: int | None = Field(default=None, ge=1)
    local_profile_id: str | None = Field(
        default=None, min_length=36, max_length=36, pattern=_UUID_PATTERN
    )
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

    profiles: list[OrcaPrintProfilePayload] = Field(..., max_length=50)
    source_instance_id: str | None = Field(default=None, min_length=16, max_length=100)
    account_id: str | None = Field(
        default=None, min_length=36, max_length=36, pattern=_UUID_PATTERN
    )
    snapshot_id: str | None = Field(
        default=None, min_length=36, max_length=36, pattern=_UUID_PATTERN
    )


class PrintProfileSyncResponse(BaseModel):
    """Результат импорта профилей печати."""

    results: list[OrcaSyncResult]


class OrcaProfileSnapshotStartRequest(BaseModel):
    """Start a complete profile-list snapshot for one local Orca account."""

    kind: Literal["machine", "process"]
    source_instance_id: str = Field(..., min_length=16, max_length=100)
    account_id: str = Field(..., min_length=36, max_length=36, pattern=_UUID_PATTERN)


class OrcaProfileSnapshotStartResponse(BaseModel):
    snapshot_id: str
    bound_local_profile_ids: list[str] = Field(default_factory=list)


class OrcaProfileSnapshotFinalizeRequest(BaseModel):
    """Finalize a snapshot only after every changed profile was accepted."""

    kind: Literal["machine", "process"]
    source_instance_id: str = Field(..., min_length=16, max_length=100)
    account_id: str = Field(..., min_length=36, max_length=36, pattern=_UUID_PATTERN)
    snapshot_id: str = Field(..., min_length=36, max_length=36, pattern=_UUID_PATTERN)
    present_local_profile_ids: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("present_local_profile_ids")
    @classmethod
    def validate_local_profile_ids(cls, values: list[str]) -> list[str]:
        try:
            normalized = [str(UUID(value)) for value in values]
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Every local profile id must be a UUID") from exc
        return list(dict.fromkeys(normalized))


class OrcaProfileSnapshotFinalizeResponse(BaseModel):
    status: Literal["finalized", "already_finalized", "superseded"]
    present_count: int = 0
    absent_count: int = 0


class OrcaFilamentPresetPayload(BaseModel):
    """Payload для импорта пресета филамента из OrcaSlicer."""

    external_id: str | None = Field(
        default=None, description="Уникальный ID профиля в OrcaSlicer (полезно для сопоставления)."
    )
    fhub_id: int | None = Field(
        default=None, ge=1, description="ID существующего пресета в FilamentHub (если обновляем)."
    )
    name: str = Field(..., max_length=200)
    slug: str | None = Field(
        default=None,
        max_length=200,
        description="Slug пресета. Если не передан, будет сгенерирован автоматически.",
    )
    description: str | None = Field(default=None, max_length=10_000)

    # Filament данные
    filament_id: int | None = Field(
        default=None, ge=1, description="ID существующего материала в FilamentHub (если обновляем)."
    )
    filament_name: str | None = Field(
        default=None, max_length=200, description="Название материала (если создаем новый)."
    )
    material_type: str | None = Field(
        default=None, max_length=50, description="Тип материала (PLA, ABS, PETG, etc.)."
    )
    inherits: str | None = Field(
        default=None,
        max_length=200,
        description="Родительский пресет из OrcaSlicer (например, 'Generic PLA @System'). Используется для определения material_type.",
    )

    # Базовые параметры печати (material scope; process-скорости/высоты слоёв на пресете нет)
    extruder_temp: float | None = Field(default=None, ge=0, le=1500, description="Температура экструдера (°C).")
    bed_temp: float | None = Field(default=None, ge=0, le=300, description="Температура стола (°C).")
    flow_rate: float | None = Field(default=None, gt=0, le=200, description="Поток материала (%).")
    fan_speed: int | None = Field(default=None, ge=0, le=100, description="Скорость вентилятора (0-100%).")
    retraction_length: float | None = Field(default=None, ge=0, le=20, description="Длина ретракции (мм).")
    retraction_speed: float | None = Field(default=None, ge=0, le=200, description="Скорость ретракции (мм/с).")

    # OrcaSlicer JSON формат
    orcaslicer_settings: dict[str, Any] = Field(
        default_factory=dict, description="Полный JSON профиль OrcaSlicer со всеми параметрами."
    )

    # .info файл содержимое (для идентификации пресета)
    info_content: str | None = Field(
        default=None,
        description=(
            "Содержимое .info файла OrcaSlicer. Используется для извлечения меток FilamentHub: "
            "bundle_id='filamenthub:<id>' (preferred, OrcaSlicer 2.4+) или legacy fhub_id/fhub_source."
        )
    )

    # Orphaned preset flags (set by C++ scanner for presets with broken inherits)
    orphaned: bool | None = Field(
        default=None, description="True if preset was found on disk but not loaded by OrcaSlicer (broken inherits)."
    )
    orphaned_reason: str | None = Field(
        default=None, max_length=200, description="Reason the preset is orphaned (e.g. 'parent_not_found')."
    )
    original_inherits: str | None = Field(
        default=None, max_length=200, description="Original inherits value from the broken preset file."
    )

    # Метаданные
    source: str | None = Field(
        default=None, max_length=50, description="Источник пресета (orcaslicer, user, system, etc.)."
    )
    source_version: str | None = Field(
        default=None,
        max_length=50,
        description="Версия интеграции, сформировавшей снимок.",
    )
    capture_mode: Literal[
        "resolved_runtime",
        "recovered_live_json",
        "recovered_backup_json",
    ] | None = Field(
        default=None,
        description="Как именно Orca-снимок был получен без раскрытия локального пути.",
    )
    active: bool | None = Field(
        default=False, description="Флаг активности. По умолчанию импортируется как черновик (False)."
    )
    notes: str | None = Field(default=None, max_length=10_000, description="Заметки к пресету.")

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Preset name cannot be empty")
        return normalized


class FilamentPresetSyncRequest(BaseModel):
    """Запрос на импорт пресетов филаментов."""

    profiles: list[OrcaFilamentPresetPayload] = Field(
        ..., description="Список пресетов филаментов для импорта (максимум 50)."
    )


class FilamentPresetSyncResponse(BaseModel):
    """Результат импорта пресетов филаментов."""

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


# ---------------------------------------------------------------------------
# Batch export (OrcaSlicer sync performance: N requests → 1)
# ---------------------------------------------------------------------------


class BatchExportRequest(BaseModel):
    """Request to batch-export multiple presets as OrcaSlicer JSON + .info."""

    preset_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of preset IDs to export (max 100).",
    )


class BatchExportItem(BaseModel):
    """Single preset export result within a batch."""

    preset_id: int
    config: dict[str, Any] | None = Field(
        default=None,
        description="Full OrcaSlicer JSON profile (generated by preset_to_orcaslicer_json).",
    )
    info: str | None = Field(
        default=None,
        description="OrcaSlicer .info file content (INI format).",
    )
    status: Literal["ok", "error"]
    error: str | None = Field(default=None, description="Error message if status is 'error'.")


class BatchExportResponse(BaseModel):
    """Response with batch-exported presets."""

    profiles: list[BatchExportItem]

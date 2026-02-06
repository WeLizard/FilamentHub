"""Pydantic schemas для SyncPlan API."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Sync Plan ─────────────────────────────────────────────────


class PresetChange(BaseModel):
    """Пресет для скачивания."""
    id: int
    name: str
    updated_at: str | None = None
    orcaslicer_settings: dict | None = None


class PresetConflict(BaseModel):
    """Конфликт синхронизации."""
    preset_id: int
    server_version: str | None = None
    client_version: str | None = None
    resolution: str | None = None  # "server_wins", "client_wins", "manual"


class SyncChanges(BaseModel):
    """Изменения для синхронизации."""
    to_download: list[PresetChange] = Field(default_factory=list)
    deleted_on_server: list[dict] = Field(default_factory=list)
    conflicts: list[PresetConflict] = Field(default_factory=list)


class SyncPlan(BaseModel):
    """План синхронизации."""
    sync_version: int
    device_id: str
    changes: SyncChanges
    last_sync_at: str | None = None


# ── Requests / Responses ──────────────────────────────────────


class SyncPlanRequest(BaseModel):
    """Запрос на создание плана синхронизации."""
    device_fingerprint: str
    preset_type: str = Field(..., pattern="^(filament|printer|print)$")
    force_full_sync: bool = False
    orcaslicer_version: str | None = None


class SyncPlanResponse(BaseModel):
    """Ответ с планом синхронизации."""
    sync_version: int
    device_id: str
    to_download: list[PresetChange] = Field(default_factory=list)
    deleted_on_server: list[dict] = Field(default_factory=list)
    conflicts: list[PresetConflict] = Field(default_factory=list)
    last_sync_at: str | None = None


class SyncCompleteRequest(BaseModel):
    """Запрос на завершение синхронизации."""
    device_fingerprint: str


class SyncStatusResponse(BaseModel):
    """Статус синхронизации устройства."""
    device_fingerprint: str
    sync_version: int
    last_sync_at: str | None = None
    last_sync_stats: dict = Field(default_factory=dict)


# ── Deleted Presets ───────────────────────────────────────────


class DeletedPresetsRequest(BaseModel):
    """Запрос на получение удалённых пресетов."""
    device_fingerprint: str
    preset_type: str = Field(..., pattern="^(filament|printer|print)$")


class DeletedPresetInfo(BaseModel):
    """Информация об удалённом пресете."""
    preset_id: int
    name: str
    was_created_by_user: bool
    was_saved_by_user: bool


class DeletedPresetsResponse(BaseModel):
    """Ответ со списком удалённых пресетов."""
    deleted: list[DeletedPresetInfo] = Field(default_factory=list)

"""Pydantic schemas для SyncPlan API."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    include_changes: bool = True


class SyncPlanResponse(BaseModel):
    """Ответ с планом синхронизации."""

    sync_version: int
    device_id: str
    to_download: list[PresetChange] = Field(default_factory=list)
    deleted_on_server: list[dict] = Field(default_factory=list)
    conflicts: list[PresetConflict] = Field(default_factory=list)
    last_sync_at: str | None = None


class PresetSyncResult(BaseModel):
    """Фактический результат одной операции на конкретном устройстве."""

    preset_id: int = Field(..., gt=0)
    preset_type: Literal["filament", "printer", "print"] = "filament"
    operation: Literal["download", "delete"] = "download"
    state: Literal["on_disk", "pending_restart", "loaded", "error", "removed"]
    error_code: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_operation_state(self) -> "PresetSyncResult":
        if self.operation == "delete" and self.state != "removed":
            raise ValueError("delete result must use removed state")
        if self.operation == "download" and self.state == "removed":
            raise ValueError("download result cannot use removed state")
        if self.state == "error" and not self.error_code:
            raise ValueError("error result requires error_code")
        if self.state != "error" and self.error_code:
            raise ValueError("error_code is only valid for error state")
        return self


class SyncCompleteRequest(BaseModel):
    """Подтверждение фактического результата синхронизации устройства."""

    device_fingerprint: str = Field(..., min_length=1, max_length=255)
    sync_version: int = Field(..., ge=1)
    results: list[PresetSyncResult] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def reject_duplicate_results(self) -> "SyncCompleteRequest":
        keys = [(item.preset_type, item.operation, item.preset_id) for item in self.results]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate preset sync result")
        return self


class SyncCompleteResponse(BaseModel):
    """Идемпотентное подтверждение принятого device report."""

    sync_version: int
    last_sync_at: str
    duplicate: bool = False


class SyncDeviceStatus(BaseModel):
    """Устройство, которое хотя бы раз запросило план синхронизации."""

    device_fingerprint: str
    orcaslicer_version: str | None = None
    sync_version: int
    last_sync_at: str | None = None


class PresetSyncStatus(BaseModel):
    """Desired state и последнее наблюдение для одного пресета."""

    preset_id: int
    desired: bool
    state: Literal["pending", "on_disk", "pending_restart", "loaded", "error", "removed"]
    operation: Literal["download", "delete"] | None = None
    error_code: str | None = None
    observed_at: str | None = None


class SyncStatusResponse(BaseModel):
    """Статус синхронизации устройства."""

    device_fingerprint: str | None = None
    sync_version: int
    last_sync_at: str | None = None
    last_sync_stats: dict = Field(default_factory=dict)
    devices: list[SyncDeviceStatus] = Field(default_factory=list)
    presets: list[PresetSyncStatus] = Field(default_factory=list)


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

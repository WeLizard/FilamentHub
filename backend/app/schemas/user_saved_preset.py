"""Pydantic schemas for UserSavedPreset."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PresetLibraryScope = Literal["unscoped", "targeted", "compatible"]


class UserSavedPresetCreate(BaseModel):
    """Schema for creating UserSavedPreset."""

    preset_id: int = Field(..., gt=0, description="ID пресета для сохранения")
    sync: bool = Field(
        default=True,
        description="Включить ли OrcaSlicer sync вместе с сохранением",
    )


class UserSavedPresetScopeUpdate(BaseModel):
    """Library scope update: the set of the user's own Orca machine profiles
    the preset is meant for. Scope is derived from the set size: empty →
    unscoped, one → targeted, several → compatible."""

    target_printer_profile_ids: list[int] = Field(
        default_factory=list,
        description="PrinterProfile.id целей; пустой список = unscoped",
    )


class UserSavedPresetVersionAction(BaseModel):
    """Choose a version or acknowledge an update while keeping the current one."""

    action: Literal["select", "keep_current"]
    version_id: int = Field(..., gt=0)


class UserSavedPresetResponse(BaseModel):
    """Schema for UserSavedPreset response."""

    id: int
    user_id: int
    preset_id: int
    saved_at: datetime
    sync: bool = Field(True, description="Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя")
    scope: PresetLibraryScope = "unscoped"
    target_printer_profile_ids: list[int] = Field(default_factory=list)
    selected_version_id: int | None = None
    selected_version_number: int | None = None
    latest_version_id: int | None = None
    latest_version_number: int | None = None
    update_available: bool = False
    update_unseen: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserSavedPresetListResponse(BaseModel):
    """Schema for list of UserSavedPreset."""

    items: list[UserSavedPresetResponse]
    total: int

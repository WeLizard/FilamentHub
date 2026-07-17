"""Pydantic schemas for UserSavedPreset."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PresetLibraryScope = Literal["unscoped", "targeted"]


class UserSavedPresetCreate(BaseModel):
    """Schema for creating UserSavedPreset."""

    preset_id: int = Field(..., gt=0, description="ID пресета для сохранения")


class UserSavedPresetScopeUpdate(BaseModel):
    """Library scope update: universal or pinned to one of the user's own
    Orca machine profiles (PrinterProfile.id)."""

    scope: PresetLibraryScope
    target_printer_profile_id: int | None = Field(
        default=None,
        gt=0,
        description="Обязателен при scope=targeted; игнорируется при unscoped",
    )


class UserSavedPresetResponse(BaseModel):
    """Schema for UserSavedPreset response."""

    id: int
    user_id: int
    preset_id: int
    saved_at: datetime
    sync: bool = Field(True, description="Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя")
    scope: PresetLibraryScope = "unscoped"
    target_printer_profile_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class UserSavedPresetListResponse(BaseModel):
    """Schema for list of UserSavedPreset."""

    items: list[UserSavedPresetResponse]
    total: int


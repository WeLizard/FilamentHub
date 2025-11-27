"""Pydantic schemas for UserSavedPreset."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserSavedPresetCreate(BaseModel):
    """Schema for creating UserSavedPreset."""

    preset_id: int = Field(..., gt=0, description="ID пресета для сохранения")


class UserSavedPresetResponse(BaseModel):
    """Schema for UserSavedPreset response."""

    id: int
    user_id: int
    preset_id: int
    saved_at: datetime
    sync: bool = Field(True, description="Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя")

    model_config = ConfigDict(from_attributes=True)


class UserSavedPresetListResponse(BaseModel):
    """Schema for list of UserSavedPreset."""

    items: list[UserSavedPresetResponse]
    total: int


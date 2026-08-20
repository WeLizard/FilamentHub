"""Achievement and contributor summary schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class AchievementResponse(BaseModel):
    code: str
    earned_at: datetime


class AchievementOverviewResponse(BaseModel):
    achievements: list[AchievementResponse] = Field(default_factory=list)
    published_presets: int = Field(ge=0)
    saved_by_other_users: int = Field(ge=0)
    confirmed_uses_by_other_users: int = Field(ge=0)

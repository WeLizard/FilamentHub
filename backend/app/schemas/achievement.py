"""Achievement and contributor summary schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class AchievementResponse(BaseModel):
    code: str
    earned_at: datetime
    category: str
    rarity: str
    hidden: bool = False


class AchievementProgressResponse(BaseModel):
    code: str
    category: str
    rarity: str
    current: int = Field(ge=0)
    target: int = Field(gt=0)


class AchievementOverviewResponse(BaseModel):
    achievements: list[AchievementResponse] = Field(default_factory=list)
    next_achievements: list[AchievementProgressResponse] = Field(default_factory=list)
    newly_earned: list[str] = Field(default_factory=list)
    contributor_roles: list[str] = Field(default_factory=list)
    published_presets: int = Field(ge=0)
    saved_by_other_users: int = Field(ge=0)
    confirmed_uses_by_other_users: int = Field(ge=0)

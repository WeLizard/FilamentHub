"""Achievement and contributor summary schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AchievementResponse(BaseModel):
    code: str
    earned_at: datetime
    category: str
    rarity: str
    hidden: bool = False
    source: str = "automatic"


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


class ManualAchievementReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def strip_reason(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ManualAchievementGrantRequest(ManualAchievementReasonRequest):
    code: str = Field(min_length=1, max_length=64)


class ManualAchievementRevokeRequest(ManualAchievementReasonRequest):
    pass


class AdminAchievementResponse(BaseModel):
    code: str
    category: str
    rarity: str
    source: str
    earned_at: datetime
    awarded_by_user_id: int | None = None
    award_reason: str | None = None
    revoked_at: datetime | None = None
    revoked_by_user_id: int | None = None
    revoke_reason: str | None = None


class AdminAchievementOverviewResponse(BaseModel):
    achievements: list[AdminAchievementResponse] = Field(default_factory=list)
    manual_awardable_codes: list[str] = Field(default_factory=list)

"""Account-level email-change challenge contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AccountEmailChangeChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_email: EmailStr
    language: Literal["ru", "en", "zh"] | None = None


class AccountEmailChangeChallengeResponse(BaseModel):
    challenge_id: str
    expires_at: datetime
    masked_email: str


class AccountEmailChangeProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(min_length=1, max_length=43)
    code: str = Field(pattern=r"^[0-9]{6}$")

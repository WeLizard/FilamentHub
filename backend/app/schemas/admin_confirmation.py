"""Exact operation parameters and one-time administrator email proofs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.admin_action_confirmation import AdminConfirmationAction


class AdminConfirmationProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(min_length=1, max_length=43)
    code: str = Field(pattern=r"^[0-9]{6}$")


class AdminConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: AdminConfirmationAction
    target_user_id: int = Field(gt=0)
    delete_reviews: bool = False
    new_email: EmailStr | None = None
    language: Literal["ru", "en", "zh"] | None = None

    @model_validator(mode="after")
    def validate_operation_parameters(self) -> "AdminConfirmationRequest":
        if self.action == AdminConfirmationAction.CHANGE_ADMIN_EMAIL:
            if self.new_email is None:
                raise ValueError("new_email is required for an email change")
        elif self.new_email is not None:
            raise ValueError("new_email is only allowed for an email change")
        if self.action != AdminConfirmationAction.DELETE_USER and self.delete_reviews:
            raise ValueError("delete_reviews is only allowed for account deletion")
        return self


class AdminConfirmationResponse(BaseModel):
    challenge_id: str
    expires_at: datetime
    masked_email: str

"""Subscription and waitlist response schemas."""

from datetime import datetime

from pydantic import BaseModel


class PlanInterestResponse(BaseModel):
    status: str
    interested_at: datetime | None

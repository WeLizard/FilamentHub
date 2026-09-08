"""Public, bounded metadata for a person's own account sessions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AccountSessionResponse(BaseModel):
    id: str
    is_current: bool
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    browser: Literal["chrome", "edge", "firefox", "safari", "opera", "unknown"]
    os: Literal["windows", "macos", "linux", "android", "ios", "unknown"]
    device_type: Literal["desktop", "mobile", "tablet", "unknown"]


class AccountSessionListResponse(BaseModel):
    items: list[AccountSessionResponse]
    total: int
    page: int
    size: int
    pages: int
    current_session_id: str


class AccountSessionRevokeResponse(BaseModel):
    revoked: bool
    current_session_revoked: bool


class OtherSessionsRevokeResponse(BaseModel):
    revoked_count: int

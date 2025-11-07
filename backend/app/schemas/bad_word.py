"""Bad word schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class BadWordBase(BaseModel):
    """Base bad word schema."""

    word: str = Field(..., min_length=1, max_length=100, description="Запрещенное слово")
    language: str = Field(default="ru", max_length=10, description="Язык (ru, en)")


class BadWordCreate(BadWordBase):
    """Create bad word schema."""

    pass


class BadWordUpdate(BaseModel):
    """Update bad word schema."""

    word: str | None = Field(None, min_length=1, max_length=100)
    language: str | None = Field(None, max_length=10)


class BadWordResponse(BadWordBase):
    """Bad word response schema."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BadWordListResponse(BaseModel):
    """Bad word list response schema."""

    items: list[BadWordResponse]
    total: int
    page: int
    size: int
    pages: int


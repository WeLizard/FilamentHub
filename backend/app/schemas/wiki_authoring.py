"""Schemas for versioned Wiki authoring and moderation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.wiki_revision import (
    WikiReviewVerdict,
    WikiRevisionAuthorship,
    WikiRevisionStatus,
)

WikiSpaceKey = Literal["guides", "knowledge"]
WikiLanguage = Literal["ru", "en", "zh"]


def _clean_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None

    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = tag.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)

    if len(cleaned) > 20:
        raise ValueError("A Wiki revision can contain at most 20 tags")
    return cleaned or None


class WikiSpaceResponse(BaseModel):
    """Stable content-space metadata; labels are localized by the frontend."""

    key: WikiSpaceKey
    order: int
    allows_community_authors: bool


class WikiArticleDraftCreate(BaseModel):
    """Create an article and its first revision."""

    category_id: int = Field(..., gt=0)
    space_key: WikiSpaceKey = "knowledge"
    language: WikiLanguage = "ru"
    title: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(None, min_length=1, max_length=200, pattern=r"^[a-z0-9-]+$")
    summary: str = Field(..., min_length=1, max_length=1000)
    content: str = Field(..., min_length=1, max_length=200_000)
    tags: list[str] | None = None
    edit_summary: str | None = Field(None, max_length=1000)
    publish: bool = False

    @field_validator("title", "summary", "content", "edit_summary")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        return _clean_tags(value)


class WikiRevisionCreate(BaseModel):
    """Create an editable revision from the currently published snapshot."""

    title: str | None = Field(None, min_length=1, max_length=200)
    summary: str | None = Field(None, min_length=1, max_length=1000)
    content: str | None = Field(None, min_length=1, max_length=200_000)
    tags: list[str] | None = None
    edit_summary: str | None = Field(None, max_length=1000)

    @field_validator("title", "summary", "content", "edit_summary")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        return _clean_tags(value)


class WikiRevisionUpdate(BaseModel):
    """Update the mutable content of an owned draft."""

    title: str | None = Field(None, min_length=1, max_length=200)
    summary: str | None = Field(None, min_length=1, max_length=1000)
    content: str | None = Field(None, min_length=1, max_length=200_000)
    tags: list[str] | None = None
    edit_summary: str | None = Field(None, max_length=1000)

    @field_validator("title", "summary", "content", "edit_summary")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        return _clean_tags(value)


class WikiRevisionSubmit(BaseModel):
    """Optional final summary supplied when a draft is submitted."""

    edit_summary: str | None = Field(None, max_length=1000)


class WikiRevisionReviewCreate(BaseModel):
    """Advisory peer validation; it never publishes content."""

    verdict: WikiReviewVerdict
    comment: str | None = Field(None, max_length=4000)
    evidence_url: str | None = Field(None, max_length=2000)


class WikiRevisionReviewResponse(BaseModel):
    id: int
    reviewer_id: int | None
    reviewer_username: str | None = None
    verdict: WikiReviewVerdict
    comment: str | None
    evidence_url: str | None
    created_at: datetime
    updated_at: datetime


class WikiModerationDecision(BaseModel):
    """An editor's authoritative decision on a submitted revision."""

    decision: Literal["publish", "reject"]
    review_note: str | None = Field(None, max_length=4000)


class WikiRevisionResponse(BaseModel):
    id: int
    article_id: int
    article_category_id: int
    article_slug: str
    article_title: str
    article_space_key: WikiSpaceKey
    article_language: WikiLanguage
    article_provenance: Literal["editorial", "community"]
    revision_number: int
    base_revision_id: int | None
    base_title: str | None = None
    base_summary: str | None = None
    base_content: str | None = None
    base_tags: list[str] | None = None
    created_by_id: int | None
    created_by_username: str | None = None
    reviewed_by_id: int | None
    reviewed_by_username: str | None = None
    status: WikiRevisionStatus
    authorship: WikiRevisionAuthorship
    title: str
    summary: str
    content: str
    tags: list[str] | None
    edit_summary: str | None
    review_note: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    peer_reviews: list[WikiRevisionReviewResponse] = Field(default_factory=list)


class WikiRevisionListResponse(BaseModel):
    items: list[WikiRevisionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WikiPublicRevisionResponse(BaseModel):
    """Published revision data that is safe to expose without authentication."""

    id: int
    revision_number: int
    base_revision_id: int | None
    created_by_username: str | None = None
    authorship: WikiRevisionAuthorship
    title: str
    summary: str
    content: str
    tags: list[str] | None
    edit_summary: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WikiPublicRevisionListResponse(BaseModel):
    items: list[WikiPublicRevisionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

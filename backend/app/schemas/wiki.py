"""Wiki schemas."""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import re


# ============================================================================
# WikiCategory Schemas
# ============================================================================

class WikiCategoryBase(BaseModel):
    """Base schema for WikiCategory."""

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1)
    icon: str | None = Field(None, max_length=50)
    order: int = Field(default=0, ge=0)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format (lowercase, alphanumeric, hyphens only)."""
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v


class WikiCategoryCreate(WikiCategoryBase):
    """Schema for creating WikiCategory."""

    pass


class WikiCategoryUpdate(BaseModel):
    """Schema for updating WikiCategory."""

    name: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, min_length=1)
    icon: str | None = Field(None, max_length=50)
    order: int | None = Field(None, ge=0)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        """Validate slug format (lowercase, alphanumeric, hyphens only)."""
        if v is not None and not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v


class WikiCategoryResponse(WikiCategoryBase):
    """Schema for WikiCategory response."""

    id: int
    created_at: datetime
    updated_at: datetime
    articles_count: int = Field(default=0, description="Number of published articles in this category")

    model_config = {"from_attributes": True}


# ============================================================================
# WikiArticle Schemas
# ============================================================================

class WikiArticleBase(BaseModel):
    """Base schema for WikiArticle."""

    category_id: int = Field(..., gt=0)
    title: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    tags: list[str] | None = Field(None, description="Array of tags")
    author: str | None = Field(None, max_length=100)
    published: bool = Field(default=True)
    order: int = Field(default=0, ge=0)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format (lowercase, alphanumeric, hyphens only)."""
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v


class WikiArticleCreate(WikiArticleBase):
    """Schema for creating WikiArticle."""

    pass


class WikiArticleUpdate(BaseModel):
    """Schema for updating WikiArticle."""

    category_id: int | None = Field(None, gt=0)
    title: str | None = Field(None, min_length=1, max_length=200)
    slug: str | None = Field(None, min_length=1, max_length=200)
    summary: str | None = Field(None, min_length=1)
    content: str | None = Field(None, min_length=1)
    tags: list[str] | None = Field(None, description="Array of tags")
    author: str | None = Field(None, max_length=100)
    published: bool | None = None
    order: int | None = Field(None, ge=0)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        """Validate slug format (lowercase, alphanumeric, hyphens only)."""
        if v is not None and not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v


class WikiArticleSummary(BaseModel):
    """Summary schema for WikiArticle (for lists)."""

    id: int
    category_id: int
    title: str
    slug: str
    summary: str
    tags: list[str] | None
    author: str | None
    published: bool
    views: int
    order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WikiArticleResponse(WikiArticleSummary):
    """Full schema for WikiArticle response."""

    content: str
    category_name: str | None = Field(default=None, description="Category name for convenience")

    model_config = {"from_attributes": True}


# ============================================================================
# List Response Schemas
# ============================================================================

class WikiCategoryListResponse(BaseModel):
    """Schema for paginated list of categories."""

    items: list[WikiCategoryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WikiArticleListResponse(BaseModel):
    """Schema for paginated list of articles."""

    items: list[WikiArticleSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


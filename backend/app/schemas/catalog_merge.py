"""Schemas for folding duplicate brands and filaments."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MergeFilamentSummary(BaseModel):
    id: int
    name: str
    slug: str
    material_type: str
    diameter: float
    color_name: str | None = None
    color_hex: str | None = None
    has_qr_code: bool = False
    presets: int = 0
    spools: int = 0
    reviews: int = 0


class FilamentMergeCandidate(MergeFilamentSummary):
    likely_same: bool = False


class FilamentMergeCandidatesResponse(BaseModel):
    source: MergeFilamentSummary
    candidates: list[FilamentMergeCandidate]


class FilamentMergeRequest(BaseModel):
    target_id: int = Field(..., ge=1)


class MergeBrandSummary(BaseModel):
    id: int
    name: str
    slug: str
    verified: bool
    filaments: int = 0


class BrandDuplicatePair(BaseModel):
    first: MergeBrandSummary
    second: MergeBrandSummary


class BrandMergeFilamentRow(BaseModel):
    source: MergeFilamentSummary
    candidates: list[FilamentMergeCandidate]
    suggested_target_id: int | None = None
    # Without a pair this filament has no free address in the kept brand.
    needs_pair: bool = False


BrandMergeFieldName = Literal[
    "logo", "website", "description", "currency", "shop_links", "social_media_urls"
]


class BrandMergeField(BaseModel):
    """One brand detail the two brands do not share.

    ``fill``: only the duplicate has it and it is kept. ``combine``: both lists
    are kept together. ``conflict``: the administrator chooses one value.
    """

    key: str
    field: BrandMergeFieldName
    country: str | None = None
    source_value: str | list[Any] | None = None
    target_value: str | list[Any] | None = None
    outcome: Literal["fill", "combine", "conflict"]


class BrandMergePreview(BaseModel):
    source: MergeBrandSummary
    target: MergeBrandSummary
    source_represented: bool
    filaments: list[BrandMergeFilamentRow]
    fields: list[BrandMergeField] = Field(default_factory=list)


class BrandMergeFilamentPair(BaseModel):
    source_filament_id: int = Field(..., ge=1)
    target_filament_id: int = Field(..., ge=1)


class BrandMergeRequest(BaseModel):
    target_id: int = Field(..., ge=1)
    filament_pairs: list[BrandMergeFilamentPair] = Field(default_factory=list, max_length=2000)
    # Conflicting details by preview ``key``: which brand's value stays.
    field_choices: dict[str, Literal["source", "target"]] = Field(
        default_factory=dict, max_length=200
    )


class DuplicateReviewAuthor(BaseModel):
    id: int
    username: str


class FilamentDuplicateReviewItem(BaseModel):
    id: int
    origin: str
    created_at: datetime
    brand_name: str
    # Author of `filament`; empty for records created before authorship was kept.
    created_by: DuplicateReviewAuthor | None = None
    filament: MergeFilamentSummary
    candidate: MergeFilamentSummary


class FilamentDuplicateReviewList(BaseModel):
    items: list[FilamentDuplicateReviewItem]
    total: int


class FilamentDuplicateScanResult(BaseModel):
    added: int

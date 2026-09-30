"""Schemas for folding duplicate brands and filaments."""

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


class BrandMergePreview(BaseModel):
    source: MergeBrandSummary
    target: MergeBrandSummary
    source_represented: bool
    filaments: list[BrandMergeFilamentRow]


class BrandMergeFilamentPair(BaseModel):
    source_filament_id: int = Field(..., ge=1)
    target_filament_id: int = Field(..., ge=1)


class BrandMergeRequest(BaseModel):
    target_id: int = Field(..., ge=1)
    filament_pairs: list[BrandMergeFilamentPair] = Field(default_factory=list, max_length=2000)

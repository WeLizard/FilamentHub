"""PresetVersion schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PresetVersionAuthor(BaseModel):
    """Minimal author info for a version row."""

    id: int
    username: str | None = None


class PresetVersionListItem(BaseModel):
    """One row in the version timeline (no heavy snapshot payload)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    label: str = ""
    label_description: str | None = None
    change_source: str
    restored_from_version_id: int | None = None
    squash_count: int = 1
    created_at: datetime
    updated_at: datetime
    created_by: PresetVersionAuthor | None = None


class PresetVersionListResponse(BaseModel):
    """Paginated list of versions."""

    items: list[PresetVersionListItem]
    total: int


class PresetVersionDetail(PresetVersionListItem):
    """Single version including its full snapshot."""

    snapshot_orcaslicer_settings: dict | None = None
    snapshot_structured: dict


class PresetVersionDiffChange(BaseModel):
    """A single changed field with human-readable metadata."""

    key: str
    label: str
    unit: str | None = None
    old: str | None = None
    new: str | None = None


class PresetVersionDiffUnmapped(BaseModel):
    """A changed field with no human label (raw key fallback)."""

    key: str
    old: str | None = None
    new: str | None = None


class PresetVersionDiffResponse(BaseModel):
    """Human-readable diff between two versions."""

    from_version: int
    to_version: int
    changes: list[PresetVersionDiffChange]
    unmapped_changes: list[PresetVersionDiffUnmapped]


class PresetVersionLabelUpdate(BaseModel):
    """Set or clear a version's label."""

    label: str = Field("", max_length=120, description="Label text; empty string clears it")
    label_description: str | None = Field(None, max_length=2000)


class PresetVersionRestoreResponse(BaseModel):
    """Result of restoring a version."""

    restored_into_version_id: int = Field(..., description="New version created by the restore")
    restored_into_version_number: int
    restored_from_version_id: int

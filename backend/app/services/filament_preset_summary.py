"""The three presets a material leads with: official, generated, best of the community.

The catalogue shows them as a carousel on every card, and the material's own page
shows the same three. Built here rather than in either endpoint so the two can
never drift into disagreeing about which preset represents a material.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Select, desc, select

from app.models.preset import PUBLIC_PRESET_STATUSES, Preset

# Within a material: the generated preset first, then by rating, then by
# recency. The kind each preset is claimed for is decided from this order, so
# "the community's best" means the best-rated one and not merely the first seen.
_SUMMARY_ORDER = (
    desc(Preset.is_weighted),
    desc(Preset.rating),
    desc(Preset.updated_at),
)


def summary_query(filament_ids: Sequence[int]) -> Select:
    """Publicly visible presets of these materials, in the order the kinds are picked."""
    return (
        select(Preset)
        .where(
            Preset.filament_id.in_(filament_ids),
            Preset.active.is_(True),
            Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
        )
        .order_by(Preset.filament_id, *_SUMMARY_ORDER)
    )


def bucket_by_kind(presets: Iterable[Preset]) -> dict[int, dict[str, Preset]]:
    """Group presets under the kind each one represents for its material."""
    buckets: dict[int, dict[str, Preset]] = {}
    for preset in presets:
        bucket = buckets.setdefault(preset.filament_id, {})
        if preset.is_official and "official" not in bucket:
            bucket["official"] = preset
        if preset.is_weighted and "weighted" not in bucket:
            bucket["weighted"] = preset
        if not preset.is_official and not preset.is_weighted and "community" not in bucket:
            bucket["community"] = preset
    return buckets


def serialize_summary(preset: Preset, preset_type: str) -> dict[str, Any]:
    return {
        "id": preset.id,
        "name": preset.name,
        "is_official": preset.is_official,
        "is_weighted": preset.is_weighted,
        "extruder_temp": preset.extruder_temp,
        "bed_temp": preset.bed_temp,
        "fan_speed": preset.fan_speed,
        "flow_rate": preset.flow_rate,
        "rating": preset.rating,
        "success_rate": preset.success_rate,
        "updated_at": preset.updated_at,
        "preset_type": preset_type,
    }


def summaries_for(bucket: dict[str, Preset]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The official preset, and the carousel of kinds a material leads with."""
    official: dict[str, Any] | None = None
    summaries: list[dict[str, Any]] = []

    if "official" in bucket:
        official = serialize_summary(bucket["official"], "official")
        summaries.append(official)

    weighted = bucket.get("weighted")
    # A generated preset can also be the official one; it must not appear twice.
    if weighted is not None and (official is None or weighted.id != official["id"]):
        summaries.append(serialize_summary(weighted, "weighted"))

    community = bucket.get("community")
    if community is not None:
        summaries.append(serialize_summary(community, "community"))

    return official, summaries

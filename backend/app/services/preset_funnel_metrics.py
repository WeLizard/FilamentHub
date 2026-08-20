"""Record categorical, non-identifying Orca draft funnel events."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset_funnel_event import PresetFunnelEvent

ALLOWED_PRESET_FUNNEL_EVENTS = frozenset(
    {
        "imported",
        "recognized",
        "review_opened",
        "important_field_confirmed",
        "filament_matched_or_created",
        "preset_published",
        "installed_or_used",
        "confirmed_after_print",
        "duplicate_prevented",
    }
)


def record_preset_funnel_event(db: AsyncSession, event_type: str) -> None:
    """Stage one allowed category; never accept identifiers or arbitrary metadata."""
    if event_type not in ALLOWED_PRESET_FUNNEL_EVENTS:
        raise ValueError(f"Unsupported preset funnel event: {event_type}")
    db.add(PresetFunnelEvent(event_type=event_type))

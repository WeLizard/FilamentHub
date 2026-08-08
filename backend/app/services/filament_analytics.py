"""Capture analytics with the market known at event time."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament_analytics_event import FilamentAnalyticsEvent
from app.models.user import User


def event_country(request: Request, user: User | None) -> str | None:
    """Resolve a country without persisting an address or other personal data."""
    candidates = [
        user.country if user else None,
        request.headers.get("cf-ipcountry"),
        request.headers.get("x-vercel-ip-country"),
        request.headers.get("x-country-code"),
    ]
    for value in candidates:
        normalized = (value or "").strip().upper()
        if len(normalized) == 2 and normalized.isalpha() and normalized not in {"XX", "T1"}:
            return normalized
    return None


def record_filament_event(
    db: AsyncSession,
    *,
    filament_id: int,
    event_type: str,
    country: str | None,
) -> None:
    db.add(
        FilamentAnalyticsEvent(
            filament_id=filament_id,
            event_type=event_type,
            country=country,
        )
    )

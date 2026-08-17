"""Capture analytics with the market known at event time."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament_analytics_event import FilamentAnalyticsEvent
from app.models.user import User
from app.services.request_region_service import resolve_request_country_code


def event_country(request: Request, user: User | None) -> str | None:
    """Resolve a country without persisting an address or other personal data.

    The same GeoIP lookup the rest of the product uses. Reading a proxy header first
    would answer this question differently from every other place that asks it, and one
    person would be counted in two countries depending on which code path ran.
    """
    candidates = [
        user.country if user else None,
        resolve_request_country_code(request),
        # Kept behind GeoIP for a deployment that terminates at a CDN and never
        # reaches the database.
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

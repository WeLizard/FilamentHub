"""Geo-IP lookups for country-based OAuth provider restrictions.

Country is resolved from the request IP using a MaxMind-DB formatted database
(MaxMind GeoLite2-Country or the no-account db-ip Lite database). The module
degrades gracefully: if the geoip2 library or the database file is missing, the
configured fallback policy (OAUTH_GEO_FALLBACK_ALLOW) decides whether restricted
providers are allowed.
"""

import logging
from pathlib import Path

from fastapi import Request

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import geoip2.database
    import geoip2.errors

    _GEOIP2_AVAILABLE = True
except Exception:  # pragma: no cover - library is an optional dependency
    _GEOIP2_AVAILABLE = False

_reader = None
_reader_loaded = False


def _resolve_db_path() -> Path:
    db_path = Path(settings.GEOIP_DB_PATH)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    return db_path


def _get_reader():
    """Open the GeoIP reader once, caching the result (including failure)."""
    global _reader, _reader_loaded
    if _reader_loaded:
        return _reader

    _reader_loaded = True
    if not _GEOIP2_AVAILABLE:
        logger.warning("geoip2 library not installed; geo OAuth restriction disabled")
        return None

    db_path = _resolve_db_path()
    if not db_path.exists():
        logger.warning(
            "GeoIP database not found at %s; geo OAuth restriction inactive (fallback policy applies)",
            db_path,
        )
        return None

    try:
        _reader = geoip2.database.Reader(str(db_path))
        logger.info("GeoIP database loaded from %s", db_path)
    except Exception as e:
        logger.error("Failed to open GeoIP database at %s: %s", db_path, e)
        _reader = None
    return _reader


def reset_reader_cache() -> None:
    """Drop the cached reader (used by tests)."""
    global _reader, _reader_loaded
    if _reader is not None:
        try:
            _reader.close()
        except Exception:
            pass
    _reader = None
    _reader_loaded = False


def get_client_ip(request: Request) -> str | None:
    """Best-effort client IP: first X-Forwarded-For hop, then X-Real-IP, then peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    if request.client:
        return request.client.host
    return None


def get_country_code(request: Request) -> str | None:
    """ISO 3166-1 alpha-2 country code for the request IP, or None if unknown."""
    reader = _get_reader()
    if reader is None:
        return None

    ip = get_client_ip(request)
    if not ip:
        return None

    try:
        response = reader.country(ip)
        return response.country.iso_code  # may be None for anonymized/unknown
    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception as e:  # invalid IP string or DB read error
        logger.warning("GeoIP lookup failed for ip=%s: %s", ip, e)
        return None


def _restricted_countries() -> set[str]:
    return {c.strip().upper() for c in settings.OAUTH_GEO_RESTRICTED_COUNTRIES.split(",") if c.strip()}


def _restricted_providers() -> set[str]:
    return {p.strip().lower() for p in settings.OAUTH_GEO_RESTRICTED_PROVIDERS.split(",") if p.strip()}


def is_provider_geo_blocked(provider: str, request: Request) -> bool:
    """Whether ``provider`` must be hidden/blocked for this request's country."""
    if provider.lower() not in _restricted_providers():
        return False

    country = get_country_code(request)
    if country is None:
        # Unknown country: apply the configured fallback policy.
        return not settings.OAUTH_GEO_FALLBACK_ALLOW

    return country.upper() in _restricted_countries()

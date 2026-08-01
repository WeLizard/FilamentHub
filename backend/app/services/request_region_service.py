"""Resolve the current request's access region without profiling the user."""

from __future__ import annotations

import atexit
import ipaddress
import logging
import time
from enum import StrEnum
from pathlib import Path
from threading import Lock

import geoip2.database
from fastapi import Request
from geoip2.errors import AddressNotFoundError
from maxminddb import InvalidDatabaseError

from app.core.config import settings

logger = logging.getLogger(__name__)


class AccessRegion(StrEnum):
    """Coarse request region used only for auth-provider policy."""

    RU = "ru"
    INTL = "intl"
    UNKNOWN = "unknown"


_reader: geoip2.database.Reader | None = None
_reader_path: str | None = None
_reader_signature: tuple[int, int, int, int] | None = None
_reader_lock = Lock()
_reported_reader_errors: set[str] = set()


def _close_reader() -> None:
    global _reader, _reader_path, _reader_signature

    with _reader_lock:
        if _reader is not None:
            _reader.close()
        _reader = None
        _reader_path = None
        _reader_signature = None


atexit.register(_close_reader)


def _trusted_proxy_networks() -> tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network,
    ...,
]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw_network in settings.AUTH_TRUSTED_PROXY_NETWORKS.split(","):
        value = raw_network.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.error("Ignoring invalid trusted proxy network: %s", value)
    return tuple(networks)


def _parse_single_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value or "," in value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def get_request_client_ip(
    request: Request,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return a validated client IP, trusting only our dedicated proxy header."""

    peer = _parse_single_ip(request.client.host if request.client else None)
    if peer is None:
        return None

    peer_is_trusted = any(
        peer.version == network.version and peer in network
        for network in _trusted_proxy_networks()
    )
    if not peer_is_trusted:
        return peer

    forwarded = _parse_single_ip(request.headers.get(settings.AUTH_CLIENT_IP_HEADER))
    return forwarded or peer


def _database_signature(path: str) -> tuple[int, int, int, int]:
    stat = Path(path).stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _reader_for_path(path: str) -> geoip2.database.Reader:
    global _reader, _reader_path, _reader_signature

    with _reader_lock:
        signature = _database_signature(path)
        if (
            _reader is not None
            and _reader_path == path
            and _reader_signature == signature
        ):
            return _reader

        if _reader is not None:
            _reader.close()
            _reader = None
            _reader_path = None
            _reader_signature = None

        for _attempt in range(2):
            signature_before_open = _database_signature(path)
            reader = geoip2.database.Reader(path)
            try:
                signature_after_open = _database_signature(path)
            except OSError:
                reader.close()
                raise

            if signature_before_open == signature_after_open:
                _reader = reader
                _reader_path = path
                _reader_signature = signature_after_open
                return reader

            reader.close()

        raise OSError("GeoIP country database changed repeatedly while opening")


def _report_reader_error_once(error_key: str, message: str, *args: object) -> None:
    if error_key in _reported_reader_errors:
        return
    _reported_reader_errors.add(error_key)
    logger.warning(message, *args)


def _lookup_country_code(
    client_ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> str | None:
    database_path = settings.GEOIP_COUNTRY_DB_PATH
    if not database_path or not Path(database_path).is_file():
        _report_reader_error_once(
            f"missing:{database_path}",
            "GeoIP country database is unavailable; auth region is fail-closed",
        )
        return None

    try:
        response = _reader_for_path(database_path).country(str(client_ip))
        return response.country.iso_code
    except AddressNotFoundError:
        return None
    except (FileNotFoundError, PermissionError, InvalidDatabaseError, ValueError, OSError) as exc:
        _report_reader_error_once(
            f"{type(exc).__name__}:{database_path}",
            "GeoIP country lookup failed; auth region is fail-closed: %s",
            type(exc).__name__,
        )
        return None


def resolve_request_country_code(request: Request) -> str | None:
    """Return the transient ISO country code for server-side policy selection.

    The value is cached only for the lifetime of the request and is not exposed
    to the client or written to the user profile.
    """
    cached = getattr(request.state, "request_country_code", None)
    if cached is not None:
        return cached or None

    if settings.AUTH_REGION_MODE == "static_ru":
        country_code = "RU"
    elif settings.AUTH_REGION_MODE in {"static_intl", "development"}:
        country_code = None
    else:
        client_ip = get_request_client_ip(request)
        country_code = (
            _lookup_country_code(client_ip)
            if client_ip is not None and client_ip.is_global
            else None
        )

    request.state.request_country_code = country_code or ""
    return country_code


def geoip_database_health() -> dict[str, str | bool | int | None]:
    """Return a coarse readiness signal without exposing the database path."""
    mode = settings.AUTH_REGION_MODE
    if mode != "geoip":
        return {
            "mode": mode,
            "ready": True,
            "database_build_epoch": None,
            "database_age_seconds": None,
        }

    database_path = settings.GEOIP_COUNTRY_DB_PATH
    if not database_path or not Path(database_path).is_file():
        return {
            "mode": mode,
            "ready": False,
            "database_build_epoch": None,
            "database_age_seconds": None,
        }

    try:
        build_epoch = int(_reader_for_path(database_path).metadata().build_epoch)
    except (FileNotFoundError, PermissionError, InvalidDatabaseError, ValueError, OSError):
        return {
            "mode": mode,
            "ready": False,
            "database_build_epoch": None,
            "database_age_seconds": None,
        }

    return {
        "mode": mode,
        "ready": True,
        "database_build_epoch": build_epoch,
        "database_age_seconds": max(0, int(time.time()) - build_epoch),
    }


def resolve_access_region(request: Request) -> AccessRegion:
    """Resolve request region for auth policy.

    This intentionally does not inspect language, time zone, email, profile
    country, name, citizenship, or VPN use.
    """

    if settings.AUTH_REGION_MODE == "static_ru":
        return AccessRegion.RU
    if settings.AUTH_REGION_MODE in {"static_intl", "development"}:
        return AccessRegion.INTL

    country_code = resolve_request_country_code(request)
    if not country_code:
        return AccessRegion.UNKNOWN
    if country_code.upper() == "RU":
        return AccessRegion.RU
    return AccessRegion.INTL

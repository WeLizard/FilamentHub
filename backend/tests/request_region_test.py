"""Tests for request-scoped auth region resolution."""

import ipaddress

from starlette.requests import Request

from app.core.config import settings
from app.services import request_region_service
from app.services.request_region_service import (
    AccessRegion,
    geoip_database_health,
    get_request_client_ip,
    resolve_access_region,
)


def _request(
    client_host: str,
    headers: dict[str, str] | None = None,
) -> Request:
    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/auth/methods",
            "raw_path": b"/api/v1/auth/methods",
            "query_string": b"",
            "headers": encoded_headers,
            "client": (client_host, 12345),
            "server": ("filamenthub.ru", 443),
        }
    )


def test_client_ip_uses_dedicated_header_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_TRUSTED_PROXY_NETWORKS", "172.16.0.0/12")
    monkeypatch.setattr(settings, "AUTH_CLIENT_IP_HEADER", "X-FilamentHub-Client-IP")

    trusted_request = _request(
        "172.20.0.5",
        {
            "X-FilamentHub-Client-IP": "8.8.8.8",
            "X-Forwarded-For": "77.88.8.8",
        },
    )
    assert get_request_client_ip(trusted_request) == ipaddress.ip_address("8.8.8.8")

    untrusted_request = _request(
        "1.1.1.1",
        {"X-FilamentHub-Client-IP": "8.8.8.8"},
    )
    assert get_request_client_ip(untrusted_request) == ipaddress.ip_address("1.1.1.1")


def test_client_ip_rejects_multi_value_dedicated_header(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_TRUSTED_PROXY_NETWORKS", "172.16.0.0/12")
    request = _request(
        "172.20.0.5",
        {"X-FilamentHub-Client-IP": "8.8.8.8, 1.1.1.1"},
    )

    assert get_request_client_ip(request) == ipaddress.ip_address("172.20.0.5")


def test_geoip_region_resolution_is_ru_intl_or_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "geoip")
    request = _request("8.8.8.8")

    monkeypatch.setattr(request_region_service, "_lookup_country_code", lambda _ip: "RU")
    assert resolve_access_region(request) == AccessRegion.RU

    monkeypatch.setattr(request_region_service, "_lookup_country_code", lambda _ip: "DE")
    assert resolve_access_region(request) == AccessRegion.INTL

    monkeypatch.setattr(request_region_service, "_lookup_country_code", lambda _ip: None)
    assert resolve_access_region(request) == AccessRegion.UNKNOWN


def test_private_or_local_address_is_unknown_without_geoip_lookup(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "geoip")

    def unexpected_lookup(_ip):
        raise AssertionError("GeoIP lookup must not run for non-global addresses")

    monkeypatch.setattr(request_region_service, "_lookup_country_code", unexpected_lookup)
    assert resolve_access_region(_request("127.0.0.1")) == AccessRegion.UNKNOWN
    assert resolve_access_region(_request("192.168.1.20")) == AccessRegion.UNKNOWN


def test_geoip_health_is_fail_closed_when_database_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "geoip")
    monkeypatch.setattr(
        settings,
        "GEOIP_COUNTRY_DB_PATH",
        str(tmp_path / "missing-country.mmdb"),
    )

    assert geoip_database_health() == {
        "mode": "geoip",
        "ready": False,
        "database_build_epoch": None,
        "database_age_seconds": None,
    }


def test_geoip_health_does_not_require_database_for_static_modes(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_ru")

    assert geoip_database_health() == {
        "mode": "static_ru",
        "ready": True,
        "database_build_epoch": None,
        "database_age_seconds": None,
    }


def test_reader_reloads_after_atomic_database_replacement(monkeypatch, tmp_path):
    database_path = tmp_path / "country.mmdb"
    database_path.write_bytes(b"first")
    opened_readers = []

    class FakeReader:
        def __init__(self, path):
            self.path = path
            self.closed = False
            opened_readers.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(request_region_service.geoip2.database, "Reader", FakeReader)
    request_region_service._close_reader()

    try:
        first = request_region_service._reader_for_path(str(database_path))
        assert request_region_service._reader_for_path(str(database_path)) is first
        assert len(opened_readers) == 1

        replacement = tmp_path / "replacement.mmdb"
        replacement.write_bytes(b"second database")
        replacement.replace(database_path)

        second = request_region_service._reader_for_path(str(database_path))
        assert second is not first
        assert first.closed is True
        assert len(opened_readers) == 2
    finally:
        request_region_service._close_reader()


def test_reader_retries_when_database_changes_during_open(monkeypatch):
    opened_readers = []
    signatures = iter(
        [
            (1, 1, 100, 1),
            (1, 1, 100, 1),
            (1, 2, 200, 2),
            (1, 2, 200, 2),
            (1, 2, 200, 2),
        ]
    )

    class FakeReader:
        def __init__(self, path):
            self.path = path
            self.closed = False
            opened_readers.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(request_region_service, "_database_signature", lambda _path: next(signatures))
    monkeypatch.setattr(request_region_service.geoip2.database, "Reader", FakeReader)
    request_region_service._close_reader()

    try:
        reader = request_region_service._reader_for_path("country.mmdb")
        assert reader is opened_readers[1]
        assert opened_readers[0].closed is True
        assert reader.closed is False
    finally:
        request_region_service._close_reader()

"""Tests for geo-IP based OAuth provider restrictions (RF law gating)."""

from types import SimpleNamespace

from app.services import geoip_service


def _fake_request(headers=None, client_host="9.9.9.9"):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=client_host))


# ── client IP extraction ─────────────────────────────────────────────

def test_get_client_ip_prefers_forwarded_for():
    req = _fake_request(headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
    assert geoip_service.get_client_ip(req) == "1.2.3.4"


def test_get_client_ip_falls_back_to_real_ip():
    req = _fake_request(headers={"x-real-ip": "8.8.8.8"})
    assert geoip_service.get_client_ip(req) == "8.8.8.8"


def test_get_client_ip_falls_back_to_peer():
    assert geoip_service.get_client_ip(_fake_request()) == "9.9.9.9"


# ── provider gating logic ────────────────────────────────────────────

def test_non_restricted_provider_never_blocked(monkeypatch):
    monkeypatch.setattr(geoip_service, "get_country_code", lambda req: "RU")
    assert geoip_service.is_provider_geo_blocked("yandex", _fake_request()) is False


def test_restricted_provider_blocked_in_restricted_country(monkeypatch):
    monkeypatch.setattr(geoip_service, "get_country_code", lambda req: "RU")
    assert geoip_service.is_provider_geo_blocked("google", _fake_request()) is True


def test_restricted_provider_allowed_elsewhere(monkeypatch):
    monkeypatch.setattr(geoip_service, "get_country_code", lambda req: "US")
    assert geoip_service.is_provider_geo_blocked("google", _fake_request()) is False


def test_unknown_country_fallback_allow(monkeypatch):
    monkeypatch.setattr(geoip_service, "get_country_code", lambda req: None)
    monkeypatch.setattr(geoip_service.settings, "OAUTH_GEO_FALLBACK_ALLOW", True)
    assert geoip_service.is_provider_geo_blocked("google", _fake_request()) is False


def test_unknown_country_fallback_block(monkeypatch):
    monkeypatch.setattr(geoip_service, "get_country_code", lambda req: None)
    monkeypatch.setattr(geoip_service.settings, "OAUTH_GEO_FALLBACK_ALLOW", False)
    assert geoip_service.is_provider_geo_blocked("google", _fake_request()) is True


def test_country_match_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(geoip_service, "get_country_code", lambda req: "ru")
    assert geoip_service.is_provider_geo_blocked("google", _fake_request()) is True


# ── public endpoint ──────────────────────────────────────────────────

async def test_oauth_providers_endpoint_lists_known_providers(client):
    resp = await client.get("/api/v1/auth/oauth-providers")
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    assert "google" in providers
    assert "yandex" in providers
    # OAuth client IDs are not configured in tests → both unavailable.
    assert providers["google"] is False
    assert providers["yandex"] is False


async def test_oauth_url_geo_blocked_returns_403(client, monkeypatch):
    # Pretend Google is configured but the caller is in a restricted country.
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.is_provider_configured", lambda provider: True
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.auth.is_provider_geo_blocked", lambda provider, request: True
    )
    resp = await client.get("/api/v1/auth/oauth/google/url")
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "ERR_OAUTH_PROVIDER_UNAVAILABLE"

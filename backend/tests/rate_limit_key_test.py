"""A rate limit must count one person, not the proxy every request passes through."""

from types import SimpleNamespace

from app.core.config import settings
from app.core.limiter import client_key


def _request(peer: str, headers: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_visitors_behind_the_proxy_are_counted_separately(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_TRUSTED_PROXY_NETWORKS", "172.30.0.10/32")
    header = settings.AUTH_CLIENT_IP_HEADER

    first = client_key(_request("172.30.0.10", {header: "203.0.113.7"}))
    second = client_key(_request("172.30.0.10", {header: "198.51.100.4"}))

    assert first == "203.0.113.7"
    assert second == "198.51.100.4"
    assert first != second


def test_the_header_is_ignored_when_it_does_not_come_from_the_proxy(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_TRUSTED_PROXY_NETWORKS", "172.30.0.10/32")
    header = settings.AUTH_CLIENT_IP_HEADER

    # Someone reaching the backend directly must not be able to claim any address
    # and hand themselves a fresh budget on every request.
    forged = client_key(_request("203.0.113.9", {header: "198.51.100.4"}))

    assert forged == "203.0.113.9"


def test_a_missing_header_falls_back_to_the_peer(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_TRUSTED_PROXY_NETWORKS", "172.30.0.10/32")

    assert client_key(_request("172.30.0.10", {})) == "172.30.0.10"

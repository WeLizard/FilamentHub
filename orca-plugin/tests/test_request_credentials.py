"""Credentials sent by the plugin stay with the origin they were issued for."""

from __future__ import annotations

import io
import re
import urllib.error
import urllib.request
from email.message import Message

from .filamenthub_plugin_test_support import PLUGIN_PATH


class _Response(io.BytesIO):
    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


def _follow(request, code):
    try:
        return urllib.request.HTTPRedirectHandler().redirect_request(
            request, io.BytesIO(), code, "Redirect", Message(), "https://elsewhere.example/x"
        )
    except urllib.error.HTTPError:
        return None


def _captured_requests(plugin, monkeypatch):
    captured = []

    def urlopen(request, **_kwargs):
        captured.append(request)
        return _Response(b"{}")

    monkeypatch.setattr(plugin.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(plugin, "external_operation", lambda: _Response())
    return captured


def test_credentials_are_not_carried_across_a_redirect(plugin_module, monkeypatch):
    plugin = plugin_module
    captured = _captured_requests(plugin, monkeypatch)

    plugin.http_get("/auth/me", token="site-token")
    plugin.http_post_json("/orcaslicer/sync-plan", "site-token", {"a": 1})
    plugin.http_post_bridge_json("/printer-bridge/snapshot", "fhpb_bridge", {"a": 1})
    plugin.http_get_bridge_json("/printer-bridge/identity-context", "fhpb_bridge")
    plugin.http_delete_bridge("/printer-bridge/connection", "fhpb_bridge")
    plugin.http_get_bearer("/stock-alerts", "site-token")
    plugin._moonraker_json(
        {"print_host": "http://printer.local:7125", "api_key": "moonraker-key"},
        "/printer/info",
    )

    assert len(captured) == 7
    for request in captured:
        sent = {name.lower() for name, _value in request.header_items()}
        assert len(sent & plugin._CREDENTIAL_HEADERS) == 1, request.full_url
        for code in (301, 302, 303, 307, 308):
            followed = _follow(request, code)
            if followed is None:
                # urllib refuses to replay this method on this status.
                continue
            forwarded = {name.lower() for name, _value in followed.header_items()}
            assert not forwarded & plugin._CREDENTIAL_HEADERS, request.full_url
            assert followed.data is None


def test_every_request_is_built_by_the_credential_aware_helper():
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    assert len(re.findall(r"urllib\.request\.Request\(", source)) == 1

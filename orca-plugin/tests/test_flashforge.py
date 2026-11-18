"""Flashforge printers linked through OrcaSlicer's own connection settings."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import PLUGIN_ROOT, set_host_attr

# One fixture and one expected reading are shared with FH Edge, which reads the
# same printer API with its own code.
EDGE_FIXTURES = PLUGIN_ROOT.parent / "edge-agent" / "tests" / "fixtures" / "flashforge"
DISCOVERY_KEY = "ab" * 32
SERIAL = "SNMQRB9400123"
CHECK_CODE = "a1b2c3d4"


def _detail():
    return json.loads((EDGE_FIXTURES / "detail_printing.json").read_text(encoding="utf-8"))["detail"]


def _connection(label="Creator 5 Pro 0.4", serial=SERIAL, check_code=CHECK_CODE):
    return {"label": label, "host": "192.168.1.40", "serial": serial, "check_code": check_code}


@pytest.fixture
def bridge(plugin_module, monkeypatch, tmp_path):
    """The plugin with its private storage, the printer and the site faked."""
    plugin = plugin_module
    calls = SimpleNamespace(paired=[], posted=[], revoked=[], reads=[], pair_ids=(7, 9))
    monkeypatch.setattr(plugin, "FLASHFORGE_CONFIG_FILE", str(tmp_path / ".fh_flashforge.json"))
    monkeypatch.setattr(plugin, "plugin_source_instance_id", lambda: "desktop-source-instance")

    def read(connection):
        calls.reads.append(connection)
        return _detail(), None

    def pair(path, token, payload):
        calls.paired.append((path, token, payload))
        return 200, json.dumps({
            "bridge_token": "fhpb_" + "t" * 40,
            "physical_printer_id": calls.pair_ids[0],
            "material_system_id": calls.pair_ids[1],
            "printer_discovery_key": DISCOVERY_KEY,
        }).encode("utf-8")

    def post(path, token, payload):
        calls.posted.append((path, token, payload))
        return calls.__dict__.get("post_status", 200), calls.__dict__.get("post_body", b"{}"), None

    monkeypatch.setattr(plugin, "read_flashforge_detail", read)
    monkeypatch.setattr(plugin, "http_post_json", pair)
    monkeypatch.setattr(plugin, "http_post_bridge_json", post)
    monkeypatch.setattr(plugin, "revoke_fresh_bridge_token", calls.revoked.append)
    monkeypatch.setattr(
        plugin, "http_delete_bridge", lambda _path, token: calls.revoked.append(token) or 204
    )
    return plugin, calls, Path(plugin.FLASHFORGE_CONFIG_FILE)


def test_snapshot_matches_the_reading_shared_with_edge(plugin_module):
    expected = json.loads(
        (EDGE_FIXTURES / "detail_printing.expected.json").read_text(encoding="utf-8")
    )
    binding = {"material_system_id": 9, "device_identity": {"kind": "flashforge_serial", "token": "0" * 64}}

    snapshot = plugin_module.build_flashforge_bridge_snapshot(binding, "source", _detail())

    assert {key: snapshot[key] for key in expected} == expected
    assert (snapshot["provider"], snapshot["transport"]) == ("flashforge", "orca_plugin_lan")
    # No per-tool usage exists on this API, so consumption is never claimed.
    assert snapshot["capabilities"] == ["read", "presence"]


def test_connections_come_from_orcas_flashforge_printer_presets(plugin_module, monkeypatch):
    def preset(name, user, **config):
        return SimpleNamespace(
            name=name, is_user=lambda: user, config_value=lambda key: config.get(key)
        )

    presets = [
        preset("Creator 5 Pro 0.4", True, host_type="flashforge", print_host="http://192.168.1.40:8898",
               flashforge_serial_number=" snmqrb9400123 ", printhost_apikey=CHECK_CODE),
        preset("Voron", True, host_type="moonraker", print_host="192.168.1.50",
               printhost_apikey="moonraker-key"),
        preset("Flashforge stock", False, host_type="flashforge", print_host="192.168.1.41"),
    ]
    printers = SimpleNamespace(size=lambda: len(presets), preset=lambda index: presets[index])
    set_host_attr(
        monkeypatch, plugin_module.orca.host, "preset_bundle",
        lambda: SimpleNamespace(printers=printers),
    )

    assert plugin_module._snapshot_local_flashforge_connections() == [
        {"label": "Creator 5 Pro 0.4", "host": "192.168.1.40", "serial": SERIAL,
         "check_code": CHECK_CODE},
    ]


def test_linking_pairs_the_printer_and_keeps_its_credentials_out_of_storage(bridge):
    plugin, calls, store = bridge

    result = plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", [_connection()])

    assert result == {"ok": True, "code": "ok"}
    _path, _token, pairing = calls.paired[0]
    assert (pairing["provider"], pairing["transport"]) == ("flashforge", "orca_plugin_lan")
    assert pairing["capabilities"] == ["read", "presence"]
    # The same account-scoped evidence FH Edge computes for this serial number.
    evidence = hmac.new(
        bytes.fromhex(DISCOVERY_KEY),
        ("device\0flashforge_serial\0" + SERIAL).encode(),
        hashlib.sha256,
    ).hexdigest()
    path, token, snapshot = calls.posted[0]
    assert path == "/printer-bridge/snapshot" and token.startswith("fhpb_")
    assert snapshot["device_identity"] == {"kind": "flashforge_serial", "token": evidence}
    stored = store.read_text(encoding="utf-8")
    assert CHECK_CODE not in stored and "192.168.1.40" not in stored
    # Neither the serial number nor the check code is sent to FilamentHub.
    sent = json.dumps([pairing, snapshot])
    assert SERIAL not in sent and CHECK_CODE not in sent


def test_linking_asks_which_printer_before_using_the_one_time_code(bridge):
    plugin, calls, store = bridge
    connections = [_connection(), _connection("AD5X", serial="SNADXA0000042")]

    result = plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", connections)

    assert result["code"] == "choose"
    assert [item["label"] for item in result["candidates"]] == ["Creator 5 Pro 0.4", "AD5X"]
    assert not calls.reads and not calls.paired and not store.exists()

    chosen = result["candidates"][1]["connectionRef"]
    assert plugin.configure_flashforge_bridge(
        7, 9, "FH-ABCDE-12345", chosen, connections
    ) == {"ok": True, "code": "ok"}
    assert calls.reads[0]["serial"] == "SNADXA0000042"


def test_linking_stops_before_pairing_when_orca_lacks_the_credentials(bridge):
    plugin, calls, _store = bridge

    assert plugin.configure_flashforge_bridge(
        7, 9, "FH-ABCDE-12345", "", [_connection(check_code="")]
    ) == {"ok": False, "code": "credentials"}
    assert plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", []) == {
        "ok": False, "code": "notFound",
    }
    assert not calls.reads and not calls.paired


def test_a_code_issued_for_another_printer_card_is_given_back(bridge):
    plugin, calls, store = bridge
    calls.pair_ids = (8, 9)

    result = plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", [_connection()])

    assert result == {"ok": False, "code": "pairing"}
    assert calls.revoked == ["fhpb_" + "t" * 40]
    assert not store.exists() and not calls.posted


def test_one_printer_cannot_feed_two_printer_cards(bridge):
    plugin, calls, _store = bridge
    assert plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", [_connection()])["ok"]
    calls.paired.clear()

    assert plugin.configure_flashforge_bridge(
        11, 12, "FH-ZZZZZ-99999", "", [_connection()]
    ) == {"ok": False, "code": "linked"}
    assert not calls.paired


def test_a_printer_the_account_knows_as_another_card_is_not_left_half_linked(bridge):
    plugin, calls, store = bridge
    calls.post_status = 409
    calls.post_body = b'{"detail": {"code": "ERR_PRINTER_IDENTITY_CONFLICT"}}'

    result = plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", [_connection()])

    assert result == {"ok": False, "code": "linked"}
    assert calls.revoked == ["fhpb_" + "t" * 40]
    assert json.loads(store.read_text(encoding="utf-8"))["printers"] == []


def test_refresh_reports_the_printer_and_drops_a_link_the_server_revoked(bridge):
    plugin, calls, store = bridge
    assert plugin.configure_flashforge_bridge(7, 9, "FH-ABCDE-12345", "", [_connection()])["ok"]
    calls.posted.clear()

    assert plugin.observe_flashforge_bindings([_connection()]) == {7: "ok"}
    assert calls.posted[0][0] == "/printer-bridge/snapshot"

    # The preset lost its check code: say the printer is unreachable, keep the link.
    calls.posted.clear()
    assert plugin.observe_flashforge_bindings([_connection(check_code="")], 7, 9) == {
        7: "credentials",
    }
    path, _token, heartbeat = calls.posted[0]
    assert path == "/printer-bridge/heartbeat" and heartbeat["provider_reachable"] is False
    assert json.loads(store.read_text(encoding="utf-8"))["printers"]

    calls.post_status = 401
    assert plugin.observe_flashforge_bindings([_connection()]) == {7: "unpaired"}
    assert json.loads(store.read_text(encoding="utf-8"))["printers"] == []


def test_the_check_code_is_sent_only_to_a_private_address(plugin_module, monkeypatch):
    plugin = plugin_module
    opened = []

    def getaddrinfo(host, port, **_kwargs):
        address = {"printer.lan": "192.168.1.40", "printer.example": "8.8.8.8"}[host]
        return [(2, 1, 6, "", (address, port))]

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def getcode(self):
            return 200

        def read(self, _limit):
            return json.dumps({"code": 0, "message": "Success", "detail": _detail()}).encode()

    def urlopen(request, **_kwargs):
        opened.append(request)
        return Response()

    monkeypatch.setattr(plugin.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(plugin.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(plugin, "external_operation", lambda: Response())

    detail, failure = plugin.read_flashforge_detail(dict(_connection(), host="printer.example"))
    assert (detail, failure, opened) == (None, "unreachable", [])

    detail, failure = plugin.read_flashforge_detail(dict(_connection(), host="printer.lan"))
    assert failure is None and detail["status"] == "printing"
    assert opened[0].full_url == "http://192.168.1.40:8898/detail"
    assert json.loads(opened[0].data) == {"serialNumber": SERIAL, "checkCode": CHECK_CODE}

    # OrcaSlicer has not allowed this address yet: a distinct, actionable result.
    def denied(_request, **_kwargs):
        raise plugin.urllib.error.URLError(PermissionError("denied by the host"))

    monkeypatch.setattr(plugin.urllib.request, "urlopen", denied)
    assert plugin.read_flashforge_detail(dict(_connection(), host="printer.lan")) == (
        None, "permission",
    )

"""Flashforge printers linked through OrcaSlicer's own connection settings."""

from __future__ import annotations

import copy
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
    assert snapshot["capabilities"] == ["read", "presence", "consumption"]


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
    assert pairing["capabilities"] == ["read", "presence", "consumption"]
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


def _detail_with(overrides):
    """The fixture reading with some fields replaced; None removes a field."""
    detail = copy.deepcopy(_detail())
    for key, value in overrides.items():
        target = detail["matlStationInfo"] if key == "currentSlot" else detail
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value
    return detail


def test_usage_books_match_the_print_scenario_shared_with_edge(plugin_module):
    # FH Edge follows the same printer with its own tracker. One job, told
    # reading by reading, must cost the same whichever of the two watched it.
    scenario = json.loads((EDGE_FIXTURES / "usage_scenario.json").read_text(encoding="utf-8"))
    books = {}

    for step, expected in zip(scenario["steps"], scenario["expected"], strict=True):
        detail = _detail_with(step["detail"])
        slots, _complete = plugin_module.flashforge_slots(detail)
        events = plugin_module.capture_flashforge_usage(
            books,
            plugin_module.flashforge_usage(detail),
            plugin_module.flashforge_usage_route(slots, scenario["desired"]),
            step["at"],
        )
        for event in events:
            event.pop("job_id")
            for item in event["items"]:
                item["used_length_mm"] = round(item["used_length_mm"], 3)
        assert events == expected, step["at"]


@pytest.fixture
def watched(bridge, monkeypatch):
    """A linked printer, its connection copied from OrcaSlicer, and a watcher driven by hand."""
    plugin, calls, _stored = bridge
    plugin.configure_flashforge_bridge(7, 9, "FH-AAAAA-BBBBB", "", [_connection()])
    calls.posted.clear()
    calls.reads.clear()
    calls.desired = []
    calls.reading = {"status": "ready"}
    calls.failure = None
    monkeypatch.setitem(plugin._FLASHFORGE_CONNECTIONS, "items", [_connection()])
    monkeypatch.setattr(plugin, "FLASHFORGE_USAGE_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(plugin, "FLASHFORGE_SNAPSHOT_MIN_SECONDS", 0.0)

    def read(connection):
        calls.reads.append(connection)
        if calls.failure:
            return None, calls.failure
        return _detail_with(calls.reading), None

    def desired(path, token):
        calls.desired.append(path)
        return 200, json.dumps({"slots": [{
            "index": 0, "usage_route_proof": "proof-slot-1", "spool": {"id": 11},
        }]}).encode("utf-8")

    monkeypatch.setattr(plugin, "read_flashforge_detail", read)
    monkeypatch.setattr(plugin, "http_get_bridge_json", desired)

    def batches():
        return [payload for path, _token, payload in calls.posted if path.endswith("usage-batches")]

    def at(status, progress):
        calls.reading = {"status": status, "printProgress": progress}

    return SimpleNamespace(plugin=plugin, calls=calls, batches=batches, at=at,
                           runtime=plugin.FlashforgeWatchRuntime())


def test_a_watched_print_is_charged_once_even_when_the_answer_is_lost(watched):
    plugin, calls = watched.plugin, watched.calls
    watched.at("printing", 0.10)
    assert watched.runtime.watch_once() == plugin.FLASHFORGE_WATCH_PRINTING_SECONDS
    watched.at("printing", 0.50)
    watched.runtime.watch_once()
    assert watched.batches() == []

    # The job ends, and the site's answer to the batch never arrives.
    calls.post_status = 0
    watched.at("completed", 0.99)
    assert watched.runtime.watch_once() == plugin.FLASHFORGE_WATCH_IDLE_SECONDS
    (lost,) = watched.batches()
    (event,) = lost["events"]
    (item,) = event["items"]
    assert (lost["provider"], lost["transport"], lost["sequence"]) == (
        "flashforge", "orca_plugin_lan", 1,
    )
    assert (event["event_type"], event["outcome"]) == ("terminal", "completed")
    # From the first reading (10 %) to the whole estimate of the fixture job.
    assert item["used_length_mm"] == pytest.approx(6170.0 * 0.9)
    assert (item["spool_id"], item["usage_route_proof"]) == (11, "proof-slot-1")
    assert (item["consumption_kind"], item["estimate_source"]) == ("estimated", "slicer_progress")

    # OrcaSlicer is restarted: the same batch is offered again, unchanged, and
    # once it is acknowledged nothing is sent a second time.
    calls.post_status = 200
    calls.post_body = json.dumps({"accepted": True, "ack_sequence": 1}).encode("utf-8")
    restarted = plugin.FlashforgeWatchRuntime()
    restarted.watch_once()
    assert watched.batches() == [lost, lost]
    restarted.watch_once()
    plugin.FlashforgeWatchRuntime().watch_once()
    assert watched.batches() == [lost, lost]


def test_an_idle_printer_costs_the_site_nothing(watched):
    watched.runtime.watch_once()
    reports = len(watched.calls.posted)
    assert reports == 1  # what the printer says, once

    # Nothing changed but a nozzle cooling down.
    watched.calls.reading = {"status": "ready", "nozzleTemps": [31.0, 25.1, 24.9, 25.0]}
    watched.runtime.watch_once()

    assert len(watched.calls.posted) == reports
    assert watched.calls.desired == []


def test_a_printer_orcaslicer_has_not_allowed_is_left_alone_until_the_person_acts(
    watched, monkeypatch
):
    # Every attempt on an address OrcaSlicer has not allowed is another
    # permission question on the person's screen.
    watched.calls.failure = "permission"
    watched.runtime.watch_once()
    watched.runtime.watch_once()
    assert len(watched.calls.reads) == 1

    monkeypatch.setattr(watched.runtime, "start", lambda: None)
    watched.runtime.wake()
    watched.runtime.watch_once()
    assert len(watched.calls.reads) == 2


def test_books_that_fell_behind_the_server_take_its_number(watched):
    plugin, calls = watched.plugin, watched.calls
    watched.at("printing", 0.10)
    watched.runtime.watch_once()
    calls.post_status = 409
    calls.post_body = json.dumps({"detail": {
        "code": "ERR_PRINTER_BRIDGE_BATCH_OUT_OF_ORDER", "params": {"expected_sequence": 5},
    }}).encode("utf-8")
    watched.at("completed", 1.0)
    watched.runtime.watch_once()

    calls.post_status = 200
    calls.post_body = json.dumps({"accepted": True, "ack_sequence": 5}).encode("utf-8")
    watched.runtime.watch_once()

    refused, accepted = watched.batches()
    assert (refused["sequence"], accepted["sequence"]) == (1, 5)
    # The same events under the server's number: nothing is counted twice.
    assert [event["event_id"] for event in accepted["events"]] == [
        event["event_id"] for event in refused["events"]
    ]


def test_a_link_the_site_revoked_is_dropped_by_the_watcher(watched):
    plugin = watched.plugin
    watched.at("printing", 0.10)
    plugin.http_get_bridge_json = lambda path, token: (401, b"")

    watched.runtime.watch_once()

    assert plugin._load_flashforge_bindings() == []
    # Nothing is linked any more, so the thread has nothing to stay for.
    assert watched.runtime.watch_once() is None

"""Prusa printers linked through OrcaSlicer's PrusaLink connection settings."""

from __future__ import annotations

import email.message
import hashlib
import io
import json
import re
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from .filamenthub_plugin_test_support import PLUGIN_ROOT

# The fixtures are shared with FH Edge, which will read the same printers.
FIXTURES = PLUGIN_ROOT.parent / "edge-agent" / "tests" / "fixtures" / "prusalink"
DISCOVERY_KEY = "cd" * 32
BUDDY_SERIAL = "10589-3742441632176154"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _digest_fields(header):
    assert header.startswith("Digest ")
    return {
        name: quoted if quoted else bare
        for name, quoted, bare in re.findall(r'(\w+)=(?:"([^"]*)"|([^\s,]+))', header[7:])
    }


class _FakePrusaPrinter:
    """Answers GET requests the way Buddy or Prusa-Link does, login included.

    The login check follows the firmware: Buddy compares MD5(HA1:nonce:HA2)
    for user ``maker`` and realm ``Printer API``; Prusa-Link (PoorWSGI) uses
    MD5-sess with ``qop=auth`` and checks ``opaque``.
    """

    def __init__(self, firmware="buddy", *, key="secret-key", user="maker", password="pa55word"):
        self.firmware = firmware
        self.key, self.user, self.password = key, user, password
        self.answers = {}
        self.requests = []
        self.nonce = "0123456789abcdef"
        if firmware == "buddy":
            self.answers.update({
                "/api/version": _fixture("buddy_version.json"),
                "/api/v1/info": _fixture("buddy_info.json"),
                "/api/v1/status": _fixture("buddy_status_printing.json"),
                "/api/v1/job": _fixture("buddy_job.json"),
                "/api/printer": _fixture("buddy_printer.json"),
            })
        else:
            self.answers.update({
                "/api/version": _fixture("prusalink_version.json"),
                "/api/v1/info": _fixture("prusalink_info.json"),
                "/api/v1/status": _fixture("prusalink_status_idle.json"),
                "/api/printer": {"telemetry": {"material": " - "}},
            })

    @property
    def realm(self):
        return "Printer API" if self.firmware == "buddy" else "Administrator"

    def _challenge(self):
        if self.firmware == "buddy":
            return 'Digest realm="Printer API", nonce="%s", stale=false' % self.nonce
        return (
            'Digest realm="Administrator",qop="auth",algorithm="MD5-sess",'
            'nonce="%s",opaque="op4que"' % self.nonce
        )

    def _digest_ok(self, header, path):
        fields = _digest_fields(header)
        if fields.get("nonce") != self.nonce or fields.get("uri") != path:
            return False
        secret = _md5("%s:%s:%s" % (self.user, self.realm, self.password))
        target = _md5("GET:" + path)
        if self.firmware == "buddy":
            expected = _md5("%s:%s:%s" % (secret, self.nonce, target))
        else:
            if fields.get("opaque") != "op4que" or fields.get("algorithm") != "MD5-sess":
                return False
            secret = _md5("%s:%s:%s" % (secret, self.nonce, fields["cnonce"]))
            expected = _md5(":".join((
                secret, self.nonce, fields["nc"], fields["cnonce"], fields["qop"], target,
            )))
        return fields.get("username") == self.user and fields.get("response") == expected

    def _refuse(self, url, code, challenge=None):
        headers = email.message.Message()
        if challenge:
            headers["WWW-Authenticate"] = challenge
        raise urllib.error.HTTPError(url, code, "refused", headers, io.BytesIO(b""))

    def urlopen(self, request, timeout):
        assert request.get_method() == "GET"
        url = request.full_url
        path = "/" + url.split("/", 3)[3]
        self.requests.append(path)
        key = request.get_header("X-api-key")
        authorization = request.get_header("Authorization")
        if key is not None:
            if key != self.key:
                self._refuse(url, 401 if self.firmware == "buddy" else 403)
        elif authorization is None or not self._digest_ok(authorization, path):
            self._refuse(url, 401, self._challenge())
        answer = self.answers.get(path)
        if answer is None:
            self._refuse(url, 404)
        status, body = (204, b"") if answer == 204 else (200, json.dumps(answer).encode())
        return _Response(status, body)


class _Response:
    def __init__(self, status, body):
        self.status, self.body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        return self.body


def _connection(plugin, mode="key", host="192.168.1.60", **login):
    if mode == "key":
        credentials = plugin.prusalink_credentials("key", login.get("key", "secret-key"), "", "")
    else:
        credentials = plugin.prusalink_credentials(
            "user", "", login.get("user", "maker"), login.get("password", "pa55word"),
        )
    return {"label": "Prusa MK4S 0.4", "host": host, "port": 80, "credentials": credentials}


@pytest.fixture
def printer(plugin_module, monkeypatch):
    plugin = plugin_module
    fake = SimpleNamespace(device=_FakePrusaPrinter())

    def use(device):
        fake.device = device

    monkeypatch.setattr(plugin, "_PRUSALINK_KNOWN_HOSTS", {})
    monkeypatch.setattr(
        plugin, "_resolved_lan_address", lambda host, port, *_: (2, 1, 6, (host, port))
    )
    monkeypatch.setattr(
        plugin, "_urlopen_authorized", lambda request, timeout: fake.device.urlopen(request, timeout)
    )
    return SimpleNamespace(plugin=plugin, fake=fake, use=use)


def test_orca_profile_address_and_login_are_read_as_orca_writes_them(plugin_module):
    plugin = plugin_module
    assert plugin.prusalink_endpoint("192.168.1.60") == ("192.168.1.60", 80)
    assert plugin.prusalink_endpoint("http://prusa-mk3s.local:8080/") == ("prusa-mk3s.local", 8080)
    # A proxy, a path or a login in the address is not the printer itself.
    assert plugin.prusalink_endpoint("https://printer.example") is None
    assert plugin.prusalink_endpoint("192.168.1.60/prusa") is None
    assert plugin.prusalink_endpoint("http://maker:pass@192.168.1.60") is None
    # Orca's default is the API key; "user" is HTTP Digest.
    assert plugin.prusalink_credentials("", "k3y", "", "") == {"mode": "key", "key": "k3y"}
    assert plugin.prusalink_credentials("user", "k3y", "maker", "pw") == {
        "mode": "digest", "user": "maker", "password": "pw",
    }
    assert plugin.prusalink_credentials(1, "", "maker", "pw")["mode"] == "digest"
    assert plugin.prusalink_credentials("key", "", "maker", "pw") is None
    assert plugin.prusalink_credentials("user", "k3y", "maker", "") is None


@pytest.mark.parametrize("firmware", ["buddy", "prusa-link"])
def test_both_firmwares_accept_the_digest_login(printer, firmware):
    device = _FakePrusaPrinter(firmware, user="maker" if firmware == "buddy" else "owner")
    printer.use(device)

    reading, failure = printer.plugin.read_prusalink_status(
        _connection(printer.plugin, "user", user=device.user, password=device.password)
    )

    assert failure is None
    assert reading["serial"] == (BUDDY_SERIAL if firmware == "buddy" else "CZPX4720X004XC12345")
    # One challenge serves the whole reading: one refused request, then answers.
    assert device.requests.count("/api/version") == 2
    assert all(device.requests.count(path) == 1 for path in device.requests[2:])


def test_a_wrong_login_or_none_at_all_is_told_apart(printer):
    plugin = printer.plugin
    assert plugin.read_prusalink_status(_connection(plugin, key="wrong")) == (None, "auth")
    printer.use(_FakePrusaPrinter("buddy", password="other"))
    assert plugin.read_prusalink_status(_connection(plugin, "user")) == (None, "auth")
    printer.use(_FakePrusaPrinter("prusa-link", key="other"))
    assert plugin.read_prusalink_status(_connection(plugin)) == (None, "auth")
    missing = dict(_connection(plugin), credentials=None)
    assert plugin.read_prusalink_status(missing) == (None, "credentials")


def test_old_firmware_and_a_real_octoprint_are_named_not_misread(printer):
    plugin = printer.plugin
    old = _FakePrusaPrinter()
    # Buddy before 4.7.0: the OctoPrint-compatible API only, no serial number.
    for path in ("/api/v1/info", "/api/v1/status", "/api/v1/job"):
        old.answers.pop(path)
    printer.use(old)
    assert plugin.read_prusalink_status(_connection(plugin)) == (None, "firmware")

    octoprint = _FakePrusaPrinter()
    octoprint.answers = {"/api/version": _fixture("octoprint_version.json")}
    printer.use(octoprint)
    assert plugin.read_prusalink_status(_connection(plugin)) == (None, "octoprint")


def test_buddy_status_and_job_fill_the_printer_card(plugin_module):
    printer = plugin_module.prusalink_printer(
        _fixture("buddy_status_printing.json"), _fixture("buddy_job.json")
    )

    assert printer == {
        "state": "printing",
        "job_name": "3DBenchy_0.4n_0.2mm_PLA_MK4S_42m.bgcode",
        "progress_percent": 42,
        "remaining_seconds": 3120,
        "nozzle_temperature": 215.1,
        "nozzle_target_temperature": 215.0,
        "bed_temperature": 60.0,
        "bed_target_temperature": 60.0,
    }
    idle = plugin_module.prusalink_printer(_fixture("prusalink_status_idle.json"))
    assert idle["state"] == "idle" and "job_name" not in idle


@pytest.mark.parametrize(("code", "has_job", "expected"), [
    ("READY", False, "idle"),
    ("PAUSED", True, "paused"),
    ("ATTENTION", True, "paused"),
    ("FINISHED", True, "finished"),
    ("STOPPED", True, "failed"),
    ("ERROR", False, "failed"),
    ("BUSY", True, "printing"),
    ("BUSY", False, "unknown"),
    ("UNKNOWN", False, "unknown"),
])
def test_printer_states_map_onto_the_bridge_contract(plugin_module, code, has_job, expected):
    status = _fixture("buddy_status_printing.json")
    status["printer"]["state"] = code
    if not has_job:
        status.pop("job")

    assert plugin_module.prusalink_printer(status)["state"] == expected


def test_one_spool_is_claimed_only_where_one_feeds_for_certain(plugin_module):
    plugin = plugin_module
    version, info = _fixture("buddy_version.json"), _fixture("buddy_info.json")

    slots, complete = plugin.prusalink_slots(version, info, _fixture("buddy_printer.json"))
    assert complete is True and plugin.prusalink_capabilities(slots) == [
        "read", "presence", "consumption",
    ]
    assert slots == [{
        "provider_index": 0, "label": "Spool", "kind": "external", "present": True,
        "spool_identity_known": False, "active_feed": True, "material": "PLA",
    }]
    empty, _complete = plugin.prusalink_slots(version, info, {"telemetry": {"material": "---"}})
    assert empty[0]["present"] is False and "material" not in empty[0]

    # An MMU3, an XL or a Prusa-Link printer: the local API names no slot.
    assert plugin.prusalink_slots(version, _fixture("buddy_info_mmu.json"), None) == ([], False)
    assert plugin.prusalink_slots(dict(version, printer="3.1.0"), info, None) == ([], False)
    assert plugin.prusalink_slots(
        _fixture("prusalink_version.json"), _fixture("prusalink_info.json"),
        {"telemetry": {"material": " - "}},
    ) == ([], False)
    assert plugin.prusalink_capabilities([]) == ["read"]


@pytest.fixture
def linked(printer, monkeypatch, tmp_path):
    """A linked MK4S, its connection copied from OrcaSlicer, and a watcher driven by hand."""
    plugin = printer.plugin
    calls = SimpleNamespace(posted=[], revoked=[])
    monkeypatch.setattr(plugin, "PLUGIN_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(plugin, "plugin_source_instance_id", lambda: "desktop-source-instance")
    monkeypatch.setattr(plugin, "USAGE_WATCH_SNAPSHOT_MIN_SECONDS", 0.0)
    connection = _connection(plugin, "user")
    monkeypatch.setitem(plugin._PRUSALINK_CONNECTIONS, "items", [connection])

    def pair(path, token, payload):
        calls.pair = payload
        return 200, json.dumps({
            "bridge_token": "fhpb_" + "c" * 40, "physical_printer_id": 7,
            "material_system_id": 9, "printer_discovery_key": DISCOVERY_KEY,
        }).encode("utf-8")

    def post(path, token, payload):
        calls.posted.append((path, token, payload))
        return 200, b"{}", None

    monkeypatch.setattr(plugin, "http_post_json", pair)
    monkeypatch.setattr(plugin, "http_post_bridge_json", post)
    monkeypatch.setattr(plugin, "revoke_fresh_bridge_token", calls.revoked.append)
    # The watcher asks the site which spools are in the slots; nothing is assigned.
    monkeypatch.setattr(plugin, "http_get_bridge_json", lambda *_args: (200, b'{"slots": []}'))

    result = plugin.configure_prusalink_bridge(7, 9, "FH-AAAAA-BBBBB", "", [connection])
    assert result == {"ok": True, "code": "ok"}
    return SimpleNamespace(
        plugin=plugin, printer=printer, calls=calls, connection=connection,
        runtime=plugin.PrusaLinkWatchRuntime(), stored=tmp_path / ".fh_prusalink.json",
    )


def test_linking_reports_the_printer_and_keeps_no_address_or_login(linked):
    assert linked.calls.pair["provider"] == "prusalink"
    assert linked.calls.pair["capabilities"] == ["read", "presence", "consumption"]
    path, _token, snapshot = linked.calls.posted[0]
    assert path == "/printer-bridge/snapshot"
    assert snapshot["printer"]["state"] == "printing"
    assert snapshot["printer"]["job_name"].startswith("3DBenchy")
    assert snapshot["slots"][0]["material"] == "PLA" and snapshot["slot_topology_complete"]
    identity = snapshot["device_identity"]
    assert identity["kind"] == "prusalink_serial" and len(identity["token"]) == 64
    stored = linked.stored.read_text(encoding="utf-8")
    assert BUDDY_SERIAL in stored
    assert "192.168.1.60" not in stored and "pa55word" not in stored and "maker" not in stored


def test_the_watcher_reports_a_change_and_only_reads_the_printer(linked):
    linked.calls.posted.clear()
    device = linked.printer.fake.device
    device.requests.clear()
    status = device.answers["/api/v1/status"]
    status["job"]["progress"] = 77.0

    assert linked.runtime.watch_once() == linked.plugin.USAGE_WATCH_PRINTING_SECONDS
    assert linked.calls.posted[-1][2]["printer"]["progress_percent"] == 77
    # The model is known from linking; a round reads only what changes.
    assert "/api/version" not in device.requests

    status["printer"]["state"] = "FINISHED"
    assert linked.runtime.watch_once() == linked.plugin.USAGE_WATCH_IDLE_SECONDS
    assert linked.calls.posted[-1][2]["printer"]["state"] == "finished"


def test_another_printer_that_took_the_address_is_not_reported(linked):
    linked.calls.posted.clear()
    stranger = _FakePrusaPrinter()
    stranger.answers["/api/v1/info"] = dict(stranger.answers["/api/v1/info"], serial="OTHER-12345")
    linked.printer.use(stranger)

    assert linked.plugin.observe_prusalink_bindings([linked.connection]) == {7: "other"}
    assert [path for path, _token, _payload in linked.calls.posted] == ["/printer-bridge/heartbeat"]
    assert linked.runtime.watch_once() == linked.plugin.USAGE_WATCH_IDLE_SECONDS
    assert all(path.endswith("heartbeat") for path, _token, _payload in linked.calls.posted)


def test_a_printer_already_on_another_card_is_not_linked_twice(linked):
    connection = linked.connection
    result = linked.plugin.configure_prusalink_bridge(8, 10, "FH-CCCCC-DDDDD", "", [connection])

    assert result == {"ok": False, "code": "linked"}


def test_several_prusa_profiles_ask_the_person_to_choose(linked):
    plugin = linked.plugin
    second = dict(linked.connection, host="192.168.1.61", label="Prusa XL")
    result = plugin.configure_prusalink_bridge(
        7, 9, "FH-AAAAA-BBBBB", "", [linked.connection, second]
    )

    assert result["code"] == "choose"
    assert [item["label"] for item in result["candidates"]] == ["Prusa MK4S 0.4", "Prusa XL"]
    assert all(item["connectionRef"].startswith("pl_") for item in result["candidates"])


def test_profiles_are_copied_from_orca_with_their_login(plugin_module, monkeypatch):
    plugin = plugin_module
    presets = [
        {"host_type": "prusalink", "print_host": "192.168.1.60",
         "printhost_authorization_type": "user", "printhost_user": "maker",
         "printhost_password": "pa55word", "printhost_apikey": ""},
        {"host_type": "prusaconnect", "print_host": "https://connect.prusa3d.com",
         "printhost_apikey": "cloud-token"},
        {"host_type": "octoprint", "print_host": "192.168.1.70", "printhost_apikey": "x"},
    ]
    bundle = SimpleNamespace(printers=SimpleNamespace(
        size=lambda: len(presets),
        preset=lambda index: SimpleNamespace(
            name="Prusa %d" % index, is_user=lambda: True,
            config_value=lambda key, values=presets[index]: values.get(key),
        ),
    ))
    monkeypatch.setattr(plugin.orca.host, "preset_bundle", lambda: bundle, raising=False)
    monkeypatch.setitem(plugin._PRUSALINK_CONNECTIONS, "items", None)

    connections = plugin._snapshot_local_prusalink_connections()

    # The cloud profile is not a local printer: only PrusaLink is read.
    assert connections == [{
        "label": "Prusa 0", "host": "192.168.1.60", "port": 80,
        "credentials": {"mode": "digest", "user": "maker", "password": "pa55word"},
    }]

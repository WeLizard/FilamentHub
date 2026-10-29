"""The Bambu observer keeps reporting that it is alive when the printer is off."""

from .filamenthub_plugin_test_support import _bambu_report, pytest

HEARTBEAT = "/printer-bridge/heartbeat"
SNAPSHOT = "/printer-bridge/snapshot"


class Harness:
    """Runs the observer loop on a fake clock, one pass per 30 seconds."""

    def __init__(self, plugin, monkeypatch, tmp_path, passes):
        self.plugin = plugin
        self.clock = {"now": 1000.0, "waits": 0}
        self.posts = []
        self.responses = {}
        self.reads = []
        monkeypatch.setattr(plugin, "BAMBU_CONFIG_FILE", str(tmp_path / ".fh_bambu.json"))
        plugin.configure_bambu_bridge(
            3, 5, "192.168.1.43", "local-secret", "SERIAL-2", "fhpb_live",
            plugin._bambu_device_identity("a" * 64, "SERIAL-2"),
        )
        self.source_instance_id = plugin.load_bambu_config()["source_instance_id"]
        self.runtime = plugin.BambuBridgeRuntime()
        monkeypatch.setattr(self.runtime, "_record_usage", lambda *_a, **_k: None)
        monkeypatch.setattr(plugin.time, "monotonic", lambda: self.clock["now"])
        monkeypatch.setattr(plugin, "http_get_bridge_json", lambda *_a: (404, b""))
        monkeypatch.setattr(plugin, "http_post_bridge_json", self.post)

        def wait(_timeout):
            self.clock["waits"] += 1
            if self.clock["waits"] > 1:
                self.clock["now"] += 30.0
            if self.clock["waits"] > passes:
                self.runtime._stop.set()
            return False

        monkeypatch.setattr(self.runtime._wake, "wait", wait)

    def post(self, path, _token, payload):
        self.posts.append((path, self.clock["now"], payload))
        return self.responses.get(path, 200), b"", None

    def printer_answers(self, answers):
        def observe(_config):
            self.reads.append(self.clock["now"])
            if not answers():
                raise TimeoutError("Bambu LAN stream is unavailable")
            return "SERIAL-2", _bambu_report()

        self.runtime._stream_observation = observe

    def heartbeats(self):
        return [item for item in self.posts if item[0] == HEARTBEAT]

    def run(self):
        self.runtime._run()


def test_unreachable_printer_sends_one_heartbeat_per_due_interval(
    plugin_module, monkeypatch, tmp_path
):
    harness = Harness(plugin_module, monkeypatch, tmp_path, passes=6)
    harness.printer_answers(lambda: False)

    harness.run()

    beats = harness.heartbeats()
    assert [item[1] for item in beats] == [1000.0, 1120.0]
    assert [item[0] for item in harness.posts] == [HEARTBEAT, HEARTBEAT]
    for _path, _at, payload in beats:
        assert payload["provider_reachable"] is False
        assert payload["contact_interval_s"] == int(plugin_module.BAMBU_HEARTBEAT_SECONDS)
        assert payload["source_instance_id"] == harness.source_instance_id
        assert payload["material_system_id"] == 5
        assert payload["provider"] == "bambu"
        assert "capabilities" not in payload
    stored = plugin_module.load_bambu_config()["printers"][0]
    assert stored["bridge_token"] == "fhpb_live"


def test_heartbeat_continues_while_the_lan_backoff_is_longer_than_the_interval(
    plugin_module, monkeypatch, tmp_path
):
    harness = Harness(plugin_module, monkeypatch, tmp_path, passes=14)
    harness.printer_answers(lambda: False)

    harness.run()

    # Reads back off (5 s, 10 s, ... up to 300 s), so far fewer reads than
    # passes happen, yet a heartbeat still goes out every 120 seconds.
    assert len(harness.reads) < 14
    assert [item[1] for item in harness.heartbeats()] == [1000.0, 1120.0, 1240.0, 1360.0]


def test_reachable_printer_heartbeat_carries_reachability_and_interval(
    plugin_module, monkeypatch, tmp_path
):
    harness = Harness(plugin_module, monkeypatch, tmp_path, passes=5)
    harness.printer_answers(lambda: True)

    harness.run()

    snapshots = [item for item in harness.posts if item[0] == SNAPSHOT]
    beats = harness.heartbeats()
    assert len(snapshots) == 1
    assert "provider_reachable" not in snapshots[0][2]
    assert [item[1] for item in beats] == [1120.0]
    payload = beats[0][2]
    assert payload["provider_reachable"] is True
    assert payload["contact_interval_s"] == int(plugin_module.BAMBU_HEARTBEAT_SECONDS)
    assert payload["source_instance_id"] == harness.source_instance_id
    assert payload["capabilities"]


def test_no_heartbeat_when_the_source_id_is_unknown(plugin_module, monkeypatch):
    plugin = plugin_module
    binding = {
        "physical_printer_id": 3, "material_system_id": 5, "bridge_token": "fhpb_live",
    }
    posts = []
    runtime = plugin.BambuBridgeRuntime()
    monkeypatch.setattr(
        plugin, "load_bambu_config", lambda: {"printers": [binding]}
    )
    monkeypatch.setattr(
        runtime, "_stream_observation",
        lambda _config: (_ for _ in ()).throw(TimeoutError("off")),
    )
    monkeypatch.setattr(
        plugin, "http_post_bridge_json",
        lambda path, _token, _payload: posts.append(path) or (200, b"", None),
    )
    calls = {"count": 0}

    def wait(_timeout):
        calls["count"] += 1
        if calls["count"] > 3:
            runtime._stop.set()
        return False

    monkeypatch.setattr(runtime._wake, "wait", wait)

    runtime._run()

    assert posts == []


def test_rejected_token_on_the_failure_heartbeat_clears_only_the_server_token(
    plugin_module, monkeypatch, tmp_path
):
    harness = Harness(plugin_module, monkeypatch, tmp_path, passes=3)
    harness.responses[HEARTBEAT] = 401
    harness.printer_answers(lambda: False)

    harness.run()

    assert len(harness.heartbeats()) == 1
    stored = plugin_module.load_bambu_config()["printers"][0]
    assert stored["bridge_token"] == ""
    assert stored["host"] == "192.168.1.43"
    assert stored["access_code"] == "local-secret"
    assert stored["serial"] == "SERIAL-2"


def test_recovery_clears_the_unreachable_flag_with_a_heartbeat(
    plugin_module, monkeypatch, tmp_path
):
    harness = Harness(plugin_module, monkeypatch, tmp_path, passes=6)
    # Off for the first pass, then the printer comes back.
    harness.printer_answers(lambda: harness.clock["now"] >= 1090.0)

    harness.run()

    flags = [
        (item[0], item[2].get("provider_reachable"))
        for item in harness.posts
        if item[0] in {HEARTBEAT, SNAPSHOT}
    ]
    assert flags[0] == (HEARTBEAT, False)
    # The snapshot has no reachability field, so a heartbeat must follow it.
    assert (SNAPSHOT, None) in flags
    assert flags[flags.index((SNAPSHOT, None)) + 1] == (HEARTBEAT, True)

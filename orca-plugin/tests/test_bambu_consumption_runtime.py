"""Focused unit coverage for the Bambu consumption journal.

These tests deliberately use prepared LAN reports and mocked bridge calls.  No
printer, account, or network connection is involved.
"""

import json
import threading

import pytest

from .filamenthub_plugin_test_support import _bambu_report


def _report(state="RUNNING", *, remaining=995, job="job-1", file_name="part.gcode",
            mc_percent=None):
    report = _bambu_report(
        gcode_state=state,
        task_id=job,
        subtask_id=job + "-subtask",
        gcode_file=file_name,
        subtask_name=file_name,
        ams={
            "tray_now": "0",
            "tray_exist_bits": "1",
            "ams": [{"id": "0", "tray": [{
                "id": "0", "tray_type": "PLA", "remain_g": remaining,
                "remain": 100, "tray_uuid": "TAG-A",
            }]}],
        },
    )
    if mc_percent is not None:
        report["mc_percent"] = mc_percent
    return report


def _desired(spool_id=7, proof="proof-a", initial=1000, index=0):
    return {"slots": [{
        "index": index,
        "usage_route_proof": proof,
        "spool": {"id": spool_id, "initial_weight_g": initial},
    }]}


def _events(plugin_module, state, report, desired, when, estimate=None):
    return plugin_module.capture_bambu_usage(
        state, report, desired, estimate, when
    )


def test_late_assignment_starts_at_observed_baseline_and_finishes(plugin_module):
    state = {}
    assert _events(plugin_module, state, _report(remaining=995), {"slots": []},
                   "2026-09-19T10:00:00+00:00") == []
    assert _events(plugin_module, state, _report(remaining=995), _desired(),
                   "2026-09-19T10:01:00+00:00") == []
    events = _events(plugin_module, state, _report("FINISH", remaining=985),
                     _desired(), "2026-09-19T10:02:00+00:00")
    assert len(events) == 1
    assert events[0]["outcome"] == "completed"
    assert events[0]["items"][0]["used_weight_g"] == pytest.approx(10)
    assert events[0]["items"][0]["spool_id"] == 7


def test_state_json_roundtrip_preserves_baseline_and_terminal_repeat_is_idempotent(
    plugin_module,
):
    state = {}
    _events(plugin_module, state, _report(remaining=1000), _desired(),
            "2026-09-19T10:00:00+00:00")
    restarted = json.loads(json.dumps(state))
    first = _events(plugin_module, restarted, _report("FINISH", remaining=990),
                    _desired(), "2026-09-19T10:05:00+00:00")
    second = _events(plugin_module, restarted, _report("FINISH", remaining=990),
                     _desired(), "2026-09-19T10:06:00+00:00")
    assert first[0]["items"][0]["used_weight_g"] == pytest.approx(10)
    assert second == []


def test_new_job_or_file_does_not_mix_previous_interval(plugin_module):
    state = {}
    _events(plugin_module, state, _report(remaining=1000), _desired(),
            "2026-09-19T10:00:00+00:00")
    assert _events(plugin_module, state, _report(remaining=900, job="job-2",
                                                 file_name="other.gcode"),
                   _desired(), "2026-09-19T10:01:00+00:00") == []
    events = _events(plugin_module, state, _report("FINISH", remaining=890,
                                                   job="job-2",
                                                   file_name="other.gcode"),
                     _desired(), "2026-09-19T10:02:00+00:00")
    assert events[0]["items"][0]["used_weight_g"] == pytest.approx(10)
    assert events[0]["file_name"] == "other.gcode"


@pytest.mark.parametrize("remaining", [None, 1010])
def test_unknown_or_upward_remaining_does_not_charge(plugin_module, remaining):
    state = {}
    _events(plugin_module, state, _report(remaining=1000), _desired(),
            "2026-09-19T10:00:00+00:00")
    report = _report(remaining=1000, mc_percent=0)
    report["ams"]["ams"][0]["tray"][0]["remain_g"] = remaining
    assert _events(plugin_module, state, report, _desired(),
                   "2026-09-19T10:01:00+00:00") == []


def test_tag_change_does_not_charge_interval_to_replacement_spool(plugin_module):
    state = {}
    _events(plugin_module, state, _report(remaining=1000), _desired(),
            "2026-09-19T10:00:00+00:00")
    changed = _report(remaining=990)
    changed["ams"]["ams"][0]["tray"][0]["tray_uuid"] = "TAG-B"
    assert _events(plugin_module, state, changed, _desired(spool_id=8, proof="proof-b"),
                   "2026-09-19T10:01:00+00:00") == []
    events = _events(plugin_module, state, _report("FINISH", remaining=985),
                     _desired(spool_id=8, proof="proof-b"),
                     "2026-09-19T10:02:00+00:00")
    assert events == [] or all(not event["items"] for event in events)


def test_slicer_file_weights_follow_multispool_mapping(plugin_module):
    state = {}
    estimate = {"weights": {"0": 20, "1": 30}, "sha256": "slice-hash"}
    report = _report(remaining=1000, mc_percent=0)
    report["ams_mapping"] = [0, 1]
    report["ams"]["tray_exist_bits"] = "3"
    report["ams"]["ams"][0]["tray"].append({
        "id": "1", "tray_type": "PETG", "remain_g": 1000,
        "remain": 100, "tray_uuid": "TAG-B",
    })
    desired = {"slots": [
        {"index": 0, "usage_route_proof": "a", "spool": {"id": 7, "initial_weight_g": 1000}},
        {"index": 1, "usage_route_proof": "b", "spool": {"id": 8, "initial_weight_g": 1000}},
    ]}
    _events(plugin_module, state, report, desired, "2026-09-19T10:00:00+00:00", estimate)
    finish = _report("FINISH", remaining=1000, mc_percent=100)
    finish["ams"]["tray_exist_bits"] = "3"
    finish["ams"]["ams"][0]["tray"].append({
        "id": "1", "tray_type": "PETG", "remain_g": 1000,
        "remain": 100, "tray_uuid": "TAG-B",
    })
    events = _events(plugin_module, state, finish, desired,
                     "2026-09-19T10:01:00+00:00", estimate)
    by_spool = {item["spool_id"]: item["used_weight_g"] for item in events[0]["items"]}
    assert by_spool == {7: pytest.approx(20), 8: pytest.approx(30)}


def test_gcode_layer_curve_follows_extrusion_instead_of_linear_progress(plugin_module):
    gcode = b"""; filament used [g] = 10, 20
M83
T0
; CHANGE_LAYER
G1 X1 E2
T1
G1 X2 E4
; CHANGE_LAYER
T0
G1 X3 E3
T1
G1 X4 E1
"""
    estimate = plugin_module.parse_bambu_consumption_file(gcode)
    assert estimate["layer_weights"][0] == pytest.approx([4, 10])
    assert estimate["layer_weights"][1] == pytest.approx([16, 20])

    desired = {"slots": [
        {"index": 0, "usage_route_proof": "a", "spool": {"id": 7}},
        {"index": 1, "usage_route_proof": "b", "spool": {"id": 8}},
    ]}

    def layer_report(layer, progress):
        report = _report(remaining=1000, mc_percent=progress)
        report["layer_num"] = layer
        report["total_layer_num"] = 2
        report["ams_mapping"] = [0, 1]
        report["ams"]["tray_exist_bits"] = "3"
        report["ams"]["ams"][0]["tray"].append({
            "id": "1", "tray_type": "PETG", "remain_g": 1000,
            "remain": 100, "tray_uuid": "TAG-B",
        })
        return report

    state = {}
    assert _events(
        plugin_module, state, layer_report(1, 50), desired,
        "2026-09-19T10:00:00+00:00", estimate,
    ) == []
    events = _events(
        plugin_module, state, layer_report(2, 60), desired,
        "2026-09-19T10:05:00+00:00", estimate,
    )
    by_spool = {item["spool_id"]: item for item in events[0]["items"]}
    assert by_spool[7]["used_weight_g"] == pytest.approx(6)
    assert by_spool[8]["used_weight_g"] == pytest.approx(4)
    assert {item["estimate_source"] for item in by_spool.values()} == {"slicer_gcode"}


def test_gcode_layer_curve_does_not_count_retraction_twice(plugin_module):
    gcode = b"""; filament used [g] = 15
M83
; CHANGE_LAYER
G1 E10
G1 E-2
; CHANGE_LAYER
G1 E2
G1 E5
"""

    estimate = plugin_module.parse_bambu_consumption_file(gcode)

    assert estimate["layer_weights"][0] == pytest.approx([8, 15])


def test_switch_from_progress_to_layer_curve_does_not_double_charge(plugin_module):
    desired = {"slots": [{
        "index": 0,
        "usage_route_proof": "proof-a",
        "spool": {"id": 7},
    }]}
    state = {}
    progress_estimate = {"sha256": "job-a", "weights": {0: 10}}
    layer_estimate = {
        **progress_estimate,
        "layer_weights": {0: [4, 10]},
    }

    start = _report(remaining=1000, mc_percent=0)
    start["layer_num"] = 0
    start["total_layer_num"] = 2
    assert _events(
        plugin_module, state, start, desired,
        "2026-09-19T10:00:00+00:00", progress_estimate,
    ) == []

    progress = _report(remaining=1000, mc_percent=50)
    progress["layer_num"] = 1
    progress["total_layer_num"] = 2
    progress_events = _events(
        plugin_module, state, progress, desired,
        "2026-09-19T10:05:00+00:00", progress_estimate,
    )
    assert progress_events[0]["items"][0]["used_weight_g"] == pytest.approx(5)

    assert _events(
        plugin_module, state, progress, desired,
        "2026-09-19T10:06:00+00:00", layer_estimate,
    ) == []

    finished = _report(state="FINISH", remaining=1000, mc_percent=100)
    finished["layer_num"] = 2
    finished["total_layer_num"] = 2
    terminal = _events(
        plugin_module, state, finished, desired,
        "2026-09-19T10:10:00+00:00", layer_estimate,
    )
    assert terminal[0]["items"][0]["used_weight_g"] == pytest.approx(5)


def test_existing_estimate_recovers_unique_layer_curve_from_slice_cache(
    plugin_module, tmp_path, monkeypatch
):
    cache = tmp_path / "slices"
    cache.mkdir()
    two_layers = cache / "two.gcode"
    two_layers.write_bytes(b"""M83
; CHANGE_LAYER
G1 E2
; CHANGE_LAYER
G1 E3
; filament used [g] = 10
""")
    three_layers = cache / "three.gcode"
    three_layers.write_bytes(b"""M83
; CHANGE_LAYER
G1 E1
; CHANGE_LAYER
G1 E1
; CHANGE_LAYER
G1 E1
; filament used [g] = 10
""")
    index = tmp_path / "slices.json"
    index.write_text(json.dumps({
        "two": {"path": str(two_layers), "name": "two.gcode"},
        "three": {"path": str(three_layers), "name": "three.gcode"},
    }), encoding="utf-8")
    monkeypatch.setattr(plugin_module, "_SLICE_CACHE_DIR", str(cache))
    monkeypatch.setattr(plugin_module, "_SLICE_INDEX_FILE", str(index))

    enriched = plugin_module.enrich_bambu_estimate_from_slice_cache(
        {"total_layer_num": 2},
        {"weights": {"0": 10}, "sha256": "archive"},
    )

    assert enriched["layer_source_key"] == "two"
    assert enriched["layer_weights"][0] == pytest.approx([4, 10])


def test_runtime_retries_identical_outbox_after_lost_ack(plugin_module, tmp_path, monkeypatch):
    config_file = tmp_path / "bambu.json"
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(config_file))
    config = {"physical_printer_id": 3, "material_system_id": 5, "bridge_token": "token"}
    report = _report("FINISH", remaining=990)
    desired = _desired()
    monkeypatch.setattr(plugin_module, "http_get_bridge_json",
                        lambda *_args: (200, json.dumps(desired).encode()))
    monkeypatch.setattr(plugin_module, "read_bambu_consumption_file", lambda *_args: None)
    writes = []
    original_write = plugin_module.write_json_atomic
    monkeypatch.setattr(plugin_module, "write_json_atomic",
                        lambda path, payload, mode=0o600: (writes.append(json.loads(json.dumps(payload))),
                                                            original_write(path, payload, mode=mode))[1])
    posts = []
    monkeypatch.setattr(plugin_module, "http_post_bridge_json",
                        lambda path, token, payload: posts.append(json.loads(json.dumps(payload))) or (503, b"", 0))
    runtime = plugin_module.BambuBridgeRuntime()
    active = _report("RUNNING", remaining=1000)
    runtime._record_usage(config, "instance", active, "2026-09-19T09:59:00+00:00")
    runtime._record_usage(config, "instance", report, "2026-09-19T10:00:00+00:00")
    binding = next(iter(runtime._usage_states))
    runtime._usage_retry_at[binding] = 0
    runtime._record_usage(config, "instance", report, "2026-09-19T10:00:00+00:00")
    assert len(posts) == 2
    assert posts[0] == posts[1]
    assert posts[0]["sequence"] == 1


def test_remaining_rebound_does_not_charge_the_same_material_twice(plugin_module):
    state = {}
    for minute, remaining in enumerate([1000, 990, 995, 990]):
        _events(plugin_module, state, _report(remaining=remaining), _desired(),
                f"2026-09-19T10:0{minute}:00+00:00")
    events = _events(plugin_module, state, _report("FINISH", remaining=985), _desired(),
                     "2026-09-19T10:04:00+00:00")
    assert events[0]["items"][0]["used_weight_g"] == 15


def test_replacement_tag_cannot_inherit_the_previous_spool_assignment(plugin_module):
    state = {}
    _events(plugin_module, state, _report(remaining=1000), _desired(),
            "2026-09-19T10:00:00+00:00")
    replacement = _report(remaining=990)
    replacement["ams"]["ams"][0]["tray"][0]["tray_uuid"] = "TAG-B"
    _events(plugin_module, state, replacement, _desired(), "2026-09-19T10:01:00+00:00")
    replacement["gcode_state"] = "FINISH"
    replacement["ams"]["ams"][0]["tray"][0]["remain_g"] = 980
    events = _events(plugin_module, state, replacement, _desired(),
                     "2026-09-19T10:02:00+00:00")
    assert events[0]["items"] == []


def test_stream_retains_cancel_before_idle_and_only_charges_partial_estimate(plugin_module):
    stream = {}
    for minute, status, progress in [(0, "RUNNING", 40), (1, "RUNNING", 60),
                                     (2, "FAILED", 70), (3, "IDLE", 70)]:
        plugin_module._buffer_bambu_usage_report(
            stream, _report(status, mc_percent=progress),
            f"2026-09-19T10:0{minute}:00+00:00",
        )
    state, events = {}, []
    for observation in stream["usage_reports"]:
        events.extend(plugin_module.capture_bambu_usage(
            state, observation["report"], _desired(),
            {"weights": {"0": 20}, "sha256": "slice"}, observation["observed_at"],
        ))
    assert len(events) == 1
    assert events[0]["outcome"] == "failed"
    assert events[0]["items"][0]["used_weight_g"] == pytest.approx(6)


def test_stream_journal_failure_preserves_unprocessed_reports(plugin_module, monkeypatch):
    runtime = plugin_module.BambuBridgeRuntime()
    config = {"host": "192.168.1.44", "serial": "LAB", "access_code": "code",
              "bridge_token": "token"}
    key = plugin_module._bambu_stream_key(config)
    stream = {"lock": threading.Lock()}
    runtime._streams[key] = stream
    for minute, status in enumerate(["RUNNING", "FAILED", "IDLE"]):
        plugin_module._buffer_bambu_usage_report(
            stream, _report(status), f"2026-09-19T10:0{minute}:00+00:00",
        )
    accepted = []

    def record(_config, _source, report, observed_at):
        if report["gcode_state"] == "FAILED":
            raise OSError("disk unavailable")
        accepted.append(report["gcode_state"])

    monkeypatch.setattr(runtime, "_record_usage", record)
    with pytest.raises(OSError):
        runtime._record_stream_usage(config, "source", _report("IDLE"), "unused")
    assert accepted == ["RUNNING"]
    assert [item["report"]["gcode_state"] for item in stream["usage_reports"]] == ["FAILED", "IDLE"]


def test_stream_queue_overflow_marks_gap_without_inventing_consumption(plugin_module):
    stream = {}
    for index in range(257):
        plugin_module._buffer_bambu_usage_report(
            stream, _report(remaining=1000-index), "2026-09-19T10:00:00+00:00",
        )
    assert len(stream["usage_reports"]) == 1
    assert stream["usage_reports"][0]["report"]["_fh_observation_gap"] is True


def test_serial_discovery_keeps_original_stream_and_binding_isolation(plugin_module, monkeypatch):
    runtime = plugin_module.BambuBridgeRuntime()
    original = {"host": "192.168.1.44", "serial": "", "bridge_token": "token",
                "physical_printer_id": 1, "material_system_id": 2}
    discovered = {**original, "serial": "LAB"}
    stream = {"lock": threading.Lock()}
    runtime._streams[plugin_module._bambu_stream_key(original)] = stream
    plugin_module._buffer_bambu_usage_report(stream, _report("FAILED"), "2026-09-19T10:00:00+00:00")
    processed = []
    monkeypatch.setattr(runtime, "_record_usage", lambda config, source, report, observed_at:
                        processed.append(report["gcode_state"]))
    runtime._record_stream_usage(discovered, "source", _report("IDLE"), "unused",
                                 stream_config=original)
    assert processed == ["FAILED"]
    assert stream["usage_reports"] == []
    assert plugin_module._bambu_stream_key(original) != plugin_module._bambu_stream_key(
        {**original, "material_system_id": 3}
    )


@pytest.mark.parametrize("changed_route", [False, True])
def test_desired_outage_defers_observation_and_rechecks_route_after_restart(
    plugin_module, tmp_path, monkeypatch, changed_route,
):
    monkeypatch.setattr(plugin_module, "BAMBU_CONFIG_FILE", str(tmp_path / "bambu.json"))
    monkeypatch.setattr(plugin_module, "read_bambu_consumption_file", lambda *_: None)
    desired = _desired()
    status = 200
    monkeypatch.setattr(plugin_module, "http_get_bridge_json",
                        lambda *_: (status, json.dumps(desired).encode()))
    uploads = []
    monkeypatch.setattr(plugin_module, "http_post_bridge_json", lambda path, token, payload:
                        (uploads.append(payload) or 200,
                         json.dumps({"accepted": True, "ack_sequence": payload["sequence"]}).encode(), None))
    config = {"physical_printer_id": 3, "material_system_id": 5, "bridge_token": "token"}
    runtime = plugin_module.BambuBridgeRuntime()
    assert runtime._record_usage(config, "source", _report(remaining=1000),
                                  "2026-09-19T10:00:00+00:00") is True
    stream = {"lock": threading.Lock()}
    runtime._streams[plugin_module._bambu_stream_key(config)] = stream
    terminal = _report("FINISH", remaining=990)
    plugin_module._buffer_bambu_usage_report(stream, terminal, "2026-09-19T10:02:00+00:00")
    status = 503
    runtime._record_stream_usage(config, "source", terminal, "unused")
    assert len(stream["usage_reports"]) == 1
    assert not uploads
    status = 200
    if changed_route:
        desired = _desired(spool_id=8, proof="new-proof")
    restarted = plugin_module.BambuBridgeRuntime()
    assert restarted._record_usage(config, "source", terminal,
                                    "2026-09-19T10:02:00+00:00") is True
    items = uploads[0]["events"][0]["items"]
    if changed_route:
        assert items == []
    else:
        assert items[0]["used_weight_g"] == 10
        assert items[0]["spool_id"] == 7

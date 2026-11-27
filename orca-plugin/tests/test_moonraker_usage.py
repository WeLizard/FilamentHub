"""Filament usage of a Klipper printer, counted while OrcaSlicer is open."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = "desktop-source-instance"
TOKEN = "fhpb_" + "k" * 40
CONNECTION = {"connection_ref": "ref-voron", "print_host": "voron.lan", "api_key": "moonraker-key"}


def _inventory(provider="legacy", printer_id=7, system_id=9):
    return {
        "source_instance_id": SOURCE,
        "printers": [{
            "id": printer_id,
            "connection_refs": ["ref-voron"],
            "material_systems": [{"id": system_id, "provider": provider, "slots": []}],
        }],
    }


@pytest.fixture
def klipper(plugin_module, monkeypatch, tmp_path):
    """The plugin with its private storage, one Klipper printer and the site faked."""
    plugin = plugin_module
    calls = SimpleNamespace(
        granted=[], posted=[], revoked=[], moonraker=[], desired_reads=0,
        grant_status=200, provider="legacy",
        config={"spoolman_free": {}},
        stats={"state": "standby", "filename": "", "filament_used": 0.0, "print_duration": 0.0},
        mmu=None, moonraker_status=200, extra={}, queries=[],
        desired={"slots": [{"index": 0, "usage_route_proof": "proof-0", "spool": {"id": 11}}]},
    )
    monkeypatch.setattr(plugin, "MOONRAKER_USAGE_CONFIG_FILE", str(tmp_path / ".fh_moonraker_usage.json"))
    monkeypatch.setattr(plugin, "_MOONRAKER_USAGE_CONNECTIONS", {})
    monkeypatch.setattr(plugin, "_MOONRAKER_USAGE_REFUSED", set())
    monkeypatch.setattr(
        plugin, "MOONRAKER_WATCH_RUNTIME",
        SimpleNamespace(start=lambda: None, relinked=lambda key: None),
    )
    monkeypatch.setattr(plugin, "plugin_source_instance_id", lambda: SOURCE)
    monkeypatch.setattr(plugin, "USAGE_WATCH_RETRY_SECONDS", 0.0)

    def grant(path, token, payload):
        calls.granted.append((path, token, payload))
        if calls.grant_status != 200:
            return calls.grant_status, b"{}"
        return 200, json.dumps({
            "bridge_token": TOKEN,
            "physical_printer_id": payload["physical_printer_id"],
            "material_system_id": payload["material_system_id"],
            "provider": calls.provider,
        }).encode("utf-8")

    def moonraker(connection, path, payload=None, timeout=None, raw_text=False):
        calls.moonraker.append((connection, path))
        if calls.moonraker_status != 200:
            return calls.moonraker_status, {}, "refused"
        if path == "/server/config":
            if calls.config is None:
                return 500, {}, ""
            return 200, {"result": {"config": calls.config}}, ""
        calls.queries.append(payload)
        status = {"print_stats": dict(calls.stats), **calls.extra}
        if calls.mmu is not None:
            status["mmu"] = dict(calls.mmu)
        return 200, {"result": {"status": status}}, ""

    def desired(path, token):
        calls.desired_reads += 1
        return 200, json.dumps(calls.desired).encode("utf-8")

    def post(path, token, payload):
        calls.posted.append((path, token, payload))
        if path.endswith("usage-batches"):
            return 200, json.dumps(
                {"accepted": True, "ack_sequence": payload["sequence"]}
            ).encode("utf-8"), None
        return 200, b"{}", None

    monkeypatch.setattr(plugin, "http_post_json", grant)
    monkeypatch.setattr(plugin, "_moonraker_json", moonraker)
    monkeypatch.setattr(plugin, "http_get_bridge_json", desired)
    monkeypatch.setattr(plugin, "http_post_bridge_json", post)
    monkeypatch.setattr(plugin, "revoke_fresh_bridge_token", calls.revoked.append)

    def link(provider="legacy"):
        calls.provider = "happy_hare" if provider == "happy_hare" else "legacy"
        return plugin.link_moonraker_usage("user-token", _inventory(provider), [dict(CONNECTION)])

    def at(state, used, printed):
        calls.stats = {
            "state": state, "filename": "benchy.gcode",
            "filament_used": used, "print_duration": printed,
        }

    def posted(suffix):
        return [payload for path, _token, payload in calls.posted if path.endswith(suffix)]

    def items():
        return [
            item
            for batch in posted("usage-batches")
            for event in batch["events"]
            for item in event["items"]
        ]

    return SimpleNamespace(
        plugin=plugin, calls=calls, link=link, at=at, posted=posted, items=items,
        runtime=plugin.MoonrakerWatchRuntime(),
        stored=Path(plugin.MOONRAKER_USAGE_CONFIG_FILE),
    )


def _print_job(klipper, readings):
    for state, used, printed in readings:
        klipper.at(state, used, printed)
        klipper.runtime.watch_once()


def test_a_klipper_print_is_charged_once_to_the_assigned_spool(klipper):
    assert klipper.link() == 1
    # The address and the API key come from OrcaSlicer each session; only the
    # site's token and the connection's reference are written down.
    stored = klipper.stored.read_text(encoding="utf-8")
    assert TOKEN in stored and "voron.lan" not in stored and "moonraker-key" not in stored

    _print_job(klipper, [
        ("printing", 100.0, 10.0),
        ("printing", 400.0, 200.0),
        ("printing", 900.0, 400.0),
        ("complete", 1200.0, 500.0),
    ])

    # The books open at the first reading: what was extruded before it is not charged.
    assert [(item["spool_id"], item["usage_route_proof"]) for item in klipper.items()] == [
        (11, "proof-0"), (11, "proof-0"),
    ]
    assert sum(item["used_length_mm"] for item in klipper.items()) == pytest.approx(1100.0)
    # Klipper measured this length; nothing marks it as an estimate.
    assert all("consumption_kind" not in item for item in klipper.items())
    batches = klipper.posted("usage-batches")
    assert {batch["provider"] for batch in batches} == {"legacy"}
    assert batches[-1]["events"][-1]["outcome"] == "completed"
    assert klipper.posted("heartbeat")[0]["capabilities"] == ["read", "consumption"]

    # The same finished job read again, also by a restarted plugin, adds nothing.
    klipper.runtime.watch_once()
    klipper.plugin.MoonrakerWatchRuntime().watch_once()
    assert len(klipper.posted("usage-batches")) == len(batches)


def test_a_klipper_print_shows_its_state_on_filamenthub(klipper):
    assert klipper.link() == 1
    klipper.at("printing", 100.0, 10.0)
    klipper.calls.stats["info"] = {"total_layer": 120, "current_layer": 30}
    klipper.calls.extra = {
        "display_status": {"progress": 0.254},
        "extruder": {"temperature": 214.96, "target": 215.0},
        # A printer without a heated bed answers an empty object (webhooks.py:506).
        "heater_bed": {},
    }
    klipper.runtime.watch_once()

    asked = klipper.calls.queries[-1]["objects"]
    assert asked["display_status"] == ["progress"]
    assert {"state", "filename", "info", "filament_used"} <= set(asked["print_stats"])
    snapshots = klipper.posted("snapshot")
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert (snapshot["provider"], snapshot["transport"], snapshot["source_instance_id"]) == (
        "legacy", "orca_plugin_lan", SOURCE
    )
    assert snapshot["material_system_id"] == 9
    # Status only: the slots of a plain Klipper are the site's, not the printer's.
    assert "slots" not in snapshot and "capabilities" not in snapshot
    assert snapshot["printer"] == {
        "state": "printing",
        "job_name": "benchy.gcode",
        "progress_percent": 25,
        "current_layer": 30,
        "total_layers": 120,
        "nozzle_temperature": 215.0,
        "nozzle_target_temperature": 215.0,
    }


@pytest.mark.parametrize(("klipper_state", "shown"), [
    ("standby", {"state": "idle"}),
    ("complete", {"state": "finished", "job_name": "cube.gcode"}),
    ("cancelled", {"state": "failed", "job_name": "cube.gcode"}),
    ("error", {"state": "failed", "job_name": "cube.gcode"}),
    ("something_new", {"state": "unknown"}),
])
def test_klipper_print_states_map_to_the_sites_states(plugin_module, klipper_state, shown):
    printer = plugin_module.moonraker_printer({
        "print_stats": {
            "state": klipper_state, "filename": "cube.gcode",
            # Layers stay None until the slicer's SET_PRINT_STATS_INFO.
            "info": {"total_layer": None, "current_layer": None},
        },
        "display_status": {"progress": 1.0},
    })
    # Progress belongs to a running job only.
    assert printer == shown


def test_a_klipper_answer_without_print_stats_shows_no_state(plugin_module):
    assert plugin_module.moonraker_printer({}) is None
    assert plugin_module.moonraker_printer({"print_stats": {}}) is None
    assert plugin_module.moonraker_printer(None) is None


@pytest.mark.parametrize("config", [
    {"spoolman": {"server": "http://localhost:3000/api/v1/spool_compat/device-key"}},
    # FilamentHub behind the person's own proxy name is still FilamentHub.
    {"spoolman": {"server": "https://fh.home.lan/api/v1/spool_compat/device-key"}},
    {"spoolman": {}},
    None,
])
def test_moonrakers_own_link_to_filamenthub_is_never_counted_a_second_time(klipper, config):
    # A link that cannot be read counts as one to FilamentHub: nothing is safer than twice.
    klipper.calls.config = config
    klipper.link()

    _print_job(klipper, [
        ("printing", 100.0, 10.0),
        ("printing", 900.0, 400.0),
        ("complete", 1200.0, 500.0),
    ])

    assert klipper.posted("usage-batches") == []
    assert klipper.calls.desired_reads == 0
    assert klipper.posted("heartbeat")[0]["capabilities"] == ["read"]


def test_happy_hare_charges_the_feeding_gate_and_nobody_for_a_gate_change(klipper):
    klipper.calls.desired = {"slots": [
        {"index": 0, "usage_route_proof": "proof-0", "spool": {"id": 11}},
        {"index": 1, "usage_route_proof": "proof-1", "spool": {"id": 12}},
    ]}

    def gate(index, toolchanges):
        klipper.calls.mmu = {
            "num_gates": 2, "gate_status": [1, 1], "gate": index, "tool": index,
            "filament_pos": 10, "spoolman_support": "off", "num_toolchanges": toolchanges,
        }

    klipper.link("happy_hare")
    gate(0, 0)
    _print_job(klipper, [("printing", 100.0, 10.0), ("printing", 500.0, 100.0)])
    gate(1, 1)
    # Which spool fed the stretch around the change is unknown.
    _print_job(klipper, [("printing", 700.0, 150.0), ("printing", 1000.0, 250.0)])
    # Gate 1 is feeding again, but the MMU went to gate 0 and back in between:
    # part of this stretch came from the other spool.
    gate(1, 3)
    _print_job(klipper, [("printing", 1500.0, 300.0)])
    _print_job(klipper, [("complete", 1600.0, 350.0)])

    assert [(item["spool_id"], item["used_length_mm"]) for item in klipper.items()] == [
        (11, pytest.approx(400.0)), (12, pytest.approx(300.0)), (12, pytest.approx(100.0)),
    ]
    assert {batch["provider"] for batch in klipper.posted("usage-batches")} == {"happy_hare"}


def test_happy_hare_that_counts_no_tool_changes_is_not_guessed_at(klipper):
    klipper.calls.desired = {"slots": [
        {"index": 0, "usage_route_proof": "proof-0", "spool": {"id": 11}},
        {"index": 1, "usage_route_proof": "proof-1", "spool": {"id": 12}},
    ]}
    klipper.calls.mmu = {
        "num_gates": 2, "gate_status": [1, 1], "gate": 0, "tool": 0, "filament_pos": 10,
    }
    klipper.link("happy_hare")

    _print_job(klipper, [("printing", 100.0, 10.0), ("complete", 900.0, 400.0)])

    (event,) = [event for batch in klipper.posted("usage-batches") for event in batch["events"]]
    assert event["items"] == [] and event["skipped"] == [{"reason": "active_slot_unknown"}]


def test_nothing_is_counted_until_the_site_names_this_plugin_the_one_that_deducts(klipper):
    # No proof: Moonraker's own link or another helper is deducting this print.
    klipper.calls.desired = {"slots": [{"index": 0, "spool": {"id": 11}}]}
    klipper.link()

    _print_job(klipper, [("printing", 100.0, 10.0), ("printing", 900.0, 400.0)])
    klipper.calls.desired = {"slots": [
        {"index": 0, "usage_route_proof": "proof-0", "spool": {"id": 11}},
    ]}
    _print_job(klipper, [("printing", 1000.0, 450.0), ("complete", 1300.0, 500.0)])

    # Only what was extruded after the site handed the print over is charged.
    assert [item["used_length_mm"] for item in klipper.items()] == [pytest.approx(300.0)]


def test_a_job_picked_up_after_orcaslicer_was_closed_skips_what_nobody_watched(klipper, monkeypatch):
    klipper.link()
    _print_job(klipper, [("printing", 100.0, 10.0), ("printing", 400.0, 100.0)])
    clock = klipper.plugin.time.time()
    monkeypatch.setattr(klipper.plugin.time, "time", lambda: clock + 3600)

    restarted = klipper.plugin.MoonrakerWatchRuntime()
    for state, used, printed in [("printing", 5000.0, 3700.0), ("complete", 5200.0, 3800.0)]:
        klipper.at(state, used, printed)
        restarted.watch_once()

    assert [item["used_length_mm"] for item in klipper.items()] == [
        pytest.approx(300.0), pytest.approx(200.0),
    ]


def test_a_link_to_some_other_spoolman_leaves_the_counting_to_the_plugin(klipper):
    # That Spoolman tells FilamentHub nothing: without the plugin nobody would deduct here.
    klipper.calls.config = {"spoolman": {"server": "http://spoolman.lan:7912"}}
    klipper.link()

    _print_job(klipper, [("printing", 100.0, 10.0), ("complete", 900.0, 400.0)])

    assert [item["used_length_mm"] for item in klipper.items()] == [pytest.approx(800.0)]
    assert klipper.posted("heartbeat")[0]["capabilities"] == ["read", "consumption"]


def test_a_qidi_box_print_is_charged_to_the_slot_the_box_loaded(klipper, monkeypatch):
    plugin = klipper.plugin
    klipper.calls.desired = {"slots": [
        {"index": index, "usage_route_proof": "proof-%d" % index, "spool": {"id": 20 + index}}
        for index in range(4)
    ]}
    loaded = {"slot": "slot2"}
    plain = plugin._moonraker_json

    def with_box(connection, path, payload=None, timeout=None, raw_text=False):
        status, body, error = plain(connection, path, payload, timeout, raw_text)
        if path == "/printer/objects/query":
            assert "save_variables" in payload["objects"]
            body["result"]["status"]["save_variables"] = {
                "variables": {"box_count": 1, "last_load_slot": loaded["slot"]},
            }
        return status, body, error

    monkeypatch.setattr(plugin, "_moonraker_json", with_box)
    klipper.link()

    _print_job(klipper, [("printing", 100.0, 10.0), ("printing", 600.0, 100.0)])
    # Nothing is loaded while the Box swaps filament: that stretch is nobody's.
    loaded["slot"] = "slot-1"
    _print_job(klipper, [("printing", 650.0, 130.0)])
    loaded["slot"] = "slot0"
    _print_job(klipper, [("printing", 700.0, 160.0), ("complete", 1000.0, 300.0)])

    assert [(item["spool_id"], item["used_length_mm"]) for item in klipper.items()] == [
        (22, pytest.approx(500.0)), (20, pytest.approx(300.0)),
    ]


def _snapmaker_head(klipper, active, switches):
    """A Snapmaker U1 printing with head ``active`` after ``switches`` head changes."""
    counts = [switches, 0, 0, 0]
    klipper.calls.extra = {
        "print_task_config": {"filament_exist": [True] * 4},
        "toolhead": {"extruder": ("extruder", "extruder1", "extruder2", "extruder3")[active]},
        **{
            name: {"switch_count": count}
            for name, count in zip(("extruder", "extruder1", "extruder2", "extruder3"), counts)
        },
    }


def test_a_snapmaker_u1_print_is_charged_to_the_head_that_prints(klipper):
    klipper.calls.desired = {"slots": [
        {"index": index, "usage_route_proof": "proof-%d" % index, "spool": {"id": 30 + index}}
        for index in range(4)
    ]}
    klipper.link()

    _snapmaker_head(klipper, 0, 0)
    _print_job(klipper, [("printing", 100.0, 10.0), ("printing", 500.0, 100.0)])
    # The query asks for the head and the change counts of every head.
    objects = klipper.calls.queries[-1]["objects"]
    assert objects["toolhead"] == ["extruder"] and "switch_count" in objects["extruder3"]
    _snapmaker_head(klipper, 2, 1)
    # Which head printed the stretch around the change is unknown.
    _print_job(klipper, [("printing", 700.0, 150.0), ("printing", 1000.0, 250.0)])
    # Head 3 prints again, but the printer went to another head and back.
    _snapmaker_head(klipper, 2, 3)
    _print_job(klipper, [("printing", 1500.0, 300.0)])
    _print_job(klipper, [("complete", 1600.0, 350.0)])

    assert [(item["spool_id"], item["used_length_mm"]) for item in klipper.items()] == [
        (30, pytest.approx(400.0)), (32, pytest.approx(300.0)), (32, pytest.approx(100.0)),
    ]


def test_a_snapmaker_u1_without_head_change_counts_is_not_guessed_at(klipper):
    klipper.calls.desired = {"slots": [
        {"index": index, "usage_route_proof": "proof-%d" % index, "spool": {"id": 30 + index}}
        for index in range(4)
    ]}
    klipper.link()
    _snapmaker_head(klipper, 1, 0)
    del klipper.calls.extra["extruder2"]

    _print_job(klipper, [("printing", 100.0, 10.0), ("complete", 900.0, 400.0)])

    (event,) = [event for batch in klipper.posted("usage-batches") for event in batch["events"]]
    assert event["items"] == [] and event["skipped"] == [{"reason": "active_slot_unknown"}]


def test_a_print_without_an_assigned_spool_says_why_nothing_was_deducted(klipper):
    klipper.calls.desired = {"slots": [{"index": 0, "spool": None}]}
    klipper.link()

    _print_job(klipper, [("printing", 100.0, 10.0), ("complete", 900.0, 400.0)])

    (event,) = [event for batch in klipper.posted("usage-batches") for event in batch["events"]]
    assert event["items"] == [] and event["skipped"] == [{"reason": "no_spool_assigned"}]


def test_a_printer_that_stops_answering_keeps_what_is_charged_and_skips_the_gap(klipper):
    klipper.link()
    _print_job(klipper, [("printing", 100.0, 10.0), ("printing", 400.0, 100.0)])
    klipper.calls.moonraker_status = 0
    klipper.runtime.watch_once()
    klipper.calls.moonraker_status = 200
    _print_job(klipper, [("printing", 2000.0, 600.0), ("complete", 2100.0, 650.0)])

    assert [item["used_length_mm"] for item in klipper.items()] == [
        pytest.approx(300.0), pytest.approx(100.0),
    ]


def test_a_link_of_another_account_is_given_back(klipper):
    klipper.link()
    klipper.calls.granted.clear()

    kept = klipper.plugin.link_moonraker_usage(
        "user-token", {"source_instance_id": SOURCE, "printers": []}, [dict(CONNECTION)]
    )

    assert kept == 0 and klipper.calls.revoked == [TOKEN]
    assert klipper.plugin._load_moonraker_usage_links() == []
    assert klipper.runtime.watch_once() is None


def test_a_site_without_the_usage_link_is_asked_once(klipper):
    klipper.calls.grant_status = 404

    assert klipper.link() == 0 and klipper.link() == 0

    assert len(klipper.calls.granted) == 1

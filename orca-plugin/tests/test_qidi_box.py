"""QIDI Box through Moonraker. Fixtures are shared with Edge and follow the
shapes read by OrcaSlicer's QidiPrinterAgent (a65ae5fe); they are reconstructed
from that implementation, not captured from a device."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "edge-agent" / "tests" / "fixtures" / "qidi_box"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _moonraker(dictionary_status=200):
    def call(_connection, path, payload=None, timeout=None, raw_text=False):
        if path == "/printer/objects/list":
            return 200, json.loads(_fixture("objects_list.json")), ""
        if path == "/printer/objects/query":
            assert "save_variables" in payload["objects"]
            return 200, json.loads(_fixture("query.json")), ""
        if path == "/server/files/config/officiall_filas_list.cfg":
            assert raw_text is True
            return dictionary_status, _fixture("officiall_filas_list.cfg"), ""
        raise AssertionError(path)

    return call


def test_slots_follow_the_orca_reader_rules(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "_moonraker_json", _moonraker())

    slots = plugin_module.read_qidi_box_snapshot({"print_host": "qidi:7125"})["qidi_slots"]

    assert [slot["present"] for slot in slots] == [True, True, False, None]
    assert (slots[0]["material"], slots[0]["color_hex"]) == ("PLA", "060606")
    assert (slots[1]["material"], slots[1]["color_hex"]) == ("PETG", "0A2989")
    assert "material" not in slots[2]
    assert all(slot["spool_identity_known"] is False for slot in slots)


def test_missing_dictionary_keeps_presence_without_guessing_material(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "_moonraker_json", _moonraker(dictionary_status=404))

    slots = plugin_module.read_qidi_box_snapshot({"print_host": "qidi:7125"})["qidi_slots"]

    assert slots[0]["present"] is True
    assert "material" not in slots[0] and "color_hex" not in slots[0]


def test_reader_dispatch_by_moonraker_objects(plugin_module, monkeypatch):
    def objects(names):
        return lambda *_args, **_kwargs: (200, {"result": {"objects": names}}, "")

    monkeypatch.setattr(plugin_module, "read_happy_hare_snapshot", lambda _c: {"gate_count": 4})
    monkeypatch.setattr(plugin_module, "read_qidi_box_snapshot", lambda _c: {"qidi_slots": []})

    monkeypatch.setattr(plugin_module, "_moonraker_json", objects(["mmu", "print_stats"]))
    assert plugin_module.read_printer_material_snapshot({}) == {"gate_count": 4}
    monkeypatch.setattr(plugin_module, "_moonraker_json", objects(["box_stepper slot0"]))
    assert plugin_module.read_printer_material_snapshot({}) == {"qidi_slots": []}
    monkeypatch.setattr(plugin_module, "_moonraker_json", objects(["print_stats"]))
    with pytest.raises(ValueError):
        plugin_module.read_printer_material_snapshot({})


def test_qidi_slots_upload_to_the_moonraker_endpoint(plugin_module, monkeypatch):
    calls = []
    monkeypatch.setattr(
        plugin_module, "http_post_json", lambda path, token, body: calls.append((path, body)) or (200, b"{}")
    )
    monkeypatch.setattr(
        plugin_module, "upload_happy_hare_snapshot", lambda *_a: pytest.fail("HH endpoint used")
    )

    plugin_module.upload_printer_material_snapshot(
        "token", 7, {"qidi_slots": [{"provider_index": 0, "kind": "slot"}]}
    )

    path, body = calls[0]
    assert path == "/orcaslicer/preset-slot-sync/moonraker/snapshot"
    assert body["physical_printer_id"] == 7 and body["slots"][0]["provider_index"] == 0

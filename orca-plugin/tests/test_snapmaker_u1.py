"""Snapmaker U1 heads through Moonraker.

The answers follow Snapmaker/u1-klipper 7ac453b5 (print_task_config.py,
kinematics/extruder.py); they are built from that source, not captured from a
printer.
"""


def _heads(**overrides):
    config = {
        "filament_exist": [True, True, False, True],
        "filament_type": ["PLA", "PETG", "NONE", "PLA"],
        "filament_sub_type": ["SILK", "NONE", "NONE", "CF"],
        "filament_color_rgba": ["FF0000FF", "1A73E8FF", "FFFFFFFF", "NONE"],
        "filament_vendor": ["Snapmaker", "Generic", "NONE", "NONE"],
    }
    config.update(overrides)
    return {"print_task_config": config, "toolhead": {"extruder": "extruder1"}}


def _moonraker(status):
    def call(_connection, path, payload=None, timeout=None, raw_text=False):
        if path == "/printer/objects/list":
            return 200, {"result": {"objects": ["print_stats", "toolhead", "print_task_config"]}}, ""
        if path == "/printer/objects/query":
            assert set(payload["objects"]) == {"print_task_config", "toolhead"}
            return 200, {"result": {"status": status}}, ""
        raise AssertionError(path)

    return call


def test_the_four_heads_become_four_slots(plugin_module, monkeypatch):
    monkeypatch.setattr(plugin_module, "_moonraker_json", _moonraker(_heads()))

    slots = plugin_module.read_printer_material_snapshot({"print_host": "u1:7125"})["qidi_slots"]

    assert [slot["provider_index"] for slot in slots] == [0, 1, 2, 3]
    assert [slot["present"] for slot in slots] == [True, True, False, True]
    # Material names combine as in OrcaSlicer's own Snapmaker agent.
    assert (slots[0]["material"], slots[0]["color_hex"]) == ("PLA SILK", "FF0000")
    assert (slots[1]["material"], slots[1]["color_hex"]) == ("PETG", "1A73E8")
    assert "material" not in slots[2]
    # "NONE" is the firmware's word for unknown: no colour is made up.
    assert slots[3]["material"] == "PLA-CF" and "color_hex" not in slots[3]
    assert [slot["active_feed"] for slot in slots] == [False, True, False, False]


def test_a_head_without_a_known_type_reports_presence_only(plugin_module):
    slots = plugin_module.parse_snapmaker_slots(
        _heads(filament_type=["NONE"] * 4, filament_exist=[True, "yes", False])
    )

    assert [slot["present"] for slot in slots] == [True, None, False, None]
    assert all("material" not in slot for slot in slots)


def test_an_unknown_toolhead_names_no_feeding_head(plugin_module):
    status = _heads()
    status["toolhead"] = {"extruder": "extruder7"}

    assert plugin_module.snapmaker_active_head(status) is None
    assert all("active_feed" not in slot for slot in plugin_module.parse_snapmaker_slots(status))


def test_head_changes_are_counted_over_all_four_heads(plugin_module):
    status = {name: {"switch_count": count} for name, count in zip(
        ("extruder", "extruder1", "extruder2", "extruder3"), (3, 2, 0, 1)
    )}
    assert plugin_module.snapmaker_switch_mark(status) == 6
    del status["extruder2"]
    assert plugin_module.snapmaker_switch_mark(status) is None

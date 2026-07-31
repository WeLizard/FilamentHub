from octoprint_filamenthub_bridge.tracker import ExtrusionTracker


def test_absolute_extrusion_retraction_and_recovery_are_not_double_counted():
    tracker = ExtrusionTracker()
    slots = {0}
    tracker.process(
        command="M82",
        gcode="M82",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E10",
        gcode="G1",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E8",
        gcode="G1",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E10",
        gcode="G1",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E14.5",
        gcode="G1",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )

    assert tracker.used_length_by_slot == {0: 14.5}


def test_relative_extrusion_can_follow_manual_slot_changes():
    tracker = ExtrusionTracker()
    slots = {0, 6}
    tracker.process(
        command="M83",
        gcode="M83",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E3",
        gcode="G1",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E2",
        gcode="G1",
        active_slot=6,
        map_tools_to_slots=False,
        available_slots=slots,
    )

    assert tracker.used_length_by_slot == {0: 3.0, 6: 2.0}


def test_tool_mapping_uses_tools_only_when_explicitly_enabled():
    tracker = ExtrusionTracker()
    slots = {0, 1, 2}
    selected, _ = tracker.process(
        command="T2",
        gcode="T",
        active_slot=0,
        map_tools_to_slots=True,
        available_slots=slots,
    )
    tracker.process(
        command="G1 E5",
        gcode="G1",
        active_slot=selected,
        map_tools_to_slots=True,
        available_slots=slots,
    )

    assert selected == 2
    assert tracker.used_length_by_slot == {2: 5.0}


def test_arc_moves_with_extrusion_are_counted():
    tracker = ExtrusionTracker()
    slots = {0}
    tracker.process(
        command="M83",
        gcode="M83",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G2 X10 Y10 I5 J0 E4.25",
        gcode="G2",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )
    tracker.process(
        command="G3 X0 Y0 I-5 J0 E3.75",
        gcode="G3",
        active_slot=0,
        map_tools_to_slots=False,
        available_slots=slots,
    )

    assert tracker.used_length_by_slot == {0: 8.0}

"""The browser's walk of a G-code toolpath stands in for the server's own walk of the file.

The same fixture and expected walk are read by the frontend test, so the two
implementations of the line walk cannot drift apart unnoticed.
"""

from __future__ import annotations

import copy
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.services.calculator_gcode_parser import (
    GcodeLines,
    ToolpathEvidence,
    ToolpathEvidenceError,
    parse_gcode_3mf_excerpt,
    parse_gcode_excerpt,
    parse_gcode_payload,
)

FIXTURES = Path(__file__).parent / "fixtures" / "gcode_toolpath_parity"
RAW = (FIXTURES / "toolpath.gcode").read_bytes()
EXPECTED = json.loads((FIXTURES / "expected_evidence.json").read_text(encoding="utf-8"))

_PER_PART_FIELDS = (
    "infill_filament_weight_g",
    "support_filament_weight_g",
    "brim_filament_weight_g",
    "prime_tower_filament_weight_g",
    "object_filament_weight_g",
    "shared_filament_weight_g",
    "object_count",
    "object_groups",
    "support_roles_detected",
    "support_used",
    "toolchange_count",
)
_PER_MATERIAL_FIELDS = (
    "infill_weight_g",
    "support_weight_g",
    "brim_weight_g",
    "prime_tower_weight_g",
)


def _walk(raw: bytes) -> ToolpathEvidence:
    evidence = ToolpathEvidence()
    for line in GcodeLines(raw.decode("utf-8")):
        evidence.consume(line.strip())
    return evidence


def _per_part(job: dict[str, Any]) -> dict[str, Any]:
    return {
        **{field: job[field] for field in _PER_PART_FIELDS},
        "materials": [
            {field: material.get(field) for field in _PER_MATERIAL_FIELDS}
            for material in job["materials"]
        ],
    }


def test_the_shared_fixture_exercises_what_the_walk_has_to_get_right() -> None:
    assert b"\r\n" in RAW
    assert re.search(rb"(?<!\r)\n", RAW) is not None
    assert len(RAW) < 200 * 1024
    assert set(EXPECTED["extrusion_by_tool_role"]) == {"0", "1"}
    assert EXPECTED["observed_toolchange_count"] == 2
    assert EXPECTED["support_roles"] == ["support", "support interface"]


def test_the_python_walk_equals_the_expected_evidence_of_the_fixture() -> None:
    assert _walk(RAW).to_payload() == EXPECTED


def test_evidence_survives_a_json_round_trip() -> None:
    evidence = _walk(RAW)
    restored = ToolpathEvidence.from_payload(json.loads(json.dumps(evidence.to_payload())))

    assert restored.to_payload() == evidence.to_payload()


def test_a_summary_with_the_toolpath_equals_the_full_parse() -> None:
    full = parse_gcode_payload("toolpath.gcode", RAW)
    toolpath = ToolpathEvidence.from_payload(EXPECTED)

    excerpt = parse_gcode_excerpt("toolpath.gcode", len(RAW), RAW, None, toolpath)

    assert excerpt.pop("detail_level") == "full"
    assert excerpt == full
    assert full["toolchange_count"] == 2
    assert full["support_roles_detected"] == ["support", "support interface"]
    assert [group["name"] for group in full["object_groups"]] == ["Bracket id 2", "Cube"]
    assert all(group["extrusion_share"] is not None for group in full["object_groups"])
    assert full["prime_tower_filament_weight_g"] is not None
    assert full["brim_filament_weight_g"] is not None


def test_the_head_and_tail_with_the_toolpath_equal_the_full_parse() -> None:
    full = parse_gcode_payload("toolpath.gcode", RAW)
    footer_start = RAW.index(b"; filament used [mm]")
    head, tail = RAW[:300], RAW[footer_start - 7 :]

    summary = parse_gcode_excerpt("toolpath.gcode", len(RAW), head, tail)
    excerpt = parse_gcode_excerpt(
        "toolpath.gcode", len(RAW), head, tail, ToolpathEvidence.from_payload(EXPECTED)
    )

    assert summary["detail_level"] == "summary"
    assert all(group["extrusion_share"] is None for group in summary["object_groups"])
    assert summary["support_roles_detected"] == []
    assert excerpt["detail_level"] == "full"
    assert _per_part(excerpt) == _per_part(full)
    assert excerpt["total_filament_weight_g"] == full["total_filament_weight_g"]


def test_a_sliced_3mf_plate_with_the_toolpath_equals_the_full_parse() -> None:
    slice_info = (
        '<?xml version="1.0" encoding="UTF-8"?><config><plate>'
        '<metadata key="index" value="1"/>'
        '<metadata key="prediction" value="730"/>'
        '<metadata key="weight" value="4.8"/>'
        # The slice info's own support flag outranks the roles seen in the moves.
        '<metadata key="support_used" value="false"/>'
        '<filament id="1" type="PETG" color="#FFFFFF" used_m="0.1" used_g="3.0"/>'
        '<filament id="2" type="PLA" color="#000000" used_m="0.06" used_g="1.8"/>'
        "</plate></config>"
    )
    settings = {
        "filament_type": ["PETG", "PLA"],
        "filament_settings_id": ["Generic PETG", "Generic PLA"],
        "filament_vendor": ["Generic", "Bambu Lab"],
        "filament_colour": ["#FFFFFF", "#000000"],
        "filament_density": ["1.27", "1.24"],
        "filament_diameter": ["1.75", "1.75"],
        "nozzle_diameter": ["0.4"],
        "layer_height": "0.2",
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("Metadata/plate_1.gcode", RAW)
        bundle.writestr("Metadata/slice_info.config", slice_info)
        bundle.writestr("Metadata/project_settings.config", json.dumps(settings))
    full = parse_gcode_payload("two.gcode.3mf", archive.getvalue())

    [plate] = parse_gcode_3mf_excerpt(
        "two.gcode.3mf",
        len(archive.getvalue()),
        {
            "metadata/slice_info.config": slice_info.encode(),
            "metadata/project_settings.config": json.dumps(settings).encode(),
        },
        {1: ToolpathEvidence.from_payload(EXPECTED)},
    )

    assert plate["detail_level"] == "full"
    assert full["support_used"] is False
    assert _per_part(plate) == _per_part(full)
    assert plate["support_filament_weight_g"] > 0


def test_a_plate_without_a_toolpath_stays_a_summary() -> None:
    slice_info = (
        '<config><plate><metadata key="index" value="1"/>'
        '<metadata key="prediction" value="60"/></plate>'
        '<plate><metadata key="index" value="2"/>'
        '<metadata key="prediction" value="90"/></plate></config>'
    ).encode()

    first, second = parse_gcode_3mf_excerpt(
        "a.gcode.3mf",
        1000,
        {"metadata/slice_info.config": slice_info},
        {2: ToolpathEvidence.from_payload(EXPECTED)},
    )

    assert (first["detail_level"], second["detail_level"]) == ("summary", "full")


BAMBU_RAW = (FIXTURES / "bambu_toolpath.gcode").read_bytes()
BAMBU_EXPECTED = json.loads(
    (FIXTURES / "bambu_expected_evidence.json").read_text(encoding="utf-8")
)


def test_the_python_walk_equals_the_expected_evidence_of_the_bambu_fixture() -> None:
    assert _walk(BAMBU_RAW).to_payload() == BAMBU_EXPECTED
    # Both copies of the part and the part named only by its label are told apart.
    assert BAMBU_EXPECTED["object_names"] == [
        "Cube_id_1111_copy_0",
        "Cube_id_1111_copy_1",
        "label 31",
        "My Part v2_id_2222_copy_0",
    ]
    assert BAMBU_EXPECTED["support_roles"] == ["support", "support interface"]


def test_a_bambu_file_gets_support_weight_and_object_groups_in_either_parse() -> None:
    full = parse_gcode_payload("bambu.gcode", BAMBU_RAW)
    excerpt = parse_gcode_excerpt(
        "bambu.gcode", len(BAMBU_RAW), BAMBU_RAW, None, ToolpathEvidence.from_payload(BAMBU_EXPECTED)
    )

    assert excerpt.pop("detail_level") == "full"
    assert excerpt == full
    assert full["support_roles_detected"] == ["support", "support interface"]
    assert full["support_used"] is True
    assert full["support_filament_weight_g"] == pytest.approx(12.0 * 3.5 / 9.7, abs=1e-3)
    assert full["prime_tower_filament_weight_g"] > 0
    assert [(group["name"], group["count"]) for group in full["object_groups"]] == [
        ("Cube", 2),
        ("label 31", 1),
        ("My Part v2", 1),
    ]
    assert sum(group["extrusion_share"] for group in full["object_groups"]) == pytest.approx(
        1.0, abs=1e-5
    )


def test_a_bambu_3mf_names_the_objects_its_gcode_left_anonymous_the_same_in_both_parses() -> None:
    slice_info = (
        '<?xml version="1.0" encoding="UTF-8"?><config><plate>'
        '<metadata key="index" value="1"/>'
        '<metadata key="prediction" value="730"/>'
        '<metadata key="weight" value="12.0"/>'
        '<metadata key="support_used" value="true"/>'
        '<object identify_id="7" name="Named by the slice info too" skipped="false" />'
        '<object identify_id="31" name="Bracket" skipped="false" />'
        '<filament id="1" type="PETG" color="#FFFFFF" used_m="0.1" used_g="12.0"/>'
        "</plate></config>"
    )
    settings = {
        "filament_type": ["PETG"],
        "filament_settings_id": ["Generic PETG"],
        "filament_vendor": ["Generic"],
        "filament_colour": ["#FFFFFF"],
        "filament_density": ["1.27"],
        "filament_diameter": ["1.75"],
        "nozzle_diameter": ["0.4"],
        "layer_height": "0.2",
    }
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("Metadata/plate_1.gcode", BAMBU_RAW)
        bundle.writestr("Metadata/slice_info.config", slice_info)
        bundle.writestr("Metadata/project_settings.config", json.dumps(settings))
    full = parse_gcode_payload("bambu.gcode.3mf", archive.getvalue())

    [plate] = parse_gcode_3mf_excerpt(
        "bambu.gcode.3mf",
        len(archive.getvalue()),
        {
            "metadata/slice_info.config": slice_info.encode(),
            "metadata/project_settings.config": json.dumps(settings).encode(),
        },
        {1: ToolpathEvidence.from_payload(BAMBU_EXPECTED)},
    )

    assert _per_part(plate) == _per_part(full)
    # The file's own name for label 7 wins; only the anonymous label 31 asks the slice info.
    assert [group["name"] for group in full["object_groups"]] == ["Bracket", "Cube", "My Part v2"]
    assert full["support_filament_weight_g"] > 0


def test_a_label_without_any_name_stays_a_label_and_one_the_slice_info_names_takes_it() -> None:
    evidence = ToolpathEvidence.from_payload(BAMBU_EXPECTED)

    evidence.rename_unresolved_labels({"31": "Bracket", "99": "Never seen"})

    payload = evidence.to_payload()
    assert "Bracket_id_31" in payload["object_names"]
    assert "label 31" not in payload["object_names"]
    assert payload["extrusion_by_tool_object"]["0"]["Bracket_id_31"] == 0.9
    assert not any("99" in name for name in payload["object_names"])


def _mutated(path: list[str | int], value: Any) -> dict[str, Any]:
    payload = copy.deepcopy(EXPECTED)
    target: Any = payload
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return payload


_TOO_MANY_TOOLS = {str(tool): {"infill": 1.0} for tool in range(257)}
_TOO_MANY_ROLES = {"0": {f"role {index}": 1.0 for index in range(65)}}
_TOO_MANY_OBJECTS = {"0": {f"object_{index}": 1.0 for index in range(1025)}}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="not-an-object"),
        pytest.param({**EXPECTED, "version": 2}, id="unknown-version"),
        pytest.param({**EXPECTED, "version": True}, id="boolean-version"),
        pytest.param({k: v for k, v in EXPECTED.items() if k != "version"}, id="no-version"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", "brim"], float("nan")), id="nan"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", "brim"], float("inf")), id="inf"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", "brim"], -0.1), id="negative"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", "brim"], True), id="boolean-amount"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", "brim"], "1.5"), id="text-amount"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", "brim"], 10**400), id="huge-int"),
        pytest.param(_mutated(["extrusion_by_tool_object", "0", "x" * 201], 1.0), id="long-name"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0", ""], 1.0), id="empty-name"),
        pytest.param(_mutated(["object_names"], ["x" * 201]), id="long-object-name"),
        pytest.param(_mutated(["object_names"], [f"o{i}" for i in range(1025)]), id="objects"),
        pytest.param(_mutated(["support_roles"], ["a"] * 65), id="support-roles"),
        pytest.param(_mutated(["extrusion_by_tool_role"], _TOO_MANY_TOOLS), id="tools"),
        pytest.param(_mutated(["extrusion_by_tool_role"], _TOO_MANY_ROLES), id="roles"),
        pytest.param(_mutated(["extrusion_by_tool_object"], _TOO_MANY_OBJECTS), id="tool-objects"),
        pytest.param(_mutated(["extrusion_by_tool_role"], {"a": {"x": 1.0}}), id="tool-key"),
        pytest.param(_mutated(["extrusion_by_tool_role"], {"01": {"x": 1.0}}), id="padded-key"),
        pytest.param(_mutated(["extrusion_by_tool_role"], {"65536": {"x": 1.0}}), id="tool-index"),
        pytest.param(_mutated(["observed_tool"], -1), id="negative-tool"),
        pytest.param(_mutated(["observed_tool"], 1.5), id="fractional-tool"),
        pytest.param(_mutated(["observed_toolchange_count"], -1), id="negative-changes"),
        pytest.param(_mutated(["observed_toolchange_count"], None), id="missing-changes"),
        pytest.param(_mutated(["extrusion_by_tool_role", "0"], ["brim"]), id="roles-not-object"),
        pytest.param(_mutated(["object_names"], "Cube"), id="names-not-list"),
    ],
)
def test_a_toolpath_that_breaks_the_contract_is_refused(payload: Any) -> None:
    with pytest.raises(ToolpathEvidenceError):
        ToolpathEvidence.from_payload(payload)


def test_a_tool_that_extruded_nothing_is_dropped_and_zero_is_allowed() -> None:
    payload = _mutated(["extrusion_by_tool_role"], {"0": {"brim": 0.0}, "3": {}})

    evidence = ToolpathEvidence.from_payload(payload)

    assert evidence.extrusion_by_tool_role == {0: {"brim": 0.0}}

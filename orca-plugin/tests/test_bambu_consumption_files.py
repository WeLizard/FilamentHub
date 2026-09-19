from __future__ import annotations

import io
import zipfile


def _archive(*plates: tuple[int, str, float]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, gcode, weight in plates:
            archive.writestr(f"Metadata/plate_{index}.gcode", gcode)
        config = "<config>" + "".join(
            f'<plate><metadata key="index" value="{index}" />'
            f'<filament id="1" used_g="{weight}" /></plate>'
            for index, _gcode, weight in plates
        ) + "</config>"
        archive.writestr("Metadata/slice_info.config", config)
    return output.getvalue()


def test_plain_gcode_returns_positive_finite_vector(plugin_module):
    result = plugin_module.parse_bambu_consumption_file(
        b"; filament used [g] = 0, 12.5, -1, nan, 3e0\n"
    )
    assert result == {"source": "slicer_gcode", "weights": {1: 12.5, 4: 3.0}}


def test_3mf_requires_explicit_plate_when_multiple_exist(plugin_module):
    data = _archive((1, "; filament used [g] = 2\n", 2), (2, "; filament used [g] = 3\n", 3))
    assert plugin_module.parse_bambu_consumption_file(data) is None
    assert plugin_module.parse_bambu_consumption_file(data, "Metadata/plate_2.gcode")["weights"] == {0: 3.0}


def test_3mf_reads_slice_info_and_rejects_xml_entities(plugin_module):
    data = _archive((1, "; no vector\n", 4.25))
    result = plugin_module.parse_bambu_consumption_file(data, "Metadata/plate_1.gcode")
    assert result["source"] == "slicer_3mf"
    assert result["weights"] == {0: 4.25}

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "; filament used [g] = 2\n")
        archive.writestr("Metadata/slice_info.config", "<!DOCTYPE config [<!ENTITY x 'bad'>]><config/>")
    assert plugin_module.parse_bambu_consumption_file(output.getvalue(), "Metadata/plate_1.gcode") is None


def test_oversized_input_is_rejected(plugin_module):
    assert plugin_module.parse_bambu_consumption_file(b"x" * (64 * 1024 * 1024 + 1)) is None

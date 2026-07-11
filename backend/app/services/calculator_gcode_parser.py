"""G-code parsing helpers for Calculator Pro."""

from __future__ import annotations

import base64
import gzip
import io
import json
import logging
import re
import zipfile
from typing import Any
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

SUPPORTED_GCODE_EXTENSIONS = (".gcode.3mf", ".gcode.gz", ".gcode", ".txt")

MAX_DECOMPRESSED_GCODE_BYTES = 200 * 1024 * 1024
MAX_GCODE_3MF_ENTRIES = 1024
MAX_GCODE_3MF_SLICE_INFO_BYTES = 2 * 1024 * 1024
MAX_GCODE_3MF_THUMBNAIL_BYTES = 8 * 1024 * 1024

_THUMBNAIL_BEGIN_RE = re.compile(r"^;\s*thumbnail begin(?:\s+(\d+)x(\d+))?", re.IGNORECASE)
_THUMBNAIL_END_RE = re.compile(r"^;\s*thumbnail end", re.IGNORECASE)
_THUMBNAIL_BLOCK_START_RE = re.compile(r"^;\s*THUMBNAIL_BLOCK_START", re.IGNORECASE)
_THUMBNAIL_BLOCK_END_RE = re.compile(r"^;\s*THUMBNAIL_BLOCK_END", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(r"^([^:=]+?)\s*(?:=|:)\s*(.+)$")
_INLINE_ASSIGNMENT_RE = re.compile(r"\b([A-Z_]+)=([^\s]+)")

_SLICER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "OrcaSlicer": ("orcaslicer", "orca slicer", "orca_slicer"),
    "BambuStudio": ("bambustudio", "bambu studio", "bambu_studio"),
    "PrusaSlicer": ("prusaslicer", "prusa slicer", "prusa_slicer"),
    "SuperSlicer": ("superslicer", "super slicer", "super_slicer"),
    "Cura": ("cura", "curaengine", "cura_steamengine", "cura_steam_engine"),
    "CrealitySlicer": ("crealityslicer", "creality slicer", "creality_slicer", "creality print", "creality_print"),
}

_VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?(?:[-+._a-z0-9]*)?)\b", re.IGNORECASE)
_CURA_SETTING_RE = re.compile(r"^SETTING_3\s+(.*)$", re.IGNORECASE)
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")
_OBJECT_CENTER_RE = re.compile(r"\bCENTER=([-\d.]+),([-\d.]+)", re.IGNORECASE)
_OBJECT_NAME_RE = re.compile(r"\bNAME=([^\s]+)", re.IGNORECASE)
_PRINT_START_PARAMETER_RE = re.compile(r"\b(EXTRUDER|BED)=([\d.]+)", re.IGNORECASE)
_NOZZLE_TEMPERATURE_COMMAND_RE = re.compile(r"^M10(?:4|9)\s+S([\d.]+)", re.IGNORECASE)
_BED_TEMPERATURE_COMMAND_RE = re.compile(r"^M1(?:4|9)0\s+S([\d.]+)", re.IGNORECASE)
_GCODE_3MF_PLATE_RE = re.compile(r"^Metadata/plate_(\d+)\.gcode$", re.IGNORECASE)
_SUPPORT_ROLE_RE = re.compile(r"^TYPE:\s*(Support(?:\s+interface)?)\s*$", re.IGNORECASE)


def parse_gcode_payload(
    file_name: str,
    raw_bytes: bytes,
    plate_index: int | None = None,
) -> dict[str, Any]:
    """Parse supported G-code payload into calculator-friendly metadata."""
    if file_name.lower().endswith(".gcode.3mf"):
        return _parse_gcode_3mf_payload(
            file_name=file_name,
            raw_bytes=raw_bytes,
            plate_index=plate_index,
        )

    return _parse_plain_gcode_payload(file_name=file_name, raw_bytes=raw_bytes)


def _parse_plain_gcode_payload(file_name: str, raw_bytes: bytes) -> dict[str, Any]:
    """Parse one plain (or gzip-compressed) G-code stream."""
    decoded_text = _decode_gcode_bytes(file_name=file_name, raw_bytes=raw_bytes)
    if not decoded_text.strip():
        raise ValueError("empty_file")

    lines = decoded_text.splitlines()
    slicer_name, slicer_version = _detect_slicer(lines)

    parsed: dict[str, Any] = {
        "file_name": file_name,
        "file_size_bytes": len(raw_bytes),
        "slicer_name": slicer_name,
        "slicer_version": slicer_version,
        "print_time_seconds": None,
        "total_filament_weight_g": None,
        "total_filament_length_mm": None,
        "total_filament_volume_cm3": None,
        "layer_height_mm": None,
        "initial_layer_height_mm": None,
        "sparse_infill_density_percent": None,
        "sparse_infill_pattern": None,
        "wall_loops": None,
        "outer_wall_line_width_mm": None,
        "inner_wall_line_width_mm": None,
        "outer_wall_speed_mm_s": None,
        "inner_wall_speed_mm_s": None,
        "sparse_infill_speed_mm_s": None,
        "support_speed_mm_s": None,
        "initial_layer_speed_mm_s": None,
        "prime_volume_mm3": None,
        "nozzle_diameter_mm": None,
        "nozzle_temperature_first_layer_c": None,
        "nozzle_temperature_other_layers_c": None,
        "bed_temperature_first_layer_c": None,
        "bed_temperature_other_layers_c": None,
        "object_count": 0,
        "total_layers": None,
        "max_z_height_mm": None,
        "support_type": None,
        "support_threshold_angle_deg": None,
        "support_used": None,
        "support_filament_config_index": None,
        "support_interface_filament_config_index": None,
        "support_roles_detected": [],
        "brim_width_mm": None,
        "raft_layers": None,
        "active_material_count": None,
        "is_multi_material": None,
        "toolchange_count": None,
        "thumbnail_data_url": _extract_thumbnail_data_url(lines),
        "container_format": "plain_gcode",
        "plate_index": None,
        "available_plate_indices": [],
        "materials": [],
    }

    collector: dict[str, Any] = {
        "filament_types": None,
        "filament_names": None,
        "filament_colors": None,
        "filament_vendors": None,
        "filament_weights_g": None,
        "filament_lengths_mm": None,
        "filament_volumes_cm3": None,
        "filament_densities": None,
        "filament_diameters": None,
        "filament_settings_ids": None,
        "filament_ids": None,
        "filament_usage_costs": None,
        "filament_profile_prices_per_kg": None,
        "filament_flow_ratios": None,
        "filament_max_volumetric_speeds": None,
        "filament_prime_volumes": None,
        "filament_is_support": None,
        "estimated_normal_seconds": None,
        "estimated_first_layer_seconds": None,
        "referenced_tools": None,
        "multi_material_hint": None,
        "cura_setting_fragments": [],
        "object_centers": set(),
        "object_names": set(),
        "support_roles": set(),
    }

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("EXCLUDE_OBJECT_DEFINE"):
            _collect_object_metadata(parsed, collector, stripped)
            continue

        if stripped:
            _collect_inline_command_metadata(parsed, collector, stripped)

        if not stripped.startswith(";"):
            _collect_temperature_command_metadata(parsed, stripped)
            continue

        comment = stripped[1:].strip()
        if not comment:
            continue

        support_role_match = _SUPPORT_ROLE_RE.match(comment)
        if support_role_match:
            collector["support_roles"].add(support_role_match.group(1).lower())

        cura_setting_match = _CURA_SETTING_RE.match(comment)
        if cura_setting_match:
            collector["cura_setting_fragments"].append(cura_setting_match.group(1).strip())
            continue

        if _THUMBNAIL_BEGIN_RE.match(stripped) or _THUMBNAIL_END_RE.match(stripped):
            continue
        if _THUMBNAIL_BLOCK_START_RE.match(stripped) or _THUMBNAIL_BLOCK_END_RE.match(stripped):
            continue

        _collect_time_metadata(parsed, collector, comment)
        _collect_summary_metadata(parsed, collector, comment)
        _collect_key_value_metadata(parsed, collector, comment)

    if collector["estimated_normal_seconds"] is not None:
        parsed["print_time_seconds"] = collector["estimated_normal_seconds"] + (collector["estimated_first_layer_seconds"] or 0)

    if collector["cura_setting_fragments"]:
        _apply_cura_settings(parsed, "".join(collector["cura_setting_fragments"]))

    parsed["support_roles_detected"] = sorted(collector["support_roles"])
    if collector["support_roles"]:
        parsed["support_used"] = True

    _finalize_materials(parsed, collector)
    _finalize_totals(parsed)
    return parsed


def is_supported_gcode_filename(file_name: str | None) -> bool:
    """Check if filename uses a supported calculator G-code extension."""
    if not file_name:
        return False
    lower_name = file_name.lower()
    return any(lower_name.endswith(extension) for extension in SUPPORTED_GCODE_EXTENSIONS)


def _read_zip_member_capped(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    limit: int,
) -> bytes:
    """Read one archive member without allowing unbounded decompression."""
    if member.file_size > limit:
        raise ValueError("gcode_3mf_member_too_large")

    with archive.open(member, "r") as source:
        payload = source.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("gcode_3mf_member_too_large")
    return payload


def _parse_gcode_3mf_payload(
    file_name: str,
    raw_bytes: bytes,
    plate_index: int | None,
) -> dict[str, Any]:
    """Parse a Bambu/Orca sliced 3MF bundle entirely in memory."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as archive:
            members = archive.infolist()
            if len(members) > MAX_GCODE_3MF_ENTRIES:
                raise ValueError("gcode_3mf_too_many_entries")

            plate_members: dict[int, zipfile.ZipInfo] = {}
            for member in members:
                match = _GCODE_3MF_PLATE_RE.fullmatch(member.filename.replace("\\", "/"))
                if match:
                    plate_members[int(match.group(1))] = member

            available_plate_indices = sorted(plate_members)
            if not available_plate_indices:
                raise ValueError("gcode_3mf_has_no_gcode")

            selected_plate_index = plate_index or available_plate_indices[0]
            selected_member = plate_members.get(selected_plate_index)
            if selected_member is None:
                raise ValueError("gcode_3mf_plate_not_found")

            gcode_bytes = _read_zip_member_capped(
                archive,
                selected_member,
                MAX_DECOMPRESSED_GCODE_BYTES,
            )
            parsed = _parse_plain_gcode_payload(
                file_name=selected_member.filename,
                raw_bytes=gcode_bytes,
            )
            parsed["file_name"] = file_name
            parsed["file_size_bytes"] = len(raw_bytes)
            parsed["container_format"] = "gcode_3mf"
            parsed["plate_index"] = selected_plate_index
            parsed["available_plate_indices"] = available_plate_indices

            slice_info = _read_gcode_3mf_slice_info(archive, members, selected_plate_index)
            _merge_gcode_3mf_slice_info(parsed, slice_info)

            thumbnail = _read_gcode_3mf_thumbnail(archive, members, selected_plate_index)
            if thumbnail is not None:
                parsed["thumbnail_data_url"] = thumbnail
            return parsed
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("invalid_gcode_3mf") from exc


def _read_gcode_3mf_slice_info(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    plate_index: int,
) -> dict[str, Any]:
    member = next(
        (
            item
            for item in members
            if item.filename.replace("\\", "/").lower() == "metadata/slice_info.config"
        ),
        None,
    )
    if member is None:
        return {}

    try:
        payload = _read_zip_member_capped(
            archive,
            member,
            MAX_GCODE_3MF_SLICE_INFO_BYTES,
        )
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise ValueError("unsafe_gcode_3mf_xml")
        root = ElementTree.fromstring(payload)
    except (ElementTree.ParseError, ValueError):
        logger.warning("Failed to parse Metadata/slice_info.config", exc_info=True)
        return {}

    for plate in root.findall(".//plate"):
        metadata = {
            item.get("key"): item.get("value")
            for item in plate.findall("metadata")
            if item.get("key")
        }
        if _parse_first_int(metadata.get("index")) != plate_index:
            continue

        filaments: list[dict[str, Any]] = []
        for item in plate.findall("filament"):
            raw_id = _parse_first_int(item.get("id"))
            if raw_id is None or raw_id <= 0:
                continue
            used_m = _parse_first_float(item.get("used_m"))
            filaments.append(
                {
                    "tool_index": raw_id - 1,
                    "type": item.get("type"),
                    "color": item.get("color"),
                    "weight_g": _parse_first_float(item.get("used_g")),
                    "length_mm": used_m * 1000 if used_m is not None else None,
                    "settings_id": item.get("tray_info_idx"),
                    "used_for_model": _parse_bool(item.get("used_for_object")),
                    "used_for_support": _parse_bool(item.get("used_for_support")),
                }
            )

        return {
            "support_used": _parse_bool(metadata.get("support_used")),
            "print_time_seconds": _parse_first_int(metadata.get("prediction")),
            "total_filament_weight_g": _parse_first_float(metadata.get("weight")),
            "filaments": filaments,
        }
    return {}


def _merge_gcode_3mf_slice_info(parsed: dict[str, Any], slice_info: dict[str, Any]) -> None:
    if not slice_info:
        return

    if slice_info.get("support_used") is not None:
        parsed["support_used"] = slice_info["support_used"]
    if parsed.get("print_time_seconds") is None and slice_info.get("print_time_seconds") is not None:
        parsed["print_time_seconds"] = slice_info["print_time_seconds"]
    if parsed.get("total_filament_weight_g") is None and slice_info.get("total_filament_weight_g") is not None:
        parsed["total_filament_weight_g"] = slice_info["total_filament_weight_g"]

    materials_by_tool = {
        material.get("tool_index"): material
        for material in parsed["materials"]
        if material.get("tool_index") is not None
    }
    for info in slice_info.get("filaments", []):
        tool_index = info["tool_index"]
        material = materials_by_tool.get(tool_index)
        if material is None:
            material = {
                "tool_index": tool_index,
                "type": None,
                "name": None,
                "vendor": None,
                "color": None,
                "weight_g": None,
                "length_mm": None,
                "volume_cm3": None,
                "density_g_cm3": None,
                "diameter_mm": None,
                "slicer_filament_id": None,
                "slicer_usage_cost": None,
                "slicer_profile_price_per_kg": None,
                "flow_ratio": None,
                "max_volumetric_speed_mm3_s": None,
                "prime_volume_mm3": None,
                "is_support_material": None,
                "used_for_model": None,
                "used_for_support": None,
                "settings_id": None,
            }
            parsed["materials"].append(material)
            materials_by_tool[tool_index] = material

        for key in (
            "type",
            "color",
            "weight_g",
            "length_mm",
            "used_for_model",
            "used_for_support",
            "settings_id",
        ):
            if material.get(key) is None and info.get(key) is not None:
                material[key] = info[key]

        if info.get("used_for_support") is True:
            material["is_support_material"] = True

    parsed["materials"].sort(key=lambda item: item.get("tool_index", 0))
    parsed["active_material_count"] = len(parsed["materials"])
    parsed["is_multi_material"] = len(parsed["materials"]) > 1
    _finalize_totals(parsed)


def _read_gcode_3mf_thumbnail(
    archive: zipfile.ZipFile,
    members: list[zipfile.ZipInfo],
    plate_index: int,
) -> str | None:
    expected_names = {
        f"metadata/plate_{plate_index}.png",
        f"metadata/plate_{plate_index}_small.png",
    }
    candidates = [
        item
        for item in members
        if item.filename.replace("\\", "/").lower() in expected_names
        and item.file_size <= MAX_GCODE_3MF_THUMBNAIL_BYTES
    ]
    if not candidates:
        return None

    member = max(candidates, key=lambda item: item.file_size)
    payload = _read_zip_member_capped(
        archive,
        member,
        MAX_GCODE_3MF_THUMBNAIL_BYTES,
    )
    if not payload.startswith(b"\x89PNG"):
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _gunzip_capped(raw_bytes: bytes, limit: int) -> bytes:
    out = bytearray()
    with gzip.GzipFile(fileobj=io.BytesIO(raw_bytes)) as gz:
        while chunk := gz.read(1024 * 1024):
            out.extend(chunk)
            if len(out) > limit:
                raise ValueError("gzip_too_large")
    return bytes(out)


def _decode_gcode_bytes(file_name: str, raw_bytes: bytes) -> str:
    lower_name = file_name.lower()
    payload = raw_bytes
    if lower_name.endswith(".gz"):
        try:
            payload = _gunzip_capped(raw_bytes, MAX_DECOMPRESSED_GCODE_BYTES)
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise ValueError("invalid_gzip") from exc

    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            return payload.decode("latin-1", errors="ignore")


def _detect_slicer(lines: list[str]) -> tuple[str | None, str | None]:
    counts = {name: 0 for name in _SLICER_KEYWORDS}
    detected_version: str | None = None

    for raw_line in lines[:200]:
        stripped = raw_line.strip()
        if not stripped.startswith(";"):
            continue

        comment = stripped[1:].strip().lower()
        if not comment:
            continue

        for slicer_name, keywords in _SLICER_KEYWORDS.items():
            if any(keyword in comment for keyword in keywords):
                counts[slicer_name] += 1
                if detected_version is None:
                    version_match = _VERSION_RE.search(comment)
                    if version_match:
                        detected_version = version_match.group(1)

        if "generated by" in comment and detected_version is None:
            version_match = _VERSION_RE.search(comment)
            if version_match:
                detected_version = version_match.group(1)

    best_name = max(counts, key=counts.get)
    if counts[best_name] == 0:
        return None, None
    return best_name, detected_version


def _collect_time_metadata(parsed: dict[str, Any], collector: dict[str, Any], comment: str) -> None:
    lower_comment = comment.lower()

    if collector["estimated_normal_seconds"] is None and "estimated printing time (normal mode)" in lower_comment:
        _, value = _split_key_value(comment)
        collector["estimated_normal_seconds"] = _parse_time_to_seconds(value)
        return

    if collector["estimated_first_layer_seconds"] is None and "estimated first layer printing time (normal mode)" in lower_comment:
        _, value = _split_key_value(comment)
        collector["estimated_first_layer_seconds"] = _parse_time_to_seconds(value)
        return

    if parsed["print_time_seconds"] is None:
        if lower_comment.startswith("time:"):
            parsed["print_time_seconds"] = _parse_time_to_seconds(comment.split(":", 1)[1].strip())
            return

        if "print time" in lower_comment:
            _, value = _split_key_value(comment)
            if value:
                parsed["print_time_seconds"] = _parse_time_to_seconds(value)


def _collect_summary_metadata(parsed: dict[str, Any], collector: dict[str, Any], comment: str) -> None:
    lower_comment = comment.lower()

    if "total filament used [g]" in lower_comment:
        _, value = _split_key_value(comment)
        parsed["total_filament_weight_g"] = _parse_first_float(value)
        return

    if "total filament weight [g]" in lower_comment:
        _, value = _split_key_value(comment)
        values = _parse_float_list(value, separators=[","])
        collector["filament_weights_g"] = values
        if values:
            parsed["total_filament_weight_g"] = sum(values)
        return

    if "total filament length [mm]" in lower_comment:
        _, value = _split_key_value(comment)
        values = _parse_float_list(value, separators=[","])
        collector["filament_lengths_mm"] = values
        if values:
            parsed["total_filament_length_mm"] = sum(values)
        return

    if "total filament volume [cm3]" in lower_comment or "total filament volume [cm^3]" in lower_comment:
        _, value = _split_key_value(comment)
        values = _parse_float_list(value, separators=[","])
        collector["filament_volumes_cm3"] = values
        if values:
            parsed["total_filament_volume_cm3"] = sum(values)
        return

    if "filament used [g]" in lower_comment:
        _, value = _split_key_value(comment)
        collector["filament_weights_g"] = _parse_float_list(value, separators=[","])
        return

    if "filament used [mm]" in lower_comment:
        _, value = _split_key_value(comment)
        collector["filament_lengths_mm"] = _parse_float_list(value, separators=[","])
        return

    if "filament used [cm3]" in lower_comment or "filament used [cm^3]" in lower_comment:
        _, value = _split_key_value(comment)
        collector["filament_volumes_cm3"] = _parse_float_list(value, separators=[","])
        return

    if lower_comment.startswith("filament used"):
        _, value = _split_key_value(comment)
        if value:
            weight_match = re.search(r"([\d.]+)\s*g\b", value, re.IGNORECASE)
            length_match = re.search(r"([\d.]+)\s*m\b", value, re.IGNORECASE)
            if weight_match and parsed["total_filament_weight_g"] is None:
                parsed["total_filament_weight_g"] = float(weight_match.group(1))
            if length_match and parsed["total_filament_length_mm"] is None:
                parsed["total_filament_length_mm"] = float(length_match.group(1)) * 1000.0
        return

    if "filament weight" in lower_comment and parsed["total_filament_weight_g"] is None:
        _, value = _split_key_value(comment)
        parsed["total_filament_weight_g"] = _parse_first_float(value)
        if parsed["total_filament_weight_g"] is None:
            weight_match = re.search(r"\[([\d.]+)\]", comment)
            if weight_match:
                parsed["total_filament_weight_g"] = float(weight_match.group(1))


def _collect_key_value_metadata(parsed: dict[str, Any], collector: dict[str, Any], comment: str) -> None:
    key, value = _split_key_value(comment)
    if not key or value is None:
        return

    normalized_key = _normalize_metadata_key(key)

    if normalized_key == "layer_height" and parsed["layer_height_mm"] is None:
        parsed["layer_height_mm"] = _parse_first_float(value)
        return

    if normalized_key in {"initial_layer_print_height", "first_layer_height", "initial_layer_height"} and parsed["initial_layer_height_mm"] is None:
        parsed["initial_layer_height_mm"] = _parse_first_float(value)
        return

    if normalized_key in {"sparse_infill_density", "fill_density", "infill"} and parsed["sparse_infill_density_percent"] is None:
        parsed["sparse_infill_density_percent"] = _parse_first_float(value)
        return

    if normalized_key == "sparse_infill_pattern" and parsed["sparse_infill_pattern"] is None:
        parsed["sparse_infill_pattern"] = value.strip().lower()
        return

    if normalized_key in {"wall_loops", "perimeters"} and parsed["wall_loops"] is None:
        wall_loops = _parse_first_int(value)
        if wall_loops is not None:
            parsed["wall_loops"] = wall_loops
        return

    if normalized_key in {"outer_wall_line_width", "external_perimeter_extrusion_width"} and parsed["outer_wall_line_width_mm"] is None:
        parsed["outer_wall_line_width_mm"] = _parse_first_float(value)
        return

    if normalized_key in {"inner_wall_line_width", "perimeter_extrusion_width"} and parsed["inner_wall_line_width_mm"] is None:
        parsed["inner_wall_line_width_mm"] = _parse_first_float(value)
        return

    speed_fields = {
        "outer_wall_speed": "outer_wall_speed_mm_s",
        "external_perimeter_speed": "outer_wall_speed_mm_s",
        "inner_wall_speed": "inner_wall_speed_mm_s",
        "perimeter_speed": "inner_wall_speed_mm_s",
        "sparse_infill_speed": "sparse_infill_speed_mm_s",
        "infill_speed": "sparse_infill_speed_mm_s",
        "support_speed": "support_speed_mm_s",
        "initial_layer_speed": "initial_layer_speed_mm_s",
        "first_layer_speed": "initial_layer_speed_mm_s",
    }
    speed_field = speed_fields.get(normalized_key)
    if speed_field and parsed[speed_field] is None:
        parsed[speed_field] = _parse_first_float(value)
        return

    if normalized_key == "prime_volume" and parsed["prime_volume_mm3"] is None:
        parsed["prime_volume_mm3"] = _parse_first_float(value)
        return

    if normalized_key in {"total_layers_count", "total_layers", "total_layer", "layer_count", "layercount"} and parsed["total_layers"] is None:
        total_layers = _parse_first_int(value)
        if total_layers is not None:
            parsed["total_layers"] = total_layers
        return

    if normalized_key in {"max_z_height", "max_z", "maxz"} and parsed["max_z_height_mm"] is None:
        parsed["max_z_height_mm"] = _parse_first_float(value)
        return

    if normalized_key == "support_type" and parsed["support_type"] is None:
        parsed["support_type"] = value.strip()
        return

    if normalized_key == "enable_support" and parsed["support_used"] is None:
        parsed["support_used"] = _parse_bool(value)
        return

    if normalized_key == "support_filament" and parsed["support_filament_config_index"] is None:
        parsed["support_filament_config_index"] = _parse_first_int(value)
        return

    if (
        normalized_key == "support_interface_filament"
        and parsed["support_interface_filament_config_index"] is None
    ):
        parsed["support_interface_filament_config_index"] = _parse_first_int(value)
        return

    if normalized_key == "support_threshold_angle" and parsed["support_threshold_angle_deg"] is None:
        parsed["support_threshold_angle_deg"] = _parse_first_float(value)
        return

    if normalized_key == "brim_width" and parsed["brim_width_mm"] is None:
        parsed["brim_width_mm"] = _parse_first_float(value)
        return

    if normalized_key == "raft_layers" and parsed["raft_layers"] is None:
        parsed["raft_layers"] = _parse_first_int(value)
        return

    if normalized_key == "nozzle_diameter" and parsed["nozzle_diameter_mm"] is None:
        parsed["nozzle_diameter_mm"] = _parse_first_float(value)
        return

    if normalized_key in {"nozzle_temperature_initial_layer", "first_layer_temperature", "nozzle_initial_c"} and parsed["nozzle_temperature_first_layer_c"] is None:
        parsed["nozzle_temperature_first_layer_c"] = _parse_first_float(value)
        return

    if normalized_key in {"nozzle_temperature", "nozzle_main_c"} and parsed["nozzle_temperature_other_layers_c"] is None:
        parsed["nozzle_temperature_other_layers_c"] = _parse_first_float(value)
        return

    if normalized_key in {"first_layer_bed_temperature", "cool_plate_temp_initial_layer", "bed_initial_c"} and parsed["bed_temperature_first_layer_c"] is None:
        parsed["bed_temperature_first_layer_c"] = _parse_first_float(value)
        return

    if normalized_key in {"bed_temperature", "cool_plate_temp", "bed_main_c"} and parsed["bed_temperature_other_layers_c"] is None:
        parsed["bed_temperature_other_layers_c"] = _parse_first_float(value)
        return

    if normalized_key == "single_extruder_multi_material" and collector["multi_material_hint"] is None:
        multi_material_value = _parse_first_int(value)
        collector["multi_material_hint"] = multi_material_value == 1 if multi_material_value is not None else None
        return

    if normalized_key == "referenced_tools" and collector["referenced_tools"] is None:
        collector["referenced_tools"] = _parse_string_list(value)
        return

    if normalized_key == "total_toolchanges" and parsed["toolchange_count"] is None:
        parsed["toolchange_count"] = _parse_first_int(value)
        return

    if normalized_key == "filament_type" and collector["filament_types"] is None:
        collector["filament_types"] = _parse_string_list(value)
        return

    if normalized_key == "filament_settings_id" and collector["filament_settings_ids"] is None:
        collector["filament_settings_ids"] = _parse_string_list(value)
        if collector["filament_names"] is None:
            collector["filament_names"] = list(collector["filament_settings_ids"])
        return

    if normalized_key == "filament_name" and collector["filament_names"] is None:
        collector["filament_names"] = _parse_string_list(value)
        return

    if normalized_key in {"filament_colour", "filament_color", "extruder_colour", "extruder_color"} and collector["filament_colors"] is None:
        collector["filament_colors"] = _parse_string_list(value)
        return

    if normalized_key == "filament_vendor" and collector["filament_vendors"] is None:
        collector["filament_vendors"] = _parse_string_list(value)
        return


    list_fields = {
        "filament_density": "filament_densities",
        "filament_diameter": "filament_diameters",
        "filament_flow_ratio": "filament_flow_ratios",
        "filament_max_volumetric_speed": "filament_max_volumetric_speeds",
        "filament_prime_volume": "filament_prime_volumes",
    }
    collector_field = list_fields.get(normalized_key)
    if collector_field and collector[collector_field] is None:
        collector[collector_field] = _parse_float_list(value)
        return

    if normalized_key == "filament_cost":
        # Orca/Bambu use `filament cost` in the header for the cost of the
        # consumed amount, while `filament_cost` in CONFIG_BLOCK is the profile
        # price per kilogram. Keep both facts separate: their units differ.
        collector_field = (
            "filament_profile_prices_per_kg" if "_" in key else "filament_usage_costs"
        )
        if collector[collector_field] is None:
            collector[collector_field] = _parse_float_list(value)
        return

    if normalized_key in {"filament_id", "filament_ids"} and collector["filament_ids"] is None:
        collector["filament_ids"] = _parse_string_list(value)
        return

    if normalized_key == "filament_is_support" and collector["filament_is_support"] is None:
        collector["filament_is_support"] = [_parse_bool(item) for item in _split_list(value)]


def _apply_cura_settings(parsed: dict[str, Any], settings_blob: str) -> None:
    payload: dict[str, Any] | None = None
    for decoder in (_try_decode_json, _try_decode_base64_json):
        payload = decoder(settings_blob)
        if payload is not None:
            break

    if payload is None:
        return

    for section_key in ("global_quality", "extruder_quality"):
        section_value = payload.get(section_key)
        if isinstance(section_value, str):
            _apply_cura_ini_block(parsed, section_value)
        elif isinstance(section_value, list):
            for item in section_value:
                if isinstance(item, str):
                    _apply_cura_ini_block(parsed, item)


def _apply_cura_ini_block(parsed: dict[str, Any], block: str) -> None:
    for raw_line in re.split(r"(?:\\n|\r?\n)", block):
        line = raw_line.strip()
        if not line or line.startswith("[") and line.endswith("]"):
            continue

        key, value = _split_key_value(line)
        if not key or value is None:
            continue

        normalized_key = _normalize_metadata_key(key)
        if normalized_key == "infill_sparse_density" and parsed["sparse_infill_density_percent"] is None:
            parsed["sparse_infill_density_percent"] = _parse_first_float(value)
        elif normalized_key in {"layer_height", "layer_height_0"} and parsed["layer_height_mm"] is None:
            parsed["layer_height_mm"] = _parse_first_float(value)
        elif normalized_key in {"initial_layer_height", "first_layer_height"} and parsed["initial_layer_height_mm"] is None:
            parsed["initial_layer_height_mm"] = _parse_first_float(value)
        elif normalized_key == "machine_nozzle_size" and parsed["nozzle_diameter_mm"] is None:
            parsed["nozzle_diameter_mm"] = _parse_first_float(value)
        elif normalized_key == "material_print_temperature_layer_0" and parsed["nozzle_temperature_first_layer_c"] is None:
            parsed["nozzle_temperature_first_layer_c"] = _parse_first_float(value)
        elif normalized_key == "material_print_temperature" and parsed["nozzle_temperature_other_layers_c"] is None:
            parsed["nozzle_temperature_other_layers_c"] = _parse_first_float(value)
        elif normalized_key == "material_bed_temperature_layer_0" and parsed["bed_temperature_first_layer_c"] is None:
            parsed["bed_temperature_first_layer_c"] = _parse_first_float(value)
        elif normalized_key == "material_bed_temperature" and parsed["bed_temperature_other_layers_c"] is None:
            parsed["bed_temperature_other_layers_c"] = _parse_first_float(value)


def _collect_inline_command_metadata(parsed: dict[str, Any], collector: dict[str, Any], line: str) -> None:
    assignments = {match.group(1).lower(): match.group(2) for match in _INLINE_ASSIGNMENT_RE.finditer(line)}
    if not assignments:
        return

    if parsed["toolchange_count"] is None and assignments.get("total_toolchanges") is not None:
        parsed["toolchange_count"] = _parse_first_int(assignments["total_toolchanges"])

    if collector["referenced_tools"] is None and assignments.get("referenced_tools") is not None:
        collector["referenced_tools"] = _parse_string_list(assignments["referenced_tools"])

    if parsed["total_layers"] is None and assignments.get("total_layer") is not None:
        parsed["total_layers"] = _parse_first_int(assignments["total_layer"])


def _collect_temperature_command_metadata(parsed: dict[str, Any], line: str) -> None:
    if line.upper().startswith("PRINT_START"):
        for parameter, raw_value in _PRINT_START_PARAMETER_RE.findall(line):
            parsed_value = _parse_first_float(raw_value)
            if parsed_value is None or parsed_value <= 0:
                continue
            if parameter.upper() == "EXTRUDER" and parsed["nozzle_temperature_first_layer_c"] is None:
                parsed["nozzle_temperature_first_layer_c"] = parsed_value
            elif parameter.upper() == "BED" and parsed["bed_temperature_first_layer_c"] is None:
                parsed["bed_temperature_first_layer_c"] = parsed_value

    nozzle_match = _NOZZLE_TEMPERATURE_COMMAND_RE.match(line)
    if nozzle_match:
        nozzle_temperature = _parse_first_float(nozzle_match.group(1))
        if nozzle_temperature is not None and nozzle_temperature > 0:
            if parsed["nozzle_temperature_first_layer_c"] is None:
                parsed["nozzle_temperature_first_layer_c"] = nozzle_temperature
            elif (
                parsed["nozzle_temperature_other_layers_c"] is None
                and parsed["nozzle_temperature_first_layer_c"] != nozzle_temperature
            ):
                parsed["nozzle_temperature_other_layers_c"] = nozzle_temperature

    bed_match = _BED_TEMPERATURE_COMMAND_RE.match(line)
    if bed_match:
        bed_temperature = _parse_first_float(bed_match.group(1))
        if bed_temperature is not None and bed_temperature > 0:
            if parsed["bed_temperature_first_layer_c"] is None:
                parsed["bed_temperature_first_layer_c"] = bed_temperature
            elif (
                parsed["bed_temperature_other_layers_c"] is None
                and parsed["bed_temperature_first_layer_c"] != bed_temperature
            ):
                parsed["bed_temperature_other_layers_c"] = bed_temperature


def _collect_object_metadata(parsed: dict[str, Any], collector: dict[str, Any], line: str) -> None:
    center_match = _OBJECT_CENTER_RE.search(line)
    if center_match:
        collector["object_centers"].add((center_match.group(1), center_match.group(2)))
        parsed["object_count"] = len(collector["object_centers"])
        return

    name_match = _OBJECT_NAME_RE.search(line)
    if name_match:
        collector["object_names"].add(name_match.group(1))
        if not collector["object_centers"]:
            parsed["object_count"] = len(collector["object_names"])
        return

    parsed["object_count"] += 1


def _finalize_materials(parsed: dict[str, Any], collector: dict[str, Any]) -> None:
    lengths = [
        len(values)
        for values in (
            collector["filament_types"],
            collector["filament_names"],
            collector["filament_colors"],
            collector["filament_vendors"],
            collector["filament_weights_g"],
            collector["filament_lengths_mm"],
            collector["filament_volumes_cm3"],
            collector["filament_densities"],
            collector["filament_diameters"],
            collector["filament_settings_ids"],
            collector["filament_ids"],
            collector["filament_usage_costs"],
            collector["filament_profile_prices_per_kg"],
            collector["filament_flow_ratios"],
            collector["filament_max_volumetric_speeds"],
            collector["filament_prime_volumes"],
            collector["filament_is_support"],
        )
        if values
    ]
    material_count = max(lengths, default=0)

    materials: list[dict[str, Any]] = []
    for index in range(material_count):
        material = {
            "tool_index": index,
            "type": _get_list_value(collector["filament_types"], index),
            "name": _get_list_value(collector["filament_names"], index),
            "vendor": _get_list_value(collector["filament_vendors"], index),
            "color": _get_list_value(collector["filament_colors"], index),
            "weight_g": _get_list_value(collector["filament_weights_g"], index),
            "length_mm": _get_list_value(collector["filament_lengths_mm"], index),
            "volume_cm3": _get_list_value(collector["filament_volumes_cm3"], index),
            "density_g_cm3": _get_list_value(collector["filament_densities"], index),
            "diameter_mm": _get_list_value(collector["filament_diameters"], index),
            "slicer_filament_id": _get_list_value(collector["filament_ids"], index),
            "slicer_usage_cost": _get_list_value(collector["filament_usage_costs"], index),
            "slicer_profile_price_per_kg": _get_list_value(
                collector["filament_profile_prices_per_kg"], index
            ),
            "flow_ratio": _get_list_value(collector["filament_flow_ratios"], index),
            "max_volumetric_speed_mm3_s": _get_list_value(
                collector["filament_max_volumetric_speeds"], index
            ),
            "prime_volume_mm3": _get_list_value(collector["filament_prime_volumes"], index),
            "is_support_material": _get_list_value(collector["filament_is_support"], index),
            "used_for_model": None,
            "used_for_support": None,
            "settings_id": _get_list_value(collector["filament_settings_ids"], index),
        }
        has_real_usage = (
            (material["weight_g"] is not None and float(material["weight_g"]) > 0)
            or (material["length_mm"] is not None and float(material["length_mm"]) > 0)
            or (material["volume_cm3"] is not None and float(material["volume_cm3"]) > 0)
        )
        if has_real_usage:
            materials.append(material)

    if not materials and parsed["total_filament_weight_g"] is not None:
        materials.append(
            {
                "tool_index": 0,
                "type": _get_list_value(collector["filament_types"], 0),
                "name": _get_list_value(collector["filament_names"], 0),
                "vendor": _get_list_value(collector["filament_vendors"], 0),
                "color": _get_list_value(collector["filament_colors"], 0),
                "weight_g": parsed["total_filament_weight_g"],
                "length_mm": parsed["total_filament_length_mm"],
                "volume_cm3": parsed["total_filament_volume_cm3"],
                "density_g_cm3": _get_list_value(collector["filament_densities"], 0),
                "diameter_mm": _get_list_value(collector["filament_diameters"], 0),
                "slicer_filament_id": _get_list_value(collector["filament_ids"], 0),
                "slicer_usage_cost": _get_list_value(collector["filament_usage_costs"], 0),
                "slicer_profile_price_per_kg": _get_list_value(
                    collector["filament_profile_prices_per_kg"], 0
                ),
                "flow_ratio": _get_list_value(collector["filament_flow_ratios"], 0),
                "max_volumetric_speed_mm3_s": _get_list_value(
                    collector["filament_max_volumetric_speeds"], 0
                ),
                "prime_volume_mm3": _get_list_value(collector["filament_prime_volumes"], 0),
                "is_support_material": _get_list_value(collector["filament_is_support"], 0),
                "used_for_model": None,
                "used_for_support": None,
                "settings_id": _get_list_value(collector["filament_settings_ids"], 0),
            }
        )

    parsed["materials"] = materials
    parsed["active_material_count"] = len(materials)

    referenced_tools = sorted({tool for tool in (collector["referenced_tools"] or []) if tool})
    referenced_tools_count = len(referenced_tools)
    if referenced_tools_count > 0:
        parsed["active_material_count"] = max(parsed["active_material_count"], referenced_tools_count)

    unique_material_signatures = {
        (
            (material.get("type") or "").strip().lower(),
            (material.get("name") or "").strip().lower(),
            (material.get("vendor") or "").strip().lower(),
        )
        for material in materials
        if any(material.get(field) for field in ("type", "name", "vendor"))
    }

    parsed["is_multi_material"] = bool(
        (parsed["active_material_count"] is not None and parsed["active_material_count"] > 1)
        or len(unique_material_signatures) > 1
        or referenced_tools_count > 1
    )


def _finalize_totals(parsed: dict[str, Any]) -> None:
    if parsed["total_filament_weight_g"] is None:
        weights = [material["weight_g"] for material in parsed["materials"] if material.get("weight_g") is not None]
        if weights:
            parsed["total_filament_weight_g"] = round(sum(weights), 2)

    if parsed["total_filament_length_mm"] is None:
        lengths = [material["length_mm"] for material in parsed["materials"] if material.get("length_mm") is not None]
        if lengths:
            parsed["total_filament_length_mm"] = round(sum(lengths), 2)

    if parsed["total_filament_volume_cm3"] is None:
        volumes = [material["volume_cm3"] for material in parsed["materials"] if material.get("volume_cm3") is not None]
        if volumes:
            parsed["total_filament_volume_cm3"] = round(sum(volumes), 3)

    if parsed["total_filament_weight_g"] is not None:
        parsed["total_filament_weight_g"] = round(float(parsed["total_filament_weight_g"]), 2)
    if parsed["total_filament_length_mm"] is not None:
        parsed["total_filament_length_mm"] = round(float(parsed["total_filament_length_mm"]), 2)
    if parsed["total_filament_volume_cm3"] is not None:
        parsed["total_filament_volume_cm3"] = round(float(parsed["total_filament_volume_cm3"]), 3)
    if parsed["layer_height_mm"] is not None:
        parsed["layer_height_mm"] = round(float(parsed["layer_height_mm"]), 3)
    if parsed["initial_layer_height_mm"] is not None:
        parsed["initial_layer_height_mm"] = round(float(parsed["initial_layer_height_mm"]), 3)
    for field in (
        "outer_wall_line_width_mm",
        "inner_wall_line_width_mm",
        "outer_wall_speed_mm_s",
        "inner_wall_speed_mm_s",
        "sparse_infill_speed_mm_s",
        "support_speed_mm_s",
        "initial_layer_speed_mm_s",
        "prime_volume_mm3",
    ):
        if parsed[field] is not None:
            parsed[field] = round(float(parsed[field]), 3)
    if parsed["nozzle_diameter_mm"] is not None:
        parsed["nozzle_diameter_mm"] = round(float(parsed["nozzle_diameter_mm"]), 3)
    if parsed["nozzle_temperature_first_layer_c"] is not None:
        parsed["nozzle_temperature_first_layer_c"] = round(float(parsed["nozzle_temperature_first_layer_c"]), 2)
    if parsed["nozzle_temperature_other_layers_c"] is not None:
        parsed["nozzle_temperature_other_layers_c"] = round(float(parsed["nozzle_temperature_other_layers_c"]), 2)
    if parsed["bed_temperature_first_layer_c"] is not None:
        parsed["bed_temperature_first_layer_c"] = round(float(parsed["bed_temperature_first_layer_c"]), 2)
    if parsed["bed_temperature_other_layers_c"] is not None:
        parsed["bed_temperature_other_layers_c"] = round(float(parsed["bed_temperature_other_layers_c"]), 2)
    if parsed["sparse_infill_density_percent"] is not None:
        parsed["sparse_infill_density_percent"] = round(float(parsed["sparse_infill_density_percent"]), 2)
    if parsed["max_z_height_mm"] is not None:
        parsed["max_z_height_mm"] = round(float(parsed["max_z_height_mm"]), 2)
    if parsed["support_threshold_angle_deg"] is not None:
        parsed["support_threshold_angle_deg"] = round(float(parsed["support_threshold_angle_deg"]), 2)
    if parsed["brim_width_mm"] is not None:
        parsed["brim_width_mm"] = round(float(parsed["brim_width_mm"]), 2)
    if parsed["object_count"] == 0:
        parsed["object_count"] = None


def _extract_thumbnail_data_url(lines: list[str]) -> str | None:
    thumbnails: list[tuple[int, str]] = []
    collecting = False
    current_area = 0
    current_lines: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()

        begin_match = _THUMBNAIL_BEGIN_RE.match(stripped)
        if begin_match:
            collecting = True
            width = int(begin_match.group(1) or 0)
            height = int(begin_match.group(2) or 0)
            current_area = width * height
            current_lines = []
            continue

        if _THUMBNAIL_BLOCK_START_RE.match(stripped):
            collecting = True
            current_area = 0
            current_lines = []
            continue

        if collecting and (_THUMBNAIL_END_RE.match(stripped) or _THUMBNAIL_BLOCK_END_RE.match(stripped)):
            data_url = _build_thumbnail_data_url(current_lines)
            if data_url:
                thumbnails.append((current_area, data_url))
            collecting = False
            current_area = 0
            current_lines = []
            continue

        if collecting:
            candidate = stripped[1:].strip() if stripped.startswith(";") else stripped
            if candidate:
                current_lines.append(candidate)

    if not thumbnails:
        return None

    thumbnails.sort(key=lambda item: item[0], reverse=True)
    return thumbnails[0][1]


def _build_thumbnail_data_url(lines: list[str]) -> str | None:
    encoded = "".join(lines).strip()
    if not encoded:
        return None

    try:
        decoded = base64.b64decode(encoded, validate=True)
    except Exception:
        logger.debug("Failed to decode thumbnail block", exc_info=True)
        return None

    if decoded.startswith(b"\x89PNG"):
        mime_type = "image/png"
    elif decoded.startswith(b"\xff\xd8\xff"):
        mime_type = "image/jpeg"
    else:
        mime_type = "image/png"

    return f"data:{mime_type};base64,{encoded}"


def _try_decode_json(payload: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _try_decode_base64_json(payload: str) -> dict[str, Any] | None:
    try:
        decoded_bytes = base64.b64decode(payload, validate=True)
    except Exception:
        return None

    try:
        decoded = json.loads(decoded_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _split_key_value(line: str) -> tuple[str | None, str | None]:
    match = _KEY_VALUE_RE.match(line)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


def _normalize_metadata_key(key: str) -> str:
    normalized = key.lower().strip()
    normalized = normalized.replace("[g]", "_g").replace("[mm]", "_mm").replace("[cm^3]", "_cm3")
    normalized = re.sub(r"[%\[\]]", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _parse_float_list(value: str, separators: list[str] | None = None) -> list[float]:
    chunks = _split_list(value, separators=separators)
    result: list[float] = []
    for chunk in chunks:
        parsed = _parse_first_float(chunk)
        if parsed is not None:
            result.append(parsed)
    return result


def _parse_string_list(value: str) -> list[str]:
    return [chunk.strip('"\'') for chunk in _split_list(value) if chunk.strip('"\'')]


def _split_list(value: str, separators: list[str] | None = None) -> list[str]:
    separators = separators or ([";"] if ";" in value else [","])
    parts = [value]
    for separator in separators:
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(part.split(separator))
        parts = next_parts
    return [part.strip() for part in parts if part.strip()]


def _parse_first_float(value: str | None) -> float | None:
    if not value:
        return None
    match = _FLOAT_RE.search(value.replace(",", "."))
    return float(match.group(0)) if match else None


def _parse_first_int(value: str | None) -> int | None:
    parsed = _parse_first_float(value)
    return int(parsed) if parsed is not None else None


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_time_to_seconds(value: str | None) -> int | None:
    if not value:
        return None

    raw_value = value.strip().lower()
    if not raw_value:
        return None

    if re.fullmatch(r"\d+", raw_value):
        return int(raw_value)

    colon_match = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+)", raw_value)
    if colon_match:
        hours = int(colon_match.group(1) or 0)
        minutes = int(colon_match.group(2))
        seconds = int(colon_match.group(3))
        return hours * 3600 + minutes * 60 + seconds

    total_seconds = 0
    matched = False
    for pattern, multiplier in (
        (r"(\d+)\s*d", 86400),
        (r"(\d+)\s*h", 3600),
        (r"(\d+)\s*m(?!m)", 60),
        (r"(\d+)\s*s", 1),
    ):
        match = re.search(pattern, raw_value)
        if match:
            total_seconds += int(match.group(1)) * multiplier
            matched = True

    return total_seconds if matched else None


def _get_list_value(values: list[Any] | None, index: int) -> Any:
    if values is None or index >= len(values):
        return None
    return values[index]

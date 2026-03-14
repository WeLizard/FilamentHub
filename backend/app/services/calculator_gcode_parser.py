"""G-code parsing helpers for Calculator Pro."""

from __future__ import annotations

import base64
import gzip
import json
import logging
import re
from typing import Any


logger = logging.getLogger(__name__)

SUPPORTED_GCODE_EXTENSIONS = (".gcode", ".gcode.gz", ".txt")

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
    "CrealitySlicer": ("crealityslicer", "creality slicer", "creality_slicer"),
}

_VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?(?:[-+._a-z0-9]*)?)\b", re.IGNORECASE)
_CURA_SETTING_RE = re.compile(r"^SETTING_3\s+(.*)$", re.IGNORECASE)
_FLOAT_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_gcode_payload(file_name: str, raw_bytes: bytes) -> dict[str, Any]:
    """Parse supported G-code payload into calculator-friendly metadata."""
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
        "layer_height_mm": None,
        "initial_layer_height_mm": None,
        "sparse_infill_density_percent": None,
        "sparse_infill_pattern": None,
        "wall_loops": None,
        "object_count": 0,
        "total_layers": None,
        "max_z_height_mm": None,
        "support_type": None,
        "support_threshold_angle_deg": None,
        "brim_width_mm": None,
        "raft_layers": None,
        "active_material_count": None,
        "is_multi_material": None,
        "toolchange_count": None,
        "thumbnail_data_url": _extract_thumbnail_data_url(lines),
        "materials": [],
    }

    collector: dict[str, Any] = {
        "filament_types": None,
        "filament_names": None,
        "filament_colors": None,
        "filament_vendors": None,
        "filament_weights_g": None,
        "filament_lengths_mm": None,
        "estimated_normal_seconds": None,
        "estimated_first_layer_seconds": None,
        "referenced_tools": None,
        "multi_material_hint": None,
        "cura_setting_fragments": [],
    }

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("EXCLUDE_OBJECT_DEFINE"):
            parsed["object_count"] += 1
            continue

        if stripped:
            _collect_inline_command_metadata(parsed, collector, stripped)

        if not stripped.startswith(";"):
            continue

        comment = stripped[1:].strip()
        if not comment:
            continue

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

    _finalize_materials(parsed, collector)
    _finalize_totals(parsed)
    return parsed


def is_supported_gcode_filename(file_name: str | None) -> bool:
    """Check if filename uses a supported calculator G-code extension."""
    if not file_name:
        return False
    lower_name = file_name.lower()
    return any(lower_name.endswith(extension) for extension in SUPPORTED_GCODE_EXTENSIONS)


def _decode_gcode_bytes(file_name: str, raw_bytes: bytes) -> str:
    lower_name = file_name.lower()
    payload = raw_bytes
    if lower_name.endswith(".gz"):
        try:
            payload = gzip.decompress(raw_bytes)
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

    if "filament used [g]" in lower_comment:
        _, value = _split_key_value(comment)
        collector["filament_weights_g"] = _parse_float_list(value, separators=[","])
        return

    if "filament used [mm]" in lower_comment:
        _, value = _split_key_value(comment)
        collector["filament_lengths_mm"] = _parse_float_list(value, separators=[","])
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

    if normalized_key in {"total_layers_count", "total_layers", "total_layer"} and parsed["total_layers"] is None:
        total_layers = _parse_first_int(value)
        if total_layers is not None:
            parsed["total_layers"] = total_layers
        return

    if normalized_key == "max_z_height" and parsed["max_z_height_mm"] is None:
        parsed["max_z_height_mm"] = _parse_first_float(value)
        return

    if normalized_key == "support_type" and parsed["support_type"] is None:
        parsed["support_type"] = value.strip()
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

    if normalized_key == "filament_settings_id" and collector["filament_names"] is None:
        collector["filament_names"] = _parse_string_list(value)
        return

    if normalized_key in {"filament_colour", "filament_color", "extruder_colour", "extruder_color"} and collector["filament_colors"] is None:
        collector["filament_colors"] = _parse_string_list(value)
        return

    if normalized_key == "filament_vendor" and collector["filament_vendors"] is None:
        collector["filament_vendors"] = _parse_string_list(value)


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
    for raw_line in block.split("\\n"):
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
        )
        if values
    ]
    material_count = max(lengths, default=0)

    materials: list[dict[str, Any]] = []
    for index in range(material_count):
        material = {
            "type": _get_list_value(collector["filament_types"], index),
            "name": _get_list_value(collector["filament_names"], index),
            "vendor": _get_list_value(collector["filament_vendors"], index),
            "color": _get_list_value(collector["filament_colors"], index),
            "weight_g": _get_list_value(collector["filament_weights_g"], index),
            "length_mm": _get_list_value(collector["filament_lengths_mm"], index),
        }
        has_real_usage = (
            (material["weight_g"] is not None and float(material["weight_g"]) > 0)
            or (material["length_mm"] is not None and float(material["length_mm"]) > 0)
        )
        if has_real_usage:
            materials.append(material)

    if not materials and parsed["total_filament_weight_g"] is not None:
        materials.append(
            {
                "type": _get_list_value(collector["filament_types"], 0),
                "name": _get_list_value(collector["filament_names"], 0),
                "vendor": _get_list_value(collector["filament_vendors"], 0),
                "color": _get_list_value(collector["filament_colors"], 0),
                "weight_g": parsed["total_filament_weight_g"],
                "length_mm": parsed["total_filament_length_mm"],
            }
        )

    parsed["materials"] = materials
    parsed["active_material_count"] = len(materials)

    referenced_tools = collector["referenced_tools"] or []
    if referenced_tools:
        parsed["active_material_count"] = max(parsed["active_material_count"], len(referenced_tools))

    parsed["is_multi_material"] = bool(
        collector["multi_material_hint"]
        or (parsed["active_material_count"] is not None and parsed["active_material_count"] > 1)
        or (parsed["toolchange_count"] is not None and parsed["toolchange_count"] > 0)
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

    if parsed["total_filament_weight_g"] is not None:
        parsed["total_filament_weight_g"] = round(float(parsed["total_filament_weight_g"]), 2)
    if parsed["total_filament_length_mm"] is not None:
        parsed["total_filament_length_mm"] = round(float(parsed["total_filament_length_mm"]), 2)
    if parsed["layer_height_mm"] is not None:
        parsed["layer_height_mm"] = round(float(parsed["layer_height_mm"]), 3)
    if parsed["initial_layer_height_mm"] is not None:
        parsed["initial_layer_height_mm"] = round(float(parsed["initial_layer_height_mm"]), 3)
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
    return [chunk for chunk in _split_list(value) if chunk]


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

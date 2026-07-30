"""Provider-neutral registry and safe manual mapping for spool CSV imports."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_SPOOL_IMPORT_INVALID_CSV,
    ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS,
    raise_error,
)
from app.models.user import User
from app.schemas.spool import (
    SpoolImportColumnMapping,
    SpoolImportPreviewResponse,
    SpoolImportResponse,
)
from app.services.spoolmanager_import_service import (
    MAX_IMPORT_ROWS,
    SPOOLMANAGER_SOURCE,
    _ParsedRow,
    import_parsed_spool_rows,
    parse_spoolmanager_csv,
    preview_parsed_spool_import,
)

CUSTOM_CSV_SOURCE = "csv_import"
SPOOLMANAGER_FORMAT = "octoprint_spoolmanager_csv"
CUSTOM_CSV_FORMAT = "custom_csv"

_SPOOLMANAGER_REQUIRED_COLUMNS = {
    "Spool Name",
    "Vendor",
    "Material",
    "Total weight [g]",
    "Used weight [g]",
}
_WEIGHT_FIELDS = {
    "initial_weight",
    "used_weight",
    "remaining_weight",
    "empty_spool_weight",
}
_LENGTH_FIELDS = {"total_length", "used_length"}
_SUPPORTED_FIELDS = {
    "spool_name",
    "vendor",
    "material",
    "color_name",
    "color_hex",
    "serial_number",
    "initial_weight",
    "used_weight",
    "remaining_weight",
    "empty_spool_weight",
    "price",
    "currency",
    "note",
    "density",
    "diameter",
    "diameter_tolerance",
    "flow_rate_compensation",
    "nozzle_temperature",
    "bed_temperature",
    "enclosure_temperature",
    "nozzle_temperature_offset",
    "bed_temperature_offset",
    "enclosure_temperature_offset",
    "total_length",
    "used_length",
    "first_use",
    "last_use",
    "purchased_from",
    "purchased_on",
}
_ALIASES = {
    "spool_name": {"spoolname", "spool", "name", "displayname"},
    "vendor": {"vendor", "brand", "manufacturer", "maker"},
    "material": {"material", "materialtype", "filamenttype", "type"},
    "color_name": {"colorname", "colourname", "color", "colour"},
    "color_hex": {"colorcodehex", "colourcodehex", "colorhex", "colourhex", "hex"},
    "serial_number": {"serialnumber", "serial", "spoolid", "uid"},
    "initial_weight": {
        "totalweightg",
        "totalweightkg",
        "totalweight",
        "initialweightg",
        "initialweightkg",
        "initialweight",
        "filamentweightg",
        "filamentweightkg",
        "filamentweight",
    },
    "used_weight": {
        "usedweightg",
        "usedweightkg",
        "usedweight",
        "usedg",
        "usedkg",
        "consumedweightg",
        "consumedweightkg",
        "consumedweight",
    },
    "remaining_weight": {
        "remainingweightg",
        "remainingweightkg",
        "remainingweight",
        "remainingg",
        "remainingkg",
        "weightremainingg",
        "weightremainingkg",
        "weightremaining",
    },
    "empty_spool_weight": {
        "spoolweightg",
        "spoolweightkg",
        "spoolweight",
        "emptyspoolweightg",
        "emptyspoolweightkg",
        "emptyspoolweight",
        "tareweightg",
        "tareweightkg",
        "tareweight",
    },
    "price": {"cost", "price", "purchaseprice"},
    "currency": {"costunit", "currency", "currencycode"},
    "note": {"note", "notes", "comment", "comments"},
    "density": {"densitygcm3", "density"},
    "diameter": {"diametermm", "diameter"},
    "diameter_tolerance": {"diametertolerancemm", "diametertolerance", "tolerance"},
    "flow_rate_compensation": {
        "flowratecompensation",
        "flowratecompensationpct",
        "flowcompensation",
        "flowratio",
    },
    "nozzle_temperature": {
        "temperaturec",
        "nozzletemperaturec",
        "nozzletemperature",
        "hotendtemperature",
    },
    "bed_temperature": {"bedtemperaturec", "bedtemperature"},
    "enclosure_temperature": {
        "enclosuretemperaturec",
        "enclosuretemperature",
        "chambertemperature",
    },
    "nozzle_temperature_offset": {
        "offsettemperaturec",
        "nozzletemperatureoffsetc",
        "nozzletemperatureoffset",
    },
    "bed_temperature_offset": {"offsetbedtemperaturec", "bedtemperatureoffset"},
    "enclosure_temperature_offset": {
        "offsetenclosuretemperaturec",
        "enclosuretemperatureoffset",
    },
    "total_length": {"totallengthmm", "totallength", "initiallength"},
    "used_length": {"usedlengthmm", "usedlength", "consumedlength"},
    "first_use": {"firstuse", "firstusedat"},
    "last_use": {"lastuse", "lastusedat"},
    "purchased_from": {"purchasedfrom", "seller", "shop", "store"},
    "purchased_on": {"purchasedon", "purchasedat", "purchaseddate"},
}


@dataclass(slots=True)
class _CsvDocument:
    headers: list[str]
    rows: list[dict[str, str]]


def _normalize_header(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def _read_csv_document(data: bytes) -> _CsvDocument:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    try:
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect, strict=True)
        headers = [str(name).strip() for name in (reader.fieldnames or [])]
        if (
            not headers
            or any(not header for header in headers)
            or len(set(headers)) != len(headers)
        ):
            raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)
        rows = [
            {
                str(key).strip(): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            for row in reader
            if any((value or "").strip() for value in row.values())
        ]
    except csv.Error:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    if not rows or len(rows) > MAX_IMPORT_ROWS:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)
    return _CsvDocument(headers=headers, rows=rows)


def _suggest_mapping(headers: list[str]) -> SpoolImportColumnMapping:
    normalized = {header: _normalize_header(header) for header in headers}
    fields: dict[str, str] = {}
    claimed: set[str] = set()
    for semantic_field, aliases in _ALIASES.items():
        match = next(
            (
                header
                for header, normalized_header in normalized.items()
                if header not in claimed and normalized_header in aliases
            ),
            None,
        )
        if match is not None:
            fields[semantic_field] = match
            claimed.add(match)

    units: dict[str, str] = {}
    for semantic_field, header in fields.items():
        normalized_header = normalized[header]
        if semantic_field in _WEIGHT_FIELDS:
            units[semantic_field] = "kg" if normalized_header.endswith("kg") else "g"
        elif semantic_field in _LENGTH_FIELDS:
            units[semantic_field] = "m" if normalized_header.endswith("m") else "mm"
    return SpoolImportColumnMapping(fields=fields, units=units)


def _validate_mapping(
    mapping: SpoolImportColumnMapping,
    headers: list[str],
) -> None:
    fields = {str(key): value for key, value in mapping.fields.items()}
    if not fields or not set(fields).issubset(_SUPPORTED_FIELDS):
        raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
    if len(set(fields.values())) != len(fields):
        raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
    if any(column not in headers for column in fields.values()):
        raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
    if not {"initial_weight", "remaining_weight"}.intersection(fields):
        raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)

    for semantic_field, unit in mapping.units.items():
        field_name = str(semantic_field)
        if field_name in _WEIGHT_FIELDS and unit not in {"g", "kg"}:
            raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
        if field_name in _LENGTH_FIELDS and unit not in {"mm", "m"}:
            raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
        if field_name not in _WEIGHT_FIELDS | _LENGTH_FIELDS:
            raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)


def _optional(value: str | None) -> str | None:
    candidate = (value or "").strip()
    return candidate if candidate and candidate != "-" else None


def _number(value: str | None) -> float | None:
    candidate = _optional(value)
    if candidate is None:
        return None
    try:
        return float(candidate.replace(",", "."))
    except ValueError:
        return None


def _scaled_number(
    raw: dict[str, str],
    mapping: SpoolImportColumnMapping,
    semantic_field: str,
) -> float | None:
    column = mapping.fields.get(semantic_field)  # type: ignore[arg-type]
    if column is None:
        return None
    value = _number(raw.get(column))
    if value is None:
        return None
    unit = mapping.units.get(semantic_field)  # type: ignore[arg-type]
    if semantic_field in _WEIGHT_FIELDS and unit == "kg":
        return value * 1000
    if semantic_field in _LENGTH_FIELDS and unit == "m":
        return value * 1000
    return value


def _mapped_value(
    raw: dict[str, str],
    mapping: SpoolImportColumnMapping,
    semantic_field: str,
) -> str:
    column = mapping.fields.get(semantic_field)  # type: ignore[arg-type]
    return raw.get(column, "") if column is not None else ""


def _canonical_csv(
    document: _CsvDocument,
    mapping: SpoolImportColumnMapping,
) -> bytes:
    output = io.StringIO(newline="")
    headers = [
        "Spool Name",
        "Color Name",
        "Color Code [hex]",
        "Vendor",
        "Material",
        "Serialnumber",
        "Density [g/cm3]",
        "Diameter [mm]",
        "Diameter Tolerance[mm]",
        "Flow rate compensation [%]",
        "Temperature [C]",
        "Bed Temperature [C]",
        "Enclosure Temperature [C]",
        "Offset Temperature [C]",
        "Offset Bed Temperature [C]",
        "Offset Enclosure Temperature [C]",
        "Total weight [g]",
        "Spool weight [g]",
        "Used weight [g]",
        "Total length [mm]",
        "Used length [mm]",
        "First use [dd.mm.yyyy hh:mm]",
        "Last use [dd.mm.yyyy hh:mm]",
        "Purchased from",
        "Purchased on [dd.mm.yyyy]",
        "Cost",
        "Cost unit",
        "Note",
    ]
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row_number, raw in enumerate(document.rows, start=1):
        initial = _scaled_number(raw, mapping, "initial_weight")
        used = _scaled_number(raw, mapping, "used_weight")
        remaining = _scaled_number(raw, mapping, "remaining_weight")
        if initial is None and remaining is not None:
            initial = remaining + max(used or 0, 0)
        if used is None and initial is not None and remaining is not None:
            used = max(0, initial - remaining)
        writer.writerow(
            {
                "Spool Name": _mapped_value(raw, mapping, "spool_name")
                or f"Spool {row_number}",
                "Color Name": _mapped_value(raw, mapping, "color_name"),
                "Color Code [hex]": _mapped_value(raw, mapping, "color_hex"),
                "Vendor": _mapped_value(raw, mapping, "vendor"),
                "Material": _mapped_value(raw, mapping, "material"),
                "Serialnumber": _mapped_value(raw, mapping, "serial_number"),
                "Density [g/cm3]": _mapped_value(raw, mapping, "density"),
                "Diameter [mm]": _mapped_value(raw, mapping, "diameter"),
                "Diameter Tolerance[mm]": _mapped_value(
                    raw, mapping, "diameter_tolerance"
                ),
                "Flow rate compensation [%]": _mapped_value(
                    raw, mapping, "flow_rate_compensation"
                ),
                "Temperature [C]": _mapped_value(
                    raw, mapping, "nozzle_temperature"
                ),
                "Bed Temperature [C]": _mapped_value(
                    raw, mapping, "bed_temperature"
                ),
                "Enclosure Temperature [C]": _mapped_value(
                    raw, mapping, "enclosure_temperature"
                ),
                "Offset Temperature [C]": _mapped_value(
                    raw, mapping, "nozzle_temperature_offset"
                ),
                "Offset Bed Temperature [C]": _mapped_value(
                    raw, mapping, "bed_temperature_offset"
                ),
                "Offset Enclosure Temperature [C]": _mapped_value(
                    raw, mapping, "enclosure_temperature_offset"
                ),
                "Total weight [g]": "" if initial is None else str(initial),
                "Spool weight [g]": _scaled_number(
                    raw, mapping, "empty_spool_weight"
                ),
                "Used weight [g]": "0" if used is None else str(used),
                "Total length [mm]": _scaled_number(raw, mapping, "total_length"),
                "Used length [mm]": _scaled_number(raw, mapping, "used_length"),
                "First use [dd.mm.yyyy hh:mm]": _mapped_value(
                    raw, mapping, "first_use"
                ),
                "Last use [dd.mm.yyyy hh:mm]": _mapped_value(
                    raw, mapping, "last_use"
                ),
                "Purchased from": _mapped_value(raw, mapping, "purchased_from"),
                "Purchased on [dd.mm.yyyy]": _mapped_value(
                    raw, mapping, "purchased_on"
                ),
                "Cost": _mapped_value(raw, mapping, "price"),
                "Cost unit": _mapped_value(raw, mapping, "currency"),
                "Note": _mapped_value(raw, mapping, "note"),
            }
        )
    return output.getvalue().encode("utf-8")


def _normalized_custom_rows(
    data: bytes,
    mapping: SpoolImportColumnMapping,
) -> tuple[str, _CsvDocument, list[_ParsedRow]]:
    document = _read_csv_document(data)
    _validate_mapping(mapping, document.headers)
    _, parsed_rows = parse_spoolmanager_csv(_canonical_csv(document, mapping))
    if len(parsed_rows) != len(document.rows):
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    normalized_keys = {
        "density": "density_g_cm3",
        "diameter": "diameter_mm",
        "diameter_tolerance": "diameter_tolerance_mm",
        "flow_rate_compensation": "flow_rate_compensation_pct",
        "nozzle_temperature": "nozzle_temperature_c",
        "bed_temperature": "bed_temperature_c",
        "enclosure_temperature": "enclosure_temperature_c",
        "nozzle_temperature_offset": "nozzle_temperature_offset_c",
        "bed_temperature_offset": "bed_temperature_offset_c",
        "enclosure_temperature_offset": "enclosure_temperature_offset_c",
        "total_length": "total_length_mm",
        "used_length": "used_length_mm",
        "first_use": "first_use",
        "last_use": "last_use",
        "purchased_from": "purchased_from",
        "purchased_on": "purchased_on",
    }
    for parsed, raw in zip(parsed_rows, document.rows, strict=True):
        parsed.raw = raw
        parsed.normalized_extra = {
            normalized_key: value
            for semantic_field, normalized_key in normalized_keys.items()
            if (value := _optional(_mapped_value(raw, mapping, semantic_field)))
            is not None
        }
        for semantic_field in _WEIGHT_FIELDS | _LENGTH_FIELDS:
            normalized_value = _scaled_number(raw, mapping, semantic_field)
            if normalized_value is not None:
                suffix = "_g" if semantic_field in _WEIGHT_FIELDS else "_mm"
                parsed.normalized_extra[f"{semantic_field}{suffix}"] = str(
                    normalized_value
                )
    return hashlib.sha256(data).hexdigest(), document, parsed_rows


async def preview_spool_import(
    db: AsyncSession,
    *,
    user_id: int,
    file_name: str,
    data: bytes,
    mapping: SpoolImportColumnMapping | None,
) -> SpoolImportPreviewResponse:
    """Detect a known source or request an explicit safe column mapping."""
    document = _read_csv_document(data)
    if _SPOOLMANAGER_REQUIRED_COLUMNS.issubset(document.headers):
        file_sha256, rows = parse_spoolmanager_csv(data)
        preview = await preview_parsed_spool_import(
            db,
            user_id=user_id,
            file_name=file_name,
            file_sha256=file_sha256,
            parsed_rows=rows,
            source=SPOOLMANAGER_SOURCE,
        )
        return SpoolImportPreviewResponse(
            **preview.model_dump(),
            detected_format=SPOOLMANAGER_FORMAT,
            detected_label="OctoPrint SpoolManager",
            available_columns=document.headers,
        )

    if mapping is None:
        return SpoolImportPreviewResponse(
            file_name=file_name,
            file_sha256=hashlib.sha256(data).hexdigest(),
            total_rows=len(document.rows),
            importable_rows=0,
            matched_rows=0,
            unmatched_rows=0,
            duplicate_rows=0,
            invalid_rows=0,
            rows=[],
            detected_format=None,
            mapping_required=True,
            available_columns=document.headers,
            sample_rows=document.rows[:3],
            suggested_mapping=_suggest_mapping(document.headers),
            required_fields=["initial_weight"],
        )

    file_sha256, document, rows = _normalized_custom_rows(data, mapping)
    preview = await preview_parsed_spool_import(
        db,
        user_id=user_id,
        file_name=file_name,
        file_sha256=file_sha256,
        parsed_rows=rows,
        source=CUSTOM_CSV_SOURCE,
    )
    return SpoolImportPreviewResponse(
        **preview.model_dump(),
        detected_format=CUSTOM_CSV_FORMAT,
        detected_label="CSV",
        mapping_required=False,
        available_columns=document.headers,
        suggested_mapping=mapping,
    )


async def import_spool_file(
    db: AsyncSession,
    *,
    user: User,
    file_name: str,
    data: bytes,
    selected_fingerprints: set[str],
    mapping: SpoolImportColumnMapping | None,
) -> SpoolImportResponse:
    """Import a detected source or a previously confirmed custom mapping."""
    document = _read_csv_document(data)
    if _SPOOLMANAGER_REQUIRED_COLUMNS.issubset(document.headers):
        file_sha256, rows = parse_spoolmanager_csv(data)
        source = SPOOLMANAGER_SOURCE
        detected_format = SPOOLMANAGER_FORMAT
    else:
        if mapping is None:
            raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
        file_sha256, _, rows = _normalized_custom_rows(data, mapping)
        source = CUSTOM_CSV_SOURCE
        detected_format = CUSTOM_CSV_FORMAT

    result = await import_parsed_spool_rows(
        db,
        user=user,
        file_name=file_name,
        file_sha256=file_sha256,
        parsed_rows=rows,
        selected_fingerprints=selected_fingerprints,
        source=source,
    )
    return SpoolImportResponse(
        **result.model_dump(),
        detected_format=detected_format,
    )

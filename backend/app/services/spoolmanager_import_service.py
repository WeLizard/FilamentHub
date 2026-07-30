"""Safe, idempotent import of OctoPrint SpoolManager CSV exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import (
    ERR_SPOOL_IMPORT_EMPTY_SELECTION,
    ERR_SPOOL_IMPORT_INVALID_CSV,
    ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS,
    raise_error,
)
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import (
    SpoolManagerFilamentMatch,
    SpoolManagerImportResponse,
    SpoolManagerPreviewResponse,
    SpoolManagerPreviewRow,
)

SPOOLMANAGER_SOURCE = "octoprint_spoolmanager"
MAX_IMPORT_ROWS = 1_000

_REQUIRED_COLUMNS = {
    "Spool Name",
    "Vendor",
    "Material",
    "Total weight [g]",
    "Used weight [g]",
}
_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


@dataclass(slots=True)
class _ParsedRow:
    row_number: int
    fingerprint: str
    raw: dict[str, str]
    spool_name: str
    vendor: str | None
    material: str | None
    color_name: str | None
    color_hex: str | None
    serial_number: str | None
    initial_weight_g: float | None
    used_weight_g: float | None
    empty_spool_weight_g: float | None
    price: float | None
    currency: str | None
    note: str | None
    normalized_extra: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    invalid: bool = False

    @property
    def remaining_weight_g(self) -> float | None:
        if self.initial_weight_g is None or self.used_weight_g is None:
            return None
        return max(0.0, self.initial_weight_g - self.used_weight_g)


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return " ".join(normalized.split())


def _normalize_material(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize(value))


def _normalize_hex(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate or candidate == "-":
        return None
    if not _HEX_RE.fullmatch(candidate):
        return None
    return f"#{candidate.lstrip('#').upper()}"


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


def _normalized_number(row: _ParsedRow, key: str) -> float | None:
    return _number(row.normalized_extra.get(key))


def _draft_settings(
    row: _ParsedRow,
    *,
    source: str,
    file_sha256: str,
    user_id: int,
) -> tuple[float, float, float | None, dict] | None:
    nozzle_temp = _normalized_number(row, "nozzle_temperature_c")
    bed_temp = _normalized_number(row, "bed_temperature_c")
    flow_rate = _normalized_number(row, "flow_rate_compensation_pct")
    if nozzle_temp is None and bed_temp is None and flow_rate is None:
        return None

    missing_fields = [
        field
        for field, value in (
            ("extruder_temp", nozzle_temp),
            ("bed_temp", bed_temp),
        )
        if value is None
    ]
    draft_id = f"import_{user_id}_{source}_{row.fingerprint[:20]}"
    settings: dict[str, object] = {
        "fhub_draft_id": draft_id,
        "import_provider": source,
        "import_external_ref": row.fingerprint,
        "import_file_sha256": file_sha256,
        "import_requires_review": True,
        "import_missing_fields": missing_fields,
        "import_fields": dict(row.normalized_extra),
    }
    if nozzle_temp is not None:
        settings["nozzle_temperature"] = [str(nozzle_temp)]
        settings["nozzle_temperature_initial_layer"] = [str(nozzle_temp)]
    if bed_temp is not None:
        settings["hot_plate_temp"] = [str(bed_temp)]
        settings["hot_plate_temp_initial_layer"] = [str(bed_temp)]
    if flow_rate is not None:
        settings["filament_flow_ratio"] = [str(round(flow_rate / 100.0, 4))]
    if row.color_hex:
        settings["default_filament_colour"] = [row.color_hex]

    return nozzle_temp or 0.0, bed_temp or 0.0, flow_rate, settings


async def _create_import_draft(
    db: AsyncSession,
    *,
    user: User,
    row: _ParsedRow,
    source: str,
    file_sha256: str,
    filament_id: int | None,
    existing_external_ids: set[str],
) -> Preset | None:
    draft_values = _draft_settings(
        row,
        source=source,
        file_sha256=file_sha256,
        user_id=user.id,
    )
    if draft_values is None:
        return None
    external_id = f"{source}:{row.fingerprint}"
    if external_id in existing_external_ids:
        return None

    extruder_temp, bed_temp, flow_rate, settings = draft_values
    preset = Preset(
        filament_id=filament_id,
        user_id=user.id,
        name=row.spool_name,
        description=None,
        is_official=False,
        is_weighted=False,
        extruder_temp=extruder_temp,
        bed_temp=bed_temp,
        flow_rate=flow_rate,
        orcaslicer_settings=settings,
        moderation_status=PresetModerationStatus.PENDING,
        active=False,
        source=source,
        external_id=external_id,
    )
    db.add(preset)
    await db.flush()
    db.add(
        UserSavedPreset(
            user_id=user.id,
            preset_id=preset.id,
            sync=False,
        )
    )
    existing_external_ids.add(external_id)
    return preset


async def link_imported_spools_to_preset(
    db: AsyncSession,
    preset: Preset,
) -> list[int]:
    """Link the physical spool(s) that produced a now-resolved import draft."""
    if preset.user_id is None or preset.filament_id is None:
        return []
    settings = preset.orcaslicer_settings
    if not isinstance(settings, dict):
        return []
    import_ref = settings.get("import_external_ref")
    import_provider = settings.get("import_provider")
    if not isinstance(import_ref, str) or not isinstance(import_provider, str):
        return []

    spools = (
        await db.scalars(
            select(UserSpool).where(
                UserSpool.user_id == preset.user_id,
                UserSpool.source == import_provider,
            )
        )
    ).all()
    linked_ids: list[int] = []
    for spool in spools:
        if not isinstance(spool.extra, dict):
            continue
        if spool.extra.get("import_external_ref") != import_ref:
            continue
        spool.filament_id = preset.filament_id
        spool.extra = {
            **spool.extra,
            "import_draft_id": str(preset.id),
            "import_resolved_filament_id": str(preset.filament_id),
        }
        linked_ids.append(spool.id)
    return linked_ids


def _identity_seed(raw: dict[str, str]) -> str:
    serial = _normalize(raw.get("Serialnumber"))
    if serial:
        return f"serial:{serial}"
    stable_columns = (
        "Spool Name",
        "Color Name",
        "Color Code [hex]",
        "Vendor",
        "Material",
        "Density [g/cm3]",
        "Diameter [mm]",
        "Total weight [g]",
        "Spool weight [g]",
        "Purchased from",
        "Purchased on [dd.mm.yyyy]",
        "Cost",
        "Cost unit",
    )
    return "\x1f".join(_normalize(raw.get(column)) for column in stable_columns)


def _known_normalized_extra(raw: dict[str, str]) -> dict[str, str]:
    """Keep useful SpoolManager fields addressable without losing the raw row."""
    columns = {
        "density_g_cm3": "Density [g/cm3]",
        "diameter_mm": "Diameter [mm]",
        "diameter_tolerance_mm": "Diameter Tolerance[mm]",
        "flow_rate_compensation_pct": "Flow rate compensation [%]",
        "nozzle_temperature_c": "Temperature [C]",
        "bed_temperature_c": "Bed Temperature [C]",
        "enclosure_temperature_c": "Enclosure Temperature [C]",
        "nozzle_temperature_offset_c": "Offset Temperature [C]",
        "bed_temperature_offset_c": "Offset Bed Temperature [C]",
        "enclosure_temperature_offset_c": "Offset Enclosure Temperature [C]",
        "total_length_mm": "Total length [mm]",
        "used_length_mm": "Used length [mm]",
        "first_use": "First use [dd.mm.yyyy hh:mm]",
        "last_use": "Last use [dd.mm.yyyy hh:mm]",
        "purchased_from": "Purchased from",
        "purchased_on": "Purchased on [dd.mm.yyyy]",
    }
    return {
        target: value
        for target, column in columns.items()
        if (value := _optional(raw.get(column))) is not None
    }


def parse_spoolmanager_csv(data: bytes) -> tuple[str, list[_ParsedRow]]:
    """Parse the current SpoolManager CSV format without mutating storage."""
    file_sha256 = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        fieldnames = {str(name).strip() for name in (reader.fieldnames or [])}
        if not _REQUIRED_COLUMNS.issubset(fieldnames):
            raise_error(400, ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS)
        raw_rows = [
            {str(key).strip(): (value or "").strip() for key, value in row.items() if key is not None}
            for row in reader
            if any((value or "").strip() for value in row.values())
        ]
    except csv.Error:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    if not raw_rows or len(raw_rows) > MAX_IMPORT_ROWS:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    occurrences: Counter[str] = Counter()
    parsed: list[_ParsedRow] = []
    for row_number, raw in enumerate(raw_rows, start=2):
        identity_seed = _identity_seed(raw)
        occurrences[identity_seed] += 1
        fingerprint = hashlib.sha256(
            f"{identity_seed}\x1f{occurrences[identity_seed]}".encode("utf-8")
        ).hexdigest()

        total_weight = _number(raw.get("Total weight [g]"))
        used_weight = _number(raw.get("Used weight [g]"))
        empty_spool_weight = _number(raw.get("Spool weight [g]"))
        price = _number(raw.get("Cost"))
        warnings: list[str] = []
        invalid = False

        if total_weight is None or total_weight <= 0 or total_weight > 10_000:
            warnings.append("invalid_total_weight")
            invalid = True
        if used_weight is None:
            used_weight = 0.0
        if used_weight < 0:
            warnings.append("invalid_used_weight")
            invalid = True
        if total_weight is not None and used_weight > total_weight:
            warnings.append("used_exceeds_total")
            invalid = True
        if empty_spool_weight is not None and empty_spool_weight < 0:
            warnings.append("invalid_empty_spool_weight")
            empty_spool_weight = None
        if price is not None and price < 0:
            warnings.append("invalid_price")
            price = None

        raw_color_hex = _optional(raw.get("Color Code [hex]"))
        color_hex = _normalize_hex(raw_color_hex)
        if raw_color_hex and color_hex is None:
            warnings.append("invalid_color_hex")

        note = _optional(raw.get("Note"))
        if note and len(note) > 500:
            warnings.append("comment_truncated")

        parsed.append(
            _ParsedRow(
                row_number=row_number,
                fingerprint=fingerprint,
                raw=raw,
                spool_name=_optional(raw.get("Spool Name")) or f"Spool {row_number - 1}",
                vendor=_optional(raw.get("Vendor")),
                material=_optional(raw.get("Material")),
                color_name=_optional(raw.get("Color Name")),
                color_hex=color_hex,
                serial_number=_optional(raw.get("Serialnumber")),
                initial_weight_g=total_weight,
                used_weight_g=used_weight,
                empty_spool_weight_g=empty_spool_weight,
                price=price,
                currency=_optional(raw.get("Cost unit")),
                note=note,
                normalized_extra=_known_normalized_extra(raw),
                warnings=warnings,
                invalid=invalid,
            )
        )
    return file_sha256, parsed


def _match_catalog_filament(
    row: _ParsedRow, filaments: list[Filament]
) -> SpoolManagerFilamentMatch | None:
    vendor = _normalize(row.vendor)
    material = _normalize_material(row.material)
    if not vendor or not material:
        return None

    candidates = [
        filament
        for filament in filaments
        if filament.brand is not None
        and _normalize(filament.brand.name) == vendor
        and _normalize_material(filament.material_type) == material
    ]
    strategies: tuple[tuple[str, list[Filament]], ...] = (
        (
            "name",
            [
                filament
                for filament in candidates
                if _normalize(filament.name) == _normalize(row.spool_name)
            ],
        ),
        (
            "color_hex",
            [
                filament
                for filament in candidates
                if row.color_hex and _normalize_hex(filament.color_hex) == row.color_hex
            ],
        ),
        (
            "color_name",
            [
                filament
                for filament in candidates
                if row.color_name
                and _normalize(filament.color_name) == _normalize(row.color_name)
            ],
        ),
    )
    for reason, matches in strategies:
        if len(matches) == 1:
            filament = matches[0]
            return SpoolManagerFilamentMatch(
                id=filament.id,
                name=filament.name,
                brand_name=filament.brand.name,
                material_type=filament.material_type,
                color_name=filament.color_name,
                color_hex=filament.color_hex,
                reason=reason,
            )
    return None


async def _catalog_filaments(db: AsyncSession) -> list[Filament]:
    result = await db.execute(
        select(Filament)
        .options(joinedload(Filament.brand))
        .where(Filament.active.is_(True))
    )
    return list(result.unique().scalars().all())


async def _existing_fingerprints(
    db: AsyncSession,
    user_id: int,
    *,
    source: str = SPOOLMANAGER_SOURCE,
) -> set[str]:
    result = await db.execute(
        select(UserSpool).where(
            UserSpool.user_id == user_id,
            UserSpool.source == source,
        )
    )
    return {
        str(spool.extra.get("import_external_ref"))
        for spool in result.scalars().all()
        if spool.extra and spool.extra.get("import_external_ref")
    }


async def preview_spoolmanager_import(
    db: AsyncSession,
    *,
    user_id: int,
    file_name: str,
    data: bytes,
) -> SpoolManagerPreviewResponse:
    file_sha256, parsed_rows = parse_spoolmanager_csv(data)
    return await preview_parsed_spool_import(
        db,
        user_id=user_id,
        file_name=file_name,
        file_sha256=file_sha256,
        parsed_rows=parsed_rows,
        source=SPOOLMANAGER_SOURCE,
    )


async def preview_parsed_spool_import(
    db: AsyncSession,
    *,
    user_id: int,
    file_name: str,
    file_sha256: str,
    parsed_rows: list[_ParsedRow],
    source: str,
) -> SpoolManagerPreviewResponse:
    """Build one common preview after a source parser has normalized its rows."""
    filaments = await _catalog_filaments(db)
    existing = await _existing_fingerprints(db, user_id, source=source)
    rows: list[SpoolManagerPreviewRow] = []

    for row in parsed_rows:
        match = None if row.invalid else _match_catalog_filament(row, filaments)
        status = (
            "invalid"
            if row.invalid
            else "already_imported"
            if row.fingerprint in existing
            else "ready"
        )
        warnings = list(row.warnings)
        if status == "already_imported":
            warnings.append("already_imported")
        elif match is None and status == "ready":
            warnings.append("unmatched_catalog")
        rows.append(
            SpoolManagerPreviewRow(
                row_number=row.row_number,
                fingerprint=row.fingerprint,
                status=status,
                spool_name=row.spool_name,
                vendor=row.vendor,
                material=row.material,
                color_name=row.color_name,
                color_hex=row.color_hex,
                serial_number=row.serial_number,
                initial_weight_g=row.initial_weight_g,
                used_weight_g=row.used_weight_g,
                remaining_weight_g=row.remaining_weight_g,
                empty_spool_weight_g=row.empty_spool_weight_g,
                price=row.price,
                currency=row.currency,
                suggested_filament=match,
                warnings=warnings,
            )
        )

    importable = [row for row in rows if row.status == "ready"]
    return SpoolManagerPreviewResponse(
        file_name=file_name,
        file_sha256=file_sha256,
        total_rows=len(rows),
        importable_rows=len(importable),
        matched_rows=sum(row.suggested_filament is not None for row in importable),
        unmatched_rows=sum(row.suggested_filament is None for row in importable),
        duplicate_rows=sum(row.status == "already_imported" for row in rows),
        invalid_rows=sum(row.status == "invalid" for row in rows),
        rows=rows,
    )


def _import_extra(
    row: _ParsedRow,
    file_sha256: str,
    *,
    source: str = SPOOLMANAGER_SOURCE,
    draft_id: int | None = None,
) -> dict[str, str]:
    extra = {
        "import_provider": source,
        "import_external_ref": row.fingerprint,
        "import_file_sha256": file_sha256,
        "display_name": row.spool_name,
        "vendor": row.vendor or "",
        "material": row.material or "",
        "color_name": row.color_name or "",
        "color_hex": row.color_hex or "",
        "serial_number": row.serial_number or "",
        "empty_spool_weight_g": (
            str(row.empty_spool_weight_g)
            if row.empty_spool_weight_g is not None
            else ""
        ),
        "currency": row.currency or "",
        "purchased_from": _optional(row.raw.get("Purchased from")) or "",
        "purchased_on": _optional(row.raw.get("Purchased on [dd.mm.yyyy]")) or "",
        "first_use": _optional(row.raw.get("First use [dd.mm.yyyy hh:mm]")) or "",
        "last_use": _optional(row.raw.get("Last use [dd.mm.yyyy hh:mm]")) or "",
        "source_row": json.dumps(row.raw, ensure_ascii=False, separators=(",", ":")),
    }
    if draft_id is not None:
        extra["import_draft_id"] = str(draft_id)
    extra.update(row.normalized_extra)
    return extra


async def import_spoolmanager_csv(
    db: AsyncSession,
    *,
    user: User,
    file_name: str,
    data: bytes,
    selected_fingerprints: set[str],
) -> SpoolManagerImportResponse:
    file_sha256, parsed_rows = parse_spoolmanager_csv(data)
    return await import_parsed_spool_rows(
        db,
        user=user,
        file_name=file_name,
        file_sha256=file_sha256,
        parsed_rows=parsed_rows,
        selected_fingerprints=selected_fingerprints,
        source=SPOOLMANAGER_SOURCE,
    )


async def import_parsed_spool_rows(
    db: AsyncSession,
    *,
    user: User,
    file_name: str,
    file_sha256: str,
    parsed_rows: list[_ParsedRow],
    selected_fingerprints: set[str],
    source: str,
) -> SpoolManagerImportResponse:
    """Persist explicitly selected normalized rows for any registered importer."""
    if not selected_fingerprints:
        raise_error(400, ERR_SPOOL_IMPORT_EMPTY_SELECTION)

    known_fingerprints = {row.fingerprint for row in parsed_rows}
    if not selected_fingerprints.issubset(known_fingerprints):
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)

    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    existing = await _existing_fingerprints(db, user.id, source=source)
    existing_external_ids = {
        external_id
        for external_id in (
            await db.scalars(
                select(Preset.external_id).where(
                    Preset.user_id == user.id,
                    Preset.source == source,
                    Preset.external_id.is_not(None),
                )
            )
        ).all()
        if external_id is not None
    }
    filaments = await _catalog_filaments(db)
    created_spools: list[UserSpool] = []
    created_drafts: list[Preset] = []
    skipped_existing = 0
    skipped_unselected = 0
    invalid = 0

    for row in parsed_rows:
        if row.fingerprint not in selected_fingerprints:
            skipped_unselected += 1
            continue
        if row.invalid or row.initial_weight_g is None or row.used_weight_g is None:
            invalid += 1
            continue

        match = _match_catalog_filament(row, filaments)
        draft = await _create_import_draft(
            db,
            user=user,
            row=row,
            source=source,
            file_sha256=file_sha256,
            filament_id=match.id if match is not None else None,
            existing_external_ids=existing_external_ids,
        )
        if draft is not None:
            created_drafts.append(draft)

        if row.fingerprint in existing:
            skipped_existing += 1
            continue

        note = row.note
        state = (
            UserSpoolState.empty
            if row.used_weight_g >= row.initial_weight_g
            else UserSpoolState.shelf
        )
        spool = UserSpool(
            user_id=user.id,
            filament_id=match.id if match is not None else None,
            initial_weight_g=row.initial_weight_g,
            used_weight_g=min(row.used_weight_g, row.initial_weight_g),
            price=row.price,
            state=state,
            source=source,
            lot_nr=None,
            comment=note[:500] if note else None,
            extra=_import_extra(
                row,
                file_sha256,
                source=source,
                draft_id=draft.id if draft is not None else None,
            ),
        )
        db.add(spool)
        created_spools.append(spool)
        existing.add(row.fingerprint)

    await db.commit()
    for spool in created_spools:
        await db.refresh(spool)
    return SpoolManagerImportResponse(
        created=len(created_spools),
        skipped_existing=skipped_existing,
        skipped_unselected=skipped_unselected,
        invalid=invalid,
        created_spool_ids=[spool.id for spool in created_spools],
        created_draft_ids=[preset.id for preset in created_drafts],
    )

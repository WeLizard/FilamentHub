"""Spool compatibility endpoints for Happy Hare / Moonraker integration."""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.db.session import AsyncSessionLocal, get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.preset_enrichment_service import _load_material_defaults
from app.services.spool_service import (
    assign_spool_to_gate,
    clear_spool_gate_assignments,
    clear_spool_location_projection,
    lock_spool_row,
    release_spool_location,
    shelf_spool_if_unassigned,
)

from . import spool_compat_fields
from .spool_compat_ws import spool_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["spool_compat"])

_LOCATION_PATTERN = re.compile(r"^(?P<device>.+):\s*gate\s*(?P<gate>\d+)$", re.IGNORECASE)
_LOCATION_FALLBACK_PATTERN = re.compile(r"^(?P<device>.+):\s*(?P<gate>\d+)$")
_LOCATION_HH_PATTERN = re.compile(r"^(?P<device>.+?)\s*@\s*MMU\s+Gate\s*:\s*(?P<gate>\d+)$", re.IGNORECASE)
_LOCATION_FILTER_TOOL = re.compile(r"^[Tt](\d+)$")
_LOCATION_FILTER_GATE = re.compile(r"^[Gg]ate\s*(\d+)$")
_DEFAULT_FILAMENT_DENSITY = 1.24
_DEFAULT_FILAMENT_DIAMETER = 1.75


class SpoolCompatSyncResponse(BaseModel):
    """Legacy response schema for deprecated /sync endpoint."""

    status: str
    message: str


class SpoolUseBody(BaseModel):
    """Compatibility body for /v1/spool/{id}/use endpoint."""

    use_length: float | None = Field(default=None, gt=0)
    use_weight: float | None = Field(default=None, gt=0)


class SpoolMeasureBody(BaseModel):
    """Compatibility body for /v1/spool/{id}/measure endpoint."""

    weight: float = Field(gt=0)


class SpoolCreateBody(BaseModel):
    """Compatibility body for POST /v1/spool."""

    filament_id: int = Field(gt=0)
    initial_weight: float | None = Field(default=None, gt=0)
    used_weight: float | None = Field(default=None, ge=0)
    remaining_weight: float | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=128)
    lot_nr: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=500)
    archived: bool = Field(default=False)
    extra: dict[str, str] | None = None


class SpoolPatchBody(BaseModel):
    """Compatibility body for PATCH /v1/spool/{id}."""

    filament_id: int | None = Field(default=None, gt=0)
    initial_weight: float | None = Field(default=None, gt=0)
    used_weight: float | None = Field(default=None, ge=0)
    remaining_weight: float | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=128)
    lot_nr: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=500)
    archived: bool | None = None
    extra: dict[str, str] | None = None


def _err(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"message": message})


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _strip_hex(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lstrip("#")


def _length_from_weight(weight_g: float | None, density: float, diameter_mm: float) -> float | None:
    if weight_g is None or weight_g < 0 or density <= 0 or diameter_mm <= 0:
        return None
    radius = diameter_mm / 2.0
    area_mm2 = math.pi * radius * radius
    volume_mm3 = (weight_g / density) * 1000.0
    return max(volume_mm3 / area_mm2, 0.0)


def _weight_from_length(length_mm: float, density: float, diameter_mm: float) -> float:
    radius = diameter_mm / 2.0
    area_mm2 = math.pi * radius * radius
    volume_mm3 = length_mm * area_mm2
    volume_cm3 = volume_mm3 / 1000.0
    return max(volume_cm3 * density, 0.0)


def _filament_density(filament: Filament | None) -> float:
    if filament is not None and filament.density and filament.density > 0:
        return filament.density
    return _DEFAULT_FILAMENT_DENSITY


def _filament_diameter(filament: Filament | None) -> float:
    if filament is not None and filament.diameter and filament.diameter > 0:
        return filament.diameter
    return _DEFAULT_FILAMENT_DIAMETER


def _representative_preset(filament: Filament) -> Preset | None:
    """Pick the preset whose temperatures best represent this filament.

    Prefers official, approved, active presets (ranked by rating/usage), then
    falls back to any approved active preset. Requires filament.presets to be
    eagerly loaded by the caller (lazy access is not allowed under async).
    """
    presets = [
        p
        for p in (filament.presets or [])
        if p.active and p.moderation_status in PUBLIC_PRESET_STATUSES
    ]
    if not presets:
        return None
    officials = [p for p in presets if p.is_official]
    pool = officials or presets
    return max(pool, key=lambda p: (p.rating or 0.0, p.usage_count or 0, p.id or 0))


def _preset_temps(preset: Preset) -> tuple[float, float]:
    """Extruder/bed temperatures of a concrete preset."""
    return float(preset.extruder_temp), float(preset.bed_temp)


def _material_default_temps(filament: Filament | None) -> tuple[float | None, float | None]:
    """Per-material default temperatures, used when no preset is available.

    Happy Hare maps these onto the gate map and runs int(temp) on them, so a
    None value crashes the whole MMU_GATE_MAP update; material defaults keep the
    value numeric for every known material.
    """
    if filament is None:
        return None, None
    defaults = _load_material_defaults()
    material = (filament.material_type or "").upper()
    material_defaults = defaults.get(material) or defaults.get("PLA", {})
    extruder = material_defaults.get("extruder_temp")
    bed = material_defaults.get("bed_temp")
    return (
        float(extruder) if extruder is not None else None,
        float(bed) if bed is not None else None,
    )


def _filament_temps(filament: Filament | None) -> tuple[float | None, float | None]:
    """Gate-less temperatures for a filament (e.g. the filament catalog).

    With no gate binding to read a concrete preset from, prefer the filament's
    representative preset, then fall back to per-material defaults.
    """
    if filament is None:
        return None, None
    preset = _representative_preset(filament)
    if preset is not None:
        return _preset_temps(preset)
    return _material_default_temps(filament)


def _filament_payload(
    filament: Filament | None,
    fallback_id: int,
    initial_weight: float | None = None,
    temp_override: tuple[float | None, float | None] | None = None,
) -> dict:
    density = _filament_density(filament)
    diameter = _filament_diameter(filament)
    extruder_temp, bed_temp = temp_override if temp_override is not None else _filament_temps(filament)
    brand = filament.brand if filament is not None else None
    # Spoolman filament.weight = net weight of filament in a full spool (grams).
    # Use filament.spool_weight from DB; fallback to spool's initial_weight_g
    # when the filament-level field is not populated.
    filament_weight = (filament.spool_weight if filament is not None else None) or initial_weight
    return {
        "id": filament.id if filament is not None else fallback_id,
        "registered": _iso(filament.created_at) if filament is not None else _iso(datetime.now(timezone.utc)),
        "name": filament.name if filament is not None else f"Spool {fallback_id}",
        "vendor": (
            {
                "id": brand.id,
                "registered": _iso(brand.created_at),
                "name": brand.name,
                "comment": brand.description,
                "empty_spool_weight": None,
                "external_id": None,
                "extra": {},
            }
            if brand is not None
            else None
        ),
        "material": filament.material_type if filament is not None else "Unknown",
        "price": filament.price_per_kg if filament is not None else None,
        "density": density,
        "diameter": diameter,
        "weight": filament_weight,
        "spool_weight": filament.empty_spool_weight_g if filament is not None else None,
        "article_number": None,
        "comment": None,
        "settings_extruder_temp": extruder_temp,
        "settings_bed_temp": bed_temp,
        "color_hex": _strip_hex(filament.color_hex if filament is not None else None),
        "multi_color_hexes": None,
        "multi_color_direction": None,
        "external_id": None,
        "extra": {},
    }


def _spool_price(spool: UserSpool, filament: Filament | None) -> float | None:
    if spool.price is not None:
        return round(spool.price, 4)
    if filament is None or filament.price_per_kg is None:
        return None
    if filament.price_per_kg < 0 or spool.initial_weight_g <= 0:
        return None
    return round((filament.price_per_kg * spool.initial_weight_g) / 1000.0, 4)


async def _resolve_user_and_device(
    db: AsyncSession, api_key: str | None
) -> tuple[User | None, UserPrinterDevice | None]:
    """Resolve user and device by per-device API key."""
    if not api_key:
        return None, None
    row = await db.execute(
        select(UserPrinterDevice, User)
        .join(User, UserPrinterDevice.user_id == User.id)
        .where(UserPrinterDevice.api_key == api_key, User.active.is_(True))
    )
    result = row.first()
    if result is None:
        return None, None
    device, user = result.tuple()
    device.last_seen_at = datetime.now(timezone.utc)
    return user, device


async def _update_device_gate_count(db: AsyncSession, device: UserPrinterDevice, location_map: dict[int, str]) -> None:
    """Derive gate_count from the highest gate index seen in location map."""
    max_gate = -1
    for loc in location_map.values():
        match = _LOCATION_HH_PATTERN.match(loc) or _LOCATION_PATTERN.match(loc) or _LOCATION_FALLBACK_PATTERN.match(loc)
        if match:
            max_gate = max(max_gate, int(match.group("gate")))
    if max_gate >= 0:
        new_count = max_gate + 1
        # Only auto-increment gate_count, never shrink (user may have set it manually)
        if device.gate_count is None or new_count > device.gate_count:
            device.gate_count = new_count
            logger.info("Updated HH device id=%s gate_count=%s", device.id, new_count)


async def _build_location_map(
    db: AsyncSession, user_id: int
) -> tuple[dict[int, str], dict[int, tuple[str, int, str, Preset | None]]]:
    """Return (location_map, gate_meta_map).

    location_map:  spool_id → "DeviceName @ MMU Gate:N"
    gate_meta_map: spool_id → (device_name, gate_index, printer_hostname, gate_preset)

    gate_preset is the preset bound to that gate from the web/profile UI, or
    None when the gate has no preset assigned.
    """
    result = await db.execute(
        select(PresetGateState, UserPrinterDevice)
        .join(UserPrinterDevice, UserPrinterDevice.id == PresetGateState.device_id)
        .options(joinedload(PresetGateState.preset))
        .where(
            PresetGateState.user_id == user_id,
            PresetGateState.spool_id.is_not(None),
            PresetGateState.is_active.is_(True),
        )
        .order_by(PresetGateState.updated_at.desc())
    )
    location_map: dict[int, str] = {}
    gate_meta_map: dict[int, tuple[str, int, str, Preset | None]] = {}
    for gate_state, device in result.all():
        if gate_state.spool_id is None or gate_state.spool_id in location_map:
            continue
        device_name = device.name or device.device_fingerprint
        hostname = device.printer_hostname or ""
        location_map[gate_state.spool_id] = f"{device_name} @ MMU Gate:{gate_state.gate_index}"
        gate_meta_map[gate_state.spool_id] = (
            device_name,
            gate_state.gate_index,
            hostname,
            gate_state.preset,
        )
    return location_map, gate_meta_map


def _to_spool_payload(
    spool: UserSpool,
    location_map: dict[int, str],
    gate_meta_map: dict[int, tuple[str, int, str, Preset | None]] | None = None,
) -> dict:
    filament = spool.filament
    density = _filament_density(filament)
    diameter = _filament_diameter(filament)
    remaining_weight = max(spool.initial_weight_g - spool.used_weight_g, 0.0)
    location = location_map.get(spool.id)

    # Gate temperatures: a preset bound to the gate (web/profile UI) wins; when
    # the gate has no preset we fall back to per-material defaults so Happy Hare
    # never receives None. Left None here for spools that are not on any gate,
    # in which case _filament_payload derives gate-less defaults.
    temp_override: tuple[float | None, float | None] | None = None

    # Merge extra: start from stored spool.extra, then fill in HH gate fields
    # from our PresetGateState if the stored values are empty/unset.
    extra: dict = dict(spool.extra or {})
    if gate_meta_map and spool.id in gate_meta_map:
        _device_name, gate_index, printer_hostname, gate_preset = gate_meta_map[spool.id]
        temp_override = (
            _preset_temps(gate_preset) if gate_preset is not None else _material_default_temps(filament)
        )
        # HH reads: json.loads(extra.get('printer_name', '""')) and int(extra.get('mmu_gate_map', -1))
        # So printer_name must be JSON-encoded string ('"voron"'), mmu_gate_map must be string int ('0')
        # IMPORTANT: printer_name must match the Klipper printer hostname, NOT the device display name.
        # Always override with the authoritative hostname from device record when available,
        # because stored extra may contain the display name (e.g. "Voron R2.4 350" vs "voron").
        if printer_hostname:
            extra["printer_name"] = json.dumps(printer_hostname)
        else:
            stored_name = extra.get("printer_name", "")
            if not stored_name or stored_name == '""':
                extra["printer_name"] = json.dumps("")
        extra["mmu_gate_map"] = json.dumps(gate_index)

    # Sanitize extra values for HH compatibility: bare empty strings are not
    # valid JSON and cause json.loads("") → ValueError in HH mmu_server.py.
    # Ensure printer_name is a JSON-encoded string and mmu_gate_map is a
    # JSON-encoded integer so HH can safely parse them.
    if "printer_name" in extra and extra["printer_name"] == "":
        extra["printer_name"] = json.dumps("")
    if "mmu_gate_map" in extra and extra["mmu_gate_map"] == "":
        extra["mmu_gate_map"] = json.dumps(-1)

    return {
        "id": spool.id,
        "registered": _iso(spool.created_at),
        "first_used": _iso(spool.first_used_at),
        "last_used": _iso(spool.last_used_at),
        "filament": _filament_payload(filament, spool.id, spool.initial_weight_g, temp_override=temp_override),
        "filament_id": spool.filament_id,
        "price": _spool_price(spool, filament),
        "remaining_weight": round(remaining_weight, 3),
        "initial_weight": round(spool.initial_weight_g, 3),
        "spool_weight": filament.empty_spool_weight_g if filament is not None else None,
        "used_weight": round(spool.used_weight_g, 3),
        "remaining_length": _length_from_weight(remaining_weight, density, diameter),
        "used_length": _length_from_weight(spool.used_weight_g, density, diameter) or 0.0,
        "location": location,
        "lot_nr": spool.lot_nr,
        "comment": spool.comment,
        "archived": spool.state == UserSpoolState.archived,
        "extra": extra,
    }


def _match_filter(value: str | None, filter_raw: str | None) -> bool:
    if filter_raw is None:
        return True
    normalized = (value or "").strip().lower()
    terms = [term.strip() for term in filter_raw.split(",")]
    for term in terms:
        if term == "":
            if normalized == "":
                return True
            continue
        if term.startswith('"') and term.endswith('"') and len(term) >= 2:
            if normalized == term[1:-1].lower():
                return True
            continue
        if term.lower() in normalized:
            return True
    return False


def _extract_gate_index(location: str | None) -> int | None:
    """Extract gate index from our internal location format."""
    if not location:
        return None
    m = _LOCATION_HH_PATTERN.match(location.strip())
    if m:
        return int(m.group("gate"))
    m = _LOCATION_PATTERN.match(location.strip())
    if m:
        return int(m.group("gate"))
    m = _LOCATION_FALLBACK_PATTERN.match(location.strip())
    if m:
        return int(m.group("gate"))
    return None


def _match_location_filter(location: str | None, filter_raw: str | None) -> bool:
    """Match location with support for T<N> and Gate <N> shorthand filters.

    Moonraker and Happy Hare may filter by tool index (T0, T1) or gate (Gate 0).
    Our location format is "DeviceName @ MMU Gate:N", so plain substring match
    on "T0" would not work. This function handles both shorthand and regular
    substring matching.
    """
    if filter_raw is None:
        return True
    terms = [term.strip() for term in filter_raw.split(",")]
    for term in terms:
        if not term:
            if not (location or "").strip():
                return True
            continue

        # Check T<N> pattern (e.g. "T0" → gate 0)
        m = _LOCATION_FILTER_TOOL.match(term)
        if m:
            gate = _extract_gate_index(location)
            if gate is not None and gate == int(m.group(1)):
                return True
            continue

        # Check "Gate <N>" pattern (e.g. "Gate 0" → gate 0)
        m = _LOCATION_FILTER_GATE.match(term)
        if m:
            gate = _extract_gate_index(location)
            if gate is not None and gate == int(m.group(1)):
                return True
            continue

        # Fallback: standard substring/exact match via _match_filter
        if _match_filter(location, term):
            return True

    return False


def _parse_int_list(raw: str | None) -> set[int] | None:
    if raw is None:
        return None
    values = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError:
            continue
    return values if values else set()


def _sort_key(payload: dict, field_name: str):
    if field_name == "filament.name":
        value = payload["filament"].get("name")
    elif field_name == "filament.vendor.id":
        vendor = payload["filament"].get("vendor")
        value = vendor.get("id") if isinstance(vendor, dict) else None
    else:
        value = payload.get(field_name)
    return (value is None, value)


async def _apply_location_assignment(
    db: AsyncSession,
    user: User,
    spool: UserSpool,
    location: str | None,
    device_from_key: UserPrinterDevice | None = None,
) -> tuple[bool, str | None]:
    if location is None or location.strip() == "":
        await release_spool_location(
            db, spool, source=PresetGateStateSource.web_manual
        )
        return True, None

    if (
        spool.remaining_weight_g <= 0
        or spool.state in {UserSpoolState.archived, UserSpoolState.empty}
    ):
        return False, "An archived or empty spool cannot be assigned to an MMU gate."

    location_clean = location.strip()
    match = (
        _LOCATION_PATTERN.match(location_clean)
        or _LOCATION_FALLBACK_PATTERN.match(location_clean)
        or _LOCATION_HH_PATTERN.match(location_clean)
    )
    if not match:
        return False, "Invalid location format. Expected '<device>:Gate<index>'."

    device_hint = match.group("device").strip()
    gate_index = int(match.group("gate"))

    # Try to find device by name, hostname, or fingerprint
    device_result = await db.execute(
        select(UserPrinterDevice).where(
            UserPrinterDevice.user_id == user.id,
            (UserPrinterDevice.name == device_hint)
            | (UserPrinterDevice.printer_hostname == device_hint)
            | (UserPrinterDevice.device_fingerprint == device_hint),
        )
    )
    device = device_result.scalar_one_or_none()

    # Fallback: use the device resolved from the API key
    if device is None and device_from_key is not None:
        device = device_from_key

    # Save the hostname from location string (HH sends "voron @ MMU Gate:1")
    if device is not None and device_hint:
        if device.printer_hostname != device_hint:
            device.printer_hostname = device_hint
            logger.info("Detected printer hostname '%s' for device id=%s", device_hint, device.id)

    if device is None:
        return False, f"Device '{device_hint}' not found for this API key."

    try:
        await assign_spool_to_gate(
            db,
            user_id=user.id,
            spool=spool,
            device=device,
            gate_index=gate_index,
            source=PresetGateStateSource.web_manual,
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        return False, "Spool is being moved by another request; retry."
    return True, None


async def _sync_extra_to_gate_state(
    db: AsyncSession,
    user: User,
    spool: UserSpool,
    device: UserPrinterDevice | None = None,
) -> None:
    """Sync HH extra fields (printer_name, mmu_gate_map) to PresetGateState.

    When Happy Hare PATCHes spool.extra with gate assignment info,
    this ensures our internal PresetGateState records stay in sync.
    """
    extra = spool.extra or {}
    raw_printer = extra.get("printer_name", "")
    raw_gate = extra.get("mmu_gate_map", "-1")

    try:
        printer_name = json.loads(raw_printer) if raw_printer else ""
    except (json.JSONDecodeError, TypeError):
        printer_name = str(raw_printer) if raw_printer else ""

    try:
        gate_index = int(json.loads(raw_gate)) if raw_gate not in ("", "-1") else -1
    except (json.JSONDecodeError, TypeError, ValueError):
        gate_index = -1

    if not printer_name or gate_index < 0:
        await release_spool_location(
            db, spool, source=PresetGateStateSource.hh_snapshot
        )
        return

    if (
        spool.remaining_weight_g <= 0
        or spool.state in {UserSpoolState.archived, UserSpoolState.empty}
    ):
        await lock_spool_row(db, spool.id)
        await clear_spool_gate_assignments(
            db, spool, source=PresetGateStateSource.hh_snapshot
        )
        await db.flush()
        clear_spool_location_projection(spool)
        return

    if device is not None and printer_name:
        device.printer_hostname = printer_name

    if device is None:
        device_result = await db.execute(
            select(UserPrinterDevice).where(
                UserPrinterDevice.user_id == user.id,
                (UserPrinterDevice.printer_hostname == printer_name)
                | (UserPrinterDevice.name == printer_name),
            )
        )
        device = device_result.scalar_one_or_none()
        if device is not None:
            device.printer_hostname = printer_name

    if device is None:
        logger.warning(
            "Cannot sync HH extra to gate state: no device '%s' for user_id=%s",
            printer_name, user.id,
        )
        return

    try:
        await assign_spool_to_gate(
            db,
            user_id=user.id,
            spool=spool,
            device=device,
            gate_index=gate_index,
            source=PresetGateStateSource.hh_snapshot,
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # Backstop race: another request moved this spool mid-sync.
        # The failed flush poisoned the transaction; discard it.
        await db.rollback()
        logger.warning(
            "Concurrent location conflict while syncing HH extra for spool %d",
            spool.id,
        )


async def _get_user_spool(db: AsyncSession, user_id: int, spool_id: int) -> UserSpool | None:
    result = await db.execute(
        select(UserSpool)
        .options(
            joinedload(UserSpool.filament).joinedload(Filament.brand),
            joinedload(UserSpool.filament).selectinload(Filament.presets),
        )
        .where(UserSpool.id == spool_id, UserSpool.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _broadcast_spool_event(user_id: int, event_type: str, payload: dict) -> None:
    await spool_ws_manager.broadcast(
        user_id,
        {
            "type": event_type,
            "resource": "spool",
            "date": _iso(datetime.now(timezone.utc)),
            "payload": payload,
        },
    )


@router.get("/sync", response_model=SpoolCompatSyncResponse)
async def sync_spool_compat() -> SpoolCompatSyncResponse:
    """Deprecated endpoint kept for backward compatibility."""
    return SpoolCompatSyncResponse(
        status="deprecated",
        message=(
            "Use spool_compat API: /api/v1/spool_compat/{api_key}/v1/* "
            "(or /api/v1/spool_compat/v1/* with X-API-Key header)."
        ),
    )


@router.get("/v1/health")
async def spool_compat_health() -> dict:
    """Compatibility health endpoint."""
    return {"status": "healthy"}


@router.get("/{api_key}/v1/health")
@router.get("/{api_key}/api/v1/health")
async def spool_compat_health_scoped(api_key: str) -> dict:
    """Compatibility health endpoint (scoped path)."""
    # Intentionally does not validate key to match upstream health semantics.
    _ = api_key
    return {"status": "healthy"}


@router.get("/v1/info")
async def spool_compat_info() -> dict:
    """Compatibility info endpoint."""
    return {
        "version": "0.21.0",
        "debug_mode": settings.DEBUG,
        "automatic_backups": False,
        "data_dir": "filamenthub",
        "logs_dir": "filamenthub",
        "backups_dir": "filamenthub",
        "db_type": "postgres",
        "git_commit": None,
        "build_date": None,
    }


@router.get("/{api_key}/v1/info")
@router.get("/{api_key}/api/v1/info")
async def spool_compat_info_scoped(api_key: str) -> dict:
    """Compatibility info endpoint (scoped path)."""
    _ = api_key
    return await spool_compat_info()


@router.get("/{api_key}")
async def spool_compat_root(api_key: str) -> dict:
    """Base URL handler — returned when Mainsail or browser hits the bare api_key path."""
    _ = api_key
    return await spool_compat_info()


@router.websocket("/v1/spool")
async def spool_ws(websocket: WebSocket) -> None:
    # No api_key — accept but never emit events (no user context).
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


@router.websocket("/{api_key}/v1/spool")
@router.websocket("/{api_key}/api/v1/spool")
async def spool_ws_scoped(websocket: WebSocket, api_key: str) -> None:
    async with AsyncSessionLocal() as db:
        user, _device = await _resolve_user_and_device(db, api_key)

    if user is None:
        await websocket.accept()
        await websocket.close(code=1008)
        return

    user_id = user.id
    await websocket.accept()
    spool_ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        spool_ws_manager.disconnect(user_id, websocket)


@router.get("/v1/spool")
async def list_spools_with_header_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_api_key: Annotated[str | None, Query(alias="api_key")] = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    allow_archived: bool = False,
    location: str | None = None,
    lot_nr: str | None = None,
    filament_name: Annotated[str | None, Query(alias="filament.name")] = None,
    filament_material: Annotated[str | None, Query(alias="filament.material")] = None,
    filament_vendor_name: Annotated[str | None, Query(alias="filament.vendor.name")] = None,
    filament_vendor_id: Annotated[str | None, Query(alias="filament.vendor.id")] = None,
    filament_id: Annotated[str | None, Query(alias="filament.id")] = None,
    sort: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    api_key = x_api_key or header_api_key
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")

    return await _list_spools_impl(
        db=db,
        user=user,
        allow_archived=allow_archived,
        location=location,
        lot_nr=lot_nr,
        filament_name=filament_name,
        filament_material=filament_material,
        filament_vendor_name=filament_vendor_name,
        filament_vendor_id=filament_vendor_id,
        filament_id=filament_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/{api_key}/v1/spool")
@router.get("/{api_key}/api/v1/spool")
async def list_spools(
    api_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    allow_archived: bool = False,
    location: str | None = None,
    lot_nr: str | None = None,
    filament_name: Annotated[str | None, Query(alias="filament.name")] = None,
    filament_material: Annotated[str | None, Query(alias="filament.material")] = None,
    filament_vendor_name: Annotated[str | None, Query(alias="filament.vendor.name")] = None,
    filament_vendor_id: Annotated[str | None, Query(alias="filament.vendor.id")] = None,
    filament_id: Annotated[str | None, Query(alias="filament.id")] = None,
    sort: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")

    return await _list_spools_impl(
        db=db,
        user=user,
        allow_archived=allow_archived,
        location=location,
        lot_nr=lot_nr,
        filament_name=filament_name,
        filament_material=filament_material,
        filament_vendor_name=filament_vendor_name,
        filament_vendor_id=filament_vendor_id,
        filament_id=filament_id,
        sort=sort,
        limit=limit,
        offset=offset,
        device=_device,
    )


async def _list_spools_impl(
    db: AsyncSession,
    user: User,
    allow_archived: bool,
    location: str | None,
    lot_nr: str | None,
    filament_name: str | None,
    filament_material: str | None,
    filament_vendor_name: str | None,
    filament_vendor_id: str | None,
    filament_id: str | None,
    sort: str | None,
    limit: int | None,
    offset: int,
    device: UserPrinterDevice | None = None,
) -> JSONResponse:
    result = await db.execute(
        select(UserSpool)
        .options(
            joinedload(UserSpool.filament).joinedload(Filament.brand),
            joinedload(UserSpool.filament).selectinload(Filament.presets),
        )
        .where(UserSpool.user_id == user.id)
        .order_by(UserSpool.created_at.desc())
    )
    spools = list(result.scalars().all())
    location_map, gate_meta_map = await _build_location_map(db, user.id)

    # Update gate_count from location data when accessed via device api_key
    if device is not None:
        await _update_device_gate_count(db, device, location_map)
        await db.commit()

    filament_ids = _parse_int_list(filament_id)
    vendor_ids = _parse_int_list(filament_vendor_id)

    payloads: list[dict] = []
    for spool in spools:
        if not allow_archived and spool.state == UserSpoolState.archived:
            continue

        payload = _to_spool_payload(spool, location_map, gate_meta_map)
        fil = payload["filament"]
        vendor = fil.get("vendor") if isinstance(fil, dict) else None

        if not _match_location_filter(payload.get("location"), location):
            continue
        if not _match_filter(payload.get("lot_nr"), lot_nr):
            continue
        if not _match_filter(fil.get("name"), filament_name):
            continue
        if not _match_filter(fil.get("material"), filament_material):
            continue
        if not _match_filter(vendor.get("name") if isinstance(vendor, dict) else None, filament_vendor_name):
            continue
        if filament_ids is not None and fil.get("id") not in filament_ids:
            continue
        if vendor_ids is not None:
            vendor_id_value = vendor.get("id") if isinstance(vendor, dict) else -1
            if vendor_id_value not in vendor_ids:
                continue

        payloads.append(payload)

    if sort:
        for item in reversed(sort.split(",")):
            field, _, direction = item.partition(":")
            direction = (direction or "asc").lower()
            payloads.sort(key=lambda p: _sort_key(p, field), reverse=direction == "desc")

    total_count = len(payloads)
    if limit is not None:
        payloads = payloads[offset : offset + limit]
    elif offset:
        payloads = payloads[offset:]

    return JSONResponse(content=payloads, headers={"x-total-count": str(total_count)})


async def _get_spool_impl(
    db: AsyncSession,
    user: User,
    spool_id: int,
) -> JSONResponse:
    spool = await _get_user_spool(db, user.id, spool_id)
    if spool is None:
        return _err(status.HTTP_404_NOT_FOUND, f"No spool with ID {spool_id} found.")

    location_map, gate_meta_map = await _build_location_map(db, user.id)
    return JSONResponse(content=_to_spool_payload(spool, location_map, gate_meta_map))


@router.get("/v1/spool/{spool_id}")
async def get_spool_with_header_key(
    spool_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_api_key: Annotated[str | None, Query(alias="api_key")] = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> JSONResponse:
    api_key = x_api_key or header_api_key
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")
    return await _get_spool_impl(db, user, spool_id)


@router.get("/{api_key}/v1/spool/{spool_id}")
@router.get("/{api_key}/api/v1/spool/{spool_id}")
async def get_spool(
    api_key: str,
    spool_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")
    return await _get_spool_impl(db, user, spool_id)


@router.post("/{api_key}/v1/spool")
@router.post("/{api_key}/api/v1/spool")
async def create_spool(
    api_key: str,
    body: SpoolCreateBody,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")

    if body.remaining_weight is not None and body.used_weight is not None:
        return _err(status.HTTP_400_BAD_REQUEST, "Only specify either remaining_weight or used_weight.")

    filament_result = await db.execute(select(Filament).where(Filament.id == body.filament_id))
    filament = filament_result.scalar_one_or_none()
    if filament is None:
        return _err(status.HTTP_404_NOT_FOUND, f"No filament with ID {body.filament_id} found.")

    initial_weight = body.initial_weight if body.initial_weight is not None else (filament.spool_weight or 1000.0)
    if body.used_weight is not None:
        used_weight = body.used_weight
    elif body.remaining_weight is not None:
        used_weight = max(initial_weight - body.remaining_weight, 0.0)
    else:
        used_weight = 0.0

    if body.used_weight is not None and body.used_weight >= initial_weight:
        return _err(status.HTTP_400_BAD_REQUEST, "A new spool must have remaining filament.")
    if body.remaining_weight is not None and (
        body.remaining_weight <= 0 or body.remaining_weight > initial_weight
    ):
        return _err(
            status.HTTP_400_BAD_REQUEST,
            "Remaining weight must be greater than zero and not exceed initial weight.",
        )

    spool = UserSpool(
        user_id=user.id,
        filament_id=body.filament_id,
        initial_weight_g=float(initial_weight),
        used_weight_g=float(min(max(used_weight, 0.0), initial_weight)),
        state=UserSpoolState.archived if body.archived else UserSpoolState.shelf,
        source="spool_compat",
        lot_nr=body.lot_nr,
        comment=body.comment,
        extra=body.extra or {},
    )
    db.add(spool)
    await db.flush()

    ok, err = await _apply_location_assignment(db, user, spool, body.location, device_from_key=_device)
    if not ok:
        await db.rollback()
        return _err(status.HTTP_400_BAD_REQUEST, err or "Failed to assign spool location.")

    await db.commit()
    created = await _get_user_spool(db, user.id, spool.id)
    if created is None:
        return _err(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create spool.")
    location_map, gate_meta_map = await _build_location_map(db, user.id)
    payload = _to_spool_payload(created, location_map, gate_meta_map)
    await _broadcast_spool_event(user.id, "added", payload)
    return JSONResponse(content=payload)


@router.patch("/{api_key}/v1/spool/{spool_id}")
@router.patch("/{api_key}/api/v1/spool/{spool_id}")
async def patch_spool(
    api_key: str,
    spool_id: int,
    body: SpoolPatchBody,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")

    spool = await _get_user_spool(db, user.id, spool_id)
    if spool is None:
        return _err(status.HTTP_404_NOT_FOUND, f"No spool with ID {spool_id} found.")

    if body.remaining_weight is not None and body.used_weight is not None:
        return _err(status.HTTP_400_BAD_REQUEST, "Only specify either remaining_weight or used_weight.")

    fields_set = body.model_fields_set

    if body.filament_id is not None:
        filament_result = await db.execute(select(Filament).where(Filament.id == body.filament_id))
        filament = filament_result.scalar_one_or_none()
        if filament is None:
            return _err(status.HTTP_404_NOT_FOUND, f"No filament with ID {body.filament_id} found.")
        spool.filament_id = body.filament_id

    if body.initial_weight is not None:
        spool.initial_weight_g = float(body.initial_weight)
    if body.used_weight is not None:
        spool.used_weight_g = float(min(max(body.used_weight, 0.0), spool.initial_weight_g))
    if body.remaining_weight is not None:
        computed_used = max(spool.initial_weight_g - body.remaining_weight, 0.0)
        spool.used_weight_g = float(min(max(computed_used, 0.0), spool.initial_weight_g))
    if "lot_nr" in fields_set:
        spool.lot_nr = body.lot_nr
    if "comment" in fields_set:
        spool.comment = body.comment
    if body.archived is not None:
        spool.state = UserSpoolState.archived if body.archived else UserSpoolState.active
    if spool.used_weight_g >= spool.initial_weight_g:
        spool.state = UserSpoolState.empty

    if "location" in fields_set:
        ok, err = await _apply_location_assignment(db, user, spool, body.location, device_from_key=_device)
        if not ok:
            await db.rollback()
            return _err(status.HTTP_400_BAD_REQUEST, err or "Failed to assign spool location.")

    if "extra" in fields_set:
        if body.extra is None:
            spool.extra = {}
        else:
            merged_extra = dict(spool.extra or {})
            merged_extra.update(body.extra)
            spool.extra = merged_extra

    # Sync HH extra fields (printer_name, mmu_gate_map) to PresetGateState
    # so gate assignments from Happy Hare are reflected in our internal model.
    if "extra" in fields_set and "location" not in fields_set:
        await _sync_extra_to_gate_state(db, user, spool, device=_device)

    if spool.state in {UserSpoolState.archived, UserSpoolState.empty}:
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)
    elif body.archived is False and "location" not in fields_set and "extra" not in fields_set:
        await shelf_spool_if_unassigned(db, spool)

    await db.commit()
    updated = await _get_user_spool(db, user.id, spool.id)
    if updated is None:
        return _err(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update spool.")
    location_map, gate_meta_map = await _build_location_map(db, user.id)
    payload = _to_spool_payload(updated, location_map, gate_meta_map)
    await _broadcast_spool_event(user.id, "updated", payload)
    return JSONResponse(content=payload)


@router.put("/{api_key}/v1/spool/{spool_id}/use")
@router.put("/{api_key}/api/v1/spool/{spool_id}/use")
async def use_spool(
    api_key: str,
    spool_id: int,
    body: SpoolUseBody,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")

    spool = await _get_user_spool(db, user.id, spool_id)
    if spool is None:
        return _err(status.HTTP_404_NOT_FOUND, f"No spool with ID {spool_id} found.")

    if body.use_weight is not None and body.use_length is not None:
        return _err(status.HTTP_400_BAD_REQUEST, "Only specify either use_weight or use_length.")
    if body.use_weight is None and body.use_length is None:
        return _err(status.HTTP_400_BAD_REQUEST, "Either use_weight or use_length must be specified.")

    filament = spool.filament
    if body.use_length is not None:
        density = _filament_density(filament)
        diameter = _filament_diameter(filament)
        delta_weight = _weight_from_length(body.use_length, density, diameter)
    else:
        delta_weight = body.use_weight or 0.0

    now = datetime.now(timezone.utc)
    spool.used_weight_g = float(min(spool.initial_weight_g, spool.used_weight_g + delta_weight))
    if spool.first_used_at is None:
        spool.first_used_at = now
    spool.last_used_at = now
    if spool.used_weight_g >= spool.initial_weight_g:
        spool.state = UserSpoolState.empty
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)

    await db.commit()
    updated = await _get_user_spool(db, user.id, spool.id)
    if updated is None:
        return _err(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to use spool.")
    location_map, gate_meta_map = await _build_location_map(db, user.id)
    payload = _to_spool_payload(updated, location_map, gate_meta_map)
    await _broadcast_spool_event(user.id, "updated", payload)
    return JSONResponse(content=payload)


@router.put("/{api_key}/v1/spool/{spool_id}/measure")
@router.put("/{api_key}/api/v1/spool/{spool_id}/measure")
async def measure_spool(
    api_key: str,
    spool_id: int,
    body: SpoolMeasureBody,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")

    spool = await _get_user_spool(db, user.id, spool_id)
    if spool is None:
        return _err(status.HTTP_404_NOT_FOUND, f"No spool with ID {spool_id} found.")

    filament = spool.filament
    tare = filament.empty_spool_weight_g if filament is not None and filament.empty_spool_weight_g else 0.0
    remaining_weight = max(body.weight - tare, 0.0)
    spool.used_weight_g = float(min(spool.initial_weight_g, max(spool.initial_weight_g - remaining_weight, 0.0)))
    now = datetime.now(timezone.utc)
    if spool.first_used_at is None:
        spool.first_used_at = now
    spool.last_used_at = now
    if spool.used_weight_g >= spool.initial_weight_g:
        spool.state = UserSpoolState.empty
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)

    await db.commit()
    updated = await _get_user_spool(db, user.id, spool.id)
    if updated is None:
        return _err(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update spool measurement.")
    location_map, gate_meta_map = await _build_location_map(db, user.id)
    payload = _to_spool_payload(updated, location_map, gate_meta_map)
    await _broadcast_spool_event(user.id, "updated", payload)
    return JSONResponse(content=payload)


@router.delete("/{api_key}/v1/spool/{spool_id}")
@router.delete("/{api_key}/api/v1/spool/{spool_id}")
async def delete_spool(
    api_key: str,
    spool_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")

    spool = await _get_user_spool(db, user.id, spool_id)
    if spool is None:
        return _err(status.HTTP_404_NOT_FOUND, f"No spool with ID {spool_id} found.")

    gate_states_result = await db.execute(
        select(PresetGateState).where(
            PresetGateState.user_id == user.id,
            PresetGateState.spool_id == spool.id,
        )
    )
    for gate_state in gate_states_result.scalars().all():
        gate_state.spool_id = None
        gate_state.source = PresetGateStateSource.web_manual
        gate_state.source_ts = datetime.now(timezone.utc)

    await db.delete(spool)
    await db.commit()
    await _broadcast_spool_event(user.id, "deleted", {"id": spool_id})
    return JSONResponse(content={"message": "Success!"})


def _vendor_payload(brand: Brand) -> dict:
    return {
        "id": brand.id,
        "registered": _iso(brand.created_at),
        "name": brand.name,
        "comment": brand.description,
        "empty_spool_weight": None,
        "external_id": None,
        "extra": {},
    }


async def _list_vendors_impl(
    db: AsyncSession,
    name: str | None,
) -> JSONResponse:
    stmt = select(Brand).where(Brand.active.is_(True)).order_by(Brand.name)
    result = await db.execute(stmt)
    brands = list(result.scalars().all())

    payloads = [_vendor_payload(b) for b in brands if _match_filter(b.name, name)]
    return JSONResponse(content=payloads)


@router.get("/v1/vendor")
async def list_vendors_with_header_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_api_key: Annotated[str | None, Query(alias="api_key")] = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    name: str | None = None,
) -> JSONResponse:
    api_key = x_api_key or header_api_key
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")
    return await _list_vendors_impl(db=db, name=name)


@router.get("/{api_key}/v1/vendor")
@router.get("/{api_key}/api/v1/vendor")
async def list_vendors(
    api_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str | None = None,
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")
    return await _list_vendors_impl(db=db, name=name)


async def _list_filaments_impl(
    db: AsyncSession,
    vendor_id: str | None,
    name: str | None,
    material: str | None,
) -> JSONResponse:
    stmt = (
        select(Filament)
        .options(joinedload(Filament.brand), selectinload(Filament.presets))
        .order_by(Filament.name)
    )
    result = await db.execute(stmt)
    filaments = list(result.unique().scalars().all())

    vendor_ids = _parse_int_list(vendor_id)

    payloads: list[dict] = []
    for f in filaments:
        if vendor_ids is not None and f.brand_id not in vendor_ids:
            continue
        if not _match_filter(f.name, name):
            continue
        if not _match_filter(f.material_type, material):
            continue
        payloads.append(_filament_payload(f, f.id))

    return JSONResponse(content=payloads)


@router.get("/v1/filament")
async def list_filaments_with_header_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_api_key: Annotated[str | None, Query(alias="api_key")] = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    vendor_id: Annotated[str | None, Query(alias="vendor.id")] = None,
    name: str | None = None,
    material: str | None = None,
) -> JSONResponse:
    api_key = x_api_key or header_api_key
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")
    return await _list_filaments_impl(db=db, vendor_id=vendor_id, name=name, material=material)


@router.get("/{api_key}/v1/filament")
@router.get("/{api_key}/api/v1/filament")
async def list_filaments(
    api_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    vendor_id: Annotated[str | None, Query(alias="vendor.id")] = None,
    name: str | None = None,
    material: str | None = None,
) -> JSONResponse:
    user, _device = await _resolve_user_and_device(db, api_key)
    if user is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")
    return await _list_filaments_impl(db=db, vendor_id=vendor_id, name=name, material=material)


router.include_router(spool_compat_fields.router)

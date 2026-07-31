"""Native OctoPrint Bridge adapter services.

The adapter translates OctoPrint-specific pairing and events into the existing
provider-neutral printer, material-system, slot and usage contracts. Nothing in
this module is required by Happy Hare, Bambu MQTT or another provider.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_MATERIAL_SLOT_NOT_FOUND,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_OCTOPRINT_BRIDGE_EVENT_CONFLICT,
    ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED,
    ERR_OCTOPRINT_BRIDGE_PAIRING_INVALID,
    ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED,
    ERR_OCTOPRINT_BRIDGE_WRONG_PROVIDER,
    raise_error,
)
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.octoprint_bridge import OctoPrintBridgeConnection, OctoPrintBridgeEvent
from app.models.preset_usage_event import PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.octoprint_bridge import (
    OctoPrintBridgeHeartbeatRequest,
    OctoPrintBridgePairRequest,
    OctoPrintBridgePairResponse,
    OctoPrintBridgePresetSnapshot,
    OctoPrintBridgeSlotSnapshot,
    OctoPrintBridgeSnapshotResponse,
    OctoPrintBridgeSpoolSnapshot,
    OctoPrintBridgeStatusResponse,
    OctoPrintBridgeUsageRequest,
    OctoPrintBridgeUsageResponse,
    OctoPrintPairingCodeResponse,
)
from app.services.material_contract_service import require_physical_printer
from app.services.spool_service import clear_spool_gate_assignments, clear_spool_location_projection
from app.services.spool_usage_service import record_spool_usage

OCTOPRINT_PROVIDER = "octoprint"
OCTOPRINT_TRANSPORT = "bridge_https"
PAIRING_TTL = timedelta(minutes=10)
DEFAULT_DENSITY_G_CM3 = 1.24
DEFAULT_DIAMETER_MM = 1.75
BRIDGE_CAPABILITIES = {
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
    "local_command",
}


@dataclass(frozen=True)
class OctoPrintBridgeContext:
    connection: OctoPrintBridgeConnection
    connector: PhysicalPrinterConnector


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_pairing_code(value: str) -> str:
    compact = "".join(character for character in value.upper() if character.isalnum())
    return compact[2:] if compact.startswith("FH") else compact


def _new_pairing_code() -> str:
    compact = secrets.token_hex(5).upper()
    return f"FH-{compact[:5]}-{compact[5:]}"


def _new_bridge_token() -> str:
    return f"fhb_{secrets.token_urlsafe(32)}"


def _safe_capabilities(values: list[str]) -> list[str]:
    return sorted(set(values).intersection(BRIDGE_CAPABILITIES))


async def _require_octoprint_system(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> MaterialSystem:
    await require_physical_printer(db, user_id, physical_printer_id)
    system = await db.scalar(
        select(MaterialSystem).where(
            MaterialSystem.id == material_system_id,
            MaterialSystem.user_id == user_id,
            MaterialSystem.physical_printer_id == physical_printer_id,
        )
    )
    if system is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)
    if system.provider != OCTOPRINT_PROVIDER:
        raise_error(409, ERR_OCTOPRINT_BRIDGE_WRONG_PROVIDER)
    return system


async def _find_connector(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> PhysicalPrinterConnector | None:
    return await db.scalar(
        select(PhysicalPrinterConnector)
        .where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
            PhysicalPrinterConnector.material_system_id == material_system_id,
            PhysicalPrinterConnector.provider == OCTOPRINT_PROVIDER,
            PhysicalPrinterConnector.transport == OCTOPRINT_TRANSPORT,
        )
        .order_by(PhysicalPrinterConnector.id.desc())
    )


async def issue_pairing_code(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> OctoPrintPairingCodeResponse:
    system = await _require_octoprint_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    connector = await _find_connector(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    if connector is None:
        connector = PhysicalPrinterConnector(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            material_system_id=material_system_id,
            provider=OCTOPRINT_PROVIDER,
            transport=OCTOPRINT_TRANSPORT,
            capabilities=list(system.capabilities),
            active=True,
        )
        db.add(connector)
        await db.flush()
    else:
        connector.material_system_id = material_system_id
        connector.active = True

    old_connectors = (
        await db.execute(
            select(PhysicalPrinterConnector).where(
                PhysicalPrinterConnector.user_id == user_id,
                PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
                PhysicalPrinterConnector.provider == OCTOPRINT_PROVIDER,
                PhysicalPrinterConnector.id != connector.id,
                PhysicalPrinterConnector.active.is_(True),
            )
        )
    ).scalars()
    for old_connector in old_connectors:
        old_connector.active = False

    connection = await db.scalar(
        select(OctoPrintBridgeConnection).where(
            OctoPrintBridgeConnection.connector_id == connector.id
        )
    )
    if connection is None:
        connection = OctoPrintBridgeConnection(connector_id=connector.id)
        db.add(connection)

    code = _new_pairing_code()
    expires_at = _now() + PAIRING_TTL
    connection.pairing_code_hash = _digest(_normalize_pairing_code(code))
    connection.pairing_expires_at = expires_at
    await db.commit()
    return OctoPrintPairingCodeResponse(pairing_code=code, expires_at=expires_at)


async def get_bridge_status(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> OctoPrintBridgeStatusResponse:
    await _require_octoprint_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    connector = await _find_connector(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    if connector is None:
        return OctoPrintBridgeStatusResponse(
            configured=False,
            paired=False,
            pairing_expires_at=None,
            last_seen_at=None,
            active_slot_index=None,
            instance_id=None,
            plugin_version=None,
            octoprint_version=None,
        )
    connection = await db.scalar(
        select(OctoPrintBridgeConnection).where(
            OctoPrintBridgeConnection.connector_id == connector.id
        )
    )
    if connection is None:
        return OctoPrintBridgeStatusResponse(
            configured=False,
            paired=False,
            pairing_expires_at=None,
            last_seen_at=connector.last_seen_at,
            active_slot_index=None,
            instance_id=None,
            plugin_version=None,
            octoprint_version=None,
        )
    return OctoPrintBridgeStatusResponse(
        configured=True,
        paired=connection.token_hash is not None and connection.revoked_at is None,
        pairing_expires_at=connection.pairing_expires_at,
        last_seen_at=connector.last_seen_at,
        active_slot_index=connection.active_slot_index,
        instance_id=connection.instance_id,
        plugin_version=connection.plugin_version,
        octoprint_version=connection.octoprint_version,
    )


async def revoke_bridge(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> None:
    await _require_octoprint_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    connector = await _find_connector(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    if connector is None:
        raise_error(404, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)
    connection = await db.scalar(
        select(OctoPrintBridgeConnection).where(
            OctoPrintBridgeConnection.connector_id == connector.id
        )
    )
    if connection is None:
        raise_error(404, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)
    connection.token_hash = None
    connection.pairing_code_hash = None
    connection.pairing_expires_at = None
    connection.revoked_at = _now()
    connector.active = False
    await db.commit()


async def pair_bridge(
    db: AsyncSession, payload: OctoPrintBridgePairRequest
) -> OctoPrintBridgePairResponse:
    normalized_code = _normalize_pairing_code(payload.pairing_code)
    connection = await db.scalar(
        select(OctoPrintBridgeConnection)
        .where(OctoPrintBridgeConnection.pairing_code_hash == _digest(normalized_code))
        .with_for_update()
    )
    if (
        connection is None
        or connection.pairing_expires_at is None
        or _as_utc(connection.pairing_expires_at) < _now()
    ):
        raise_error(401, ERR_OCTOPRINT_BRIDGE_PAIRING_INVALID)
    connector = await db.get(PhysicalPrinterConnector, connection.connector_id)
    if (
        connector is None
        or connector.provider != OCTOPRINT_PROVIDER
        or connector.transport != OCTOPRINT_TRANSPORT
    ):
        raise_error(401, ERR_OCTOPRINT_BRIDGE_PAIRING_INVALID)
    if connector.material_system_id is None:
        raise_error(409, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)

    token = _new_bridge_token()
    now = _now()
    connection.token_hash = _digest(token)
    connection.pairing_code_hash = None
    connection.pairing_expires_at = None
    connection.paired_at = now
    connection.revoked_at = None
    connection.instance_id = payload.instance_id
    connection.plugin_version = payload.plugin_version
    connection.octoprint_version = payload.octoprint_version
    connection.observed_at = now
    connector.capabilities = _safe_capabilities(payload.capabilities)
    connector.last_seen_at = now
    connector.active = True
    await db.commit()
    return OctoPrintBridgePairResponse(
        bridge_token=token,
        physical_printer_id=connector.physical_printer_id,
        material_system_id=connector.material_system_id,
    )


async def require_bridge_token(db: AsyncSession, token: str | None) -> OctoPrintBridgeContext:
    if token is None or not token.startswith("fhb_"):
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
    connection = await db.scalar(
        select(OctoPrintBridgeConnection).where(
            OctoPrintBridgeConnection.token_hash == _digest(token),
            OctoPrintBridgeConnection.revoked_at.is_(None),
        )
    )
    if connection is None:
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
    connector = await db.get(PhysicalPrinterConnector, connection.connector_id)
    if connector is None or not connector.active:
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
    return OctoPrintBridgeContext(connection=connection, connector=connector)


async def record_heartbeat(
    db: AsyncSession,
    context: OctoPrintBridgeContext,
    payload: OctoPrintBridgeHeartbeatRequest,
) -> OctoPrintBridgeStatusResponse:
    connector = context.connector
    connection = context.connection
    if connector.material_system_id is None:
        raise_error(409, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)
    if payload.active_slot_index is not None:
        slot_exists = await db.scalar(
            select(MaterialSlot.id).where(
                MaterialSlot.material_system_id == connector.material_system_id,
                MaterialSlot.provider_index == payload.active_slot_index,
            )
        )
        if slot_exists is None:
            raise_error(404, ERR_MATERIAL_SLOT_NOT_FOUND)

    now = _now()
    connection.instance_id = payload.instance_id
    connection.plugin_version = payload.plugin_version
    connection.octoprint_version = payload.octoprint_version
    connection.active_slot_index = payload.active_slot_index
    connection.observed_at = now
    connector.capabilities = _safe_capabilities(payload.capabilities)
    connector.last_seen_at = now
    connector.active = True
    await db.commit()
    return OctoPrintBridgeStatusResponse(
        configured=True,
        paired=True,
        pairing_expires_at=None,
        last_seen_at=connector.last_seen_at,
        active_slot_index=connection.active_slot_index,
        instance_id=connection.instance_id,
        plugin_version=connection.plugin_version,
        octoprint_version=connection.octoprint_version,
    )


async def build_snapshot(
    db: AsyncSession, context: OctoPrintBridgeContext
) -> OctoPrintBridgeSnapshotResponse:
    connector = context.connector
    if connector.material_system_id is None:
        raise_error(409, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)
    system = await db.scalar(
        select(MaterialSystem)
        .where(MaterialSystem.id == connector.material_system_id)
        .options(
            selectinload(MaterialSystem.slots)
            .selectinload(MaterialSlot.assignment)
            .selectinload(MaterialSlotAssignment.spool)
            .selectinload(UserSpool.filament)
            .selectinload(Filament.brand),
            selectinload(MaterialSystem.slots)
            .selectinload(MaterialSlot.assignment)
            .selectinload(MaterialSlotAssignment.preset),
        )
    )
    if system is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)

    slots: list[OctoPrintBridgeSlotSnapshot] = []
    for slot in sorted(system.slots, key=lambda item: (item.provider_index, item.id)):
        assignment = slot.assignment
        spool_snapshot = None
        preset_snapshot = None
        if assignment is not None and assignment.spool is not None:
            spool = assignment.spool
            filament = spool.filament
            spool_snapshot = OctoPrintBridgeSpoolSnapshot(
                id=spool.id,
                filament_id=spool.filament_id,
                name=filament.name if filament is not None else f"Spool #{spool.id}",
                brand=(
                    filament.brand.name
                    if filament is not None and filament.brand is not None
                    else None
                ),
                material_type=filament.material_type if filament is not None else None,
                color_hex=filament.color_hex if filament is not None else None,
                remaining_weight_g=spool.remaining_weight_g,
                initial_weight_g=spool.initial_weight_g,
                density_g_cm3=(
                    filament.density
                    if filament is not None and filament.density and filament.density > 0
                    else DEFAULT_DENSITY_G_CM3
                ),
                diameter_mm=(
                    filament.diameter
                    if filament is not None and filament.diameter and filament.diameter > 0
                    else DEFAULT_DIAMETER_MM
                ),
            )
        if assignment is not None and assignment.preset is not None:
            preset_snapshot = OctoPrintBridgePresetSnapshot(
                id=assignment.preset.id,
                name=assignment.preset.name,
            )
        slots.append(
            OctoPrintBridgeSlotSnapshot(
                index=slot.provider_index,
                label=slot.label,
                kind=slot.kind,
                spool=spool_snapshot,
                preset=preset_snapshot,
            )
        )

    revision_payload = {
        "physical_printer_id": connector.physical_printer_id,
        "material_system_id": system.id,
        "system_name": system.name,
        "system_kind": system.kind,
        "slots": [slot.model_dump(mode="json") for slot in slots],
    }
    revision = hashlib.sha256(
        json.dumps(
            revision_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    context.connector.last_seen_at = _now()
    context.connection.observed_at = context.connector.last_seen_at
    await db.commit()
    return OctoPrintBridgeSnapshotResponse(revision=revision, **revision_payload)


def _weight_from_length(length_mm: float, density: float, diameter_mm: float) -> float:
    radius = diameter_mm / 2.0
    return max(length_mm * math.pi * radius * radius / 1000.0 * density, 0.0)


def _usage_payload_hash(payload: OctoPrintBridgeUsageRequest) -> str:
    return hashlib.sha256(
        json.dumps(
            payload.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


async def record_usage_event(
    db: AsyncSession,
    context: OctoPrintBridgeContext,
    payload: OctoPrintBridgeUsageRequest,
) -> OctoPrintBridgeUsageResponse:
    connector = context.connector
    # Serialize terminal events per Bridge connection. This closes the replay
    # race even when two conflicting retries mention different spools and would
    # therefore not contend on the same inventory rows.
    connection = await db.scalar(
        select(OctoPrintBridgeConnection)
        .where(OctoPrintBridgeConnection.id == context.connection.id)
        .with_for_update()
    )
    if connection is None:
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
    if connector.material_system_id is None:
        raise_error(409, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)

    payload_hash = _usage_payload_hash(payload)
    existing = await db.scalar(
        select(OctoPrintBridgeEvent).where(
            OctoPrintBridgeEvent.connection_id == connection.id,
            OctoPrintBridgeEvent.event_id == payload.event_id,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise_error(409, ERR_OCTOPRINT_BRIDGE_EVENT_CONFLICT)
        return OctoPrintBridgeUsageResponse(
            accepted=True,
            deduplicated=True,
            consumed_weight_g=existing.consumed_weight_g,
        )

    valid_slot_indices = set(
        (
            await db.execute(
                select(MaterialSlot.provider_index).where(
                    MaterialSlot.material_system_id == connector.material_system_id
                )
            )
        ).scalars()
    )
    if any(item.slot_index not in valid_slot_indices for item in payload.items):
        raise_error(404, ERR_MATERIAL_SLOT_NOT_FOUND)

    spool_ids = {item.spool_id for item in payload.items}
    spools = list(
        (
            await db.execute(
                select(UserSpool)
                .where(UserSpool.id.in_(spool_ids), UserSpool.user_id == connector.user_id)
                .options(selectinload(UserSpool.filament))
                .with_for_update()
            )
        ).scalars()
    )
    spools_by_id = {spool.id: spool for spool in spools}
    if set(spools_by_id) != spool_ids:
        raise_error(404, ERR_ACCESS_DENIED)

    now = _now()
    total_consumed = 0.0
    for item in payload.items:
        spool = spools_by_id[item.spool_id]
        filament = spool.filament
        density = (
            filament.density
            if filament is not None and filament.density and filament.density > 0
            else DEFAULT_DENSITY_G_CM3
        )
        diameter = (
            filament.diameter
            if filament is not None and filament.diameter and filament.diameter > 0
            else DEFAULT_DIAMETER_MM
        )
        reported_weight = (
            item.used_weight_g
            if item.used_weight_g is not None
            else _weight_from_length(item.used_length_mm or 0.0, density, diameter)
        )
        before = spool.used_weight_g
        spool.used_weight_g = min(spool.initial_weight_g, before + reported_weight)
        consumed = spool.used_weight_g - before
        total_consumed += consumed
        spool.last_used_at = now
        if spool.first_used_at is None:
            spool.first_used_at = now
        await record_spool_usage(
            db,
            spool=spool,
            event_type=PresetUsageEventType.printer_report,
            delta_weight_g=consumed,
            device_id=connector.physical_printer_id,
            job_ref=f"octoprint_bridge:{payload.event_id}:{spool.id}",
            reported_weight_g=reported_weight,
            meta={
                "adapter": OCTOPRINT_PROVIDER,
                "job_id": payload.job_id,
                "outcome": payload.outcome,
                "slot_index": item.slot_index,
                "file_name": payload.file_name,
                "duration_s": payload.duration_s,
                "used_length_mm": item.used_length_mm,
            },
        )
        if spool.remaining_weight_g <= 0:
            spool.state = UserSpoolState.empty
            await clear_spool_gate_assignments(db, spool)
            clear_spool_location_projection(spool)

    db.add(
        OctoPrintBridgeEvent(
            connection_id=connection.id,
            event_id=payload.event_id,
            payload_hash=payload_hash,
            consumed_weight_g=total_consumed,
        )
    )
    connector.last_seen_at = now
    connection.observed_at = now
    await db.commit()
    return OctoPrintBridgeUsageResponse(
        accepted=True,
        deduplicated=False,
        consumed_weight_g=total_consumed,
    )

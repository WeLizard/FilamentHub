"""Native OctoPrint Bridge adapter services.

The adapter translates OctoPrint-specific pairing and events into the existing
provider-neutral printer, material-system, slot and usage contracts. Nothing in
this module is required by Happy Hare, Bambu MQTT or another provider.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_MATERIAL_SLOT_NOT_FOUND,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_OCTOPRINT_BRIDGE_EVENT_CONFLICT,
    ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED,
    ERR_OCTOPRINT_BRIDGE_PAIRING_INVALID,
    ERR_OCTOPRINT_BRIDGE_ROUTING_CONFLICT,
    ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED,
    ERR_OCTOPRINT_BRIDGE_WRONG_PROVIDER,
    raise_error,
)
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.octoprint_bridge import OctoPrintBridgeConnection
from app.models.preset_gate_state import PresetGateStateSource
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.material_contract import MaterialSlotAssignmentUpdate
from app.schemas.octoprint_bridge import (
    OctoPrintBridgeHeartbeatRequest,
    OctoPrintBridgePairRequest,
    OctoPrintBridgePairResponse,
    OctoPrintBridgeRoutingState,
    OctoPrintBridgeRoutingUpdateRequest,
    OctoPrintBridgeSnapshotResponse,
    OctoPrintBridgeSpoolAssignmentRequest,
    OctoPrintBridgeSpoolLocation,
    OctoPrintBridgeSpoolOption,
    OctoPrintBridgeSpoolOptionsResponse,
    OctoPrintBridgeStatusResponse,
    OctoPrintBridgeUsageRequest,
    OctoPrintBridgeUsageResponse,
    OctoPrintPairingCodeResponse,
)
from app.services.material_assignment_service import update_material_slot_assignment
from app.services.material_contract_service import (
    build_printer_bridge_desired_snapshot,
    require_physical_printer,
)
from app.services.printer_usage_service import process_printer_usage_event

OCTOPRINT_PROVIDER = "octoprint"
OCTOPRINT_TRANSPORT = "bridge_https"
PAIRING_TTL = timedelta(minutes=10)
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


async def _record_capabilities(
    db: AsyncSession,
    *,
    connector: PhysicalPrinterConnector,
    reported: list[str],
) -> None:
    """Keep the OctoPrint system aligned with the live bridge contract."""
    capabilities = _safe_capabilities(reported)
    connector.capabilities = capabilities
    if connector.material_system_id is None:
        return
    system = await db.get(MaterialSystem, connector.material_system_id)
    if system is not None and system.provider == OCTOPRINT_PROVIDER:
        system.capabilities = list(capabilities)


def _normalized_tool_slot_map(values: list | None) -> list[dict[str, int]]:
    normalized: dict[int, int] = {}
    for value in values or []:
        if hasattr(value, "tool_index") and hasattr(value, "slot_index"):
            tool_index = int(value.tool_index)
            slot_index = int(value.slot_index)
        elif isinstance(value, dict):
            try:
                tool_index = int(value["tool_index"])
                slot_index = int(value["slot_index"])
            except (KeyError, TypeError, ValueError):
                continue
        else:
            continue
        if 0 <= tool_index <= 1023 and 0 <= slot_index <= 1023:
            normalized[tool_index] = slot_index
    return [
        {"tool_index": tool_index, "slot_index": normalized[tool_index]}
        for tool_index in sorted(normalized)
    ]


def _routing_state(connection: OctoPrintBridgeConnection) -> OctoPrintBridgeRoutingState:
    mode = connection.desired_routing_mode
    return OctoPrintBridgeRoutingState(
        mode=mode if mode in {"manual", "tools"} else "manual",
        tool_slot_map=_normalized_tool_slot_map(connection.desired_tool_slot_map),
        revision=max(int(connection.routing_revision or 0), 0),
        applied_revision=connection.applied_routing_revision,
    )


def _routing_matches(
    connection: OctoPrintBridgeConnection,
    *,
    mode: str,
    mapping: list,
) -> bool:
    state = _routing_state(connection)
    return state.mode == mode and [item.model_dump() for item in state.tool_slot_map] == (
        _normalized_tool_slot_map(mapping)
    )


async def _missing_routing_slots(
    db: AsyncSession,
    *,
    material_system_id: int,
    mapping: list,
) -> set[int]:
    requested = {item["slot_index"] for item in _normalized_tool_slot_map(mapping)}
    if not requested:
        return set()
    existing = set(
        (
            await db.scalars(
                select(MaterialSlot.provider_index).where(
                    MaterialSlot.material_system_id == material_system_id,
                    MaterialSlot.provider_index.in_(requested),
                )
            )
        ).all()
    )
    return requested - existing


async def _validate_routing_slots(
    db: AsyncSession,
    *,
    material_system_id: int,
    mapping: list,
) -> None:
    if await _missing_routing_slots(
        db,
        material_system_id=material_system_id,
        mapping=mapping,
    ):
        raise_error(404, ERR_MATERIAL_SLOT_NOT_FOUND)


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
            routing=OctoPrintBridgeRoutingState(
                mode="manual",
                tool_slot_map=[],
                revision=0,
                applied_revision=None,
            ),
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
            routing=OctoPrintBridgeRoutingState(
                mode="manual",
                tool_slot_map=[],
                revision=0,
                applied_revision=None,
            ),
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
        routing=_routing_state(connection),
    )


async def _update_routing_configuration(
    db: AsyncSession,
    *,
    connection_id: int,
    material_system_id: int,
    payload: OctoPrintBridgeRoutingUpdateRequest,
) -> OctoPrintBridgeRoutingState:
    connection = await db.scalar(
        select(OctoPrintBridgeConnection)
        .where(OctoPrintBridgeConnection.id == connection_id)
        .with_for_update()
    )
    if connection is None:
        raise_error(404, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)

    mapping = _normalized_tool_slot_map(payload.tool_slot_map)
    if _routing_matches(connection, mode=payload.mode, mapping=mapping):
        return _routing_state(connection)
    if connection.routing_revision != payload.expected_revision:
        raise_error(
            409,
            ERR_OCTOPRINT_BRIDGE_ROUTING_CONFLICT,
            params={"current_revision": connection.routing_revision},
        )

    await _validate_routing_slots(
        db,
        material_system_id=material_system_id,
        mapping=mapping,
    )
    connection.desired_routing_mode = payload.mode
    connection.desired_tool_slot_map = mapping
    connection.routing_revision += 1
    await db.commit()
    return _routing_state(connection)


async def update_user_routing_configuration(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    payload: OctoPrintBridgeRoutingUpdateRequest,
) -> OctoPrintBridgeRoutingState:
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
    return await _update_routing_configuration(
        db,
        connection_id=connection.id,
        material_system_id=material_system_id,
        payload=payload,
    )


async def update_bridge_routing_configuration(
    db: AsyncSession,
    *,
    context: OctoPrintBridgeContext,
    payload: OctoPrintBridgeRoutingUpdateRequest,
) -> OctoPrintBridgeRoutingState:
    material_system_id = context.connector.material_system_id
    if material_system_id is None:
        raise_error(409, ERR_OCTOPRINT_BRIDGE_NOT_CONFIGURED)
    return await _update_routing_configuration(
        db,
        connection_id=context.connection.id,
        material_system_id=material_system_id,
        payload=payload,
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
    await revoke_bridge_context(
        db,
        OctoPrintBridgeContext(connection=connection, connector=connector),
    )


async def revoke_bridge_context(
    db: AsyncSession,
    context: OctoPrintBridgeContext,
) -> None:
    connection = context.connection
    connector = context.connector
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
    await _record_capabilities(db, connector=connector, reported=payload.capabilities)
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
    connection = await db.scalar(
        select(OctoPrintBridgeConnection)
        .where(OctoPrintBridgeConnection.id == context.connection.id)
        .with_for_update()
    )
    if connection is None:
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
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

    if payload.routing_mode is not None and payload.tool_slot_map is not None:
        reported_mapping = _normalized_tool_slot_map(payload.tool_slot_map)
        initialized_from_bridge = False
        if connection.routing_revision == 0:
            if await _missing_routing_slots(
                db,
                material_system_id=connector.material_system_id,
                mapping=reported_mapping,
            ):
                # A pre-contract local mapping can refer to a slot that no longer
                # exists. Do not let that stale upgrade state break all future
                # heartbeats; initialize a safe manual configuration instead.
                connection.desired_routing_mode = "manual"
                connection.desired_tool_slot_map = []
            else:
                connection.desired_routing_mode = payload.routing_mode
                connection.desired_tool_slot_map = reported_mapping
            connection.routing_revision = 1
            initialized_from_bridge = True

        reported_revision = int(payload.routing_revision or 0)
        if (
            initialized_from_bridge or reported_revision == connection.routing_revision
        ) and _routing_matches(
            connection,
            mode=payload.routing_mode,
            mapping=reported_mapping,
        ):
            connection.applied_routing_revision = (
                connection.routing_revision if initialized_from_bridge else reported_revision
            )
        elif reported_revision < connection.routing_revision:
            connection.applied_routing_revision = reported_revision
        else:
            connection.applied_routing_revision = None

    now = _now()
    connection.instance_id = payload.instance_id
    connection.plugin_version = payload.plugin_version
    connection.octoprint_version = payload.octoprint_version
    connection.active_slot_index = payload.active_slot_index
    connection.observed_at = now
    await _record_capabilities(db, connector=connector, reported=payload.capabilities)
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
        routing=_routing_state(connection),
    )


async def build_snapshot(
    db: AsyncSession, context: OctoPrintBridgeContext
) -> OctoPrintBridgeSnapshotResponse:
    snapshot = await build_printer_bridge_desired_snapshot(db, context.connector)
    return OctoPrintBridgeSnapshotResponse.model_validate(snapshot.model_dump())


async def list_bridge_spool_options(
    db: AsyncSession,
    context: OctoPrintBridgeContext,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> OctoPrintBridgeSpoolOptionsResponse:
    """Return a bounded, tenant-scoped picker page for an adapter UI."""
    user_id = context.connector.user_id
    statement = (
        select(UserSpool)
        .outerjoin(Filament, Filament.id == UserSpool.filament_id)
        .outerjoin(Brand, Brand.id == Filament.brand_id)
        .where(
            UserSpool.user_id == user_id,
            UserSpool.state.not_in({UserSpoolState.archived, UserSpoolState.empty}),
            UserSpool.used_weight_g < UserSpool.initial_weight_g,
        )
        .options(selectinload(UserSpool.filament).selectinload(Filament.brand))
    )
    normalized_query = (query or "").strip()
    if normalized_query:
        escaped = normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                cast(UserSpool.id, String).ilike(pattern, escape="\\"),
                Filament.name.ilike(pattern, escape="\\"),
                Filament.material_type.ilike(pattern, escape="\\"),
                Filament.color_name.ilike(pattern, escape="\\"),
                Brand.name.ilike(pattern, escape="\\"),
            )
        )
    spools = list(
        (
            await db.scalars(
                statement.order_by(UserSpool.updated_at.desc(), UserSpool.id.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        ).unique()
    )
    has_more = len(spools) > limit
    page = spools[:limit]

    locations: dict[int, MaterialSlotAssignment] = {}
    spool_ids = [spool.id for spool in page]
    if spool_ids:
        assignments = (
            await db.scalars(
                select(MaterialSlotAssignment)
                .where(MaterialSlotAssignment.spool_id.in_(spool_ids))
                .options(
                    selectinload(MaterialSlotAssignment.material_slot)
                    .selectinload(MaterialSlot.material_system)
                    .selectinload(MaterialSystem.physical_printer)
                )
            )
        ).all()
        locations = {
            assignment.spool_id: assignment
            for assignment in assignments
            if assignment.spool_id is not None
        }

    items: list[OctoPrintBridgeSpoolOption] = []
    for spool in page:
        filament = spool.filament
        assignment = locations.get(spool.id)
        location = None
        if assignment is not None:
            slot = assignment.material_slot
            system = slot.material_system
            location = OctoPrintBridgeSpoolLocation(
                material_slot_id=slot.id,
                slot_index=slot.provider_index,
                slot_label=slot.label,
                system_name=system.name,
                printer_name=system.physical_printer.name,
            )
        items.append(
            OctoPrintBridgeSpoolOption(
                id=spool.id,
                name=filament.name if filament is not None else f"Spool #{spool.id}",
                brand=(
                    filament.brand.name
                    if filament is not None and filament.brand is not None
                    else None
                ),
                material_type=filament.material_type if filament is not None else None,
                color_hex=filament.color_hex if filament is not None else None,
                remaining_weight_g=spool.remaining_weight_g,
                location=location,
            )
        )
    return OctoPrintBridgeSpoolOptionsResponse(
        items=items,
        next_offset=offset + limit if has_more else None,
    )


async def update_bridge_spool_assignment(
    db: AsyncSession,
    context: OctoPrintBridgeContext,
    *,
    material_slot_id: int,
    payload: OctoPrintBridgeSpoolAssignmentRequest,
) -> OctoPrintBridgeSnapshotResponse:
    """Apply an explicit adapter-UI command through the canonical writer."""
    user = await db.get(User, context.connector.user_id)
    if user is None:
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
    await update_material_slot_assignment(
        db,
        user,
        physical_printer_id=context.connector.physical_printer_id,
        material_slot_id=material_slot_id,
        payload=MaterialSlotAssignmentUpdate(
            expected_revision=payload.expected_revision,
            expected_spool_id=payload.expected_spool_id,
            spool_id=payload.spool_id,
        ),
        source=PresetGateStateSource.web_manual,
    )
    return await build_snapshot(db, context)


async def record_usage_event(
    db: AsyncSession,
    context: OctoPrintBridgeContext,
    payload: OctoPrintBridgeUsageRequest,
) -> OctoPrintBridgeUsageResponse:
    connector = context.connector
    # Serialize usage events per Bridge connection. This closes the replay
    # race even when two conflicting retries mention different spools and would
    # therefore not contend on the same inventory rows.
    connection = await db.scalar(
        select(OctoPrintBridgeConnection)
        .where(OctoPrintBridgeConnection.id == context.connection.id)
        .with_for_update()
    )
    if connection is None:
        raise_error(401, ERR_OCTOPRINT_BRIDGE_UNAUTHORIZED)
    source_instance_id = connection.instance_id or f"octoprint-connection-{connection.id}"
    result = await process_printer_usage_event(
        db,
        connector=connector,
        source_instance_id=source_instance_id,
        payload=payload,
        print_job_source=OCTOPRINT_PROVIDER,
        print_job_source_ref=f"{connection.id}:{payload.job_id}",
        adapter=OCTOPRINT_PROVIDER,
        conflict_error=ERR_OCTOPRINT_BRIDGE_EVENT_CONFLICT,
    )
    connector.last_seen_at = _now()
    connection.observed_at = connector.last_seen_at
    await db.commit()
    return OctoPrintBridgeUsageResponse(
        accepted=True,
        deduplicated=result.deduplicated,
        consumed_weight_g=result.consumed_weight_g,
    )

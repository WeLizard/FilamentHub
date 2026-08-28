"""Pairing and narrow authorization for local printer bridge adapters."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_PRINTER_BRIDGE_BATCH_CONFLICT,
    ERR_PRINTER_BRIDGE_BATCH_OUT_OF_ORDER,
    ERR_PRINTER_BRIDGE_CAPABILITY_REQUIRED,
    ERR_PRINTER_BRIDGE_NOT_CONFIGURED,
    ERR_PRINTER_BRIDGE_PAIRING_INVALID,
    ERR_PRINTER_BRIDGE_UNAUTHORIZED,
    ERR_PRINTER_BRIDGE_WRONG_PROVIDER,
    raise_error,
)
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.printer_bridge_credential import PrinterBridgeCredential
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.schemas.printer_bridge import (
    PrinterBridgeHeartbeatRequest,
    PrinterBridgeHeartbeatResponse,
    PrinterBridgePairingCodeResponse,
    PrinterBridgePairRequest,
    PrinterBridgePairResponse,
    PrinterBridgeStatusResponse,
    PrinterBridgeTransport,
    PrinterBridgeUsageBatchRequest,
    PrinterBridgeUsageBatchResponse,
)
from app.schemas.printer_usage import PrinterUsageEventResult
from app.services.material_contract_service import require_physical_printer
from app.services.printer_usage_service import process_printer_usage_event

PAIRING_TTL = timedelta(minutes=10)
BAMBU_PROVIDER = "bambu"
BAMBU_TRANSPORT: PrinterBridgeTransport = "orca_plugin_lan"
EDGE_TRANSPORT: PrinterBridgeTransport = "edge_agent"
SUPPORTED_TRANSPORTS = {BAMBU_TRANSPORT, EDGE_TRANSPORT}
BRIDGE_CAPABILITIES = {
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
    "local_command",
}
BATCH_RECEIPT_KIND = "usage_batch"
PRINT_JOB_SOURCE = "printer_bridge"


@dataclass(frozen=True)
class PrinterBridgeContext:
    credential: PrinterBridgeCredential
    connector: PhysicalPrinterConnector


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _print_job_source_ref(connector_id: int, job_id: str) -> str:
    source_ref = f"{connector_id}:{job_id}"
    if len(source_ref) <= 200:
        return source_ref
    return f"{connector_id}:sha256:{_digest(job_id)}"


def _normalize_pairing_code(value: str) -> str:
    compact = "".join(character for character in value.upper() if character.isalnum())
    return compact[2:] if compact.startswith("FH") else compact


def _new_pairing_code() -> str:
    compact = secrets.token_hex(5).upper()
    return f"FH-{compact[:5]}-{compact[5:]}"


def _new_bridge_token() -> str:
    return f"fhpb_{secrets.token_urlsafe(32)}"


def _safe_capabilities(values: list[str]) -> list[str]:
    return sorted(set(values).intersection(BRIDGE_CAPABILITIES))


async def _require_bridge_system(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    transport: PrinterBridgeTransport,
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
    if transport == BAMBU_TRANSPORT and system.provider != BAMBU_PROVIDER:
        raise_error(409, ERR_PRINTER_BRIDGE_WRONG_PROVIDER)
    return system


async def _find_bridge_connector(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    provider: str,
    transport: PrinterBridgeTransport,
) -> PhysicalPrinterConnector | None:
    return await db.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
            PhysicalPrinterConnector.material_system_id == material_system_id,
            PhysicalPrinterConnector.provider == provider,
            PhysicalPrinterConnector.transport == transport,
        )
    )


async def issue_printer_bridge_pairing_code(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    transport: PrinterBridgeTransport = BAMBU_TRANSPORT,
) -> PrinterBridgePairingCodeResponse:
    system = await _require_bridge_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        transport=transport,
    )
    connector = await _find_bridge_connector(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        provider=system.provider,
        transport=transport,
    )
    if connector is None:
        connector = PhysicalPrinterConnector(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            material_system_id=material_system_id,
            provider=system.provider,
            transport=transport,
            capabilities=_safe_capabilities(system.capabilities),
            active=True,
        )
        db.add(connector)
        await db.flush()
    else:
        connector.active = True

    credential = await db.scalar(
        select(PrinterBridgeCredential).where(
            PrinterBridgeCredential.connector_id == connector.id
        )
    )
    if credential is None:
        credential = PrinterBridgeCredential(connector_id=connector.id)
        db.add(credential)

    code = _new_pairing_code()
    expires_at = _now() + PAIRING_TTL
    credential.pairing_code_hash = _digest(_normalize_pairing_code(code))
    credential.pairing_expires_at = expires_at
    # Issuing a replacement code must not disconnect an already running bridge.
    await db.commit()
    return PrinterBridgePairingCodeResponse(pairing_code=code, expires_at=expires_at)


async def get_printer_bridge_status(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
    transport: PrinterBridgeTransport = BAMBU_TRANSPORT,
) -> PrinterBridgeStatusResponse:
    system = await _require_bridge_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        transport=transport,
    )
    connector = await _find_bridge_connector(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        provider=system.provider,
        transport=transport,
    )
    if connector is None:
        return PrinterBridgeStatusResponse(
            configured=False,
            paired=False,
            pairing_expires_at=None,
            last_seen_at=None,
            last_observation_at=None,
            last_snapshot_sequence=None,
            last_snapshot_source_instance_id=None,
            source_instance_id=None,
            provider=system.provider,
            transport=transport,
            capabilities=[],
        )
    credential = await db.scalar(
        select(PrinterBridgeCredential).where(
            PrinterBridgeCredential.connector_id == connector.id
        )
    )
    return PrinterBridgeStatusResponse(
        configured=credential is not None,
        paired=(
            credential is not None
            and credential.token_hash is not None
            and credential.revoked_at is None
        ),
        pairing_expires_at=credential.pairing_expires_at if credential else None,
        last_seen_at=connector.last_seen_at,
        last_observation_at=connector.last_observation_at,
        last_snapshot_sequence=connector.last_snapshot_sequence,
        last_snapshot_source_instance_id=connector.last_snapshot_source_instance_id,
        source_instance_id=connector.source_instance_id,
        provider=connector.provider,
        transport=transport,
        capabilities=list(connector.capabilities),
    )


async def pair_printer_bridge(
    db: AsyncSession, payload: PrinterBridgePairRequest
) -> PrinterBridgePairResponse:
    normalized_code = _normalize_pairing_code(payload.pairing_code)
    credential = await db.scalar(
        select(PrinterBridgeCredential)
        .where(PrinterBridgeCredential.pairing_code_hash == _digest(normalized_code))
        .with_for_update()
    )
    if (
        credential is None
        or credential.pairing_expires_at is None
        or _as_utc(credential.pairing_expires_at) < _now()
    ):
        raise_error(401, ERR_PRINTER_BRIDGE_PAIRING_INVALID)
    connector = await db.get(PhysicalPrinterConnector, credential.connector_id)
    if (
        connector is None
        or connector.provider != payload.provider
        or connector.transport != payload.transport
        or connector.material_system_id is None
    ):
        raise_error(401, ERR_PRINTER_BRIDGE_PAIRING_INVALID)

    token = _new_bridge_token()
    now = _now()
    credential.token_hash = _digest(token)
    credential.pairing_code_hash = None
    credential.pairing_expires_at = None
    credential.paired_at = now
    credential.revoked_at = None
    credential.source_instance_id = payload.source_instance_id
    credential.plugin_version = payload.plugin_version
    connector.source_instance_id = payload.source_instance_id
    connector.capabilities = _safe_capabilities(payload.capabilities)
    connector.active = True
    system = await db.get(MaterialSystem, connector.material_system_id)
    if system is not None:
        system.capabilities = list(connector.capabilities)
    await db.commit()
    return PrinterBridgePairResponse(
        bridge_token=token,
        physical_printer_id=connector.physical_printer_id,
        material_system_id=connector.material_system_id,
    )


async def require_printer_bridge_token(
    db: AsyncSession, token: str | None
) -> PrinterBridgeContext:
    if token is None or not token.startswith("fhpb_"):
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)
    credential = await db.scalar(
        select(PrinterBridgeCredential).where(
            PrinterBridgeCredential.token_hash == _digest(token),
            PrinterBridgeCredential.revoked_at.is_(None),
        )
    )
    if credential is None:
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)
    connector = await db.get(PhysicalPrinterConnector, credential.connector_id)
    if (
        connector is None
        or not connector.active
        or connector.transport not in SUPPORTED_TRANSPORTS
        or connector.material_system_id is None
    ):
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)
    return PrinterBridgeContext(credential=credential, connector=connector)


async def record_printer_bridge_usage_batch(
    db: AsyncSession,
    context: PrinterBridgeContext,
    payload: PrinterBridgeUsageBatchRequest,
) -> PrinterBridgeUsageBatchResponse:
    """Atomically apply one ordered Edge batch and return its durable ACK."""
    connector = await db.scalar(
        select(PhysicalPrinterConnector)
        .where(PhysicalPrinterConnector.id == context.connector.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if connector is None or connector.source_instance_id != payload.source_instance_id:
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)

    receipt_id = str(payload.sequence)
    payload_hash = _payload_digest(payload.model_dump(mode="json"))
    existing = await db.scalar(
        select(PrinterBridgeReceipt).where(
            PrinterBridgeReceipt.connector_id == connector.id,
            PrinterBridgeReceipt.source_instance_id == payload.source_instance_id,
            PrinterBridgeReceipt.receipt_kind == BATCH_RECEIPT_KIND,
            PrinterBridgeReceipt.receipt_id == receipt_id,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash or existing.response_payload is None:
            raise_error(409, ERR_PRINTER_BRIDGE_BATCH_CONFLICT)
        response = PrinterBridgeUsageBatchResponse.model_validate(existing.response_payload)
        connector.last_seen_at = _now()
        await db.commit()
        return response.model_copy(update={"deduplicated": True})

    if "consumption" not in connector.capabilities:
        raise_error(
            409,
            ERR_PRINTER_BRIDGE_CAPABILITY_REQUIRED,
            {"capability": "consumption"},
        )

    last_sequence = await db.scalar(
        select(func.max(PrinterBridgeReceipt.sequence)).where(
            PrinterBridgeReceipt.connector_id == connector.id,
            PrinterBridgeReceipt.source_instance_id == payload.source_instance_id,
            PrinterBridgeReceipt.receipt_kind == BATCH_RECEIPT_KIND,
        )
    )
    expected_sequence = int(last_sequence or 0) + 1
    if payload.sequence != expected_sequence:
        raise_error(
            409,
            ERR_PRINTER_BRIDGE_BATCH_OUT_OF_ORDER,
            {"expected_sequence": expected_sequence},
        )

    event_results: list[PrinterUsageEventResult] = []
    adapter = f"{connector.provider}_{connector.transport}"
    try:
        for event in payload.events:
            result = await process_printer_usage_event(
                db,
                connector=connector,
                source_instance_id=payload.source_instance_id,
                payload=event,
                print_job_source=PRINT_JOB_SOURCE,
                print_job_source_ref=_print_job_source_ref(connector.id, event.job_id),
                adapter=adapter,
            )
            event_results.append(
                PrinterUsageEventResult(
                    event_id=result.event_id,
                    deduplicated=result.deduplicated,
                    consumed_weight_g=result.consumed_weight_g,
                )
            )
    except Exception:
        # A batch ACK is all-or-nothing. In particular, a valid first event
        # must not leak a spool mutation when a later event is rejected.
        await db.rollback()
        raise

    response = PrinterBridgeUsageBatchResponse(
        accepted=True,
        deduplicated=False,
        ack_sequence=payload.sequence,
        events=event_results,
    )
    db.add(
        PrinterBridgeReceipt(
            connector_id=connector.id,
            source_instance_id=payload.source_instance_id,
            receipt_kind=BATCH_RECEIPT_KIND,
            receipt_id=receipt_id,
            sequence=payload.sequence,
            payload_hash=payload_hash,
            consumed_weight_g=sum(item.consumed_weight_g for item in event_results),
            response_payload=response.model_dump(mode="json"),
        )
    )
    connector.last_seen_at = _now()
    await db.commit()
    return response


async def revoke_printer_bridge(
    db: AsyncSession,
    context: PrinterBridgeContext,
) -> None:
    context.credential.token_hash = None
    context.credential.pairing_code_hash = None
    context.credential.pairing_expires_at = None
    context.credential.revoked_at = _now()
    context.connector.active = False
    await db.commit()


def validate_snapshot_context(
    context: PrinterBridgeContext,
    *,
    material_system_id: int,
    source_instance_id: str,
    provider: str,
    transport: PrinterBridgeTransport,
) -> None:
    connector = context.connector
    if (
        connector.material_system_id != material_system_id
        or connector.provider != provider
        or connector.transport != transport
        or connector.source_instance_id != source_instance_id
        or context.credential.source_instance_id != source_instance_id
    ):
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)


def require_configured_system_id(context: PrinterBridgeContext) -> int:
    material_system_id = context.connector.material_system_id
    if material_system_id is None:
        raise_error(409, ERR_PRINTER_BRIDGE_NOT_CONFIGURED)
    return material_system_id


async def record_printer_bridge_heartbeat(
    db: AsyncSession,
    context: PrinterBridgeContext,
    payload: PrinterBridgeHeartbeatRequest,
) -> PrinterBridgeHeartbeatResponse:
    """Record connector liveness without inventing a printer observation."""
    validate_snapshot_context(
        context,
        material_system_id=payload.material_system_id,
        source_instance_id=payload.source_instance_id,
        provider=payload.provider,
        transport=payload.transport,
    )
    received_at = _now()
    printer = await require_physical_printer(
        db,
        context.connector.user_id,
        context.connector.physical_printer_id,
    )
    # Liveness means that this server has just received an authenticated
    # request. A workstation clock may be wrong by hours or years, so the
    # client-supplied observed_at must not make a live adapter look stale.
    context.connector.last_seen_at = received_at
    context.connector.active = True
    if payload.capabilities is not None:
        context.connector.capabilities = _safe_capabilities(payload.capabilities)
        system = await db.get(MaterialSystem, payload.material_system_id)
        if system is not None:
            system.capabilities = list(context.connector.capabilities)
    printer.last_seen_at = received_at
    printer.reports_feed = True
    await db.commit()
    return PrinterBridgeHeartbeatResponse(
        accepted=True,
        last_seen_at=received_at,
    )

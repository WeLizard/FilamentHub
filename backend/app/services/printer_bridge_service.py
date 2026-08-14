"""Pairing and narrow authorization for local printer bridge adapters."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_PRINTER_BRIDGE_NOT_CONFIGURED,
    ERR_PRINTER_BRIDGE_PAIRING_INVALID,
    ERR_PRINTER_BRIDGE_UNAUTHORIZED,
    ERR_PRINTER_BRIDGE_WRONG_PROVIDER,
    raise_error,
)
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.printer_bridge_credential import PrinterBridgeCredential
from app.schemas.printer_bridge import (
    PrinterBridgePairingCodeResponse,
    PrinterBridgePairRequest,
    PrinterBridgePairResponse,
    PrinterBridgeStatusResponse,
)
from app.services.material_contract_service import require_physical_printer

PAIRING_TTL = timedelta(minutes=10)
BAMBU_PROVIDER = "bambu"
BAMBU_TRANSPORT = "orca_plugin_lan"
BRIDGE_CAPABILITIES = {"read", "write", "presence"}


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


async def _require_bambu_system(
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
    if system.provider != BAMBU_PROVIDER:
        raise_error(409, ERR_PRINTER_BRIDGE_WRONG_PROVIDER)
    return system


async def _find_bambu_connector(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> PhysicalPrinterConnector | None:
    return await db.scalar(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
            PhysicalPrinterConnector.material_system_id == material_system_id,
            PhysicalPrinterConnector.provider == BAMBU_PROVIDER,
            PhysicalPrinterConnector.transport == BAMBU_TRANSPORT,
        )
    )


async def issue_printer_bridge_pairing_code(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> PrinterBridgePairingCodeResponse:
    system = await _require_bambu_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    connector = await _find_bambu_connector(
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
            provider=BAMBU_PROVIDER,
            transport=BAMBU_TRANSPORT,
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
) -> PrinterBridgeStatusResponse:
    await _require_bambu_system(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    connector = await _find_bambu_connector(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )
    if connector is None:
        return PrinterBridgeStatusResponse(
            configured=False,
            paired=False,
            pairing_expires_at=None,
            last_seen_at=None,
            source_instance_id=None,
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
        source_instance_id=connector.source_instance_id,
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
        or connector.provider != BAMBU_PROVIDER
        or connector.transport != BAMBU_TRANSPORT
        or connector.material_system_id is None
    ):
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)
    return PrinterBridgeContext(credential=credential, connector=connector)


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
) -> None:
    connector = context.connector
    if (
        connector.material_system_id != material_system_id
        or connector.source_instance_id != source_instance_id
        or context.credential.source_instance_id != source_instance_id
    ):
        raise_error(401, ERR_PRINTER_BRIDGE_UNAUTHORIZED)


def require_configured_system_id(context: PrinterBridgeContext) -> int:
    material_system_id = context.connector.material_system_id
    if material_system_id is None:
        raise_error(409, ERR_PRINTER_BRIDGE_NOT_CONFIGURED)
    return material_system_id

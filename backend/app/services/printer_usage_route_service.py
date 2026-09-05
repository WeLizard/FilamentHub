"""Server-issued historical routes, scoped to an authenticated printer bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_MATERIAL_ASSIGNMENT_CONFLICT, raise_error
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.schemas.printer_bridge import PrinterBridgeDesiredSlotSnapshot
from app.schemas.printer_usage import PrinterUsageItem

USAGE_ROUTE_KIND = "usage_route"
_PROOF_FORMAT = re.compile(r"([0-9a-f]{64})\.([A-Za-z0-9_-]{43})\Z")


def identity_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _scope(connector: PhysicalPrinterConnector, source_instance_id: str) -> dict:
    return {
        "version": 1,
        "user_id": connector.user_id,
        "connector_id": connector.id,
        "connector_created_at": identity_timestamp(connector.created_at),
        "source_instance_id": source_instance_id,
        "provider": connector.provider,
        "transport": connector.transport,
        "physical_printer_id": connector.physical_printer_id,
        "material_system_id": connector.material_system_id,
    }


async def issue_usage_route_proofs(
    db: AsyncSession,
    *,
    connector: PhysicalPrinterConnector,
    source_instance_id: str,
    system: MaterialSystem,
    slots: list[MaterialSlot],
    snapshots: list[PrinterBridgeDesiredSlotSnapshot],
) -> None:
    """Issue at most one receipt per route while the caller holds the connector.

    Read the desired graph in one SQL statement before calling. The receipt
    remains valid after an assignment changes, but never authenticates a caller.
    """
    routes: dict[str, tuple[dict, PrinterBridgeDesiredSlotSnapshot]] = {}
    slots_by_id = {slot.id: slot for slot in slots}
    for snapshot in snapshots:
        slot = slots_by_id[snapshot.material_slot_id]
        assignment = slot.assignment
        if (
            not slot.active
            or slot.user_id != connector.user_id
            or assignment is None
            or not assignment.active
            or assignment.user_id != connector.user_id
            or assignment.spool is None
            or assignment.spool.user_id != connector.user_id
            or snapshot.spool is None
        ):
            continue
        route = {
            **_scope(connector, source_instance_id),
            "material_slot_id": slot.id,
            "material_slot_created_at": identity_timestamp(slot.created_at),
            "material_system_created_at": identity_timestamp(system.created_at),
            "slot_index": slot.provider_index,
            "assignment_revision": slot.assignment_revision,
            "spool_id": assignment.spool.id,
            "spool_created_at": identity_timestamp(assignment.spool.created_at),
            "preset_id": assignment.preset_id,
            "preset_created_at": (
                identity_timestamp(assignment.preset.created_at)
                if assignment.preset is not None
                else None
            ),
            "filament_id": assignment.spool.filament_id,
            "density_g_cm3": snapshot.spool.density_g_cm3,
            "diameter_mm": snapshot.spool.diameter_mm,
        }
        receipt_id = hashlib.sha256(
            json.dumps(route, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        # Legacy observation projections can refresh source_ts without changing
        # the desired revision. Capture provenance once without rotating proof.
        route.update(
            assignment_source=assignment.source,
            assignment_source_ts=identity_timestamp(assignment.source_ts),
        )
        routes[receipt_id] = (route, snapshot)
    if not routes:
        return
    existing = {
        receipt.receipt_id: receipt
        for receipt in await db.scalars(
            select(PrinterBridgeReceipt).where(
                PrinterBridgeReceipt.connector_id == connector.id,
                PrinterBridgeReceipt.source_instance_id == source_instance_id,
                PrinterBridgeReceipt.receipt_kind == USAGE_ROUTE_KIND,
                PrinterBridgeReceipt.receipt_id.in_(routes),
            )
        )
    }
    for receipt_id, (route, snapshot) in routes.items():
        receipt = existing.get(receipt_id)
        if receipt is None:
            secret = secrets.token_urlsafe(32)
            receipt = PrinterBridgeReceipt(
                connector_id=connector.id,
                source_instance_id=source_instance_id,
                receipt_kind=USAGE_ROUTE_KIND,
                receipt_id=receipt_id,
                payload_hash=hashlib.sha256(secret.encode("ascii")).hexdigest(),
                response_payload={"route": route, "proof_secret": secret},
            )
            db.add(receipt)
        snapshot.usage_route_proof = f"{receipt_id}.{receipt.response_payload['proof_secret']}"
    await db.flush()


async def resolve_usage_routes(
    db: AsyncSession,
    *,
    connector: PhysicalPrinterConnector,
    source_instance_id: str,
    items: list[PrinterUsageItem],
) -> dict[int, dict]:
    """Verify supplied proofs without falling back to current assignment."""
    proofs: dict[int, tuple[str, str]] = {}
    for item in items:
        if item.usage_route_proof is None:
            continue
        match = _PROOF_FORMAT.fullmatch(item.usage_route_proof)
        if match is None:
            raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT)
        proofs[item.slot_index] = match.groups()
    if not proofs:
        return {}
    receipts = {
        receipt.receipt_id: receipt
        for receipt in await db.scalars(
            select(PrinterBridgeReceipt).where(
                PrinterBridgeReceipt.connector_id == connector.id,
                PrinterBridgeReceipt.source_instance_id == source_instance_id,
                PrinterBridgeReceipt.receipt_kind == USAGE_ROUTE_KIND,
                PrinterBridgeReceipt.receipt_id.in_([proof[0] for proof in proofs.values()]),
            )
        )
    }
    scope = _scope(connector, source_instance_id)
    system_created_at = await db.scalar(
        select(MaterialSystem.created_at).where(
            MaterialSystem.id == connector.material_system_id,
            MaterialSystem.user_id == connector.user_id,
            MaterialSystem.physical_printer_id == connector.physical_printer_id,
        )
    )
    scope["material_system_created_at"] = (
        identity_timestamp(system_created_at) if system_created_at is not None else None
    )
    routes = {}
    for item in items:
        if item.slot_index not in proofs:
            continue
        receipt_id, secret = proofs[item.slot_index]
        receipt = receipts.get(receipt_id)
        route = (receipt.response_payload or {}).get("route", {}) if receipt else {}
        if (
            receipt is None
            or not hmac.compare_digest(
                receipt.payload_hash, hashlib.sha256(secret.encode("ascii")).hexdigest()
            )
            or any(route.get(key) != value for key, value in scope.items())
            or route.get("slot_index") != item.slot_index
            or route.get("spool_id") != item.spool_id
        ):
            raise_error(409, ERR_MATERIAL_ASSIGNMENT_CONFLICT)
        routes[item.slot_index] = route
    return routes

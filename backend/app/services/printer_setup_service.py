"""Resume printer setup on the same physical device, regardless of transport."""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_MATERIAL_SYSTEM_EXISTS, ERR_PRINTER_IDENTITY_CONFLICT, raise_error
from app.models.material_system import MaterialSystem
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.schemas.material_contract import MaterialSystemCreate, PrinterSetupConnection
from app.services.printer_identity_service import identity_printer, remember_identity


async def find_setup_printer(
    db: AsyncSession, user_id: int, connection: PrinterSetupConnection | None,
) -> int | None:
    if connection is None:
        return None
    ids = set((await db.execute(select(PrinterConnectionBinding.physical_printer_id).where(
        PrinterConnectionBinding.user_id == user_id,
        PrinterConnectionBinding.source_instance_id == connection.source_instance_id,
        or_(
            PrinterConnectionBinding.connection_ref == connection.connection_ref,
            PrinterConnectionBinding.endpoint_token == connection.endpoint_token,
        ),
    ))).scalars())
    if connection.device_identity:
        identified = await identity_printer(db, user_id, connection.device_identity)
        if identified is not None:
            ids.add(identified)
    if len(ids) > 1:
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    return next(iter(ids), None)


async def attach_setup_connection(
    db: AsyncSession, user_id: int, printer_id: int, connection: PrinterSetupConnection | None,
) -> None:
    if connection is None:
        return
    known_id = await find_setup_printer(db, user_id, connection)
    if known_id is not None and known_id != printer_id:
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    if connection.device_identity and not await remember_identity(
        db, user_id, printer_id, connection.device_identity,
    ):
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    binding = await db.scalar(select(PrinterConnectionBinding).where(
        PrinterConnectionBinding.user_id == user_id,
        PrinterConnectionBinding.source_instance_id == connection.source_instance_id,
        PrinterConnectionBinding.connection_ref == connection.connection_ref,
    ))
    if binding is not None and binding.status == "conflict":
        # Reconnection is not a substitute for the explicit replacement flow.
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    if binding is None:
        key = hashlib.sha256(
            f"{connection.source_instance_id}\0{connection.connection_ref}".encode()
        ).hexdigest()
        binding = PrinterConnectionBinding(
            user_id=user_id, physical_printer_id=printer_id,
            source_instance_id=connection.source_instance_id,
            connection_ref=connection.connection_ref,
            normalized_endpoint=f"setup:{key}",
        )
        db.add(binding)
    binding.source = (
        "local_setup" if connection.origin == "local_manual" else "orcaslicer_plugin"
    )
    binding.provider = connection.provider
    binding.endpoint_token = connection.endpoint_token
    binding.assignment_confirmed = True
    binding.status = "bound"
    binding.last_seen_at = datetime.now(timezone.utc)
    if connection.device_identity:
        binding.identity_kind = connection.device_identity.kind
        binding.identity_token = connection.device_identity.token
    await db.flush()


async def setup_material_system(
    db: AsyncSession, user_id: int, printer_id: int, payload: MaterialSystemCreate | None,
) -> None:
    if payload is None:
        return
    system = await db.scalar(select(MaterialSystem).where(
        MaterialSystem.user_id == user_id, MaterialSystem.physical_printer_id == printer_id,
    ))
    if system is not None:
        if system.provider not in {"manual", payload.provider}:
            raise_error(409, ERR_MATERIAL_SYSTEM_EXISTS)
        # Keep existing slot IDs and assignments. A verified provider snapshot
        # can enrich the manual topology through the existing ingestion service.
        return
    from app.services.material_contract_service import create_material_system
    await create_material_system(db, user_id, printer_id, payload, commit=False)

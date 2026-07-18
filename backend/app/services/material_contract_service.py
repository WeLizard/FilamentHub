"""Physical-printer and provider-neutral material contract services."""

from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_MATERIAL_SYSTEM_NOT_FOUND,
    ERR_PRINTER_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_FOUND,
    raise_error,
)
from app.models.material_system import (
    MaterialSlot,
    MaterialSystem,
    PhysicalPrinterConnector,
)
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.material_contract import (
    MaterialSystemCreate,
    PhysicalPrinterConfigurationsUpdate,
    PhysicalPrinterConnectorCreate,
    PhysicalPrinterCreate,
    PhysicalPrinterUpdate,
)


def _printer_load_options():
    return (
        selectinload(UserPrinterDevice.profile_links),
        selectinload(UserPrinterDevice.material_systems).selectinload(MaterialSystem.slots),
        selectinload(UserPrinterDevice.connectors),
    )


async def require_physical_printer(
    db: AsyncSession, user_id: int, physical_printer_id: int
) -> UserPrinterDevice:
    result = await db.execute(
        select(UserPrinterDevice)
        .where(
            UserPrinterDevice.id == physical_printer_id,
            UserPrinterDevice.user_id == user_id,
        )
        .options(*_printer_load_options())
    )
    printer = result.scalar_one_or_none()
    if printer is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)
    return printer


async def list_physical_printers(
    db: AsyncSession, user_id: int
) -> list[UserPrinterDevice]:
    result = await db.execute(
        select(UserPrinterDevice)
        .where(UserPrinterDevice.user_id == user_id)
        .options(*_printer_load_options())
        .order_by(UserPrinterDevice.created_at, UserPrinterDevice.id)
    )
    return list(result.scalars().unique().all())


async def _validate_profile_ids(
    db: AsyncSession, user_id: int, profile_ids: list[int]
) -> list[PrinterProfile]:
    if not profile_ids:
        return []
    result = await db.execute(
        select(PrinterProfile).where(
            PrinterProfile.id.in_(profile_ids),
            PrinterProfile.active.is_(True),
            or_(
                PrinterProfile.owner_user_id == user_id,
                (PrinterProfile.owner_user_id.is_(None) & PrinterProfile.is_official.is_(True)),
            ),
        )
    )
    profiles = list(result.scalars().all())
    if {profile.id for profile in profiles} != set(profile_ids):
        raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)
    return profiles


async def _validate_catalog_printer_id(
    db: AsyncSession, printer_id: int | None
) -> None:
    if printer_id is None:
        return
    exists = await db.scalar(
        select(Printer.id).where(Printer.id == printer_id, Printer.active.is_(True))
    )
    if exists is None:
        raise_error(404, ERR_PRINTER_NOT_FOUND)


async def _replace_profile_links(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    profile_ids: list[int],
) -> None:
    await _validate_profile_ids(db, user_id, profile_ids)
    await db.execute(
        delete(UserPrinterProfileLink).where(
            UserPrinterProfileLink.physical_printer_id == physical_printer_id,
            UserPrinterProfileLink.user_id == user_id,
        )
    )
    db.add_all(
        [
            UserPrinterProfileLink(
                user_id=user_id,
                physical_printer_id=physical_printer_id,
                printer_profile_id=profile_id,
            )
            for profile_id in profile_ids
        ]
    )


async def create_physical_printer(
    db: AsyncSession, user_id: int, payload: PhysicalPrinterCreate
) -> UserPrinterDevice:
    await _validate_catalog_printer_id(db, payload.printer_id)
    await _validate_profile_ids(db, user_id, payload.printer_profile_ids)
    printer = UserPrinterDevice(
        user_id=user_id,
        name=payload.name,
        printer_id=payload.printer_id,
        device_fingerprint=None,
        supports_hh=False,
    )
    db.add(printer)
    await db.flush()
    await _replace_profile_links(
        db,
        user_id=user_id,
        physical_printer_id=printer.id,
        profile_ids=payload.printer_profile_ids,
    )
    await db.commit()
    return await require_physical_printer(db, user_id, printer.id)


async def update_physical_printer(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PhysicalPrinterUpdate,
) -> UserPrinterDevice:
    printer = await require_physical_printer(db, user_id, physical_printer_id)
    fields = payload.model_fields_set
    if "name" in fields and payload.name is not None:
        printer.name = payload.name
    if "printer_id" in fields:
        await _validate_catalog_printer_id(db, payload.printer_id)
        printer.printer_id = payload.printer_id
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def set_physical_printer_configurations(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PhysicalPrinterConfigurationsUpdate,
) -> UserPrinterDevice:
    await require_physical_printer(db, user_id, physical_printer_id)
    await _replace_profile_links(
        db,
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        profile_ids=payload.printer_profile_ids,
    )
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def create_material_system(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: MaterialSystemCreate,
) -> UserPrinterDevice:
    await require_physical_printer(db, user_id, physical_printer_id)
    system = MaterialSystem(
        user_id=user_id,
        physical_printer_id=physical_printer_id,
        name=payload.name,
        kind=payload.kind,
        provider=payload.provider,
        capabilities=list(payload.capabilities),
    )
    system.slots = [
        MaterialSlot(
            user_id=user_id,
            provider_index=slot.provider_index,
            label=slot.label,
            kind=slot.kind,
        )
        for slot in payload.slots
    ]
    db.add(system)
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)


async def _require_material_system(
    db: AsyncSession,
    *,
    user_id: int,
    physical_printer_id: int,
    material_system_id: int,
) -> MaterialSystem:
    result = await db.execute(
        select(MaterialSystem).where(
            MaterialSystem.id == material_system_id,
            MaterialSystem.user_id == user_id,
            MaterialSystem.physical_printer_id == physical_printer_id,
        )
    )
    system = result.scalar_one_or_none()
    if system is None:
        raise_error(404, ERR_MATERIAL_SYSTEM_NOT_FOUND)
    return system


async def upsert_physical_printer_connector(
    db: AsyncSession,
    user_id: int,
    physical_printer_id: int,
    payload: PhysicalPrinterConnectorCreate,
) -> UserPrinterDevice:
    await require_physical_printer(db, user_id, physical_printer_id)
    if payload.material_system_id is not None:
        await _require_material_system(
            db,
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            material_system_id=payload.material_system_id,
        )
    result = await db.execute(
        select(PhysicalPrinterConnector).where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.physical_printer_id == physical_printer_id,
            PhysicalPrinterConnector.provider == payload.provider,
            PhysicalPrinterConnector.transport == payload.transport,
        )
    )
    connector = result.scalar_one_or_none()
    if connector is None:
        connector = PhysicalPrinterConnector(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            provider=payload.provider,
            transport=payload.transport,
        )
        db.add(connector)
    connector.material_system_id = payload.material_system_id
    connector.capabilities = list(payload.capabilities)
    connector.active = True
    await db.commit()
    return await require_physical_printer(db, user_id, physical_printer_id)

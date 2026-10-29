"""Observed printers are proposals; a person or a real device confirms them."""

from datetime import datetime, timezone

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_DEVICE_NOT_FOUND, raise_error
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice


def confirm_printer_if_needed(
    printer: UserPrinterDevice, at: datetime | None = None
) -> UserPrinterDevice:
    if printer.confirmed_at is None:
        printer.confirmed_at = at or datetime.now(timezone.utc)
    return printer


def confirmed_printer_clause() -> ColumnElement[bool]:
    """Rows shown as the user's printers; unconfirmed/dismissed ones stay internal."""
    return and_(
        UserPrinterDevice.confirmed_at.is_not(None), UserPrinterDevice.dismissed_at.is_(None)
    )


async def list_printer_suggestions(
    db: AsyncSession, user_id: int, *, limit: int = 100
) -> list[dict]:
    rows = (
        await db.execute(
            select(UserPrinterDevice, Printer.name)
            .outerjoin(Printer, Printer.id == UserPrinterDevice.printer_id)
            .where(
                UserPrinterDevice.user_id == user_id,
                UserPrinterDevice.confirmed_at.is_(None),
                UserPrinterDevice.dismissed_at.is_(None),
            )
            .order_by(UserPrinterDevice.created_at, UserPrinterDevice.id)
            .limit(limit)
        )
    ).all()
    if not rows:
        return []
    ids = [device.id for device, _ in rows]
    profile_names: dict[int, list[str]] = {}
    for device_id, name in await db.execute(
        select(UserPrinterProfileLink.physical_printer_id, PrinterProfile.name)
        .join(PrinterProfile, PrinterProfile.id == UserPrinterProfileLink.printer_profile_id)
        .where(UserPrinterProfileLink.physical_printer_id.in_(ids))
        .order_by(PrinterProfile.name)
    ):
        profile_names.setdefault(device_id, []).append(name)
    model_ids = {device.printer_id for device, _ in rows if device.printer_id is not None}
    same_model: dict[int, list[int]] = {}
    if model_ids:
        for printer_id, device_id in await db.execute(
            select(UserPrinterDevice.printer_id, UserPrinterDevice.id)
            .where(
                UserPrinterDevice.user_id == user_id,
                UserPrinterDevice.printer_id.in_(model_ids),
                confirmed_printer_clause(),
            )
            .order_by(UserPrinterDevice.id)
        ):
            same_model.setdefault(printer_id, []).append(device_id)
    return [
        {
            "id": device.id,
            "name": device.name,
            "catalog_printer_name": catalog_name,
            "profile_names": profile_names.get(device.id, []),
            "created_at": device.created_at,
            "same_model_printer_ids": same_model.get(device.printer_id, []),
        }
        for device, catalog_name in rows
    ]


async def set_printer_confirmation(
    db: AsyncSession, user_id: int, physical_printer_id: int, *, dismiss: bool
) -> None:
    printer = await db.scalar(
        select(UserPrinterDevice)
        .where(
            UserPrinterDevice.id == physical_printer_id,
            UserPrinterDevice.user_id == user_id,
        )
        .with_for_update()
    )
    if printer is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)
    if dismiss:
        if printer.dismissed_at is None:
            printer.dismissed_at = datetime.now(timezone.utc)
    else:
        confirm_printer_if_needed(printer)
        printer.dismissed_at = None
    await db.commit()

"""Remember slices leaving OrcaSlicer and tie each to the printer it was made for."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orca_slice_report import OrcaSliceReport
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_profile import PrinterProfile
from app.schemas.orca_slice_report import (
    OrcaSliceReportIn,
    OrcaSliceReportResponse,
)


def _dedupe_key(user_id: int, payload: OrcaSliceReportIn) -> str:
    """Recognise the same slice arriving twice.

    Exporting to a file and uploading to a printer each fire the plugin once, so
    the same slice arrives twice; the plugin's own handle for the file is what
    tells one slice from a later re-slice of the same name.
    """
    parts = [
        str(user_id),
        payload.file_name.strip().lower(),
        payload.printer_settings_id or "",
        payload.source_key or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def _resolve_printer(
    db: AsyncSession, *, user_id: int, printer_settings_id: str | None
) -> tuple[int | None, int | None]:
    """Find the configuration the slice names, and the printer it is linked to."""
    if not printer_settings_id:
        return None, None

    profile_id = await db.scalar(
        select(PrinterProfile.id)
        .where(
            PrinterProfile.owner_user_id == user_id,
            PrinterProfile.setting_id == printer_settings_id,
        )
        .order_by(PrinterProfile.id.desc())
    )
    if profile_id is None:
        return None, None

    physical_printer_id = await db.scalar(
        select(UserPrinterProfileLink.physical_printer_id)
        .where(
            UserPrinterProfileLink.user_id == user_id,
            UserPrinterProfileLink.printer_profile_id == profile_id,
        )
        .order_by(UserPrinterProfileLink.id)
    )
    return physical_printer_id, profile_id


async def record_slice_reports(
    db: AsyncSession, *, user_id: int, payloads: list[OrcaSliceReportIn]
) -> tuple[int, int]:
    """Store what the plugin reported. Returns (accepted, duplicates)."""
    accepted = duplicates = 0
    for payload in payloads:
        key = _dedupe_key(user_id, payload)
        existing = await db.scalar(
            select(OrcaSliceReport.id).where(
                OrcaSliceReport.user_id == user_id,
                OrcaSliceReport.dedupe_key == key,
            )
        )
        if existing is not None:
            duplicates += 1
            continue

        physical_printer_id, profile_id = await _resolve_printer(
            db, user_id=user_id, printer_settings_id=payload.printer_settings_id
        )
        report = OrcaSliceReport(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            printer_profile_id=profile_id,
            printer_settings_id=payload.printer_settings_id,
            printer_model=payload.printer_model,
            file_name=payload.file_name.strip()[:300],
            target_host=payload.target_host,
            slicer_version=payload.slicer_version,
            source_key=payload.source_key,
            sliced_at=payload.sliced_at,
            dedupe_key=key,
        )
        db.add(report)
        try:
            await db.flush()
        except IntegrityError:
            # Two exports racing each other land here; the first one wins.
            await db.rollback()
            duplicates += 1
            continue
        accepted += 1

    await db.commit()
    return accepted, duplicates


async def list_slice_reports(
    db: AsyncSession, *, user_id: int, limit: int = 20
) -> list[OrcaSliceReportResponse]:
    """The newest slices this person's slicer produced."""
    rows = (
        await db.execute(
            select(OrcaSliceReport)
            .where(OrcaSliceReport.user_id == user_id)
            .options(selectinload(OrcaSliceReport.physical_printer))
            .order_by(OrcaSliceReport.received_at.desc(), OrcaSliceReport.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        OrcaSliceReportResponse(
            id=row.id,
            file_name=row.file_name,
            printer_settings_id=row.printer_settings_id,
            printer_model=row.printer_model,
            physical_printer_id=row.physical_printer_id,
            physical_printer_name=(
                row.physical_printer.name if row.physical_printer is not None else None
            ),
            printer_profile_id=row.printer_profile_id,
            target_host=row.target_host,
            source_key=row.source_key,
            sliced_at=row.sliced_at,
            received_at=row.received_at,
        )
        for row in rows
    ]


async def delete_slice_report(db: AsyncSession, *, user_id: int, slice_id: int) -> bool:
    """Drop one slice from the list. Returns whether there was one to drop."""
    report = await db.scalar(
        select(OrcaSliceReport).where(
            OrcaSliceReport.id == slice_id,
            OrcaSliceReport.user_id == user_id,
        )
    )
    if report is None:
        return False
    await db.delete(report)
    await db.commit()
    return True

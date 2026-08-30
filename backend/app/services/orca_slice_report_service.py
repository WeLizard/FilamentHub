"""Remember slices leaving OrcaSlicer and tie each to the printer it was made for."""

from __future__ import annotations

import hashlib

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.orca_slice_report import OrcaSliceReport
from app.models.print_job import PrintJob
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.schemas.orca_slice_report import (
    OrcaSliceReportIn,
    OrcaSliceReportResponse,
)
from app.services.slicer_identity_access import (
    visible_print_profile_ids,
    visible_printer_profile_ids,
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
        payload.source_instance_id or "",
        payload.source_key or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


async def _resolve_printer(
    db: AsyncSession, *, user_id: int, printer_settings_id: str | None,
    fhub_printer_profile_id: int | None, source_instance_id: str | None,
) -> tuple[int | None, int | None]:
    """A slice identifies its configuration, not necessarily the physical machine."""
    from app.services.physical_printer_discovery_service import observation_physical_printer

    profile_hint = None
    if fhub_printer_profile_id is not None:
        visible_ids = await visible_printer_profile_ids(
            db, user_id=user_id, profile_ids={fhub_printer_profile_id}
        )
        if fhub_printer_profile_id in visible_ids:
            profile_hint = fhub_printer_profile_id
    if source_instance_id and printer_settings_id:
        observations = list((await db.execute(select(OrcaPrinterConnectionObservation).where(
            OrcaPrinterConnectionObservation.owner_user_id == user_id,
            OrcaPrinterConnectionObservation.source_instance_id == source_instance_id,
            OrcaPrinterConnectionObservation.matched_printer_profile_id.is_not(None),
            or_(OrcaPrinterConnectionObservation.preset_name == printer_settings_id,
                OrcaPrinterConnectionObservation.printer_settings_id == printer_settings_id),
        ))).scalars())
        observations = [o for o in observations
                        if (o.sanitized_payload or {}).get("present_in_snapshot") is not False]
        exact = [o for o in observations if o.preset_name == printer_settings_id]
        observations = exact or observations
        if profile_hint is not None:
            observations = [o for o in observations if o.matched_printer_profile_id == profile_hint]
        if observations:
            profile_ids = {o.matched_printer_profile_id for o in observations}
            physical_ids = {await observation_physical_printer(db, user_id, o) for o in observations}
            profile_id = next(iter(profile_ids)) if len(profile_ids) == 1 else profile_hint
            physical_id = next(iter(physical_ids)) if len(physical_ids) == 1 else None
            return physical_id if profile_id is not None else None, profile_id
    if profile_hint is not None or not printer_settings_id:
        return None, profile_hint
    profile_ids = set((await db.execute(select(PrinterProfile.id).where(
        or_(PrinterProfile.owner_user_id == user_id,
            (PrinterProfile.owner_user_id.is_(None) & PrinterProfile.is_official.is_(True))),
        or_(PrinterProfile.setting_id == printer_settings_id, PrinterProfile.name == printer_settings_id),
    ))).scalars())
    return None, next(iter(profile_ids)) if len(profile_ids) == 1 else None

async def _resolve_print_profile(
    db: AsyncSession,
    *,
    user_id: int,
    print_settings_id: str | None,
    fhub_print_profile_id: int | None,
) -> int | None:
    if fhub_print_profile_id is not None:
        visible_ids = await visible_print_profile_ids(
            db, user_id=user_id, profile_ids={fhub_print_profile_id}
        )
        if fhub_print_profile_id in visible_ids:
            return fhub_print_profile_id
    if not print_settings_id:
        return None
    profile_ids = set(
        (
            await db.execute(
                select(PrintProfile.id).where(
                    or_(
                        PrintProfile.owner_user_id == user_id,
                        (
                            PrintProfile.owner_user_id.is_(None)
                            & PrintProfile.is_official.is_(True)
                        ),
                    ),
                    or_(
                        PrintProfile.setting_id == print_settings_id,
                        PrintProfile.name == print_settings_id,
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    return next(iter(profile_ids)) if len(profile_ids) == 1 else None


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
            db,
            user_id=user_id,
            printer_settings_id=payload.printer_settings_id,
            fhub_printer_profile_id=payload.fhub_printer_profile_id,
            source_instance_id=payload.source_instance_id,
        )
        print_profile_id = await _resolve_print_profile(
            db,
            user_id=user_id,
            print_settings_id=payload.print_settings_id,
            fhub_print_profile_id=payload.fhub_print_profile_id,
        )
        report = OrcaSliceReport(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            printer_profile_id=profile_id,
            print_profile_id=print_profile_id,
            printer_settings_id=payload.printer_settings_id,
            print_settings_id=payload.print_settings_id,
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
        (
            await db.execute(
                select(OrcaSliceReport)
                .where(OrcaSliceReport.user_id == user_id)
                .options(selectinload(OrcaSliceReport.physical_printer))
                .order_by(OrcaSliceReport.received_at.desc(), OrcaSliceReport.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return [
        OrcaSliceReportResponse(
            id=row.id,
            file_name=row.file_name,
            printer_settings_id=row.printer_settings_id,
            print_settings_id=row.print_settings_id,
            printer_model=row.printer_model,
            physical_printer_id=row.physical_printer_id,
            physical_printer_name=(
                row.physical_printer.name if row.physical_printer is not None else None
            ),
            printer_profile_id=row.printer_profile_id,
            print_profile_id=row.print_profile_id,
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
    await db.execute(
        update(PrintJob)
        .where(PrintJob.orca_slice_report_id == report.id)
        .values(orca_slice_report_id=None)
    )
    await db.delete(report)
    await db.commit()
    return True

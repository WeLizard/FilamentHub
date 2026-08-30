"""Explicit, previewed repair of duplicate printer cards without dropping history."""

import hashlib
import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_DEVICE_NOT_FOUND, ERR_PRINTER_MERGE_CONFLICT, raise_error
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.orca_slice_report import OrcaSliceReport
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset_gate_state import PresetGateState
from app.models.preset_usage_event import PresetUsageEvent
from app.models.print_job import PrintJob
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_identity import PrinterIdentity
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.orca_import_guard import hold_account_import_lock

REFERENCES = (
    (PrinterConnectionBinding, "physical_printer_id"),
    (PrinterIdentity, "physical_printer_id"),
    (PrintJob, "physical_printer_id"),
    (PresetUsageEvent, "device_id"),
    (OrcaSliceReport, "physical_printer_id"),
    (User, "recommend_physical_printer_id"),
)
PROTECTED = (
    (MaterialSystem, "physical_printer_id"),
    (PhysicalPrinterConnector, "physical_printer_id"),
    (PresetGateState, "device_id"),
)
FACTS = (
    "printer_id",
    "device_fingerprint",
    "purchase_cost",
    "residual_value",
    "useful_life_hours",
    "average_power_watts",
    "power_hotend_w",
    "power_bed_w",
    "power_steppers_w",
    "power_electronics_w",
    "maintenance_cost_per_hour",
    "machine_hour_rate",
    "economics_currency",
)


async def preview_printer_merge(
    db: AsyncSession, user_id: int, source_id: int, target_id: int
) -> dict:
    if source_id == target_id:
        raise_error(409, ERR_PRINTER_MERGE_CONFLICT)
    printers = {
        p.id: p
        for p in (
            await db.execute(
                select(UserPrinterDevice)
                .where(
                    UserPrinterDevice.user_id == user_id,
                    UserPrinterDevice.id.in_([source_id, target_id]),
                )
                .order_by(UserPrinterDevice.id)
                .with_for_update()
            )
        ).scalars()
    }
    if len(printers) != 2:
        raise_error(404, ERR_DEVICE_NOT_FOUND)
    source, target = printers[source_id], printers[target_id]
    counts = {}
    for model, column in (*REFERENCES, *PROTECTED, (UserPrinterProfileLink, "physical_printer_id")):
        counts[model.__tablename__] = await db.scalar(
            select(func.count())
            .select_from(model)
            .where(
                getattr(model, column) == source_id,
            )
        )
    reason = None
    if any(counts[model.__tablename__] for model, _ in PROTECTED) or any(
        (
            source.api_key,
            source.printer_hostname,
            source.supports_hh,
            source.reports_feed,
        )
    ):
        # The card carrying hardware/credentials must survive. Combining two
        # independently configured feeds is not a duplicate-card repair.
        reason = "source_connected"
    elif any(
        getattr(source, f) is not None
        and getattr(target, f) is not None
        and getattr(source, f) != getattr(target, f)
        for f in FACTS
    ):
        reason = "facts_conflict"
    revision = hashlib.sha256(
        json.dumps(
            {
                "source": source_id,
                "target": target_id,
                "counts": counts,
                "source_updated": str(source.updated_at),
                "target_updated": str(target.updated_at),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "source_id": source_id,
        "target_id": target_id,
        "source_name": source.name,
        "target_name": target.name,
        "allowed": reason is None,
        "reason": reason,
        "revision": revision,
        "configurations": counts["user_printer_profile_links"],
        "connections": counts["printer_connection_bindings"],
        "history": counts["print_jobs"]
        + counts["preset_usage_events"]
        + counts["orca_slice_reports"],
    }


async def merge_printers(
    db: AsyncSession, user_id: int, source_id: int, target_id: int, revision: str
) -> None:
    await hold_account_import_lock(db, user_id)
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    preview = await preview_printer_merge(db, user_id, source_id, target_id)
    if not preview["allowed"] or preview["revision"] != revision:
        raise_error(409, ERR_PRINTER_MERGE_CONFLICT)
    source, target = (
        await db.get(UserPrinterDevice, source_id),
        await db.get(UserPrinterDevice, target_id),
    )
    source_fingerprint = source.device_fingerprint
    source.device_fingerprint = None
    await db.flush()
    for field in FACTS:
        if getattr(target, field) is None:
            setattr(
                target,
                field,
                source_fingerprint if field == "device_fingerprint" else getattr(source, field),
            )
    await db.flush()
    target_profiles = select(UserPrinterProfileLink.printer_profile_id).where(
        UserPrinterProfileLink.physical_printer_id == target_id,
    )
    await db.execute(
        delete(UserPrinterProfileLink).where(
            UserPrinterProfileLink.physical_printer_id == source_id,
            UserPrinterProfileLink.printer_profile_id.in_(target_profiles),
        )
    )
    await db.execute(
        update(UserPrinterProfileLink)
        .where(
            UserPrinterProfileLink.physical_printer_id == source_id,
        )
        .values(physical_printer_id=target_id)
    )
    await db.execute(
        update(PrinterConnectionBinding)
        .where(
            PrinterConnectionBinding.physical_printer_id.in_([source_id, target_id]),
        )
        .values(assignment_confirmed=True)
    )
    for model, column in REFERENCES:
        await db.execute(
            update(model).where(getattr(model, column) == source_id).values({column: target_id})
        )
    # No material system, connector, slot or assignment was deleted or recreated.
    await db.execute(delete(UserPrinterDevice).where(UserPrinterDevice.id == source_id))
    await db.flush()
    from app.services.physical_printer_discovery_service import reconcile_user_printers

    await reconcile_user_printers(db, user_id)

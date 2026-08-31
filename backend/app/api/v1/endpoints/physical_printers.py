"""Endpoints for physical printers, Orca configurations, and material systems."""

import asyncio
import random
import time
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, require_printer_bundle_read
from app.core.errors import (
    ERR_EXPORT_PRINTER_DISABLED,
    ERR_SERVER_BUSY,
    raise_error,
)
from app.core.security import decode_access_token, token_fingerprint
from app.db.session import get_db
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.material_contract import (
    MaterialSlotAssignmentUpdate,
    MaterialSystemAssignmentsClearRequest,
    MaterialSystemCreate,
    MaterialSystemUpdate,
    PhysicalPrinterConfigurationsUpdate,
    PhysicalPrinterConnectionSetup,
    PhysicalPrinterConnectorCreate,
    PhysicalPrinterCreate,
    PhysicalPrinterMergeRequest,
    PhysicalPrinterResponse,
    PhysicalPrinterUpdate,
)
from app.schemas.orca_sync import OrcaPrinterRecoveryPlanRequest
from app.schemas.printer_economics import (
    PrinterEconomicsResponse,
    PrinterEconomicsSuggestion,
    PrinterEconomicsUpdate,
)
from app.services.material_assignment_service import (
    clear_material_system_assignments,
    update_material_slot_assignment,
)
from app.services.material_contract_service import (
    create_material_system,
    create_physical_printer,
    delete_material_system,
    delete_physical_printer,
    list_physical_printers,
    require_physical_printer,
    set_physical_printer_configurations,
    update_material_system,
    update_physical_printer,
    upsert_physical_printer_connector,
)
from app.services.orca_printer_bundle_service import (
    build_orca_printer_archive,
    build_orca_printer_bundle,
    build_orca_printer_recovery_bundle,
)
from app.services.printer_contact_events import (
    CONTACT_PROTOCOL,
    STREAM_SECONDS,
    StreamLimitReached,
    StreamUnavailable,
    broker,
)
from app.services.printer_economics_service import (
    DEFAULT_USAGE,
    USAGE_LIFE_HOURS,
    resolve_economics,
    suggest_economics,
)

router = APIRouter(prefix="/physical-printers", tags=["physical-printers"])


@router.post("/contact-ticket")
async def contact_ticket(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
) -> dict:
    user_id = current_user.id
    authorization = request.headers.get("authorization", "")
    token = (
        authorization.split(" ", 1)[1]
        if authorization.lower().startswith("bearer ")
        else request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME, "")
    )
    # Authentication above is authoritative. This second decode only bounds the
    # connection by the authenticated token's expiry. The one-use ticket travels
    # in the WebSocket subprotocol header, never a URL or persistent storage.
    payload = decode_access_token(token) or {}
    lifetime = max(0, min(random.uniform(STREAM_SECONDS * 0.8, STREAM_SECONDS), float(payload.get("exp", 0)) - time.time()))
    expires_at = time.time() + lifetime
    # The socket has no database dependency at all. Release this short auth
    # transaction before Redis; even a waiting ticket request holds no DB slot.
    await db.close()
    try:
        ticket = await broker.issue_ticket(user_id, token_fingerprint(token), expires_at)
    except StreamLimitReached:
        raise_error(429, ERR_SERVER_BUSY, headers={"Retry-After": "15"})
    except StreamUnavailable:
        raise_error(503, ERR_SERVER_BUSY, headers={"Retry-After": "30"})
    response.headers["Cache-Control"] = "private, no-store"
    return {"ticket": ticket}


@router.websocket("/contact-events")
async def contact_events(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    protocols = websocket.scope.get("subprotocols", [])
    tickets = [value.removeprefix("fh-ticket.") for value in protocols if value.startswith("fh-ticket.")]
    if (origin and origin not in settings.CORS_ORIGINS) or CONTACT_PROTOCOL not in protocols or len(tickets) != 1:
        await websocket.close(code=1008)
        return
    try:
        session = await broker.consume_ticket(tickets[0])
        if not session or session["expires_at"] <= time.time():
            await websocket.close(code=1008)
            return
        async with broker.subscribe(session["user_id"], session["token_id"]) as subscription:
            if session["expires_at"] <= time.time() or not subscription.can_deliver():
                return
            await websocket.accept(subprotocol=CONTACT_PROTOCOL)
            # Uvicorn closes WebSockets with 1012 before draining requests on
            # shutdown. An HTTP event stream would instead delay a reload.
            disconnected = asyncio.create_task(websocket.receive())
            next_event = None
            try:
                async with asyncio.timeout(5):
                    await websocket.send_json({"type": "ready"})
                while (remaining := session["expires_at"] - time.time()) > 0:
                    next_event = asyncio.create_task(subscription.queue.get())
                    done, _ = await asyncio.wait(
                        {disconnected, next_event}, timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    # This is a server-to-screen channel, not a command API:
                    # both disconnect and unsolicited client data end it.
                    if disconnected in done or next_event not in done:
                        break
                    update = next_event.result()
                    if update is None or not subscription.can_deliver():
                        break
                    async with asyncio.timeout(5):
                        await websocket.send_json(update)
            finally:
                tasks = [disconnected] + ([next_event] if next_event is not None else [])
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (StreamUnavailable, WebSocketDisconnect, TimeoutError):
        # Expected disconnect/overload: reconnect uses backoff and fresh auth.
        return
    finally:
        with suppress(WebSocketDisconnect, RuntimeError):
            await websocket.close(code=1000)


@router.get("/{physical_printer_id}/merge-preview")
async def merge_preview(
    physical_printer_id: int, target_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    from app.services.printer_merge_service import preview_printer_merge
    return await preview_printer_merge(db, current_user.id, physical_printer_id, target_id)


@router.post("/{physical_printer_id}/merge", status_code=status.HTTP_204_NO_CONTENT)
async def merge_items(
    physical_printer_id: int, payload: PhysicalPrinterMergeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    from app.services.printer_merge_service import merge_printers
    await merge_printers(db, current_user.id, physical_printer_id, payload.target_id, payload.revision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[PhysicalPrinterResponse])
async def list_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PhysicalPrinterResponse]:
    printers = await list_physical_printers(db, current_user.id)
    return [PhysicalPrinterResponse.from_model(printer) for printer in printers]


@router.post("/orcaslicer-recovery-plan", response_model=None)
async def get_orcaslicer_recovery_plan(
    payload: OrcaPrinterRecoveryPlanRequest,
    current_user: Annotated[User, Depends(require_printer_bundle_read)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Preview recoverable profiles for one exact Orca account on user action."""

    if not (
        current_user.allow_printer_profiles_export
        or current_user.allow_print_profiles_export
    ):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_EXPORT_PRINTER_DISABLED)
    return await build_orca_printer_recovery_bundle(
        db=db,
        user_id=current_user.id,
        source_instance_id=payload.source_instance_id,
        account_id=payload.account_id,
        include_machine_profiles=current_user.allow_printer_profiles_export,
        include_process_profiles=current_user.allow_print_profiles_export,
        machine_snapshot_complete=payload.machine_snapshot_complete,
        machine_present_local_profile_ids=set(
            payload.machine_present_local_profile_ids
        ),
        process_snapshot_complete=payload.process_snapshot_complete,
        process_present_local_profile_ids=set(
            payload.process_present_local_profile_ids
        ),
    )


@router.post(
    "", response_model=PhysicalPrinterResponse, status_code=status.HTTP_201_CREATED
)
async def create_item(
    payload: PhysicalPrinterCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await create_physical_printer(db, current_user.id, payload)
    return PhysicalPrinterResponse.from_model(printer)


@router.get("/{physical_printer_id}", response_model=PhysicalPrinterResponse)
async def get_item(
    physical_printer_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await require_physical_printer(db, current_user.id, physical_printer_id)
    return PhysicalPrinterResponse.from_model(printer)


@router.post("/{physical_printer_id}/connection-setup", response_model=PhysicalPrinterResponse)
async def setup_connection(
    physical_printer_id: int,
    payload: PhysicalPrinterConnectionSetup,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    from app.services.orca_import_guard import hold_account_import_lock
    from app.services.printer_setup_service import attach_setup_connection, setup_material_system

    await hold_account_import_lock(db, current_user.id)
    await require_physical_printer(db, current_user.id, physical_printer_id)
    await attach_setup_connection(db, current_user.id, physical_printer_id, payload.connection)
    if payload.material_system_update is not None:
        await update_material_system(
            db, current_user.id, physical_printer_id, payload.material_system_id,
            payload.material_system_update, commit=False,
        )
    await setup_material_system(db, current_user.id, physical_printer_id, payload.material_system)
    await db.commit()
    return PhysicalPrinterResponse.from_model(
        await require_physical_printer(db, current_user.id, physical_printer_id)
    )


@router.get("/{physical_printer_id}/orcaslicer-bundle", response_model=None)
async def get_orcaslicer_bundle(
    physical_printer_id: int,
    current_user: Annotated[User, Depends(require_printer_bundle_read)],
    db: Annotated[AsyncSession, Depends(get_db)],
    archive: bool = False,
) -> dict | Response:
    """Build a user-requested managed Orca bundle for one physical printer."""
    if not current_user.allow_printer_profiles_export:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_EXPORT_PRINTER_DISABLED)
    printer = await require_physical_printer(
        db, current_user.id, physical_printer_id
    )
    bundle = await build_orca_printer_bundle(
        db=db,
        physical_printer=printer,
        user_id=current_user.id,
        include_process_profiles=current_user.allow_print_profiles_export,
    )
    if archive:
        return Response(
            content=build_orca_printer_archive(bundle),
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="filamenthub-printer-{physical_printer_id}.zip"'
                )
            },
        )
    return bundle


@router.delete("/{physical_printer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    physical_printer_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a physical printer the user no longer has.

    Spools loaded in its gates go back to the shelf first: they are real
    material the person still owns, and the foreign keys would otherwise leave
    them pointing at gates that no longer exist. Material systems, gate states,
    configuration links and connection bindings go with the printer; print
    history keeps its rows and simply loses the device reference.
    """
    await delete_physical_printer(db, current_user.id, physical_printer_id)


@router.patch("/{physical_printer_id}", response_model=PhysicalPrinterResponse)
async def patch_item(
    physical_printer_id: int,
    payload: PhysicalPrinterUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await update_physical_printer(
        db, current_user.id, physical_printer_id, payload
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.put(
    "/{physical_printer_id}/configurations",
    response_model=PhysicalPrinterResponse,
)
async def replace_configurations(
    physical_printer_id: int,
    payload: PhysicalPrinterConfigurationsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await set_physical_printer_configurations(
        db, current_user.id, physical_printer_id, payload
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.post(
    "/{physical_printer_id}/material-systems",
    response_model=PhysicalPrinterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_material_system(
    physical_printer_id: int,
    payload: MaterialSystemCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await create_material_system(
        db, current_user.id, physical_printer_id, payload
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.patch(
    "/{physical_printer_id}/material-systems/{material_system_id}",
    response_model=PhysicalPrinterResponse,
)
async def patch_material_system(
    physical_printer_id: int,
    material_system_id: int,
    payload: MaterialSystemUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await update_material_system(
        db, current_user.id, physical_printer_id, material_system_id, payload
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.delete(
    "/{physical_printer_id}/material-systems/{material_system_id}",
    response_model=PhysicalPrinterResponse,
)
async def remove_material_system(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await delete_material_system(
        db, current_user.id, physical_printer_id, material_system_id
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.put(
    "/{physical_printer_id}/connectors",
    response_model=PhysicalPrinterResponse,
)
async def upsert_connector(
    physical_printer_id: int,
    payload: PhysicalPrinterConnectorCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    printer = await upsert_physical_printer_connector(
        db, current_user.id, physical_printer_id, payload
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.patch(
    "/{physical_printer_id}/material-slots/{material_slot_id}",
    response_model=PhysicalPrinterResponse,
)
async def patch_material_slot_assignment(
    physical_printer_id: int,
    material_slot_id: int,
    payload: MaterialSlotAssignmentUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    await update_material_slot_assignment(
        db,
        current_user,
        physical_printer_id=physical_printer_id,
        material_slot_id=material_slot_id,
        payload=payload,
    )
    printer = await require_physical_printer(
        db, current_user.id, physical_printer_id
    )
    return PhysicalPrinterResponse.from_model(printer)


@router.post(
    "/{physical_printer_id}/material-systems/{material_system_id}/clear",
    response_model=PhysicalPrinterResponse,
)
async def clear_material_system(
    physical_printer_id: int,
    material_system_id: int,
    payload: MaterialSystemAssignmentsClearRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    await clear_material_system_assignments(
        db,
        current_user,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        payload=payload,
    )
    printer = await require_physical_printer(
        db, current_user.id, physical_printer_id
    )
    return PhysicalPrinterResponse.from_model(printer)


async def _economics_response(
    db: AsyncSession, printer: UserPrinterDevice
) -> PrinterEconomicsResponse:
    resolved = await resolve_economics(db, printer)
    return PrinterEconomicsResponse(
        printer_id=printer.id,
        configured=any(
            value is not None
            for value in (
                printer.purchase_cost,
                printer.useful_life_hours,
                printer.average_power_watts,
                printer.maintenance_cost_per_hour,
                printer.machine_hour_rate,
            )
        ),
        purchase_cost=printer.purchase_cost,
        residual_value=printer.residual_value,
        useful_life_hours=printer.useful_life_hours,
        average_power_watts=printer.average_power_watts,
        power_hotend_w=printer.power_hotend_w,
        power_bed_w=printer.power_bed_w,
        power_steppers_w=printer.power_steppers_w,
        power_electronics_w=printer.power_electronics_w,
        maintenance_cost_per_hour=printer.maintenance_cost_per_hour,
        machine_hour_rate=printer.machine_hour_rate,
        economics_currency=printer.economics_currency,
        depreciation_per_hour=round(resolved.depreciation_per_hour, 2),
        electricity_per_hour=round(resolved.electricity_per_hour, 2),
        maintenance_per_hour=round(resolved.maintenance_per_hour, 2),
        machine_cost_per_hour=round(resolved.machine_cost_per_hour, 2),
        effective_machine_hour_rate=round(resolved.machine_hour_rate, 2),
        rate_below_cost=resolved.rate_below_cost,
        calculator_printer_power_w=round(resolved.printer_power_w, 2),
        calculator_printing_rate_per_hour=round(resolved.printing_rate_per_hour, 2),
        calculator_amortization_rate_per_hour=round(
            resolved.amortization_rate_per_hour, 2
        ),
        calculator_electricity_cost_per_kwh=round(resolved.electricity_cost_per_kwh, 2),
        sources=resolved.sources,
    )


@router.get("/{physical_printer_id}/economics", response_model=PrinterEconomicsResponse)
async def get_economics(
    physical_printer_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterEconomicsResponse:
    """What this machine costs to run, and what the calculator will charge."""
    printer = await require_physical_printer(db, current_user.id, physical_printer_id)
    return await _economics_response(db, printer)


@router.patch("/{physical_printer_id}/economics", response_model=PrinterEconomicsResponse)
async def update_economics(
    physical_printer_id: int,
    payload: PrinterEconomicsUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterEconomicsResponse:
    """Set once, change whenever. Fields left out keep their current value."""
    printer = await require_physical_printer(db, current_user.id, physical_printer_id)
    for field_name in payload.model_fields_set:
        setattr(printer, field_name, getattr(payload, field_name))
    await db.commit()
    await db.refresh(printer)
    return await _economics_response(db, printer)


@router.get(
    "/{physical_printer_id}/economics/suggestion",
    response_model=PrinterEconomicsSuggestion,
)
async def get_economics_suggestion(
    physical_printer_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    usage: str = DEFAULT_USAGE,
) -> PrinterEconomicsSuggestion:
    """Starting numbers, so nobody has to know their printer's wattage first."""
    printer = await require_physical_printer(db, current_user.id, physical_printer_id)
    suggestion = await suggest_economics(
        db, printer, usage if usage in USAGE_LIFE_HOURS else DEFAULT_USAGE
    )
    machine = suggestion.machine
    return PrinterEconomicsSuggestion(
        printer_id=printer.id,
        machine_class=machine.machine_class,
        confidence=machine.confidence,
        vendor=machine.vendor,
        model_name=machine.model_name,
        bed_max_mm=machine.bed_max_mm,
        extruders=machine.extruders,
        usage=suggestion.usage,
        average_power_watts=suggestion.average_power_watts,
        power_hotend_w=suggestion.power_hotend_w,
        power_bed_w=suggestion.power_bed_w,
        power_steppers_w=suggestion.power_steppers_w,
        power_electronics_w=suggestion.power_electronics_w,
        useful_life_hours=suggestion.useful_life_hours,
        maintenance_cost_per_hour=suggestion.maintenance_cost_per_hour,
        orca_time_cost=machine.orca_time_cost,
    )

"""OrcaSlicer plugin printer-connection observation endpoint (stage A)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_preset_write
from app.core.errors import ERR_IMPORT_PRINTER_DISABLED, raise_error
from app.db.session import get_db
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import (
    PrinterConnectionBindingAssignRequest,
    PrinterConnectionBindingResponse,
    PrinterConnectionObserveRequest,
    PrinterConnectionObserveResponse,
    PrinterConnectionResolveRequest,
)
from app.services.orca_import_guard import hold_account_import_lock
from app.services.physical_printer_discovery_service import (
    assign_user_binding,
    binding_preset_names,
    current_printer_context,
    display_endpoint,
    list_installed_printer_candidates,
    list_pending_connections,
    list_user_bindings,
    reconcile_user_printers,
    resolve_pending_connection,
)
from app.services.printer_connection_observation_service import record_observations

router = APIRouter(prefix="/orcaslicer/printer-connections", tags=["printer-connections"])


@router.post("/observe", response_model=PrinterConnectionObserveResponse)
async def observe_printer_connections(
    payload: PrinterConnectionObserveRequest,
    current_user: Annotated[User, Depends(require_preset_write)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterConnectionObserveResponse:
    """Record observed printer connection data from the OrcaSlicer plugin, then
    reconcile it into physical printers + connection bindings."""
    if not current_user.allow_printer_profiles_import:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_IMPORT_PRINTER_DISABLED)

    # The plugin may trigger an automatic and a manual sync nearly together.
    # Serialize both the observation upsert and physical-printer reconciliation
    # per account so two requests cannot create the same selected machine twice.
    await hold_account_import_lock(db, current_user.id)
    accepted, matched, unmatched = await record_observations(
        db, current_user.id, payload.source_instance_id, payload.observations,
        commit=False, snapshot_complete=payload.snapshot_complete,
    )
    await hold_account_import_lock(db, current_user.id)
    created = await reconcile_user_printers(
        db,
        current_user.id,
        source_instance_id=payload.source_instance_id,
    )
    return PrinterConnectionObserveResponse(
        accepted=accepted,
        matched=matched,
        unmatched=unmatched,
        created=created,
        pending=len(await list_pending_connections(db, current_user.id)),
    )


@router.get("/current")
async def get_current_printer(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict | None:
    """The machine selected in OrcaSlicer as of the last sync, or null."""
    return await current_printer_context(db, current_user.id)


@router.get("/installed-candidates")
async def list_installed_candidates(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """Printer models present in the user's OrcaSlicer but not registered here.

    Offered as one-click additions; nothing is created without the user asking.
    """
    return await list_installed_printer_candidates(db, current_user.id)


@router.get("/bindings", response_model=list[PrinterConnectionBindingResponse])
async def list_connection_bindings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PrinterConnectionBindingResponse]:
    """Safe display view of the user's connection bindings (endpoint as a label)."""
    bindings = await list_user_bindings(db, current_user.id)
    printer_names = dict(
        (
            await db.execute(
                select(UserPrinterDevice.id, UserPrinterDevice.name).where(
                    UserPrinterDevice.user_id == current_user.id
                )
            )
        ).all()
    )
    preset_names = await binding_preset_names(db, current_user.id)
    return [
        PrinterConnectionBindingResponse(
            id=b.id,
            physical_printer_id=b.physical_printer_id,
            physical_printer_name=printer_names[b.physical_printer_id],
            connection_ref=b.connection_ref,
            preset_name=(
                preset_names.get((b.source_instance_id, b.connection_ref))
                if b.connection_ref
                else None
            ),
            provider=b.provider,
            display_endpoint=display_endpoint(b),
            endpoint_shared=bool(b.endpoint_ciphertext or b.print_host),
            last_seen_at=b.last_seen_at,
            status=b.status,
        )
        for b in bindings
    ]


@router.patch("/bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_connection_binding(
    binding_id: int,
    payload: PrinterConnectionBindingAssignRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Move one owned, observed connection to the selected physical printer."""
    await assign_user_binding(
        db,
        user_id=current_user.id,
        binding_id=binding_id,
        physical_printer_id=payload.physical_printer_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pending")
async def pending_connections(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    return await list_pending_connections(db, current_user.id)


@router.post("/pending/{observation_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_connection(
    observation_id: int,
    payload: PrinterConnectionResolveRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await resolve_pending_connection(
        db, user_id=current_user.id, observation_id=observation_id,
        physical_printer_id=payload.physical_printer_id, create_new=payload.create_new,
        revision=payload.revision,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

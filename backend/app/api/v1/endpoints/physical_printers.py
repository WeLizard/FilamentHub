"""Endpoints for physical printers, Orca configurations, and material systems."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_EXPORT_PRINTER_DISABLED,
    raise_error,
)
from app.db.session import get_db
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.material_contract import (
    MaterialSlotAssignmentUpdate,
    MaterialSystemCreate,
    MaterialSystemUpdate,
    PhysicalPrinterConfigurationsUpdate,
    PhysicalPrinterConnectorCreate,
    PhysicalPrinterCreate,
    PhysicalPrinterResponse,
    PhysicalPrinterUpdate,
)
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
)
from app.services.printer_economics_service import (
    DEFAULT_USAGE,
    USAGE_LIFE_HOURS,
    resolve_economics,
    suggest_economics,
)

router = APIRouter(prefix="/physical-printers", tags=["physical-printers"])


@router.get("", response_model=list[PhysicalPrinterResponse])
async def list_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PhysicalPrinterResponse]:
    printers = await list_physical_printers(db, current_user.id)
    return [PhysicalPrinterResponse.from_model(printer) for printer in printers]


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


@router.get("/{physical_printer_id}/orcaslicer-bundle", response_model=None)
async def get_orcaslicer_bundle(
    physical_printer_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
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
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhysicalPrinterResponse:
    await clear_material_system_assignments(
        db,
        current_user,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
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
        useful_life_hours=suggestion.useful_life_hours,
        maintenance_cost_per_hour=suggestion.maintenance_cost_per_hour,
        orca_time_cost=machine.orca_time_cost,
    )

"""Endpoints for physical printers, Orca configurations, and material systems."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
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

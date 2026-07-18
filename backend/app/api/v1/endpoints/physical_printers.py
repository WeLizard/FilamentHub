"""Endpoints for physical printers, Orca configurations, and material systems."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.material_contract import (
    MaterialSystemCreate,
    PhysicalPrinterConfigurationsUpdate,
    PhysicalPrinterConnectorCreate,
    PhysicalPrinterCreate,
    PhysicalPrinterResponse,
    PhysicalPrinterUpdate,
)
from app.services.material_contract_service import (
    create_material_system,
    create_physical_printer,
    list_physical_printers,
    require_physical_printer,
    set_physical_printer_configurations,
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

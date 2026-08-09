"""Slices the OrcaSlicer plugin saw leaving the slicer."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.calculator import parse_uploaded_gcode
from app.core.dependencies import get_current_active_user, require_preset_write
from app.core.errors import ERR_CALCULATOR_ACCESS_REQUIRED, ERR_SLICE_NOT_FOUND, raise_error
from app.db.session import get_db
from app.models.user import User
from app.schemas.calculator import CalculatorGcodeParseResponse
from app.schemas.orca_slice_report import (
    OrcaSliceReportAccepted,
    OrcaSliceReportBatch,
    OrcaSliceReportResponse,
)
from app.services.orca_slice_report_service import (
    delete_slice_report,
    list_slice_reports,
    record_slice_reports,
)
from app.services.subscription_service import pro_active

router = APIRouter(prefix="/orcaslicer/slices", tags=["orca-slices"])


@router.post("", response_model=OrcaSliceReportAccepted)
async def report_slices(
    payload: OrcaSliceReportBatch,
    current_user: Annotated[User, Depends(require_preset_write)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrcaSliceReportAccepted:
    """Take the figures Orca wrote into a produced G-code.

    The file stays on the person's machine: only its totals travel, and the
    breakdown by role is parsed later, if they ask for it in the calculator.
    """
    accepted, duplicates = await record_slice_reports(
        db, user_id=current_user.id, payloads=payload.slices
    )
    return OrcaSliceReportAccepted(accepted=accepted, duplicates=duplicates)


@router.post("/parse", response_model=CalculatorGcodeParseResponse)
async def parse_slice(
    current_user: Annotated[User, Depends(require_preset_write)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    plate_index: int | None = Query(None, ge=1),
) -> CalculatorGcodeParseResponse:
    """Read a slice the plugin kept, for the calculator the person is looking at.

    The plugin holds the file, so it uploads it here instead of the calculator's
    own route: a plugin session is scoped and cannot pass as a browser session.
    The paid-feature gate is the same one the calculator applies.
    """
    if not pro_active(current_user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_CALCULATOR_ACCESS_REQUIRED)
    return await parse_uploaded_gcode(
        file,
        plate_index,
        db=db,
        user_id=current_user.id,
    )


@router.get("", response_model=list[OrcaSliceReportResponse])
async def get_slices(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
) -> list[OrcaSliceReportResponse]:
    """The newest slices, whichever printer they were made for."""
    return await list_slice_reports(db, user_id=current_user.id, limit=limit)


@router.delete("/{slice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_slice(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    slice_id: Annotated[int, Path(ge=1)],
) -> None:
    """Forget a slice a person no longer wants in the list."""
    if not await delete_slice_report(db, user_id=current_user.id, slice_id=slice_id):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_SLICE_NOT_FOUND)

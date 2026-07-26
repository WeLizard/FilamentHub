"""Slices the OrcaSlicer plugin saw leaving the slicer."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_preset_write
from app.db.session import get_db
from app.models.user import User
from app.schemas.orca_slice_report import (
    OrcaSliceReportAccepted,
    OrcaSliceReportBatch,
    OrcaSliceReportResponse,
)
from app.services.orca_slice_report_service import (
    list_slice_reports,
    record_slice_reports,
)

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


@router.get("", response_model=list[OrcaSliceReportResponse])
async def get_slices(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
) -> list[OrcaSliceReportResponse]:
    """The newest slices, whichever printer they were made for."""
    return await list_slice_reports(db, user_id=current_user.id, limit=limit)

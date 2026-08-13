"""Authenticated production print history endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.print_job import (
    PrintJobCreate,
    PrintJobListResponse,
    PrintJobResponse,
    PrintJobTransitionCreate,
)
from app.services.print_job_service import (
    create_print_job,
    get_print_job,
    list_print_jobs,
    transition_print_job,
)

router = APIRouter(prefix="/print-jobs", tags=["print-jobs"])


@router.get("", response_model=PrintJobListResponse)
async def list_items(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    physical_printer_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> PrintJobListResponse:
    return await list_print_jobs(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        page=page,
        size=size,
    )


@router.post("", response_model=PrintJobResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: PrintJobCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintJobResponse:
    return await create_print_job(db, user_id=current_user.id, payload=payload)


@router.get("/{job_id}", response_model=PrintJobResponse)
async def get_item(
    job_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintJobResponse:
    return await get_print_job(db, user_id=current_user.id, job_id=job_id)


@router.post("/{job_id}/events", response_model=PrintJobResponse)
async def add_event(
    job_id: int,
    payload: PrintJobTransitionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintJobResponse:
    return await transition_print_job(
        db,
        user_id=current_user.id,
        job_id=job_id,
        payload=payload,
    )

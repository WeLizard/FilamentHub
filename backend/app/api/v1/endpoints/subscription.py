"""Subscription and plan-interest endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import ERR_PLAN_INTEREST_UNAVAILABLE, raise_error
from app.db.session import get_db
from app.models.user import User
from app.schemas.subscription import PlanInterestResponse
from app.services import subscription_service

router = APIRouter(prefix="/subscription", tags=["subscription"])


@router.post("/interest", response_model=PlanInterestResponse)
async def join_workshop_interest(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanInterestResponse:
    try:
        subscription = await subscription_service.join_workshop_interest(db, current_user)
    except subscription_service.PlanInterestUnavailableError:
        raise_error(status.HTTP_409_CONFLICT, ERR_PLAN_INTEREST_UNAVAILABLE)
    return PlanInterestResponse(
        status=subscription.status.value,
        interested_at=subscription.interested_at,
    )


@router.delete("/interest", status_code=status.HTTP_204_NO_CONTENT)
async def leave_workshop_interest(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await subscription_service.leave_workshop_interest(db, current_user)
    except subscription_service.PlanInterestUnavailableError:
        raise_error(status.HTTP_409_CONFLICT, ERR_PLAN_INTEREST_UNAVAILABLE)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

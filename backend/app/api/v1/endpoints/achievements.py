"""Unified achievements, hidden milestones, and factual contributor summary."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.achievement import AchievementOverviewResponse
from app.services.achievement_service import (
    evaluate_achievement_overview,
    read_achievement_overview,
)

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("/me", response_model=AchievementOverviewResponse)
async def get_my_achievements(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AchievementOverviewResponse:
    return await read_achievement_overview(db, user_id=current_user.id)


@router.post("/me/evaluate", response_model=AchievementOverviewResponse)
async def evaluate_my_achievements(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AchievementOverviewResponse:
    return await evaluate_achievement_overview(db, user_id=current_user.id)

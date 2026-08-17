"""Currency reference used by the calculator, quotes and catalogue prices."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.currency import Currency
from app.schemas.currency import CurrencyResponse

router = APIRouter(prefix="/currencies", tags=["currencies"])


@router.get("", response_model=list[CurrencyResponse])
async def list_currencies(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Currency]:
    """Active currencies, most likely first — the same list everywhere money is shown."""
    rows = await db.execute(
        select(Currency)
        .where(Currency.active.is_(True))
        .order_by(Currency.sort_order, Currency.code)
    )
    return list(rows.scalars().all())

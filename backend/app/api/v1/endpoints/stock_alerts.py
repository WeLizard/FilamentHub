"""Low-stock alert rules and the alert feed the desktop plugin shows once each."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_stock_alerts_read
from app.db.session import get_db
from app.models.user import User
from app.services.stock_alert_service import (
    DEFAULT_THRESHOLD_G,
    delete_rule,
    list_alert_events,
    list_rules,
    upsert_rule,
)

router = APIRouter(prefix="/stock-alerts", tags=["stock-alerts"])


class StockAlertRuleBody(BaseModel):
    scope: Literal["all", "spool", "material"]
    spool_id: int | None = Field(default=None, ge=1)
    material_key: str | None = Field(default=None, max_length=40, pattern=r"^[fc]:\d{1,10}$")
    threshold_g: float = Field(default=DEFAULT_THRESHOLD_G, gt=0, le=100_000, allow_inf_nan=False)
    enabled: bool = True

    @model_validator(mode="after")
    def target_matches_scope(self) -> "StockAlertRuleBody":
        if (self.scope == "spool") != (self.spool_id is not None) or (
            (self.scope == "material") != (self.material_key is not None)
        ):
            raise ValueError("rule target does not match its scope")
        return self


class StockAlertRuleResponse(BaseModel):
    id: int
    scope: str
    spool_id: int | None
    material_key: str | None
    threshold_g: float
    enabled: bool

    model_config = {"from_attributes": True}


class StockAlertRulesResponse(BaseModel):
    default_threshold_g: float
    rules: list[StockAlertRuleResponse]


class StockAlertEvent(BaseModel):
    id: int
    type: str
    link: str | None
    extra_data: dict | None
    created_at: str


class StockAlertEventsResponse(BaseModel):
    items: list[StockAlertEvent]
    # Newest alert id, so a client starting fresh can begin after it without
    # replaying history.
    latest_id: int


@router.get("/rules", response_model=StockAlertRulesResponse)
async def get_rules(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StockAlertRulesResponse:
    rules = await list_rules(db, current_user.id)
    return StockAlertRulesResponse(
        default_threshold_g=DEFAULT_THRESHOLD_G,
        rules=[StockAlertRuleResponse.model_validate(rule) for rule in rules],
    )


@router.put("/rules", response_model=StockAlertRuleResponse)
async def put_rule(
    payload: StockAlertRuleBody,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StockAlertRuleResponse:
    rule = await upsert_rule(
        db,
        current_user.id,
        scope=payload.scope,
        spool_id=payload.spool_id,
        material_key_value=payload.material_key,
        threshold_g=payload.threshold_g,
        enabled=payload.enabled,
    )
    return StockAlertRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_rule(
    rule_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await delete_rule(db, current_user.id, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events", response_model=StockAlertEventsResponse)
async def get_events(
    current_user: Annotated[User, Depends(require_stock_alerts_read)],
    db: Annotated[AsyncSession, Depends(get_db)],
    after_id: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> StockAlertEventsResponse:
    rows, latest_id = await list_alert_events(db, current_user.id, after_id=after_id, limit=limit)
    return StockAlertEventsResponse(
        items=[
            StockAlertEvent(
                id=row.id,
                type=row.type.value,
                link=row.link,
                extra_data=row.extra_data,
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ],
        latest_id=latest_id,
    )

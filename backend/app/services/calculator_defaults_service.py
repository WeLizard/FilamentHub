"""Persistent platform defaults for newly created calculator profiles."""

import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.schemas.calculator import CalculatorProfileDefaults

logger = logging.getLogger(__name__)

SETTING_CALCULATOR_PROFILE_DEFAULTS = "calculator_profile_defaults_v1"


async def get_calculator_profile_defaults(
    db: AsyncSession,
) -> CalculatorProfileDefaults:
    """Return validated defaults, falling back safely if stored data is corrupt."""
    row = await db.scalar(
        select(AppSetting).where(AppSetting.key == SETTING_CALCULATOR_PROFILE_DEFAULTS)
    )
    if row is None or not row.value:
        return CalculatorProfileDefaults()
    try:
        payload = json.loads(row.value)
        return CalculatorProfileDefaults.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError):
        logger.exception("Invalid calculator profile defaults; using built-in values")
        return CalculatorProfileDefaults()


async def set_calculator_profile_defaults(
    db: AsyncSession,
    defaults: CalculatorProfileDefaults,
) -> CalculatorProfileDefaults:
    """Persist one complete validated defaults snapshot."""
    row = await db.scalar(
        select(AppSetting).where(AppSetting.key == SETTING_CALCULATOR_PROFILE_DEFAULTS)
    )
    value = json.dumps(defaults.model_dump(mode="json"), separators=(",", ":"))
    if row is None:
        db.add(AppSetting(key=SETTING_CALCULATOR_PROFILE_DEFAULTS, value=value))
    else:
        row.value = value
    await db.commit()
    return defaults


def calculator_profile_default_values(
    defaults: CalculatorProfileDefaults,
) -> dict[str, object]:
    """Convert validated defaults into UserCalculatorProfile constructor values."""
    return defaults.model_dump(mode="json")

"""Persistent platform defaults for newly created calculator profiles."""

import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.user import User
from app.schemas.calculator import (
    CalculatorCountryDefaultsMap,
    CalculatorProfileDefaults,
)
from app.services.currency_service import currency_for_country

logger = logging.getLogger(__name__)

SETTING_CALCULATOR_PROFILE_DEFAULTS = "calculator_profile_defaults_v1"
SETTING_CALCULATOR_COUNTRY_DEFAULTS = "calculator_profile_defaults_by_country_v1"


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


# Amounts of money. Everything else — watts, percentages, hours, rounding mode — means
# the same thing in every country.
MONETARY_DEFAULT_FIELDS: frozenset[str] = frozenset(
    {
        "electricity_cost_per_kwh",
        "modeling_rate_per_hour",
        "postprocessing_rate_per_hour",
        "printing_rate_per_hour",
        "amortization_rate_per_hour",
        "fixed_costs",
        "bed_prep_cost_per_print",
        "min_order_price",
        "round_to_nearest",
        "printer_purchase_price",
        "maintenance_cost_per_hour",
    }
)


def calculator_profile_default_values(
    defaults: CalculatorProfileDefaults,
    *,
    profile_currency: str | None = None,
) -> dict[str, object]:
    """Convert validated defaults into UserCalculatorProfile constructor values.

    A profile being created has no currency of its own yet, so it takes the one the
    defaults were written in along with the money. A profile that already exists keeps
    the currency its owner chose, and money crosses over only when the two agree:
    an hourly rate priced in one currency is not a starting point in another, it is a
    number wrong by the exchange rate.
    """
    values = defaults.model_dump(mode="json")
    defaults_currency = str(values.get("currency") or "RUB").upper()

    if profile_currency is None:
        values["currency"] = defaults_currency
        return values

    values.pop("currency", None)
    if profile_currency.upper() != defaults_currency:
        for field in MONETARY_DEFAULT_FIELDS:
            values.pop(field, None)
    return values


async def get_calculator_country_defaults(
    db: AsyncSession,
) -> CalculatorCountryDefaultsMap:
    """Return per-country overrides, falling back to an empty map if stored data is corrupt."""
    row = await db.scalar(
        select(AppSetting).where(AppSetting.key == SETTING_CALCULATOR_COUNTRY_DEFAULTS)
    )
    if row is None or not row.value:
        return CalculatorCountryDefaultsMap()
    try:
        payload = json.loads(row.value)
        return CalculatorCountryDefaultsMap.model_validate(payload)
    except (json.JSONDecodeError, TypeError, ValidationError):
        logger.exception("Invalid calculator country defaults; ignoring them")
        return CalculatorCountryDefaultsMap()


async def set_calculator_country_defaults(
    db: AsyncSession,
    defaults: CalculatorCountryDefaultsMap,
) -> CalculatorCountryDefaultsMap:
    """Persist the whole per-country table as one validated snapshot."""
    normalized = CalculatorCountryDefaultsMap(
        countries={
            code.strip().upper(): value
            for code, value in defaults.countries.items()
            if code.strip()
        }
    )
    value = json.dumps(normalized.model_dump(mode="json"), separators=(",", ":"))
    row = await db.scalar(
        select(AppSetting).where(AppSetting.key == SETTING_CALCULATOR_COUNTRY_DEFAULTS)
    )
    if row is None:
        db.add(AppSetting(key=SETTING_CALCULATOR_COUNTRY_DEFAULTS, value=value))
    else:
        row.value = value
    await db.commit()
    return normalized


def apply_country_defaults(
    defaults: CalculatorProfileDefaults,
    country_defaults: CalculatorCountryDefaultsMap,
    country: str | None,
) -> CalculatorProfileDefaults:
    """Overlay what is known for one country on top of the global starting economics.

    Only the fields an admin actually filled in for that country are applied; the rest
    keeps the global value, so a half-filled row never blanks out working numbers.
    """
    if not country:
        return defaults
    entry = country_defaults.countries.get(country.strip().upper())
    if entry is None:
        return defaults
    overrides = {
        field: value
        for field, value in entry.model_dump(mode="json").items()
        if value is not None
    }
    if not overrides:
        return defaults
    return defaults.model_copy(update=overrides)


async def starting_defaults_for_user(
    db: AsyncSession,
    user: User,
) -> tuple[CalculatorProfileDefaults, str]:
    """Starting economics for one person, and the currency their profile should use.

    These are two separate answers on purpose. The amounts were entered in the currency
    of the row they came from; the person bills in the currency of their country. When
    those differ the amounts do not belong to them, and returning the pair lets the
    caller drop the money instead of relabelling it.
    """
    defaults = await get_calculator_profile_defaults(db)
    country_defaults = await get_calculator_country_defaults(db)
    resolved = apply_country_defaults(defaults, country_defaults, user.country)

    # An admin who wrote a row for the country stated its currency along with its
    # amounts, and is the authority on both.
    entry = country_defaults.countries.get((user.country or "").strip().upper())
    if entry is not None and entry.currency:
        return resolved, resolved.currency

    country_currency = await currency_for_country(db, user.country)
    return resolved, country_currency or resolved.currency

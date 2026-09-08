"""What a machine costs to run, and what the calculator should charge for it.

Two jobs live here. Suggesting: a person should not have to know their printer's
average wattage before they can price a job, so we offer starting numbers from
what FilamentHub already knows about the machine, always as a hint they can
overrule. Resolving: the assigned machine-hour rate has to reach the calculator
without being counted twice, because electricity and wear are already separate
lines there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calculator_profile import UserCalculatorProfile
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.calculator_defaults_service import MONETARY_DEFAULT_FIELDS
from app.services.calculator_power_service import average_power_w

ECONOMICS_SOURCES = {
    "printer_explicit",
    "account_explicit",
    "orca_import",
    "platform_default",
    "catalog_estimate",
    "none",
}
PROFILE_ECONOMICS_FIELDS = frozenset(
    {
        "electricity_cost_per_kwh",
        "printer_power_w",
        "modeling_rate_per_hour",
        "postprocessing_rate_per_hour",
        "printing_rate_per_hour",
        "amortization_rate_per_hour",
        "overhead_percent",
        "markup_percent",
        "tax_rate_percent",
        "fixed_costs",
        "bed_prep_cost_per_print",
        "min_order_price",
        "round_to_nearest",
        "rounding_mode",
        "printer_purchase_price",
        "printer_useful_hours",
        "maintenance_cost_per_hour",
        "power_hotend_w",
        "power_bed_w",
        "power_steppers_w",
        "power_electronics_w",
        "currency",
    }
)

USAGE_LIFE_HOURS = {
    "occasional": 3000,
    "regular": 7000,
    "intensive": 12000,
}
DEFAULT_USAGE = "regular"

CLASS_COMPACT = "compact"
CLASS_STANDARD = "standard"
CLASS_LARGE = "large"
CLASS_LARGE_ENCLOSED = "large_enclosed"
CLASS_MULTI_TOOL = "multi_tool"
CLASS_RESIN = "resin"
CLASS_UNKNOWN = "unknown"

CLASS_POWER_W = {
    CLASS_COMPACT: 120.0,
    CLASS_STANDARD: 250.0,
    CLASS_LARGE: 350.0,
    CLASS_LARGE_ENCLOSED: 450.0,
    CLASS_MULTI_TOOL: 500.0,
    CLASS_RESIN: 80.0,
    CLASS_UNKNOWN: 350.0,
}
# The same wattage split into the parts that draw it: hotend, bed, motors, electronics.
# A total alone cannot say how a print's temperatures change the bill, and asking every
# shop to open its printer and measure four numbers is not a starting point.
# Resin has neither hotend nor heated bed, so its draw stays with the electronics.
CLASS_POWER_PARTS_W = {
    CLASS_COMPACT: (40.0, 55.0, 15.0, 10.0),
    CLASS_STANDARD: (50.0, 150.0, 30.0, 20.0),
    CLASS_LARGE: (60.0, 220.0, 45.0, 25.0),
    CLASS_LARGE_ENCLOSED: (70.0, 290.0, 55.0, 35.0),
    CLASS_MULTI_TOOL: (100.0, 300.0, 60.0, 40.0),
    CLASS_RESIN: (0.0, 0.0, 10.0, 70.0),
    CLASS_UNKNOWN: (60.0, 220.0, 45.0, 25.0),
}
CLASS_MAINTENANCE_PER_HOUR = {
    CLASS_COMPACT: 2.0,
    CLASS_STANDARD: 3.0,
    CLASS_LARGE: 5.0,
    CLASS_LARGE_ENCLOSED: 6.0,
    CLASS_MULTI_TOOL: 9.0,
    CLASS_RESIN: 4.0,
    CLASS_UNKNOWN: 5.0,
}
# A heated bed draws roughly this per square centimetre. The relation is close to
# linear because the bed is a resistive sheet: doubling its area doubles the heater.
# Better than a per-class figure, which puts a 180×180 and a 350×350 in one bracket.
#
# The two figures are the two kinds of bed. Small machines carry a low-voltage PCB
# heater; past roughly 300 mm the practical choice is a mains silicone mat, which runs
# noticeably hotter per square centimetre. Size is what decides which one a machine has,
# so it is also what decides the figure.
BED_W_PER_CM2_PCB = 0.28
BED_W_PER_CM2_SILICONE = 0.45
BED_SILICONE_FROM_MM = 300.0
BED_W_MIN = 40.0
BED_W_MAX = 800.0

CONFIDENCE_MODEL = "model"
CONFIDENCE_CLASS = "class"
CONFIDENCE_MODIFIED = "modified"

_SELF_BUILT_VENDORS = {"voron", "ratrig", "rat rig", "vzbot", "hevort", "vcore"}
_MODDED_VENDORS = {"creality", "anet", "anycubic", "elegoo", "artillery", "sovol"}
_TRUSTED_VENDORS = {"bambu lab", "bambulab", "prusa", "prusa research", "ultimaker", "raise3d"}


@dataclass
class MachineProfile:
    """What we could tell about the machine before anyone typed a number."""

    machine_class: str = CLASS_UNKNOWN
    confidence: str = CONFIDENCE_CLASS
    vendor: str | None = None
    model_name: str | None = None
    bed_max_mm: float | None = None
    bed_area_cm2: float | None = None
    extruders: int = 1
    orca_time_cost: float | None = None


@dataclass
class EconomicsSuggestion:
    machine: MachineProfile
    average_power_watts: float
    power_hotend_w: float
    power_bed_w: float
    power_steppers_w: float
    power_electronics_w: float
    useful_life_hours: int
    maintenance_cost_per_hour: float
    usage: str


@dataclass
class ResolvedEconomics:
    """Numbers the calculator can use, already free of double counting."""

    printer_power_w: float
    amortization_rate_per_hour: float
    printing_rate_per_hour: float
    electricity_cost_per_kwh: float
    currency: str | None

    machine_hour_rate: float
    depreciation_per_hour: float
    electricity_per_hour: float
    maintenance_per_hour: float
    machine_cost_per_hour: float
    rate_below_cost: bool
    sources: dict[str, str] = field(default_factory=dict)
    applied_sources: dict[str, str] = field(default_factory=dict)
    readiness: "EconomicsReadiness" | None = None


@dataclass(frozen=True)
class EconomicsReadinessFieldValue:
    key: str
    value: float | str | None
    source: str
    source_currency: str | None
    usable: bool
    missing_reason: str | None = None


@dataclass(frozen=True)
class EconomicsReadiness:
    version: int
    status: str
    money_currency: str | None
    required_fields: list[EconomicsReadinessFieldValue]
    reasons: list[str]


def _positive(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _currency_code(value: str | None) -> str | None:
    code = (value or "").strip().upper()
    return code or None


def _non_negative(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _stored_source(mapping: object, field_name: str) -> str:
    if not isinstance(mapping, dict):
        return "none"
    source = mapping.get(field_name)
    return source if source in ECONOMICS_SOURCES else "none"


def platform_default_economics_sources(
    values: dict[str, object] | None = None, *, include_currency: bool = True
) -> dict[str, str]:
    """Mark a freshly seeded profile without calling its defaults user input."""
    fields = (
        PROFILE_ECONOMICS_FIELDS
        if include_currency
        else PROFILE_ECONOMICS_FIELDS - {"currency"}
    )
    selected_fields = fields if values is None else set(values) & fields
    return {field_name: "platform_default" for field_name in selected_fields}


def update_account_economics_sources(
    profile: UserCalculatorProfile,
    field_names: set[str],
    source: str,
) -> None:
    """Assign field provenance without inferring anything about untouched values."""
    sources = dict(profile.economics_field_sources or {})
    for field_name in field_names & PROFILE_ECONOMICS_FIELDS:
        sources[field_name] = source
    profile.economics_field_sources = sources


def clear_incompatible_account_money(
    profile: UserCalculatorProfile,
    *,
    previous_currency: str | None,
    explicit_fields: set[str],
) -> set[str]:
    """Clear old-currency amounts unless the same request replaces them.

    No exchange-rate contract exists, so retaining a number while changing only
    its currency code would relabel rather than convert it. Percentages, physical
    values, useful life and rounding mode are currency-independent and stay intact.
    """
    if _currency_code(previous_currency) == _currency_code(profile.currency):
        return set()

    cleared_fields = set(MONETARY_DEFAULT_FIELDS) - explicit_fields
    sources = dict(profile.economics_field_sources or {})
    for field_name in cleared_fields:
        setattr(profile, field_name, 0)
        sources.pop(field_name, None)
    profile.economics_field_sources = sources
    return cleared_fields


def _combined_source(sources: list[str], *, fallback: str = "none") -> str:
    present = [source for source in sources if source != "none"]
    if not present:
        return fallback
    if len(present) != len(sources):
        return "none"
    if "catalog_estimate" in present:
        return "catalog_estimate"
    return present[0] if len(set(present)) == 1 else "none"


def _readiness(
    *,
    currency: str | None,
    fields: list[EconomicsReadinessFieldValue],
    extra_reasons: list[str] | None = None,
) -> EconomicsReadiness:
    reasons = list(extra_reasons or [])
    for item in fields:
        if item.missing_reason and item.missing_reason not in reasons:
            reasons.append(item.missing_reason)
        if item.usable and item.source == "none" and "provenance_unknown" not in reasons:
            reasons.append("provenance_unknown")
        if item.source == "platform_default" and "platform_default_used" not in reasons:
            reasons.append("platform_default_used")
        if item.source == "catalog_estimate" and "catalog_estimate_used" not in reasons:
            reasons.append("catalog_estimate_used")

    if any(not item.usable for item in fields):
        readiness_status = "incomplete"
    elif reasons:
        readiness_status = "partial"
    else:
        readiness_status = "configured"
    return EconomicsReadiness(
        version=1,
        status=readiness_status,
        money_currency=currency,
        required_fields=fields,
        reasons=reasons,
    )


def account_economics_readiness(profile: UserCalculatorProfile) -> EconomicsReadiness:
    """Resolve account economics without mistaking seeded values for user choices."""
    currency = _currency_code(profile.currency)
    sources = profile.economics_field_sources or {}

    rate = _non_negative(profile.printing_rate_per_hour)
    tariff = _non_negative(profile.electricity_cost_per_kwh)
    power = _positive(profile.printer_power_w)
    wear = _non_negative(profile.amortization_rate_per_hour)
    fields = [
        EconomicsReadinessFieldValue(
            key="currency",
            value=currency,
            source=_stored_source(sources, "currency"),
            source_currency=currency,
            usable=currency is not None,
            missing_reason=None if currency is not None else "missing_currency",
        ),
        EconomicsReadinessFieldValue(
            key="machine_hour_rate",
            value=rate,
            source=_stored_source(sources, "printing_rate_per_hour"),
            source_currency=currency,
            usable=rate is not None and rate > 0,
            missing_reason="non_positive" if rate == 0 else "missing" if rate is None else None,
        ),
        EconomicsReadinessFieldValue(
            key="electricity_cost_per_kwh",
            value=tariff,
            source=_stored_source(sources, "electricity_cost_per_kwh"),
            source_currency=currency,
            usable=tariff is not None,
            missing_reason=None if tariff is not None else "missing",
        ),
        EconomicsReadinessFieldValue(
            key="printer_power_w",
            value=power,
            source=_stored_source(sources, "printer_power_w"),
            source_currency=None,
            usable=power is not None,
            missing_reason=None if power is not None else "missing",
        ),
        EconomicsReadinessFieldValue(
            key="machine_wear_per_hour",
            value=wear,
            source=_stored_source(sources, "amortization_rate_per_hour"),
            source_currency=currency,
            usable=wear is not None,
            missing_reason=None if wear is not None else "missing",
        ),
    ]
    return _readiness(currency=currency, fields=fields)


def _parse_orca_time_cost(raw: object) -> float | None:
    """Orca writes its config values as strings, and lists for multi-extruder."""
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _classify(
    bed_max_mm: float | None, extruders: int, vendor: str | None, technology: str | None
) -> str:
    if technology and technology.upper() in {"SLA", "DLP", "MSLA", "LCD"}:
        return CLASS_RESIN
    if extruders > 1:
        return CLASS_MULTI_TOOL
    if bed_max_mm is None:
        return CLASS_UNKNOWN
    if bed_max_mm <= 150:
        return CLASS_COMPACT
    if bed_max_mm <= 260:
        return CLASS_STANDARD
    if bed_max_mm <= 320:
        return CLASS_LARGE
    return CLASS_LARGE_ENCLOSED


def _confidence(vendor: str | None) -> str:
    name = (vendor or "").strip().lower()
    if not name:
        return CONFIDENCE_CLASS
    if any(name.startswith(known) for known in _SELF_BUILT_VENDORS):
        return CONFIDENCE_MODIFIED
    if any(name.startswith(known) for known in _MODDED_VENDORS):
        return CONFIDENCE_MODIFIED
    if any(name.startswith(known) for known in _TRUSTED_VENDORS):
        return CONFIDENCE_MODEL
    return CONFIDENCE_CLASS


async def describe_machine(db: AsyncSession, printer: UserPrinterDevice) -> MachineProfile:
    """Read the machine from the catalog model and its OrcaSlicer configurations."""
    profile = MachineProfile()

    if printer.printer_id is not None:
        catalog = await db.get(Printer, printer.printer_id)
        if catalog is not None:
            profile.vendor = catalog.manufacturer or catalog.vendor
            profile.model_name = catalog.name
            sizes = [
                size
                for size in (catalog.build_volume_x, catalog.build_volume_y)
                if size is not None
            ]
            if sizes:
                profile.bed_max_mm = max(sizes)
            if catalog.technology:
                profile.machine_class = _classify(
                    profile.bed_max_mm, 1, profile.vendor, catalog.technology
                )

    configurations = (
        await db.execute(
            select(PrinterProfile)
            .join(
                UserPrinterProfileLink,
                UserPrinterProfileLink.printer_profile_id == PrinterProfile.id,
            )
            .where(UserPrinterProfileLink.physical_printer_id == printer.id)
            .order_by(PrinterProfile.id)
        )
    ).scalars().all()

    technology = None
    for configuration in configurations:
        settings = configuration.orcaslicer_settings or {}
        if profile.orca_time_cost is None:
            profile.orca_time_cost = _parse_orca_time_cost(settings.get("time_cost"))
        nozzles = configuration.nozzle_diameters or settings.get("nozzle_diameter")
        if isinstance(nozzles, (list, tuple)) and len(nozzles) > profile.extruders:
            profile.extruders = len(nozzles)
        dimensions = _bed_dimensions(configuration.printable_area)
        if dimensions is not None:
            width_mm, depth_mm = dimensions
            longest = max(width_mm, depth_mm)
            if profile.bed_max_mm is None or longest > profile.bed_max_mm:
                profile.bed_max_mm = longest
            area_cm2 = (width_mm * depth_mm) / 100.0
            if profile.bed_area_cm2 is None or area_cm2 > profile.bed_area_cm2:
                profile.bed_area_cm2 = area_cm2
        technology = technology or settings.get("printer_technology")
        profile.vendor = profile.vendor or configuration.vendor

    profile.machine_class = _classify(
        profile.bed_max_mm, profile.extruders, profile.vendor, technology
    )
    profile.confidence = _confidence(profile.vendor)
    return profile


def _bed_dimensions(area: object) -> tuple[float, float] | None:
    """Bed width and depth in millimetres, from either shape Orca ships.

    Most profiles carry ``x_min``/``x_max``; a minority carry plain ``x``/``y``.
    Reading only one shape leaves the size unknown for almost the whole catalogue.
    """
    if not isinstance(area, dict):
        return None

    span_x = _positive(area.get("x")) or _positive(area.get("width"))
    span_y = _positive(area.get("y")) or _positive(area.get("depth"))
    if span_x is None and area.get("x_max") is not None:
        span_x = _positive(float(area["x_max"]) - float(area.get("x_min") or 0.0))
    if span_y is None and area.get("y_max") is not None:
        span_y = _positive(float(area["y_max"]) - float(area.get("y_min") or 0.0))

    if span_x is None or span_y is None:
        return None
    return span_x, span_y


async def suggest_economics(
    db: AsyncSession, printer: UserPrinterDevice, usage: str = DEFAULT_USAGE
) -> EconomicsSuggestion:
    """Starting numbers for a machine nobody has measured."""
    machine = await describe_machine(db, printer)
    usage_key = usage if usage in USAGE_LIFE_HOURS else DEFAULT_USAGE
    hotend_w, bed_w, steppers_w, electronics_w = CLASS_POWER_PARTS_W[machine.machine_class]
    # A known bed size beats the class bracket: the heater scales with the sheet.
    if bed_w > 0 and machine.bed_area_cm2:
        per_cm2 = (
            BED_W_PER_CM2_SILICONE
            if (machine.bed_max_mm or 0) >= BED_SILICONE_FROM_MM
            else BED_W_PER_CM2_PCB
        )
        bed_w = min(BED_W_MAX, max(BED_W_MIN, machine.bed_area_cm2 * per_cm2))
    return EconomicsSuggestion(
        machine=machine,
        average_power_watts=CLASS_POWER_W[machine.machine_class],
        power_hotend_w=hotend_w,
        power_bed_w=bed_w,
        power_steppers_w=steppers_w,
        power_electronics_w=electronics_w,
        useful_life_hours=USAGE_LIFE_HOURS[usage_key],
        maintenance_cost_per_hour=CLASS_MAINTENANCE_PER_HOUR[machine.machine_class],
        usage=usage_key,
    )


async def _account_profile(db: AsyncSession, user_id: int) -> UserCalculatorProfile | None:
    return await db.scalar(
        select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == user_id)
    )


async def lock_account_economics_profile(
    db: AsyncSession, user_id: int
) -> UserCalculatorProfile | None:
    """Serialize account economics writes, including first-profile creation."""
    await db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    return await db.scalar(
        select(UserCalculatorProfile)
        .where(UserCalculatorProfile.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def resolve_economics(
    db: AsyncSession, printer: UserPrinterDevice
) -> ResolvedEconomics:
    """Turn what is known about a machine into the calculator's own fields.

    The rate a person charges already covers wear, power and upkeep, so it is
    split: the cost part fills the lines that exist for it, and only what is
    left over rides on the printing rate. Their sum per hour is the rate again.
    """
    account = await _account_profile(db, printer.user_id)
    account_sources = account.economics_field_sources if account else {}
    printer_sources = printer.economics_field_sources or {}
    account_currency = _currency_code(account.currency if account else None)
    printer_currency = _currency_code(printer.economics_currency)
    currency = account_currency or printer_currency
    currency_source = (
        _stored_source(account_sources, "currency")
        if account_currency is not None
        else _stored_source(printer_sources, "economics_currency")
    )
    printer_money_usable = (
        printer_currency is not None
        and currency is not None
        and printer_currency == currency
    )
    printer_has_money = any(
        value is not None
        for value in (
            printer.purchase_cost,
            printer.residual_value,
            printer.maintenance_cost_per_hour,
            printer.machine_hour_rate,
        )
    )
    extra_reasons: list[str] = []
    sources: dict[str, str] = {}
    if printer_has_money and not printer_money_usable:
        sources["printer_money"] = "currency_mismatch"
        extra_reasons.append(
            "missing_currency" if printer_currency is None else "currency_mismatch"
        )

    tariff_value = _non_negative(account.electricity_cost_per_kwh if account else None)
    tariff = tariff_value if tariff_value is not None else 0.0
    tariff_source = _stored_source(account_sources, "electricity_cost_per_kwh")

    component_fields = {
        "power_hotend_w": printer.power_hotend_w,
        "power_bed_w": printer.power_bed_w,
        "power_steppers_w": printer.power_steppers_w,
        "power_electronics_w": printer.power_electronics_w,
    }
    provided_power_parts = [
        field_name for field_name, value in component_fields.items() if value is not None
    ]
    complete_power_parts = len(provided_power_parts) == len(component_fields)
    if provided_power_parts and not complete_power_parts:
        extra_reasons.append("incomplete_pair")

    power = None
    power_source = "none"
    if complete_power_parts:
        power = _positive(
            average_power_w(
                hotend_w=printer.power_hotend_w,
                bed_w=printer.power_bed_w,
                steppers_w=printer.power_steppers_w,
                electronics_w=printer.power_electronics_w,
            )
        )
        if power is not None:
            power_source = _combined_source(
                [
                    _stored_source(printer_sources, field_name)
                    for field_name in component_fields
                ]
            )
            sources["power"] = "printer"

    if power is None:
        power = _positive(printer.average_power_watts)
        if power is not None:
            power_source = _stored_source(printer_sources, "average_power_watts")
            sources["power"] = "printer"

    if power is None:
        power = _positive(account.printer_power_w if account else None)
        if power is not None:
            power_source = _stored_source(account_sources, "printer_power_w")
            sources["power"] = "account"

    if power is None:
        suggestion = await suggest_economics(db, printer)
        power = average_power_w(
            hotend_w=suggestion.power_hotend_w,
            bed_w=suggestion.power_bed_w,
            steppers_w=suggestion.power_steppers_w,
            electronics_w=suggestion.power_electronics_w,
            fallback_w=suggestion.average_power_watts,
        )
        if power is not None:
            power_source = "catalog_estimate"
            sources["power"] = "estimate"
    if power is None:
        power = 0.0
        sources["power"] = "none"

    depreciation = 0.0
    depreciation_source = "none"
    maintenance = 0.0
    maintenance_source = "none"
    printer_depreciation_complete = False
    printer_maintenance_complete = False
    printer_wear_attempted = any(
        value is not None
        for value in (
            printer.purchase_cost,
            printer.residual_value,
            printer.useful_life_hours,
            printer.maintenance_cost_per_hour,
        )
    )
    if printer_money_usable:
        purchase = _non_negative(printer.purchase_cost)
        residual_value = _non_negative(printer.residual_value)
        residual = residual_value if residual_value is not None else 0.0
        life_hours = _positive(printer.useful_life_hours)
        if purchase is not None:
            if purchase == 0:
                printer_depreciation_complete = True
                depreciation_source = _stored_source(printer_sources, "purchase_cost")
            elif life_hours is not None:
                depreciation = max(0.0, purchase - residual) / life_hours
                printer_depreciation_complete = True
                depreciation_sources = [
                    _stored_source(printer_sources, "purchase_cost"),
                    _stored_source(printer_sources, "useful_life_hours"),
                ]
                if printer.residual_value is not None:
                    depreciation_sources.append(
                        _stored_source(printer_sources, "residual_value")
                    )
                depreciation_source = _combined_source(depreciation_sources)

        if printer.maintenance_cost_per_hour is not None:
            maintenance_value = _non_negative(printer.maintenance_cost_per_hour)
            if maintenance_value is not None:
                maintenance = maintenance_value
                maintenance_source = _stored_source(
                    printer_sources, "maintenance_cost_per_hour"
                )
                printer_maintenance_complete = True

    printer_wear_complete = (
        printer_money_usable
        and printer_depreciation_complete
        and printer_maintenance_complete
    )
    if printer_money_usable and printer_wear_attempted and not printer_wear_complete:
        extra_reasons.append("incomplete_pair")

    account_wear = _non_negative(
        account.amortization_rate_per_hour if account else None
    )
    if printer_wear_complete:
        wear_and_upkeep = depreciation + maintenance
        wear_source = _combined_source(
            [depreciation_source, maintenance_source], fallback="none"
        )
        sources["wear"] = "printer"
        sources["depreciation"] = "printer"
        sources["maintenance"] = "printer"
    else:
        # Account amortization is an aggregate wear/upkeep value. It replaces an
        # incomplete printer override as a whole; adding one printer component to
        # it would silently double count part of the same cost.
        depreciation = 0.0
        maintenance = 0.0
        depreciation_source = "none"
        maintenance_source = "none"
        wear_and_upkeep = account_wear if account_wear is not None else 0.0
        wear_source = _stored_source(account_sources, "amortization_rate_per_hour")
        sources["wear"] = "account" if account_wear is not None else "none"

    electricity_per_hour = power / 1000.0 * tariff

    rate: float | None = None
    rate_source = "none"
    rate_missing_reason: str | None = None
    printer_rate = _non_negative(printer.machine_hour_rate)
    if printer.machine_hour_rate is not None and printer_money_usable:
        rate = printer_rate
        rate_source = _stored_source(printer_sources, "machine_hour_rate")
        sources["rate"] = "printer"
    else:
        account_rate = _non_negative(account.printing_rate_per_hour if account else None)
        account_rate_source = _stored_source(account_sources, "printing_rate_per_hour")
        account_rate_is_explicit_zero = (
            account_rate == 0 and account_rate_source == "account_explicit"
        )
        if account_rate is not None and (account_rate > 0 or account_rate_is_explicit_zero):
            rate = account_rate
            rate_source = account_rate_source
            sources["rate"] = "account"
        else:
            machine = await describe_machine(db, printer)
            if machine.orca_time_cost is not None and printer_currency is not None:
                if currency is None or printer_currency == currency:
                    rate = machine.orca_time_cost
                    rate_source = "orca_import"
                    sources["rate"] = "orca"
                else:
                    rate_missing_reason = "currency_mismatch"
            elif machine.orca_time_cost is not None:
                rate_missing_reason = "missing_currency"
            sources.setdefault("rate", "none")

    if rate == 0:
        rate_missing_reason = "non_positive"
    elif rate is None and rate_missing_reason is None:
        rate_missing_reason = "missing"

    machine_cost = wear_and_upkeep + electricity_per_hour
    margin = rate - machine_cost if rate is not None else 0.0
    required_fields = [
        EconomicsReadinessFieldValue(
            key="currency",
            value=currency,
            source=currency_source,
            source_currency=currency,
            usable=currency is not None,
            missing_reason=None if currency is not None else "missing_currency",
        ),
        EconomicsReadinessFieldValue(
            key="machine_hour_rate",
            value=rate,
            source=rate_source,
            source_currency=(
                printer_currency
                if rate_source in {"printer_explicit", "catalog_estimate", "orca_import"}
                else account_currency
            ),
            usable=rate is not None and rate > 0,
            missing_reason=rate_missing_reason,
        ),
        EconomicsReadinessFieldValue(
            key="electricity_cost_per_kwh",
            value=tariff_value,
            source=tariff_source,
            source_currency=account_currency,
            usable=tariff_value is not None,
            missing_reason=None if tariff_value is not None else "missing",
        ),
        EconomicsReadinessFieldValue(
            key="printer_power_w",
            value=power if power > 0 else None,
            source=power_source,
            source_currency=None,
            usable=power > 0,
            missing_reason=None if power > 0 else "missing",
        ),
        EconomicsReadinessFieldValue(
            key="machine_wear_per_hour",
            value=(
                wear_and_upkeep if printer_wear_complete or account_wear is not None else None
            ),
            source=wear_source,
            source_currency=(printer_currency if printer_wear_complete else account_currency),
            usable=printer_wear_complete or account_wear is not None,
            missing_reason=(
                None if printer_wear_complete or account_wear is not None else "missing"
            ),
        ),
    ]
    readiness = _readiness(
        currency=currency,
        fields=required_fields,
        extra_reasons=extra_reasons,
    )
    return ResolvedEconomics(
        printer_power_w=power,
        amortization_rate_per_hour=wear_and_upkeep,
        printing_rate_per_hour=max(0.0, margin),
        electricity_cost_per_kwh=tariff,
        currency=currency,
        machine_hour_rate=rate or 0.0,
        depreciation_per_hour=depreciation,
        electricity_per_hour=electricity_per_hour,
        maintenance_per_hour=maintenance,
        machine_cost_per_hour=machine_cost,
        rate_below_cost=rate is not None and rate > 0 and margin < 0,
        sources=sources,
        applied_sources={
            "currency": currency_source,
            "machine_hour_rate": rate_source,
            "electricity_cost_per_kwh": tariff_source,
            "printer_power_w": power_source,
            "machine_wear_per_hour": wear_source,
            "depreciation_per_hour": depreciation_source,
            "maintenance_per_hour": maintenance_source,
        },
        readiness=readiness,
    )

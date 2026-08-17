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
from app.models.user_printer_device import UserPrinterDevice
from app.services.calculator_power_service import average_power_w

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

    machine_hour_rate: float
    depreciation_per_hour: float
    electricity_per_hour: float
    maintenance_per_hour: float
    machine_cost_per_hour: float
    rate_below_cost: bool
    sources: dict[str, str] = field(default_factory=dict)


def _positive(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


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


async def resolve_economics(
    db: AsyncSession, printer: UserPrinterDevice
) -> ResolvedEconomics:
    """Turn what is known about a machine into the calculator's own fields.

    The rate a person charges already covers wear, power and upkeep, so it is
    split: the cost part fills the lines that exist for it, and only what is
    left over rides on the printing rate. Their sum per hour is the rate again.
    """
    account = await _account_profile(db, printer.user_id)
    tariff = _positive(account.electricity_cost_per_kwh if account else None) or 0.0
    sources: dict[str, str] = {}

    # Known parts win over the nameplate: an hour of printing is mostly heaters holding
    # a temperature, not every component at full draw.
    power = average_power_w(
        hotend_w=printer.power_hotend_w,
        bed_w=printer.power_bed_w,
        steppers_w=printer.power_steppers_w,
        electronics_w=printer.power_electronics_w,
        fallback_w=_positive(printer.average_power_watts),
    )
    if power:
        sources["power"] = "printer"
    else:
        power = _positive(account.printer_power_w if account else None) or 0.0
        sources["power"] = "account" if power else "none"

    if not power:
        # Nothing anywhere. What we can work out about this machine beats charging the
        # order as though the printer drew nothing at all.
        suggestion = await suggest_economics(db, printer)
        power = average_power_w(
            hotend_w=suggestion.power_hotend_w,
            bed_w=suggestion.power_bed_w,
            steppers_w=suggestion.power_steppers_w,
            electronics_w=suggestion.power_electronics_w,
            fallback_w=suggestion.average_power_watts,
        ) or 0.0
        if power:
            sources["power"] = "estimate"

    purchase = _positive(printer.purchase_cost)
    residual = max(0.0, float(printer.residual_value or 0.0))
    life_hours = _positive(printer.useful_life_hours)
    depreciation = 0.0
    if purchase is not None and life_hours is not None:
        depreciation = max(0.0, (purchase - residual)) / life_hours
        sources["depreciation"] = "printer"

    maintenance = max(0.0, float(printer.maintenance_cost_per_hour or 0.0))
    if printer.maintenance_cost_per_hour is not None:
        sources["maintenance"] = "printer"

    wear_and_upkeep = depreciation + maintenance
    if "depreciation" not in sources and "maintenance" not in sources:
        wear_and_upkeep = float(account.amortization_rate_per_hour if account else 0.0)
        sources["wear"] = "account"
    else:
        sources["wear"] = "printer"

    electricity_per_hour = power / 1000.0 * tariff

    machine = await describe_machine(db, printer)
    rate = machine.orca_time_cost
    if rate is not None:
        sources["rate"] = "orca"
    else:
        rate = _positive(printer.machine_hour_rate)
        if rate is not None:
            sources["rate"] = "printer"
    if rate is None:
        account_printing = float(account.printing_rate_per_hour if account else 0.0)
        sources["rate"] = "account"
        return ResolvedEconomics(
            printer_power_w=power,
            amortization_rate_per_hour=wear_and_upkeep,
            printing_rate_per_hour=account_printing,
            electricity_cost_per_kwh=tariff,
            machine_hour_rate=account_printing + wear_and_upkeep + electricity_per_hour,
            depreciation_per_hour=depreciation,
            electricity_per_hour=electricity_per_hour,
            maintenance_per_hour=maintenance,
            machine_cost_per_hour=wear_and_upkeep + electricity_per_hour,
            rate_below_cost=False,
            sources=sources,
        )

    machine_cost = wear_and_upkeep + electricity_per_hour
    margin = rate - machine_cost
    return ResolvedEconomics(
        printer_power_w=power,
        amortization_rate_per_hour=wear_and_upkeep,
        printing_rate_per_hour=max(0.0, margin),
        electricity_cost_per_kwh=tariff,
        machine_hour_rate=rate,
        depreciation_per_hour=depreciation,
        electricity_per_hour=electricity_per_hour,
        maintenance_per_hour=maintenance,
        machine_cost_per_hour=machine_cost,
        rate_below_cost=margin < 0,
        sources=sources,
    )

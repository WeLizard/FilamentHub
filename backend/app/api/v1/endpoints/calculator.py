"""Calculator endpoints."""

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capacity import Gate
from app.core.config import settings
from app.core.dependencies import get_current_verified_user, require_calculator_access
from app.core.errors import (
    ERR_CALCULATOR_HISTORY_NOT_FOUND,
    ERR_CALCULATOR_TRIAL_ALREADY_USED,
    ERR_FILE_TOO_LARGE,
    ERR_GCODE_PARSE_FAILED,
    ERR_INVALID_FILE_EXT,
    ERR_PDF_GENERATION_FAILED,
    ERR_PRICE_PER_HOUR_REQUIRED,
    ERR_SHARED_QUOTE_EXPIRED,
    ERR_SHARED_QUOTE_NOT_FOUND,
    ERR_SPOOL_PRICE_REQUIRED,
    ERR_TIME_REQUIRED,
    ERR_UNSUPPORTED_PRICING_METHOD,
    ERR_WEIGHT_REQUIRED,
    raise_error,
)
from app.core.field_encryption import decrypt_field, encrypt_field
from app.db.session import get_db
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.calculator_profile import UserCalculatorProfile
from app.models.print_job import PrintJob
from app.models.shared_quote import SharedQuote
from app.models.user import User
from app.schemas.calculator import (
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
    CalculatorGcodeParseResponse,
    CalculatorHistoryEntryCreate,
    CalculatorHistoryEntryListResponse,
    CalculatorHistoryEntryResponse,
    CalculatorHistoryParsedJob,
    CalculatorMaterialLineCost,
    CalculatorMaterialRoleCost,
    CalculatorPreflightRequest,
    CalculatorPreflightResponse,
    CalculatorProfileDefaults,
    CalculatorProfileResponse,
    CalculatorProfileUpdate,
    PricingMethod,
    RoundingMode,
    SharedQuoteCreate,
    SharedQuoteResponse,
)
from app.schemas.user import UserResponse
from app.services.calculator_defaults_service import (
    calculator_profile_default_values,
    get_calculator_profile_defaults,
)
from app.services.calculator_gcode_parser import (
    SUPPORTED_GCODE_EXTENSIONS,
    is_supported_gcode_filename,
    parse_gcode_payload,
)
from app.services.calculator_material_identity_service import (
    resolve_calculator_material_identities,
)
from app.services.calculator_preflight_service import calculate_material_preflight
from app.services.subscription_service import (
    TrialAlreadyUsedError,
    paywall_enforced,
    start_trial,
)
from app.services.usage_metrics_service import record_calculator_estimate

router = APIRouter(prefix="/calculator", tags=["calculator"])
logger = logging.getLogger(__name__)

_pdf_gate = Gate("pdf", settings.PDF_RENDER_CONCURRENCY, settings.PDF_RENDER_WAIT_SECONDS)
_gcode_gate = Gate("gcode", settings.GCODE_PARSE_CONCURRENCY, settings.GCODE_PARSE_WAIT_SECONDS)


def _parse_gcode_bytes(file_name: str, raw_bytes: bytes, plate_index: int | None):
    """Named so the gate has something to call with plain arguments."""
    return parse_gcode_payload(file_name=file_name, raw_bytes=raw_bytes, plate_index=plate_index)


@router.post("/start-trial", response_model=UserResponse)
async def start_calculator_trial(
    current_user: Annotated[User, Depends(get_current_verified_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Activate the current user's one-time Calculator Pro trial."""
    if not paywall_enforced():
        return UserResponse.model_validate(current_user)

    try:
        await start_trial(db, current_user)
    except TrialAlreadyUsedError:
        raise_error(status.HTTP_409_CONFLICT, ERR_CALCULATOR_TRIAL_ALREADY_USED)

    await db.refresh(current_user, attribute_names=["subscription"])
    return UserResponse.model_validate(current_user)


def _convert_time_to_hours(
    hours: float | None = None,
    minutes: float | None = None,
    seconds: float | None = None,
) -> float:
    """Конвертировать время в часы."""
    total_hours = hours or 0.0
    if minutes:
        total_hours += minutes / 60.0
    if seconds:
        total_hours += seconds / 3600.0
    return total_hours


def _apply_rounding(value: float, step: int, mode: RoundingMode) -> float:
    """Apply configurable commercial rounding to a positive price."""
    if step <= 0:
        return value

    normalized = value / step
    if mode == RoundingMode.DOWN:
        return math.floor(normalized) * step
    if mode == RoundingMode.NEAREST:
        return math.floor(normalized + 0.5) * step
    return math.ceil(normalized) * step


def _calculate_tax(value: float, tax_rate_percent: float | None) -> float:
    """Calculate tax amount for a taxable subtotal."""
    if not tax_rate_percent or tax_rate_percent <= 0 or value <= 0:
        return 0.0
    return value * (tax_rate_percent / 100.0)


def _machine_hours_by_rate(
    data: CalculatorEstimateRequest,
    time_hours_total: float,
) -> list[tuple[float, float | None, float | None, float | None]]:
    """Split machine time into stretches priced at their own machine's rates.

    Returns (hours, printing rate, amortization rate, power) per stretch. Without
    per-plate machines this is one stretch on the order-wide rates, so an order that
    never names a printer keeps costing exactly what it used to.
    """
    if not data.print_jobs:
        return [(
            time_hours_total,
            data.printing_rate_per_hour,
            data.amortization_rate_per_hour,
            data.printer_power_w,
        )]

    return [
        (
            (job.print_time_seconds * job.repeats) / 3600.0,
            job.printing_rate_per_hour
            if job.printing_rate_per_hour is not None
            else data.printing_rate_per_hour,
            job.amortization_rate_per_hour
            if job.amortization_rate_per_hour is not None
            else data.amortization_rate_per_hour,
            job.printer_power_w if job.printer_power_w is not None else data.printer_power_w,
        )
        for job in data.print_jobs
    ]


def _resolve_print_execution(
    data: CalculatorEstimateRequest,
) -> tuple[int, int, float, float, dict[str, int]]:
    """Resolve commercial output and machine execution without conflating objects with beds."""
    if data.print_jobs:
        repeats_by_job = {job.job_key: job.repeats for job in data.print_jobs}
        quantity = sum(job.output_quantity_per_run * job.repeats for job in data.print_jobs)
        print_runs = sum(job.repeats for job in data.print_jobs)
        time_hours_total = (
            sum(job.print_time_seconds * job.repeats for job in data.print_jobs) / 3600.0
        )
        average_time_per_run = time_hours_total / print_runs
        return quantity, print_runs, average_time_per_run, time_hours_total, repeats_by_job

    quantity = data.quantity
    parts_per_print = max(1, min(quantity, data.parts_per_print or 1))
    print_runs = math.ceil(quantity / parts_per_print)
    time_hours_per_run = _convert_time_to_hours(
        data.time_hours,
        data.time_minutes,
        data.time_sec,
    )
    return quantity, print_runs, time_hours_per_run, time_hours_per_run * print_runs, {}


def _material_line_multiplier(
    job_key: str | None,
    quantity: int,
    repeats_by_job: dict[str, int],
) -> int:
    """Use the owning plate repeat count when structured print jobs are present."""
    if repeats_by_job:
        return repeats_by_job[job_key or ""]
    return quantity


def _calculate_material_lines(
    data: CalculatorEstimateRequest,
    quantity: int,
    repeats_by_job: dict[str, int],
) -> tuple[float, float, list[CalculatorMaterialLineCost]]:
    """Calculate material cost with per-tool provenance when lines are supplied."""
    total_cost = 0.0
    total_weight_g = 0.0
    resolved: list[CalculatorMaterialLineCost] = []

    for line in data.material_lines:
        price_per_gram = ((line.spool_price + line.delivery_cost) / line.spool_weight_kg) / 1000.0
        line_multiplier = _material_line_multiplier(
            line.job_key,
            quantity,
            repeats_by_job,
        )
        line_weight_g = line.weight_g * line_multiplier
        line_cost = line_weight_g * price_per_gram
        rounded_line_weight_g = round(line_weight_g, 3)
        rounded_line_cost = round(line_cost, 2)
        role_weights_g = dict(line.role_weights_g)
        if line.support_weight_g is not None:
            role_weights_g.setdefault("support", line.support_weight_g)
        role_weight_source = line.role_weight_source or line.support_weight_source
        role_costs: list[CalculatorMaterialRoleCost] = []
        remaining_weight_g = rounded_line_weight_g
        remaining_cost = rounded_line_cost
        for role in ("support", "brim", "prime_tower"):
            raw_role_weight_g = role_weights_g.get(role)
            if raw_role_weight_g is None:
                continue
            if role_weight_source is None:
                raise ValueError("material role weights require a source")
            role_weight_g = min(
                remaining_weight_g,
                round(raw_role_weight_g * line_multiplier, 3),
            )
            role_cost = min(remaining_cost, round(role_weight_g * price_per_gram, 2))
            role_costs.append(
                CalculatorMaterialRoleCost(
                    role=role,
                    weight_g=role_weight_g,
                    cost=role_cost,
                    source=role_weight_source,
                )
            )
            remaining_weight_g = round(remaining_weight_g - role_weight_g, 3)
            remaining_cost = round(remaining_cost - role_cost, 2)
        support_role_cost = next(
            (role_cost for role_cost in role_costs if role_cost.role == "support"),
            None,
        )
        support_weight_g = support_role_cost.weight_g if support_role_cost else None
        support_cost = support_role_cost.cost if support_role_cost else None
        non_support_weight_g = (
            round(rounded_line_weight_g - support_weight_g, 3)
            if support_weight_g is not None
            else None
        )
        non_support_cost = (
            round(rounded_line_cost - support_cost, 2) if support_cost is not None else None
        )
        total_cost += line_cost
        total_weight_g += line_weight_g
        resolved.append(
            CalculatorMaterialLineCost(
                line_id=line.line_id,
                job_key=line.job_key,
                tool_index=line.tool_index,
                label=line.label,
                weight_g=rounded_line_weight_g,
                price_per_gram=round(price_per_gram, 6),
                cost=rounded_line_cost,
                price_source=line.price_source,
                spool_id=line.spool_id,
                filament_id=line.filament_id,
                support_weight_g=support_weight_g,
                support_cost=support_cost,
                non_support_weight_g=non_support_weight_g,
                non_support_cost=non_support_cost,
                support_weight_source=(role_weight_source if support_role_cost else None),
                role_costs=role_costs,
                other_weight_g=(remaining_weight_g if role_costs else None),
                other_cost=(remaining_cost if role_costs else None),
            )
        )

    return total_cost, total_weight_g, resolved


def _strip_history_thumbnail(parsed_gcode: CalculatorGcodeParseResponse | None) -> dict | None:
    """Remove heavy preview payload before persisting calculator history."""
    if not parsed_gcode:
        return None

    payload = parsed_gcode.model_dump(mode="json")
    payload["thumbnail_data_url"] = None
    return payload


def _encode_history_gcode(data: CalculatorHistoryEntryCreate) -> dict | None:
    """Persist old single-job and new batch histories in the existing JSON column."""
    if data.parsed_jobs:
        return {
            "format": "calculator_batch_v1",
            "jobs": [
                {
                    "job_key": job.job_key,
                    "parsed_gcode": _strip_history_thumbnail(job.parsed_gcode),
                }
                for job in data.parsed_jobs
            ],
        }
    return _strip_history_thumbnail(data.parsed_gcode)


def _decode_history_gcode(
    payload: dict | None,
) -> tuple[CalculatorGcodeParseResponse | None, list[CalculatorHistoryParsedJob]]:
    """Read both legacy single-job snapshots and calculator_batch_v1 envelopes."""
    if not payload:
        return None, []
    if payload.get("format") == "calculator_batch_v1":
        jobs = [CalculatorHistoryParsedJob.model_validate(job) for job in payload.get("jobs", [])]
        return (jobs[0].parsed_gcode if jobs else None), jobs
    return CalculatorGcodeParseResponse.model_validate(payload), []


def _build_history_title(data: CalculatorHistoryEntryCreate) -> str:
    """Generate a stable history title when the client does not provide one."""
    if data.title and data.title.strip():
        return data.title.strip()[:255]

    first_parsed = data.parsed_jobs[0].parsed_gcode if data.parsed_jobs else data.parsed_gcode
    if first_parsed and first_parsed.file_name:
        file_stem = Path(first_parsed.file_name).name
        return file_stem[:255]

    if data.filament_snapshot:
        label_parts = [data.filament_snapshot.brand_name, data.filament_snapshot.name]
        label = " · ".join(part for part in label_parts if part)
        if label:
            return label[:255]

    return "Calculator estimate"


def _serialize_history_entry(entry: CalculatorHistoryEntry) -> CalculatorHistoryEntryResponse:
    """Convert ORM row into typed response payload."""
    parsed_gcode, parsed_jobs = _decode_history_gcode(entry.parsed_gcode)
    return CalculatorHistoryEntryResponse(
        id=entry.id,
        user_id=entry.user_id,
        title=entry.title,
        pricing_method=PricingMethod(entry.pricing_method),
        request_data=CalculatorEstimateRequest.model_validate(entry.request_data),
        result_data=CalculatorEstimateResponse.model_validate(entry.result_data),
        parsed_gcode=parsed_gcode,
        parsed_jobs=parsed_jobs,
        filament_snapshot=entry.filament_snapshot,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.post("/estimate", response_model=CalculatorEstimateResponse)
async def estimate_cost(
    current_user: Annotated[User, Depends(require_calculator_access)],
    data: CalculatorEstimateRequest,
) -> CalculatorEstimateResponse:
    """Рассчитать стоимость печати; учесть расчёт в статистике только если он удался."""
    estimate = await _build_estimate(data)
    await record_calculator_estimate(current_user.id, data.pricing_method.value)
    return estimate


@router.post("/preflight", response_model=CalculatorPreflightResponse)
async def calculate_preflight(
    data: CalculatorPreflightRequest,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorPreflightResponse:
    """Check material readiness without reserving or consuming user inventory."""
    return await calculate_material_preflight(
        db,
        user_id=current_user.id,
        payload=data,
    )


async def _build_estimate(data: CalculatorEstimateRequest) -> CalculatorEstimateResponse:
    """
    Рассчитать стоимость печати по различным методам.

    Поддерживает три метода расчета:
    1. **by_weight** (по граммам): стоимость = (вес_г / 1000) * цена_за_кг
    2. **by_time** (по часам): стоимость = время_часы * цена_за_час
    3. **combined** (комбинированный): полный расчет по формуле из Excel:
       - Материал: ((цена_катушки + доставка) / вес_катушки_кг) / 1000 * (вес_г * количество)
       - Электроэнергия: мощность_кВт * цена_кВт·ч * время_печати_часы
       - Моделирование: (часы + минуты/60) * ставка_за_час
       - Печать: (часы + минуты/60) * ставка_за_час
       - Постобработка: (часы + минуты/60) * ставка_за_час
       - Амортизация: время_печати_часы * ставка_за_час

       Первая деталь включает все затраты, последующие - без моделирования.
    """
    quantity, print_runs, time_hours_per_run, time_hours_total, repeats_by_job = (
        _resolve_print_execution(data)
    )
    tax_rate_percent = data.tax_rate_percent or 0.0

    if data.pricing_method == PricingMethod.BY_WEIGHT:
        material_line_costs: list[CalculatorMaterialLineCost] = []
        if data.material_lines:
            cost_material, total_material_weight_g, material_line_costs = _calculate_material_lines(
                data, quantity, repeats_by_job
            )
            weight_kg = total_material_weight_g / 1000.0
        else:
            if data.weight_g is None:
                raise_error(400, ERR_WEIGHT_REQUIRED)
            if data.spool_price is None or data.spool_weight_kg is None:
                raise_error(400, ERR_SPOOL_PRICE_REQUIRED)

            delivery = data.delivery_cost or 0.0
            weight_kg = (data.weight_g * quantity) / 1000.0
            cost_material = (
                ((data.spool_price + delivery) / data.spool_weight_kg)
                / 1000.0
                * (data.weight_g * quantity)
            )

        cost_electricity = 0.0
        time_hours = time_hours_per_run if time_hours_total > 0 else None
        if time_hours_total > 0:
            if data.electricity_cost_per_kwh and data.printer_power_w and time_hours_total > 0:
                power_kw = data.printer_power_w / 1000.0
                cost_electricity = time_hours_total * power_kw * data.electricity_cost_per_kwh

        cost_subtotal = cost_material + cost_electricity
        cost_tax = _calculate_tax(cost_subtotal, tax_rate_percent)
        cost_total = cost_subtotal + cost_tax

        return CalculatorEstimateResponse(
            cost_material=round(cost_material, 2),
            cost_electricity=round(cost_electricity, 2),
            cost_modeling=0.0,
            cost_printing=0.0,
            cost_postprocessing=0.0,
            cost_amortization=0.0,
            cost_tax=round(cost_tax, 2),
            material_line_costs=material_line_costs,
            cost_first_part=round(cost_total, 2),
            cost_subsequent_parts=round(cost_total, 2),
            cost_total=round(cost_total, 2),
            cost_final=round(cost_total, 2),
            weight_kg=round(weight_kg, 3),
            time_hours=round(time_hours, 2) if time_hours else None,
            quantity=quantity,
            print_runs=print_runs,
            pricing_method=data.pricing_method,
            applied_tax_rate_percent=tax_rate_percent if tax_rate_percent > 0 else None,
        )

    elif data.pricing_method == PricingMethod.BY_TIME:
        if (
            not data.print_jobs
            and data.time_sec is None
            and data.time_hours is None
            and data.time_minutes is None
        ):
            raise_error(400, ERR_TIME_REQUIRED)
        if data.price_per_hour is None:
            raise_error(400, ERR_PRICE_PER_HOUR_REQUIRED)

        cost_printing = time_hours_total * data.price_per_hour

        cost_electricity = 0.0
        if data.electricity_cost_per_kwh and data.printer_power_w and time_hours_total > 0:
            power_kw = data.printer_power_w / 1000.0
            cost_electricity = time_hours_total * power_kw * data.electricity_cost_per_kwh

        cost_subtotal = cost_printing + cost_electricity
        cost_tax = _calculate_tax(cost_subtotal, tax_rate_percent)
        cost_total = cost_subtotal + cost_tax

        weight_kg = None
        if data.weight_g:
            weight_kg = (data.weight_g * quantity) / 1000.0

        return CalculatorEstimateResponse(
            cost_material=0.0,
            cost_electricity=round(cost_electricity, 2),
            cost_modeling=0.0,
            cost_printing=round(cost_printing, 2),
            cost_postprocessing=0.0,
            cost_amortization=0.0,
            cost_tax=round(cost_tax, 2),
            cost_first_part=round(cost_total / quantity, 2)
            if quantity > 0
            else round(cost_total, 2),  # Цена одной детали
            cost_subsequent_parts=round(cost_total / quantity, 2)
            if quantity > 0
            else round(cost_total, 2),
            cost_total=round(cost_total, 2),  # Общая стоимость всей партии
            cost_final=round(cost_total, 2),
            weight_kg=round(weight_kg, 3) if weight_kg else None,
            time_hours=round(time_hours_per_run, 2)
            if time_hours_per_run > 0
            else None,  # Время одного запуска / стола
            quantity=quantity,
            print_runs=print_runs,
            pricing_method=data.pricing_method,
            applied_tax_rate_percent=tax_rate_percent if tax_rate_percent > 0 else None,
        )

    elif data.pricing_method == PricingMethod.COMBINED:
        cost_material = 0.0
        weight_kg = None
        material_line_costs: list[CalculatorMaterialLineCost] = []
        if data.material_lines:
            cost_material, total_material_weight_g, material_line_costs = _calculate_material_lines(
                data, quantity, repeats_by_job
            )
            weight_kg = total_material_weight_g / 1000.0
        elif data.weight_g and data.spool_price and data.spool_weight_kg:
            delivery = data.delivery_cost or 0.0
            price_per_gram = ((data.spool_price + delivery) / data.spool_weight_kg) / 1000.0

            part_weight = data.weight_g * quantity
            weight_kg = part_weight / 1000.0

            supports_weight = (data.supports_weight_g or 0.0) * quantity
            supports_loss_coef = data.supports_loss_coefficient or 1.2

            cost_material = (part_weight * price_per_gram) + (
                supports_weight * price_per_gram * supports_loss_coef
            )

        cost_bed_prep = 0.0
        if data.bed_prep_cost_per_print and data.bed_prep_cost_per_print > 0:
            cost_bed_prep = data.bed_prep_cost_per_print * print_runs

        cost_waste = 0.0
        waste_factor_percent = data.waste_factor_percent or 0.0
        if waste_factor_percent > 0 and cost_material > 0:
            cost_waste = cost_material * (waste_factor_percent / 100.0)

        machine_hours = _machine_hours_by_rate(data, time_hours_total)

        cost_electricity = 0.0
        if data.electricity_cost_per_kwh:
            for hours, _rate, _amortization, power_w in machine_hours:
                if hours <= 0 or not power_w:
                    continue
                cost_electricity += (power_w / 1000.0) * data.electricity_cost_per_kwh * hours

        cost_modeling = 0.0
        if data.modeling_rate_per_hour:
            modeling_time = _convert_time_to_hours(data.modeling_hours, data.modeling_minutes)
            cost_modeling = modeling_time * data.modeling_rate_per_hour

        cost_printing = 0.0
        for hours, rate, _amortization, _power_w in machine_hours:
            if hours > 0 and rate:
                cost_printing += hours * rate

        cost_postprocessing = 0.0
        if data.postprocessing_rate_per_hour:
            postprocessing_time_per_part = _convert_time_to_hours(
                data.postprocessing_hours, data.postprocessing_minutes
            )
            postprocessing_time_total = postprocessing_time_per_part * quantity
            cost_postprocessing = postprocessing_time_total * data.postprocessing_rate_per_hour

        cost_monitoring = 0.0
        monitoring_factor = data.monitoring_factor or 0.0
        if monitoring_factor > 0 and time_hours_total > 0 and data.printing_rate_per_hour:
            monitoring_time_hours = time_hours_total * monitoring_factor
            cost_monitoring = monitoring_time_hours * data.printing_rate_per_hour

        cost_amortization = 0.0
        for hours, _rate, amortization, _power_w in machine_hours:
            if hours > 0 and amortization:
                cost_amortization += hours * amortization

        cost_nozzle_wear = 0.0
        if data.nozzle_price and data.nozzle_life_cm3:
            if data.material_lines:
                wear_equivalent_volume_cm3 = sum(
                    (
                        line.weight_g
                        * _material_line_multiplier(line.job_key, quantity, repeats_by_job)
                        / (line.density_g_cm3 or 1.24)
                    )
                    * (line.abrasiveness or 1.0)
                    for line in data.material_lines
                )
                cost_nozzle_wear = data.nozzle_price * (
                    wear_equivalent_volume_cm3 / data.nozzle_life_cm3
                )
            elif data.weight_g:
                density = data.filament_density or 1.24
                total_weight_g = (
                    data.weight_g * quantity + (data.supports_weight_g or 0.0) * quantity
                )
                extruded_volume_cm3 = total_weight_g / density
                abrasiveness = data.material_abrasiveness or 1.0
                cost_nozzle_wear = (
                    data.nozzle_price * (extruded_volume_cm3 / data.nozzle_life_cm3) * abrasiveness
                )

        cost_direct = (
            cost_material
            + cost_bed_prep
            + cost_waste
            + cost_electricity
            + cost_modeling
            + cost_printing
            + cost_postprocessing
            + cost_monitoring
            + cost_amortization
            + cost_nozzle_wear
        )

        overhead_percent = data.overhead_percent or 20.0  # По умолчанию 20%
        cost_overhead = cost_direct * (overhead_percent / 100.0)

        fixed_costs = data.fixed_costs or 0.0

        cost_before_markup = cost_direct + cost_overhead + fixed_costs

        markup_percent = data.markup_percent or 30.0  # По умолчанию 30%
        cost_markup = cost_before_markup * (markup_percent / 100.0)

        intermediate_price = cost_before_markup + cost_markup

        urgency_coef = data.urgency_coefficient or 1.0
        complexity_coef = data.complexity_coefficient or 1.0
        volume_discount_coef = data.volume_discount_coefficient or 1.0

        taxable_subtotal = (
            intermediate_price * urgency_coef * complexity_coef * volume_discount_coef
        )

        if data.min_order_price and taxable_subtotal < data.min_order_price:
            taxable_subtotal = data.min_order_price

        cost_tax = _calculate_tax(taxable_subtotal, tax_rate_percent)
        cost_final_before_rounding = taxable_subtotal + cost_tax
        cost_final = cost_final_before_rounding

        if data.round_to_nearest and data.round_to_nearest > 0:
            cost_final = _apply_rounding(cost_final, data.round_to_nearest, data.rounding_mode)

        if quantity > 1:
            cost_without_modeling = (
                cost_material
                + cost_bed_prep
                + cost_waste
                + cost_electricity
                + cost_printing
                + cost_postprocessing
                + cost_monitoring
                + cost_amortization
                + cost_nozzle_wear
            )
            cost_without_modeling_with_overhead = (
                cost_without_modeling
                + (cost_without_modeling * overhead_percent / 100.0)
                + fixed_costs
            )
            cost_without_modeling_final = (
                (cost_without_modeling_with_overhead * (1 + markup_percent / 100.0))
                * urgency_coef
                * complexity_coef
                * volume_discount_coef
            )
            cost_subsequent_parts = (
                cost_without_modeling_final
                + _calculate_tax(cost_without_modeling_final, tax_rate_percent)
            ) / quantity
            cost_first_part = cost_final - (cost_subsequent_parts * (quantity - 1))
        else:
            cost_first_part = cost_final
            cost_subsequent_parts = cost_first_part

        cost_total = cost_final

        total_time_hours = time_hours_total
        if monitoring_factor > 0 and time_hours_total > 0:
            total_time_hours += time_hours_total * monitoring_factor
        if data.modeling_hours or data.modeling_minutes:
            modeling_time = _convert_time_to_hours(data.modeling_hours, data.modeling_minutes)
            total_time_hours += modeling_time  # Моделирование делается один раз
        if data.postprocessing_hours or data.postprocessing_minutes:
            postprocessing_time_per_part = _convert_time_to_hours(
                data.postprocessing_hours, data.postprocessing_minutes
            )
            postprocessing_time_total = (
                postprocessing_time_per_part * quantity
            )  # Постобработка каждой детали
            total_time_hours += postprocessing_time_total

        cost_of_goods_sold = cost_before_markup
        revenue_before_tax = max(cost_final - cost_tax, 0.0)
        profit_margin = revenue_before_tax - cost_of_goods_sold
        profit_margin_percent = (
            (profit_margin / revenue_before_tax * 100.0) if revenue_before_tax > 0 else 0.0
        )

        return CalculatorEstimateResponse(
            cost_material=round(cost_material, 2),
            cost_bed_prep=round(cost_bed_prep, 2),
            cost_waste=round(cost_waste, 2),
            cost_electricity=round(cost_electricity, 2),
            cost_modeling=round(cost_modeling, 2),
            cost_printing=round(cost_printing, 2),
            cost_postprocessing=round(cost_postprocessing, 2),
            cost_monitoring=round(cost_monitoring, 2),
            cost_amortization=round(cost_amortization, 2),
            cost_nozzle_wear=round(cost_nozzle_wear, 2),
            cost_tax=round(cost_tax, 2),
            cost_direct=round(cost_direct, 2),
            cost_overhead=round(cost_overhead, 2),
            cost_before_markup=round(cost_before_markup, 2),
            cost_markup=round(cost_markup, 2),
            material_line_costs=material_line_costs,
            cost_first_part=round(cost_first_part, 2),
            cost_subsequent_parts=round(cost_subsequent_parts, 2),
            cost_total=round(cost_total, 2),
            cost_final=round(cost_final, 2),
            weight_kg=round(weight_kg, 3) if weight_kg else None,
            time_hours=round(time_hours_per_run, 2)
            if time_hours_per_run > 0
            else None,  # Время одного запуска / стола
            total_time_hours=round(total_time_hours, 2)
            if total_time_hours and total_time_hours > 0
            else None,
            quantity=quantity,
            print_runs=print_runs,
            cost_of_goods_sold=round(cost_of_goods_sold, 2)
            if data.pricing_method == PricingMethod.COMBINED
            else None,
            profit_margin=round(profit_margin, 2)
            if data.pricing_method == PricingMethod.COMBINED
            else None,
            profit_margin_percent=round(profit_margin_percent, 2)
            if data.pricing_method == PricingMethod.COMBINED and profit_margin_percent
            else None,
            pricing_method=data.pricing_method,
            applied_urgency_coefficient=urgency_coef if urgency_coef != 1.0 else None,
            applied_complexity_coefficient=complexity_coef if complexity_coef != 1.0 else None,
            applied_volume_discount=volume_discount_coef if volume_discount_coef != 1.0 else None,
            applied_tax_rate_percent=tax_rate_percent if tax_rate_percent > 0 else None,
        )

    else:
        raise_error(400, ERR_UNSUPPORTED_PRICING_METHOD, params={"method": data.pricing_method})


async def parse_uploaded_gcode(
    file: UploadFile,
    plate_index: int | None,
    *,
    db: AsyncSession | None = None,
    user_id: int | None = None,
) -> CalculatorGcodeParseResponse:
    """Read an uploaded G-code the same way wherever it came from.

    The site uploads the file a person dropped in; the OrcaSlicer plugin uploads
    one it produced. Both land here so a calculation cannot depend on the route.
    """
    if not is_supported_gcode_filename(file.filename):
        file_name = file.filename or ""
        file_ext = (
            ".gcode.gz"
            if file_name.lower().endswith(".gcode.gz")
            else file_name[file_name.rfind(".") :].lower()
            if "." in file_name
            else ""
        )
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_INVALID_FILE_EXT,
            {"ext": file_ext, "expected": ", ".join(SUPPORTED_GCODE_EXTENSIONS)},
        )

    raw_bytes = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_FILE_TOO_LARGE,
            {"max_size": f"{settings.MAX_UPLOAD_SIZE_MB}MB"},
        )

    try:
        # Reading a sliced model walks every line of it — eight seconds for a
        # large one — so it happens off the event loop and a few at a time.
        # Left in the request path it would stop this worker answering anyone.
        parsed = await _gcode_gate.run(
            _parse_gcode_bytes,
            file.filename or "gcode",
            raw_bytes,
            plate_index,
        )
    except ValueError as exc:
        logger.warning("Calculator G-code parse failed for %s: %s", file.filename, exc)
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_GCODE_PARSE_FAILED)

    response = CalculatorGcodeParseResponse(**parsed)
    if db is not None and user_id is not None:
        response = await resolve_calculator_material_identities(
            db,
            response,
            user_id=user_id,
        )
    return response


@router.post("/parse-gcode", response_model=CalculatorGcodeParseResponse)
async def parse_gcode(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    plate_index: int | None = Query(None, ge=1),
) -> CalculatorGcodeParseResponse:
    """Parse uploaded G-code metadata for Calculator Pro auto-fill."""
    return await parse_uploaded_gcode(
        file,
        plate_index,
        db=db,
        user_id=current_user.id,
    )


@router.get("/history", response_model=CalculatorHistoryEntryListResponse)
async def list_calculator_history(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> CalculatorHistoryEntryListResponse:
    """List saved Calculator Pro history entries for the current user."""
    query = select(CalculatorHistoryEntry).where(CalculatorHistoryEntry.user_id == current_user.id)
    total = (
        await db.execute(
            select(func.count())
            .select_from(CalculatorHistoryEntry)
            .where(CalculatorHistoryEntry.user_id == current_user.id)
        )
    ).scalar_one()

    offset = (page - 1) * size
    result = await db.execute(
        query.order_by(CalculatorHistoryEntry.created_at.desc()).offset(offset).limit(size)
    )
    entries = result.scalars().all()

    return CalculatorHistoryEntryListResponse(
        items=[_serialize_history_entry(entry) for entry in entries],
        total=total,
    )


@router.post(
    "/history", response_model=CalculatorHistoryEntryResponse, status_code=status.HTTP_201_CREATED
)
async def save_calculator_history(
    data: CalculatorHistoryEntryCreate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorHistoryEntryResponse:
    """Persist a Calculator Pro estimate to user history."""
    entry = CalculatorHistoryEntry(
        user_id=current_user.id,
        title=_build_history_title(data),
        pricing_method=data.request_data.pricing_method.value,
        request_data=data.request_data.model_dump(mode="json"),
        result_data=data.result_data.model_dump(mode="json"),
        parsed_gcode=_encode_history_gcode(data),
        filament_snapshot=data.filament_snapshot.model_dump(mode="json")
        if data.filament_snapshot
        else None,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _serialize_history_entry(entry)


@router.delete("/history/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calculator_history(
    entry_id: int,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete one Calculator Pro history entry."""
    result = await db.execute(
        select(CalculatorHistoryEntry).where(
            CalculatorHistoryEntry.id == entry_id,
            CalculatorHistoryEntry.user_id == current_user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_CALCULATOR_HISTORY_NOT_FOUND)

    await db.execute(
        update(PrintJob)
        .where(PrintJob.calculator_history_id == entry.id)
        .values(calculator_history_id=None)
    )
    await db.delete(entry)
    await db.commit()


ENCRYPTED_PROFILE_FIELDS = (
    "seller_name",
    "seller_inn",
    "seller_phone",
    "payment_terms",
    "seller_registration_id",
    "seller_tax_code",
    "seller_address",
    "seller_bank_details",
)


def _profile_response(profile: UserCalculatorProfile) -> CalculatorProfileResponse:
    response = CalculatorProfileResponse.model_validate(profile)
    return response.model_copy(
        update={name: decrypt_field(getattr(profile, name)) for name in ENCRYPTED_PROFILE_FIELDS}
    )


@router.get("/profile", response_model=CalculatorProfileResponse)
async def get_calculator_profile(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorProfileResponse:
    """Return the current user's calculator profile (create with defaults if missing)."""
    result = await db.execute(
        select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        defaults = await get_calculator_profile_defaults(db)
        profile = UserCalculatorProfile(
            user_id=current_user.id,
            **calculator_profile_default_values(defaults),
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)

    return _profile_response(profile)


@router.put("/profile", response_model=CalculatorProfileResponse)
async def update_calculator_profile(
    data: CalculatorProfileUpdate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorProfileResponse:
    """Create or update the current user's calculator profile."""
    result = await db.execute(
        select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        defaults = await get_calculator_profile_defaults(db)
        profile = UserCalculatorProfile(
            user_id=current_user.id,
            **calculator_profile_default_values(defaults),
        )
        db.add(profile)
    else:
        _profile_response(profile)

    for field_name, value in data.model_dump(exclude_unset=True).items():
        if field_name in ENCRYPTED_PROFILE_FIELDS:
            value = encrypt_field(value)
        setattr(profile, field_name, value)

    await db.commit()
    await db.refresh(profile)
    return _profile_response(profile)


@router.post("/profile/reset-defaults", response_model=CalculatorProfileResponse)
async def reset_calculator_profile_defaults(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorProfileResponse:
    """Explicitly reset only economics to the current platform defaults."""
    profile = await db.scalar(
        select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == current_user.id)
    )
    defaults: CalculatorProfileDefaults = await get_calculator_profile_defaults(db)
    values = calculator_profile_default_values(
        defaults,
        profile_currency=profile.currency if profile is not None else None,
    )
    if profile is None:
        profile = UserCalculatorProfile(user_id=current_user.id, **values)
        db.add(profile)
    else:
        _profile_response(profile)
        for field_name, value in values.items():
            setattr(profile, field_name, value)
    await db.commit()
    await db.refresh(profile)
    return _profile_response(profile)


SHARED_QUOTE_LIFETIME_DAYS = 90

_SHARED_QUOTE_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data: https: http:; "
    "font-src data:; base-uri 'none'; form-action 'none'"
)


@router.post(
    "/quote/share", response_model=SharedQuoteResponse, status_code=status.HTTP_201_CREATED
)
async def create_shared_quote(
    data: SharedQuoteCreate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SharedQuoteResponse:
    """Create a publicly accessible shared quote link."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=SHARED_QUOTE_LIFETIME_DAYS)

    quote = SharedQuote(
        user_id=current_user.id,
        title=data.title[:255] if data.title else "",
        html_content=encrypt_field(data.html_content),
        expires_at=expires_at,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    share_url = f"{settings.BASE_URL}/quote/{quote.uuid}"
    return SharedQuoteResponse(uuid=quote.uuid, share_url=share_url, expires_at=quote.expires_at)


@router.get("/quote/{uuid}")
async def get_shared_quote(
    uuid: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HTMLResponse:
    """Return a shared quote as a standalone HTML page (no auth required)."""
    result = await db.execute(select(SharedQuote).where(SharedQuote.uuid == uuid))
    quote = result.scalar_one_or_none()

    if not quote:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_SHARED_QUOTE_NOT_FOUND)

    if quote.expires_at and quote.expires_at < datetime.now(timezone.utc):
        raise_error(status.HTTP_410_GONE, ERR_SHARED_QUOTE_EXPIRED)

    return HTMLResponse(
        content=decrypt_field(quote.html_content),
        headers={
            "Content-Security-Policy": _SHARED_QUOTE_CSP,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/quote/pdf")
async def generate_quote_pdf(
    data: SharedQuoteCreate,
    current_user: Annotated[User, Depends(require_calculator_access)],
) -> Response:
    """Generate a PDF from quote HTML content and return it for download."""
    from app.services.pdf_service import generate_pdf_from_html

    try:
        pdf_bytes = await _pdf_gate.run(generate_pdf_from_html, data.html_content)
    except HTTPException:
        raise
    except Exception:
        logger.warning("PDF generation failed", exc_info=True)
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_PDF_GENERATION_FAILED)

    filename = data.title or "quote"
    filename = re.sub(r"[^\w\s\-.]", "", filename)[:80]
    if not filename:
        filename = "quote"

    from urllib.parse import quote

    ascii_fallback = re.sub(r"[^A-Za-z0-9\-_.]", "_", filename)
    utf8_encoded = quote(filename)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}.pdf"; '
                f"filename*=UTF-8''{utf8_encoded}.pdf"
            ),
        },
    )

"""Calculator endpoints."""

import math
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_CALCULATOR_HISTORY_NOT_FOUND,
    ERR_FILE_TOO_LARGE,
    ERR_GCODE_PARSE_FAILED,
    ERR_INVALID_FILE_EXT,
    ERR_WEIGHT_REQUIRED,
    ERR_SPOOL_PRICE_REQUIRED,
    ERR_TIME_REQUIRED,
    ERR_PRICE_PER_HOUR_REQUIRED,
    ERR_UNSUPPORTED_PRICING_METHOD,
    raise_error,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.user import User
from app.schemas.calculator import (
    CalculatorEstimateRequest,
    CalculatorEstimateResponse,
    CalculatorGcodeParseResponse,
    CalculatorHistoryEntryCreate,
    CalculatorHistoryEntryListResponse,
    CalculatorHistoryEntryResponse,
    PricingMethod,
    RoundingMode,
)
from app.services.calculator_gcode_parser import (
    SUPPORTED_GCODE_EXTENSIONS,
    is_supported_gcode_filename,
    parse_gcode_payload,
)

router = APIRouter(prefix="/calculator", tags=["calculator"])
logger = logging.getLogger(__name__)


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


def _strip_history_thumbnail(parsed_gcode: CalculatorGcodeParseResponse | None) -> dict | None:
    """Remove heavy preview payload before persisting calculator history."""
    if not parsed_gcode:
        return None

    payload = parsed_gcode.model_dump(mode="json")
    payload["thumbnail_data_url"] = None
    return payload


def _build_history_title(data: CalculatorHistoryEntryCreate) -> str:
    """Generate a stable history title when the client does not provide one."""
    if data.title and data.title.strip():
        return data.title.strip()[:255]

    if data.parsed_gcode and data.parsed_gcode.file_name:
        file_stem = Path(data.parsed_gcode.file_name).name
        return file_stem[:255]

    if data.filament_snapshot:
        label_parts = [data.filament_snapshot.brand_name, data.filament_snapshot.name]
        label = " · ".join(part for part in label_parts if part)
        if label:
            return label[:255]

    return "Calculator estimate"


def _serialize_history_entry(entry: CalculatorHistoryEntry) -> CalculatorHistoryEntryResponse:
    """Convert ORM row into typed response payload."""
    return CalculatorHistoryEntryResponse(
        id=entry.id,
        user_id=entry.user_id,
        title=entry.title,
        pricing_method=PricingMethod(entry.pricing_method),
        request_data=CalculatorEstimateRequest.model_validate(entry.request_data),
        result_data=CalculatorEstimateResponse.model_validate(entry.result_data),
        parsed_gcode=CalculatorGcodeParseResponse.model_validate(entry.parsed_gcode) if entry.parsed_gcode else None,
        filament_snapshot=entry.filament_snapshot,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.post("/estimate", response_model=CalculatorEstimateResponse)
async def estimate_cost(
    data: CalculatorEstimateRequest,
) -> CalculatorEstimateResponse:
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
    quantity = data.quantity
    
    # ========== Простые методы (для обратной совместимости) ==========
    if data.pricing_method == PricingMethod.BY_WEIGHT:
        if data.weight_g is None:
            raise_error(400, ERR_WEIGHT_REQUIRED)
        if data.spool_price is None or data.spool_weight_kg is None:
            raise_error(400, ERR_SPOOL_PRICE_REQUIRED)
        
        delivery = data.delivery_cost or 0.0
        weight_kg = (data.weight_g * quantity) / 1000.0
        # Формула из Excel: ((цена_катушки + доставка) / вес_катушки_кг) / 1000 * (вес_г * количество)
        cost_material = ((data.spool_price + delivery) / data.spool_weight_kg) / 1000.0 * (data.weight_g * quantity)
        
        # Электроэнергия (если указана)
        cost_electricity = 0.0
        time_hours = None
        if data.time_sec or data.time_hours or data.time_minutes:
            time_hours = _convert_time_to_hours(data.time_hours, data.time_minutes, data.time_sec)
            if data.electricity_cost_per_kwh and data.printer_power_w and time_hours > 0:
                power_kw = data.printer_power_w / 1000.0
                cost_electricity = time_hours * power_kw * data.electricity_cost_per_kwh
        
        cost_total = cost_material + cost_electricity
    
        return CalculatorEstimateResponse(
            cost_material=round(cost_material, 2),
            cost_electricity=round(cost_electricity, 2),
            cost_modeling=0.0,
            cost_printing=0.0,
            cost_postprocessing=0.0,
            cost_amortization=0.0,
            cost_first_part=round(cost_total, 2),
            cost_subsequent_parts=round(cost_total, 2),
            cost_total=round(cost_total, 2),
            weight_kg=round(weight_kg, 3),
            time_hours=round(time_hours, 2) if time_hours else None,
            quantity=quantity,
            pricing_method=data.pricing_method,
        )
    
    elif data.pricing_method == PricingMethod.BY_TIME:
        if data.time_sec is None and data.time_hours is None and data.time_minutes is None:
            raise_error(400, ERR_TIME_REQUIRED)
        if data.price_per_hour is None:
            raise_error(400, ERR_PRICE_PER_HOUR_REQUIRED)
        
        # Время печати на 1 деталь (для отображения)
        time_hours_per_part = _convert_time_to_hours(data.time_hours, data.time_minutes, data.time_sec)
        # Время печати для всей партии (умножаем на количество деталей)
        time_hours_total = time_hours_per_part * quantity
        
        cost_printing = time_hours_total * data.price_per_hour
        
        # Электроэнергия (если указана, рассчитывается на общее время печати партии)
        cost_electricity = 0.0
        if data.electricity_cost_per_kwh and data.printer_power_w and time_hours_total > 0:
            power_kw = data.printer_power_w / 1000.0
            cost_electricity = time_hours_total * power_kw * data.electricity_cost_per_kwh
        
        cost_total = cost_printing + cost_electricity
        
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
            cost_first_part=round(cost_total / quantity, 2) if quantity > 0 else round(cost_total, 2),  # Цена одной детали
            cost_subsequent_parts=round(cost_total / quantity, 2) if quantity > 0 else round(cost_total, 2),
            cost_total=round(cost_total, 2),  # Общая стоимость всей партии
            weight_kg=round(weight_kg, 3) if weight_kg else None,
            time_hours=round(time_hours_per_part, 2) if time_hours_per_part > 0 else None,  # Время на 1 деталь для отображения
            quantity=quantity,
            pricing_method=data.pricing_method,
        )
    
    # ========== Комбинированный метод (полная формула из Excel + профессиональная формула) ==========
    elif data.pricing_method == PricingMethod.COMBINED:
        # 1. Материал (с учетом поддержек и коэффициента потерь)
        cost_material = 0.0
        weight_kg = None
        if data.weight_g and data.spool_price and data.spool_weight_kg:
            delivery = data.delivery_cost or 0.0
            price_per_gram = ((data.spool_price + delivery) / data.spool_weight_kg) / 1000.0
            
            # Вес детали
            part_weight = data.weight_g * quantity
            weight_kg = part_weight / 1000.0
            
            # Вес поддержек (если указан)
            supports_weight = (data.supports_weight_g or 0.0) * quantity
            supports_loss_coef = data.supports_loss_coefficient or 1.2
            
            # Формула из документа: (Вес детали × Цена материала) + (Вес поддержек × Цена материала × Коэффициент потерь)
            cost_material = (part_weight * price_per_gram) + (supports_weight * price_per_gram * supports_loss_coef)
        
        # 2. Время печати на 1 деталь (для отображения в результатах)
        time_hours_per_part = _convert_time_to_hours(data.time_hours, data.time_minutes, data.time_sec)
        # Время печати для всей партии (умножаем на количество деталей)
        time_hours_total = time_hours_per_part * quantity
        
        # 3. Электроэнергия (рассчитывается на общее время печати партии)
        cost_electricity = 0.0
        if data.electricity_cost_per_kwh and data.printer_power_w and time_hours_total > 0:
            power_kw = data.printer_power_w / 1000.0
            # Формула из Excel: мощность_кВт * цена_кВт·ч * время_печати_часы_всего
            cost_electricity = power_kw * data.electricity_cost_per_kwh * time_hours_total
        
        # 4. Моделирование (делается один раз для всей партии, не умножается на quantity)
        cost_modeling = 0.0
        if data.modeling_rate_per_hour:
            modeling_time = _convert_time_to_hours(data.modeling_hours, data.modeling_minutes)
            # Формула из Excel: (часы + минуты/60) * ставка_за_час
            cost_modeling = modeling_time * data.modeling_rate_per_hour
        
        # 5. Печать (почасовая ставка, умножается на общее время печати партии)
        cost_printing = 0.0
        if data.printing_rate_per_hour and time_hours_total > 0:
            # Формула из Excel: время_печати_часы_всего * ставка_за_час
            cost_printing = time_hours_total * data.printing_rate_per_hour
        
        # 6. Постобработка (умножается на количество деталей, так как каждая деталь обрабатывается отдельно)
        cost_postprocessing = 0.0
        if data.postprocessing_rate_per_hour:
            postprocessing_time_per_part = _convert_time_to_hours(data.postprocessing_hours, data.postprocessing_minutes)
            postprocessing_time_total = postprocessing_time_per_part * quantity
            # Формула из Excel: (время_на_деталь * количество) * ставка_за_час
            cost_postprocessing = postprocessing_time_total * data.postprocessing_rate_per_hour
        
        # 7. Амортизация (привязана к общему времени печати партии)
        cost_amortization = 0.0
        if data.amortization_rate_per_hour and time_hours_total > 0:
            # Формула из Excel: время_печати_часы_всего * ставка_амортизации_за_час
            cost_amortization = time_hours_total * data.amortization_rate_per_hour
        
        # 8. Прямые затраты (материалы + время + труд)
        cost_direct = (
            cost_material +
            cost_electricity +
            cost_modeling +
            cost_printing +
            cost_postprocessing +
            cost_amortization
        )
        
        # 9. Накладные расходы (процент от прямых затрат)
        overhead_percent = data.overhead_percent or 20.0  # По умолчанию 20%
        cost_overhead = cost_direct * (overhead_percent / 100.0)
        
        # 10. Фиксированные расходы
        fixed_costs = data.fixed_costs or 0.0
        
        # 11. Стоимость до наценки
        cost_before_markup = cost_direct + cost_overhead + fixed_costs
        
        # 12. Наценка (процент от стоимости до наценки)
        markup_percent = data.markup_percent or 30.0  # По умолчанию 30%
        cost_markup = cost_before_markup * (markup_percent / 100.0)
        
        # 13. Промежуточная цена (до применения коэффициентов)
        intermediate_price = cost_before_markup + cost_markup
        
        # 14. Применение коэффициентов корректировки
        urgency_coef = data.urgency_coefficient or 1.0
        complexity_coef = data.complexity_coefficient or 1.0
        volume_discount_coef = data.volume_discount_coefficient or 1.0
        
        # Применяем коэффициенты
        cost_final = intermediate_price * urgency_coef * complexity_coef * volume_discount_coef
        
        # 15. Минимальная цена заказа (если указана)
        if data.min_order_price and cost_final < data.min_order_price:
            cost_final = data.min_order_price
        
        # 16. Округление (если указано)
        if data.round_to_nearest and data.round_to_nearest > 0:
            cost_final = _apply_rounding(cost_final, data.round_to_nearest, data.rounding_mode)
        
        # 17. Расчет цены первой детали и последующих (для отображения)
        # В combined-mode все промежуточные суммы выше считаются для всей партии.
        # Поэтому:
        # - subsequent = цена одной детали без one-time затрат на моделирование
        # - first part = остаток от общей партии после вычитания остальных subsequent деталей
        if quantity > 1:
            cost_without_modeling = (
                cost_material +
                cost_electricity +
                cost_printing +
                cost_postprocessing +
                cost_amortization
            )
            cost_without_modeling_with_overhead = (cost_without_modeling + (cost_without_modeling * overhead_percent / 100.0) + fixed_costs)
            cost_without_modeling_final = (cost_without_modeling_with_overhead * (1 + markup_percent / 100.0)) * urgency_coef * complexity_coef * volume_discount_coef
            cost_subsequent_parts = cost_without_modeling_final / quantity
            cost_first_part = cost_final - (cost_subsequent_parts * (quantity - 1))
        else:
            cost_first_part = cost_final
            cost_subsequent_parts = cost_first_part
        
        # 18. Общая стоимость партии
        cost_total = cost_final
        
        # 19. Расчет общего времени (печать + подготовка + постобработка)
        # Общее время = время печати всех деталей + время моделирования (1 раз) + время постобработки всех деталей
        total_time_hours = time_hours_total  # Уже умножено на quantity
        if data.modeling_hours or data.modeling_minutes:
            modeling_time = _convert_time_to_hours(data.modeling_hours, data.modeling_minutes)
            total_time_hours = total_time_hours + modeling_time  # Моделирование делается один раз
        if data.postprocessing_hours or data.postprocessing_minutes:
            postprocessing_time_per_part = _convert_time_to_hours(data.postprocessing_hours, data.postprocessing_minutes)
            postprocessing_time_total = postprocessing_time_per_part * quantity  # Постобработка каждой детали
            total_time_hours = total_time_hours + postprocessing_time_total
        
        # 20. Расчет маржи (прибыли)
        # Себестоимость = прямые затраты + накладные + фиксированные расходы
        cost_of_goods_sold = cost_before_markup
        # Маржа = Финальная цена - Себестоимость
        profit_margin = cost_final - cost_of_goods_sold
        # Маржа в процентах
        profit_margin_percent = (profit_margin / cost_final * 100.0) if cost_final > 0 else 0.0
        
        return CalculatorEstimateResponse(
            cost_material=round(cost_material, 2),
            cost_electricity=round(cost_electricity, 2),
            cost_modeling=round(cost_modeling, 2),
            cost_printing=round(cost_printing, 2),
            cost_postprocessing=round(cost_postprocessing, 2),
            cost_amortization=round(cost_amortization, 2),
            cost_direct=round(cost_direct, 2),
            cost_overhead=round(cost_overhead, 2),
            cost_before_markup=round(cost_before_markup, 2),
            cost_markup=round(cost_markup, 2),
            cost_first_part=round(cost_first_part, 2),
            cost_subsequent_parts=round(cost_subsequent_parts, 2),
            cost_total=round(cost_total, 2),
            cost_final=round(cost_final, 2),
            weight_kg=round(weight_kg, 3) if weight_kg else None,
            time_hours=round(time_hours_per_part, 2) if time_hours_per_part > 0 else None,  # Время на 1 деталь для отображения
            total_time_hours=round(total_time_hours, 2) if total_time_hours and total_time_hours > 0 else None,
            quantity=quantity,
            cost_of_goods_sold=round(cost_of_goods_sold, 2) if data.pricing_method == PricingMethod.COMBINED else None,
            profit_margin=round(profit_margin, 2) if data.pricing_method == PricingMethod.COMBINED else None,
            profit_margin_percent=round(profit_margin_percent, 2) if data.pricing_method == PricingMethod.COMBINED and profit_margin_percent else None,
            pricing_method=data.pricing_method,
            applied_urgency_coefficient=urgency_coef if urgency_coef != 1.0 else None,
            applied_complexity_coefficient=complexity_coef if complexity_coef != 1.0 else None,
            applied_volume_discount=volume_discount_coef if volume_discount_coef != 1.0 else None,
        )
    
    else:
        raise_error(400, ERR_UNSUPPORTED_PRICING_METHOD, params={"method": data.pricing_method})


@router.post("/parse-gcode", response_model=CalculatorGcodeParseResponse)
async def parse_gcode(
    file: UploadFile = File(...),
) -> CalculatorGcodeParseResponse:
    """Parse uploaded G-code metadata for Calculator Pro auto-fill."""
    if not is_supported_gcode_filename(file.filename):
        file_name = file.filename or ""
        file_ext = ".gcode.gz" if file_name.lower().endswith(".gcode.gz") else file_name[file_name.rfind(".") :].lower() if "." in file_name else ""
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_INVALID_FILE_EXT,
            {"ext": file_ext, "expected": ", ".join(SUPPORTED_GCODE_EXTENSIONS)},
        )

    raw_bytes = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_FILE_TOO_LARGE, {"max_size": f"{settings.MAX_UPLOAD_SIZE_MB}MB"})

    try:
        parsed = parse_gcode_payload(file_name=file.filename or "gcode", raw_bytes=raw_bytes)
    except ValueError as exc:
        logger.warning("Calculator G-code parse failed for %s: %s", file.filename, exc)
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_GCODE_PARSE_FAILED, {"reason": str(exc)})

    return CalculatorGcodeParseResponse(**parsed)


@router.get("/history", response_model=CalculatorHistoryEntryListResponse)
async def list_calculator_history(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> CalculatorHistoryEntryListResponse:
    """List saved Calculator Pro history entries for the current user."""
    query = select(CalculatorHistoryEntry).where(CalculatorHistoryEntry.user_id == current_user.id)
    total = (
        await db.execute(
            select(func.count()).select_from(CalculatorHistoryEntry).where(CalculatorHistoryEntry.user_id == current_user.id)
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


@router.post("/history", response_model=CalculatorHistoryEntryResponse, status_code=status.HTTP_201_CREATED)
async def save_calculator_history(
    data: CalculatorHistoryEntryCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CalculatorHistoryEntryResponse:
    """Persist a Calculator Pro estimate to user history."""
    entry = CalculatorHistoryEntry(
        user_id=current_user.id,
        title=_build_history_title(data),
        pricing_method=data.request_data.pricing_method.value,
        request_data=data.request_data.model_dump(mode="json"),
        result_data=data.result_data.model_dump(mode="json"),
        parsed_gcode=_strip_history_thumbnail(data.parsed_gcode),
        filament_snapshot=data.filament_snapshot.model_dump(mode="json") if data.filament_snapshot else None,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _serialize_history_entry(entry)


@router.delete("/history/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calculator_history(
    entry_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
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

    await db.delete(entry)
    await db.commit()

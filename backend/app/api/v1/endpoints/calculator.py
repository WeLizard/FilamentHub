"""Calculator endpoints."""

import math
from fastapi import APIRouter, HTTPException

from app.core.errors import (
    ERR_WEIGHT_REQUIRED,
    ERR_SPOOL_PRICE_REQUIRED,
    ERR_TIME_REQUIRED,
    ERR_PRICE_PER_HOUR_REQUIRED,
    ERR_UNSUPPORTED_PRICING_METHOD,
    raise_error,
)
from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse, PricingMethod

router = APIRouter(prefix="/calculator", tags=["calculator"])


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
            cost_final = math.floor(cost_final / data.round_to_nearest) * data.round_to_nearest
        
        # 17. Расчет цены первой детали и последующих (для отображения)
        # Первая деталь включает все затраты (включая моделирование)
        cost_first_part = cost_final / quantity if quantity > 0 else cost_final
        
        # Последующие детали без моделирования (если количество > 1)
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
        else:
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


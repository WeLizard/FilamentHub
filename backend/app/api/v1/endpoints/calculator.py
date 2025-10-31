"""Calculator endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse

router = APIRouter(prefix="/calculator", tags=["calculator"])


@router.post("/estimate", response_model=CalculatorEstimateResponse)
async def estimate_cost(
    data: CalculatorEstimateRequest,
) -> CalculatorEstimateResponse:
    """
    Рассчитать стоимость печати (простая формула, без G-code парсинга).
    
    **Заглушка для MVP.** Полный калькулятор с G-code парсингом будет в Фазе 6.
    
    Формула:
    - cost_material = (weight_g / 1000) * price_per_kg
    - cost_electricity = (time_sec / 3600) * (printer_power_w / 1000) * electricity_cost_per_kwh (если указано)
    - cost_total = cost_material + cost_electricity
    """
    # Calculate material cost
    weight_kg = data.weight_g / 1000.0
    cost_material = weight_kg * data.price_per_kg
    
    # Calculate electricity cost (optional)
    cost_electricity = None
    if data.electricity_cost_per_kwh is not None and data.printer_power_w is not None:
        time_hours = data.time_sec / 3600.0
        power_kw = data.printer_power_w / 1000.0
        cost_electricity = time_hours * power_kw * data.electricity_cost_per_kwh
    
    # Calculate total
    cost_total = cost_material + (cost_electricity or 0.0)
    
    # Convert time to hours
    time_hours = data.time_sec / 3600.0
    
    return CalculatorEstimateResponse(
        cost_material=round(cost_material, 2),
        cost_electricity=round(cost_electricity, 2) if cost_electricity is not None else None,
        cost_total=round(cost_total, 2),
        weight_kg=round(weight_kg, 3),
        time_hours=round(time_hours, 2),
    )


"""Pydantic schemas for Calculator."""

from pydantic import BaseModel, Field


class CalculatorEstimateRequest(BaseModel):
    """Schema for calculator estimate request."""

    weight_g: float = Field(..., gt=0, description="Weight of material used in grams")
    time_sec: float = Field(..., gt=0, description="Print time in seconds")
    price_per_kg: float = Field(..., ge=0, description="Material price per kilogram")
    
    # Optional: electricity and printer costs (для будущего расширения)
    electricity_cost_per_kwh: float | None = Field(
        None, ge=0, description="Electricity cost per kWh (optional, for full calculation)"
    )
    printer_power_w: float | None = Field(
        None, gt=0, description="Printer power consumption in watts (optional)"
    )


class CalculatorEstimateResponse(BaseModel):
    """Schema for calculator estimate response."""

    # Material cost
    cost_material: float = Field(..., ge=0, description="Material cost")
    
    # Electricity cost (if provided)
    cost_electricity: float | None = Field(None, ge=0, description="Electricity cost (if provided)")
    
    # Total cost
    cost_total: float = Field(..., ge=0, description="Total cost (material + electricity)")
    
    # Statistics
    weight_kg: float = Field(..., ge=0, description="Weight in kilograms")
    time_hours: float = Field(..., ge=0, description="Print time in hours")


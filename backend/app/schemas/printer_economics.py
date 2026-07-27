"""What a machine costs to run: what a person enters, and what we derive."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PrinterEconomicsUpdate(BaseModel):
    """A machine's own economics. Sending null clears a value back to the account."""

    purchase_cost: float | None = Field(None, ge=0, le=1_000_000_000)
    residual_value: float | None = Field(None, ge=0, le=1_000_000_000)
    useful_life_hours: int | None = Field(None, ge=1, le=200_000)
    average_power_watts: float | None = Field(None, gt=0, le=20_000)
    power_hotend_w: float | None = Field(None, ge=0, le=20_000)
    power_bed_w: float | None = Field(None, ge=0, le=20_000)
    power_steppers_w: float | None = Field(None, ge=0, le=20_000)
    power_electronics_w: float | None = Field(None, ge=0, le=20_000)
    maintenance_cost_per_hour: float | None = Field(None, ge=0, le=100_000)
    machine_hour_rate: float | None = Field(None, ge=0, le=1_000_000)
    economics_currency: str | None = Field(None, min_length=3, max_length=4)

    model_config = {"str_strip_whitespace": True}

    @model_validator(mode="after")
    def residual_below_purchase(self) -> "PrinterEconomicsUpdate":
        if (
            self.residual_value is not None
            and self.purchase_cost is not None
            and self.residual_value > self.purchase_cost
        ):
            raise ValueError("residual_value_above_purchase_cost")
        return self


class PrinterEconomicsResponse(BaseModel):
    """The stored numbers plus what the calculator will actually use."""

    printer_id: int
    configured: bool

    purchase_cost: float | None
    residual_value: float | None
    useful_life_hours: int | None
    average_power_watts: float | None
    power_hotend_w: float | None
    power_bed_w: float | None
    power_steppers_w: float | None
    power_electronics_w: float | None
    maintenance_cost_per_hour: float | None
    machine_hour_rate: float | None
    economics_currency: str | None

    # Per hour of printing, as shown in the breakdown.
    depreciation_per_hour: float
    electricity_per_hour: float
    maintenance_per_hour: float
    machine_cost_per_hour: float
    effective_machine_hour_rate: float
    rate_below_cost: bool

    # The calculator's own fields, already split so nothing is counted twice.
    calculator_printer_power_w: float
    calculator_printing_rate_per_hour: float
    calculator_amortization_rate_per_hour: float
    calculator_electricity_cost_per_kwh: float

    sources: dict[str, str]


class PrinterEconomicsSuggestion(BaseModel):
    """Starting numbers for a machine nobody has measured yet."""

    printer_id: int
    machine_class: str
    confidence: str
    vendor: str | None
    model_name: str | None
    bed_max_mm: float | None
    extruders: int
    usage: str
    average_power_watts: float
    useful_life_hours: int
    maintenance_cost_per_hour: float
    # Present when the person filled OrcaSlicer's own per-hour machine cost.
    orca_time_cost: float | None

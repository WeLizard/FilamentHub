"""What a machine costs to run: what a person enters, and what we derive."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

EconomicsSource = Literal[
    "printer_explicit",
    "account_explicit",
    "orca_import",
    "platform_default",
    "catalog_estimate",
    "none",
]
EconomicsReadinessStatus = Literal["configured", "partial", "incomplete"]
EconomicsMissingReason = Literal[
    "missing",
    "non_positive",
    "missing_currency",
    "currency_mismatch",
    "incomplete_pair",
]
EconomicsReadinessReason = Literal[
    "missing",
    "non_positive",
    "missing_currency",
    "currency_mismatch",
    "incomplete_pair",
    "provenance_unknown",
    "platform_default_used",
    "catalog_estimate_used",
]

PRINTER_ECONOMICS_FIELDS = frozenset(
    {
        "purchase_cost",
        "residual_value",
        "useful_life_hours",
        "average_power_watts",
        "power_hotend_w",
        "power_bed_w",
        "power_steppers_w",
        "power_electronics_w",
        "maintenance_cost_per_hour",
        "machine_hour_rate",
        "economics_currency",
    }
)


def residual_exceeds_purchase(
    purchase_cost: float | None, residual_value: float | None
) -> bool:
    return (
        residual_value is not None
        and purchase_cost is not None
        and residual_value > purchase_cost
    )


class EconomicsReadinessField(BaseModel):
    """One required input after precedence and currency checks are applied."""

    key: Literal[
        "currency",
        "machine_hour_rate",
        "electricity_cost_per_kwh",
        "printer_power_w",
        "machine_wear_per_hour",
    ]
    value: float | str | None
    source: EconomicsSource
    source_currency: str | None = None
    usable: bool
    missing_reason: EconomicsMissingReason | None = None


class EconomicsReadinessContract(BaseModel):
    """Stable v1 contract for deciding whether a quote's economics are complete."""

    version: Literal[1] = 1
    status: EconomicsReadinessStatus
    money_currency: str | None
    required_fields: list[EconomicsReadinessField]
    reasons: list[EconomicsReadinessReason] = Field(default_factory=list)


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
        if residual_exceeds_purchase(self.purchase_cost, self.residual_value):
            raise ValueError("residual_value_above_purchase_cost")
        return self


class PrinterEconomicsSuggestionApply(BaseModel):
    """Server-verified physical fields to copy from the current catalog suggestion."""

    usage: Literal["occasional", "regular", "intensive"] = "regular"
    fields: list[
        Literal[
            "average_power_watts",
            "power_hotend_w",
            "power_bed_w",
            "power_steppers_w",
            "power_electronics_w",
            "useful_life_hours",
        ]
    ] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_fields(self) -> "PrinterEconomicsSuggestionApply":
        if len(self.fields) != len(set(self.fields)):
            raise ValueError("duplicate_economics_suggestion_field")
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
    calculator_currency: str | None

    depreciation_per_hour: float
    electricity_per_hour: float
    maintenance_per_hour: float
    machine_cost_per_hour: float
    effective_machine_hour_rate: float
    rate_below_cost: bool

    calculator_printer_power_w: float
    calculator_printing_rate_per_hour: float
    calculator_amortization_rate_per_hour: float
    calculator_electricity_cost_per_kwh: float

    sources: dict[str, str]
    applied_sources: dict[str, EconomicsSource]
    readiness: EconomicsReadinessContract


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
    power_hotend_w: float
    power_bed_w: float
    power_steppers_w: float
    power_electronics_w: float
    useful_life_hours: int
    maintenance_cost_per_hour: float
    orca_time_cost: float | None

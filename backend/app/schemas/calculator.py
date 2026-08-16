"""Pydantic schemas for Calculator."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PricingMethod(str, Enum):
    """Метод расчета стоимости печати."""
    BY_WEIGHT = "by_weight"  # По граммам (весу материала)
    BY_TIME = "by_time"  # По часам печати
    COMBINED = "combined"  # Комбинированный (материал + время + дополнительные затраты)


class RoundingMode(str, Enum):
    """Стратегия округления итоговой цены."""
    UP = "up"
    DOWN = "down"
    NEAREST = "nearest"


CalculatorMaterialRole = Literal["support", "brim", "prime_tower"]
CalculatorMaterialRoleSource = Literal["gcode_extrusion_roles"]


class CalculatorMaterialLineRequest(BaseModel):
    """One material/tool contribution to a calculator estimate."""

    line_id: str = Field(..., min_length=1, max_length=160)
    job_key: str | None = Field(None, max_length=160)
    tool_index: int | None = Field(None, ge=0)
    label: str | None = Field(None, max_length=255)
    weight_g: float = Field(..., gt=0)
    spool_price: float = Field(..., ge=0)
    spool_weight_kg: float = Field(..., gt=0)
    delivery_cost: float = Field(0, ge=0)
    price_source: Literal["spool", "filamenthub", "slicer", "manual"] = "manual"
    spool_id: int | None = Field(None, ge=1)
    filament_id: int | None = Field(None, ge=1)
    density_g_cm3: float | None = Field(None, gt=0, le=10)
    abrasiveness: float | None = Field(None, ge=0.5, le=5)
    role_weights_g: dict[CalculatorMaterialRole, float] = Field(default_factory=dict)
    role_weight_source: CalculatorMaterialRoleSource | None = None
    support_weight_g: float | None = Field(None, ge=0)
    support_weight_source: CalculatorMaterialRoleSource | None = None

    @model_validator(mode="after")
    def validate_role_weights(self) -> "CalculatorMaterialLineRequest":
        if any(weight < 0 for weight in self.role_weights_g.values()):
            raise ValueError("role_weights_g values cannot be negative")
        if self.role_weights_g and self.role_weight_source is None:
            raise ValueError("role_weights_g requires role_weight_source")
        if not self.role_weights_g and self.role_weight_source is not None:
            raise ValueError("role_weight_source requires role_weights_g")
        if self.support_weight_g is None:
            if self.support_weight_source is not None:
                raise ValueError("support_weight_source requires support_weight_g")
        else:
            if self.support_weight_source is None:
                raise ValueError("support_weight_g requires support_weight_source")
            mapped_support_weight = self.role_weights_g.get("support")
            if (
                mapped_support_weight is not None
                and abs(mapped_support_weight - self.support_weight_g) > 0.001
            ):
                raise ValueError("support_weight_g conflicts with role_weights_g")
        effective_role_weights = dict(self.role_weights_g)
        if self.support_weight_g is not None:
            effective_role_weights.setdefault("support", self.support_weight_g)
        if sum(effective_role_weights.values()) > self.weight_g + 0.001:
            raise ValueError("role weights cannot exceed weight_g")
        return self


class CalculatorMaterialRoleCost(BaseModel):
    """Resolved cost of one proven G-code extrusion role."""

    role: CalculatorMaterialRole
    weight_g: float = Field(..., ge=0)
    cost: float = Field(..., ge=0)
    source: CalculatorMaterialRoleSource


class CalculatorMaterialLineCost(BaseModel):
    """Resolved cost of one material/tool line."""

    line_id: str
    job_key: str | None = None
    tool_index: int | None = None
    label: str | None = None
    weight_g: float = Field(..., gt=0)
    price_per_gram: float = Field(..., ge=0)
    cost: float = Field(..., ge=0)
    price_source: Literal["spool", "filamenthub", "slicer", "manual"]
    spool_id: int | None = None
    filament_id: int | None = None
    support_weight_g: float | None = Field(None, ge=0)
    support_cost: float | None = Field(None, ge=0)
    non_support_weight_g: float | None = Field(None, ge=0)
    non_support_cost: float | None = Field(None, ge=0)
    support_weight_source: CalculatorMaterialRoleSource | None = None
    role_costs: list[CalculatorMaterialRoleCost] = Field(default_factory=list)
    other_weight_g: float | None = Field(None, ge=0)
    other_cost: float | None = Field(None, ge=0)


class CalculatorPrintJobRequest(BaseModel):
    """Execution and commercial quantity of one uploaded G-code plate."""

    job_key: str = Field(..., min_length=1, max_length=160)
    repeats: int = Field(1, ge=1, le=1000)
    output_quantity_per_run: int = Field(1, ge=1, le=100_000)
    print_time_seconds: float = Field(..., ge=0, le=31_536_000)
    quote_mode: Literal["set", "groups"] = "set"


CalculatorPreflightStatus = Literal[
    "ready",
    "ready_with_change",
    "ready_at_risk",
    "insufficient",
    "needs_clarification",
    "conflict",
]
CalculatorRemainingStatus = Literal["known", "stale", "unknown"]
CalculatorRemainingEvidence = Literal[
    "measurement",
    "provider_report",
    "manual_update",
    "import",
    "intake",
    "estimate",
]


class CalculatorPreflightLineRequest(BaseModel):
    """One material demand checked against explicitly selected physical spools."""

    line_id: str = Field(..., min_length=1, max_length=160)
    job_key: str | None = Field(None, max_length=160)
    tool_index: int | None = Field(None, ge=0)
    label: str | None = Field(None, max_length=255)
    weight_g: float = Field(..., gt=0)
    length_mm: float | None = Field(None, ge=0)
    volume_cm3: float | None = Field(None, ge=0)
    filament_id: int | None = Field(None, ge=1)
    spool_ids: list[int] = Field(default_factory=list, max_length=16)
    evidence_source: Literal["gcode", "manual"] = "manual"
    mapping_source: Literal["explicit", "automatic", "unresolved"] = "unresolved"
    mapping_confidence: Literal["high", "medium", "low"] | None = None

    @model_validator(mode="after")
    def validate_spool_ids(self) -> "CalculatorPreflightLineRequest":
        if any(spool_id < 1 for spool_id in self.spool_ids):
            raise ValueError("spool_ids must contain positive integers")
        if len(self.spool_ids) != len(set(self.spool_ids)):
            raise ValueError("spool_ids must be unique within a material line")
        return self


class CalculatorPreflightMachineEvidence(BaseModel):
    """Machine facts carried by one sliced job, without inventing device state."""

    job_key: str | None = Field(None, max_length=160)
    printer_profile_id: int | None = Field(None, ge=1)
    printer_settings_id: str | None = Field(None, max_length=200)
    nozzle_diameter_mm: float | None = Field(None, ge=0.1, le=2.0)
    max_nozzle_temperature_c: float | None = Field(None, ge=0, le=500)
    source: Literal["gcode", "orca_plugin"] = "gcode"


class CalculatorPreflightRequest(BaseModel):
    """Read-only material readiness check for the current calculation."""

    lines: list[CalculatorPreflightLineRequest] = Field(min_length=1, max_length=128)
    print_jobs: list[CalculatorPrintJobRequest] = Field(default_factory=list, max_length=20)
    physical_printer_id: int | None = Field(None, ge=1)
    machine_evidence: list[CalculatorPreflightMachineEvidence] = Field(
        default_factory=list,
        max_length=20,
    )
    quantity: int = Field(default=1, ge=1, le=100_000)
    safety_buffer_percent: float = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def validate_jobs(self) -> "CalculatorPreflightRequest":
        line_ids = [line.line_id for line in self.lines]
        if len(line_ids) != len(set(line_ids)):
            raise ValueError("lines must contain unique line_id values")
        evidence_jobs = [item.job_key for item in self.machine_evidence]
        if len(evidence_jobs) != len(set(evidence_jobs)):
            raise ValueError("machine_evidence must contain unique job_key values")
        if not self.print_jobs:
            if any(job_key is not None for job_key in evidence_jobs):
                raise ValueError("machine evidence cannot reference a job without print_jobs")
            return self
        job_keys = [job.job_key for job in self.print_jobs]
        if len(job_keys) != len(set(job_keys)):
            raise ValueError("print_jobs must contain unique job_key values")
        known_jobs = set(job_keys)
        if any(line.job_key not in known_jobs for line in self.lines):
            raise ValueError("every preflight line must reference a known print job")
        if any(job_key not in known_jobs for job_key in evidence_jobs):
            raise ValueError("every machine evidence item must reference a known print job")
        return self


class CalculatorPreflightSpoolAllocation(BaseModel):
    """How one selected spool contributes to one demand line."""

    spool_id: int
    filament_id: int | None
    state: str
    remaining_before_g: float = Field(ge=0)
    reserved_elsewhere_g: float = Field(default=0, ge=0)
    planned_coverage_g: float = Field(ge=0)
    expected_consumption_g: float = Field(ge=0)
    expected_after_g: float = Field(ge=0)
    sequence_index: int | None = Field(None, ge=1)
    remaining_source: Literal["inventory_ledger"] = "inventory_ledger"
    remaining_status: CalculatorRemainingStatus
    remaining_evidence: CalculatorRemainingEvidence
    remaining_confidence: Literal["high", "medium", "low"]
    remaining_updated_at: datetime
    last_used_at: datetime | None = None
    purchase_currency: str | None = None
    unit_purchase_cost_per_g: float | None = Field(None, ge=0)
    expected_purchase_cost: float | None = Field(None, ge=0)
    issues: list[
        Literal[
            "material_mismatch",
            "unavailable_state",
            "empty",
            "stale_remaining",
            "unknown_remaining",
        ]
    ] = Field(default_factory=list)


class CalculatorPreflightSpoolSuggestion(BaseModel):
    """One owned spool that may close the current material gap."""

    spool_id: int
    filament_id: int
    relation: Literal[
        "same_filament", "same_line", "same_type_and_color", "same_material_type"
    ]
    requires_reslice: bool
    remaining_g: float = Field(ge=0)
    reserved_elsewhere_g: float = Field(default=0, ge=0)
    coverage_target_g: float = Field(ge=0)
    covers_target: bool
    remaining_status: CalculatorRemainingStatus
    remaining_evidence: CalculatorRemainingEvidence
    remaining_confidence: Literal["high", "medium", "low"]
    remaining_updated_at: datetime


class CalculatorPreflightLineResponse(BaseModel):
    """Explainable readiness result for one material/tool line."""

    line_id: str
    job_key: str | None
    tool_index: int | None
    label: str | None
    filament_id: int | None
    status: CalculatorPreflightStatus
    evidence_source: Literal["gcode", "manual"]
    mapping_source: Literal["explicit", "automatic", "unresolved"]
    mapping_confidence: Literal["high", "medium", "low"] | None
    required_base_g: float = Field(ge=0)
    required_length_mm: float | None = Field(None, ge=0)
    required_volume_cm3: float | None = Field(None, ge=0)
    safety_buffer_g: float = Field(ge=0)
    required_planned_g: float = Field(ge=0)
    selected_remaining_g: float = Field(ge=0)
    expected_after_g: float = Field(ge=0)
    shortfall_base_g: float = Field(ge=0)
    shortfall_buffer_g: float = Field(ge=0)
    change_count: int = Field(ge=0)
    requires_spool_change: bool
    purchase_cost_by_currency: dict[str, float] = Field(default_factory=dict)
    purchase_cost_complete: bool
    allocations: list[CalculatorPreflightSpoolAllocation] = Field(default_factory=list)
    spool_suggestions: list[CalculatorPreflightSpoolSuggestion] = Field(default_factory=list)


CalculatorPrinterCompatibilityStatus = Literal["compatible", "incompatible", "unknown"]


class CalculatorPrinterCompatibilityCheck(BaseModel):
    """One explainable, advisory machine/material compatibility comparison."""

    kind: Literal["nozzle_diameter", "nozzle_hrc", "hotend_temperature"]
    status: CalculatorPrinterCompatibilityStatus
    job_key: str | None = None
    line_id: str | None = None
    printer_profile_id: int | None = None
    printer_profile_name: str | None = None
    required_value: float | None = None
    available_values: list[float] = Field(default_factory=list)
    unit: Literal["mm", "HRC", "°C"]
    requirement_source: Literal["gcode", "filament_catalog"]
    capability_source: Literal["printer_profile", "catalog_printer"] | None = None


class CalculatorPrinterCompatibilityResponse(BaseModel):
    """Advisory compatibility for the explicitly selected physical printer."""

    physical_printer_id: int
    physical_printer_name: str
    status: CalculatorPrinterCompatibilityStatus
    checks: list[CalculatorPrinterCompatibilityCheck] = Field(default_factory=list)


class CalculatorPreflightResponse(BaseModel):
    """Read-only readiness result; it never reserves or consumes inventory."""

    status: CalculatorPreflightStatus
    safety_buffer_percent: float = Field(ge=0, le=100)
    required_base_g: float = Field(ge=0)
    safety_buffer_g: float = Field(ge=0)
    required_planned_g: float = Field(ge=0)
    purchase_cost_by_currency: dict[str, float] = Field(default_factory=dict)
    purchase_cost_complete: bool
    printer_compatibility: CalculatorPrinterCompatibilityResponse | None = None
    lines: list[CalculatorPreflightLineResponse]


class CalculatorEstimateRequest(BaseModel):
    """Schema for calculator estimate request."""

    pricing_method: PricingMethod = Field(
        default=PricingMethod.COMBINED,
        description="Метод расчета стоимости: by_weight, by_time или combined"
    )

    # ========== Параметры материала ==========
    weight_g: float | None = Field(
        None, gt=0, description="Вес использованного материала в граммах"
    )
    supports_weight_g: float | None = Field(
        None, ge=0, description="Вес поддержек в граммах"
    )
    supports_loss_coefficient: float | None = Field(
        None, ge=1.0, le=3.0, description="Коэффициент потерь на поддержки (1.0-3.0, обычно 1.2-1.5)"
    )
    spool_price: float | None = Field(
        None, ge=0, description="Цена катушки материала (руб)"
    )
    spool_weight_kg: float | None = Field(
        None, gt=0, description="Вес катушки материала (кг)"
    )
    delivery_cost: float | None = Field(
        None, ge=0, description="Стоимость доставки материала (руб), по умолчанию 0"
    )
    material_lines: list[CalculatorMaterialLineRequest] = Field(
        default_factory=list,
        max_length=128,
        description="Построчная стоимость материалов для multi-job/multi-material расчёта",
    )
    print_jobs: list[CalculatorPrintJobRequest] = Field(
        default_factory=list,
        max_length=20,
        description="Столы G-code с собственным числом запусков и товарным выходом",
    )

    # ========== Параметры времени печати ==========
    time_sec: float | None = Field(
        None, ge=0, description="Время печати в секундах"
    )
    time_hours: float | None = Field(
        None, ge=0, description="Время печати в часах (альтернатива time_sec)"
    )
    time_minutes: float | None = Field(
        None, ge=0, description="Время печати в минутах (дополнительно к часам)"
    )

    # ========== Почасовая ставка печати (для метода by_time) ==========
    price_per_hour: float | None = Field(
        None, ge=0, description="Цена за час печати (руб/ч) - для метода by_time"
    )

    # ========== Электроэнергия ==========
    electricity_cost_per_kwh: float | None = Field(
        None, ge=0, description="Стоимость 1 кВт·ч электроэнергии (руб)"
    )
    printer_power_w: float | None = Field(
        None, gt=0, description="Мощность принтера в ваттах"
    )

    # ========== Дополнительные услуги (почасовая оплата) ==========
    modeling_hours: float | None = Field(
        None, ge=0, description="Время моделирования в часах"
    )
    modeling_minutes: float | None = Field(
        None, ge=0, description="Время моделирования в минутах (дополнительно к часам)"
    )
    modeling_rate_per_hour: float | None = Field(
        None, ge=0, description="Ставка за час моделирования (руб/ч)"
    )

    postprocessing_hours: float | None = Field(
        None, ge=0, description="Время постобработки в часах"
    )
    postprocessing_minutes: float | None = Field(
        None, ge=0, description="Время постобработки в минутах (дополнительно к часам)"
    )
    postprocessing_rate_per_hour: float | None = Field(
        None, ge=0, description="Ставка за час постобработки (руб/ч)"
    )

    printing_rate_per_hour: float | None = Field(
        None, ge=0, description="Ставка за час печати (руб/ч) - для combined метода"
    )

    amortization_rate_per_hour: float | None = Field(
        None, ge=0, description="Ставка амортизации оборудования за час (руб/ч)"
    )

    # ========== Количество деталей ==========
    quantity: int = Field(
        default=1, gt=0, description="Количество деталей для печати"
    )
    parts_per_print: int | None = Field(
        default=None, ge=1, le=1000, description="Сколько деталей печатается за один запуск / на одном столе"
    )

    # ========== Накладные расходы и наценка ==========
    overhead_percent: float | None = Field(
        None, ge=0, le=100, description="Процент накладных расходов (20-30% по умолчанию)"
    )
    markup_percent: float | None = Field(
        None, ge=0, le=200, description="Процент наценки (20-70% в зависимости от сегмента)"
    )
    tax_rate_percent: float | None = Field(
        None, ge=0, le=100, description="Налоговая ставка в процентах (например 0, 4, 6)"
    )

    # ========== Коэффициенты корректировки ==========
    urgency_coefficient: float | None = Field(
        None, ge=1.0, le=2.0, description="Коэффициент срочности (1.0 = стандарт, 1.2-1.5 = срочно, +20-50%)"
    )
    complexity_coefficient: float | None = Field(
        None, ge=1.0, le=3.0, description="Коэффициент сложности (1.0 = просто, 1.2-2.5 = сложно, +15-30%)"
    )
    volume_discount_coefficient: float | None = Field(
        None, ge=0.85, le=1.0, description="Коэффициент скидки за объем (0.85-1.0, скидка 0-15%)"
    )

    # ========== Фиксированные расходы ==========
    fixed_costs: float | None = Field(
        None, ge=0, description="Фиксированные расходы (упаковка, доставка до ПВЗ, обычно 50-100 руб)"
    )

    # ========== Минимальная цена заказа ==========
    min_order_price: float | None = Field(
        None, ge=0, description="Минимальная цена заказа (если итоговая цена меньше, устанавливается минимум, обычно 300-500 руб)"
    )

    # ========== Подготовка стола ==========
    bed_prep_cost_per_print: float | None = Field(
        None, ge=0, description="Стоимость подготовки стола за один запуск (клей, спрей, протирка — обычно 10-50 руб)"
    )

    # ========== Потери материала ==========
    waste_factor_percent: float | None = Field(
        None, ge=0, le=30, description="Процент потерь материала (пурга, скирт, дефекты) помимо поддержек (обычно 5-15%)"
    )

    # ========== Износ сопла ==========
    nozzle_price: float | None = Field(
        None, ge=0, description="Цена сопла (руб)"
    )
    nozzle_life_cm3: float | None = Field(
        None, gt=0, description="Ресурс сопла в см³ экструдированного материала (латунь ~15000, сталь ~50000)"
    )
    material_abrasiveness: float | None = Field(
        None, ge=0.5, le=5.0, description="Коэффициент абразивности материала (PLA=1.0, PETG=1.2, Carbon=2.5, Glass=3.0)"
    )
    filament_density: float | None = Field(
        None, gt=0, le=10.0, description="Плотность филамента г/см³ (PLA=1.24, PETG=1.27, ABS=1.04, Nylon=1.14)"
    )

    # ========== Мониторинг (пассивное время оператора) ==========
    monitoring_factor: float | None = Field(
        None, ge=0, le=0.5, description="Доля времени печати на мониторинг оператором (0.05-0.15 = 5-15%)"
    )

    # ========== Округление ==========
    round_to_nearest: int | None = Field(
        None, ge=0, description="Округлять итоговую сумму до ближайшего N (например, 10 для округления до десятков)"
    )
    rounding_mode: RoundingMode = Field(
        default=RoundingMode.UP,
        description="Стратегия округления итоговой суммы: up, down или nearest"
    )

    @model_validator(mode="after")
    def validate_print_jobs(self) -> "CalculatorEstimateRequest":
        """Keep job multipliers unambiguous and material lines attached to a known plate."""
        if not self.print_jobs:
            return self

        job_keys = [job.job_key for job in self.print_jobs]
        if len(job_keys) != len(set(job_keys)):
            raise ValueError("print_jobs must contain unique job_key values")
        known_jobs = set(job_keys)
        if any(line.job_key not in known_jobs for line in self.material_lines):
            raise ValueError("every material line must reference a known print job")
        return self


class CalculatorEstimateResponse(BaseModel):
    """Schema for calculator estimate response."""

    # Компоненты стоимости
    cost_material: float = Field(0, ge=0, description="Стоимость материала")
    cost_waste: float = Field(0, ge=0, description="Потери материала (пурга, скирт, дефекты)")
    cost_electricity: float = Field(0, ge=0, description="Стоимость электроэнергии")
    cost_modeling: float = Field(0, ge=0, description="Стоимость моделирования")
    cost_printing: float = Field(0, ge=0, description="Стоимость печати (почасовая)")
    cost_postprocessing: float = Field(0, ge=0, description="Стоимость постобработки")
    cost_monitoring: float = Field(0, ge=0, description="Мониторинг печати (пассивное время оператора)")
    cost_amortization: float = Field(0, ge=0, description="Стоимость амортизации")
    cost_bed_prep: float = Field(0, ge=0, description="Стоимость подготовки стола")
    cost_nozzle_wear: float = Field(0, ge=0, description="Износ сопла (объёмная модель)")
    cost_tax: float = Field(0, ge=0, description="Сумма налога, включенная в итоговую цену")

    # Промежуточные расчеты
    cost_direct: float = Field(0, ge=0, description="Прямые затраты (материалы + время + труд)")
    cost_overhead: float = Field(0, ge=0, description="Накладные расходы")
    cost_before_markup: float = Field(0, ge=0, description="Стоимость до наценки")
    cost_markup: float = Field(0, ge=0, description="Наценка")
    material_line_costs: list[CalculatorMaterialLineCost] = Field(default_factory=list)

    # Итоговые суммы
    cost_first_part: float = Field(..., ge=0, description="Цена первой детали (включает все затраты)")
    cost_subsequent_parts: float = Field(..., ge=0, description="Цена последующих деталей (без моделирования)")
    cost_total: float = Field(..., ge=0, description="Общая стоимость всей партии")
    cost_final: float = Field(..., ge=0, description="Финальная цена с учетом всех коэффициентов и минимума")

    # Статистика
    weight_kg: float | None = Field(None, ge=0, description="Вес материала в килограммах")
    time_hours: float | None = Field(None, ge=0, description="Время печати в часах")
    total_time_hours: float | None = Field(None, ge=0, description="Общее время (печать + подготовка + постобработка) в часах")
    quantity: int = Field(..., gt=0, description="Количество деталей")
    print_runs: int | None = Field(None, gt=0, description="Количество запусков печати")

    # Финансовые показатели (только для combined)
    cost_of_goods_sold: float | None = Field(None, ge=0, description="Себестоимость (прямые затраты + накладные + фиксированные, без налога)")
    profit_margin: float | None = Field(None, description="Маржинальность / прибыль = цена без налога - себестоимость")
    profit_margin_percent: float | None = Field(None, description="Маржинальность в процентах от цены без налога")

    # Метод расчета
    pricing_method: PricingMethod = Field(..., description="Использованный метод расчета")

    # Примененные коэффициенты
    applied_urgency_coefficient: float | None = Field(None, description="Примененный коэффициент срочности")
    applied_complexity_coefficient: float | None = Field(None, description="Примененный коэффициент сложности")
    applied_volume_discount: float | None = Field(None, description="Примененный коэффициент скидки за объем")
    applied_tax_rate_percent: float | None = Field(None, description="Примененная налоговая ставка")


class CalculatorMaterialIdentityResolution(BaseModel):
    """Server-side resolution of a stable material identifier from the slicer."""

    status: Literal["resolved", "ambiguous", "unresolved"]
    source: Literal[
        "filamenthub_filament_id",
        "filamenthub_preset_id",
        "user_preset_filament_id",
        "catalog_preset_filament_id",
    ] | None = None
    stable_id: str = Field(..., description="Исходный стабильный ID из G-code или профиля слайсера")
    filament_id: int | None = Field(None, ge=1)
    preset_id: int | None = Field(None, ge=1)
    candidate_filament_ids: list[int] = Field(default_factory=list)


class CalculatorParsedMaterial(BaseModel):
    """Parsed material row extracted from G-code metadata."""

    tool_index: int | None = Field(None, ge=0, description="Индекс инструмента T0..TN")
    type: str | None = Field(None, description="Тип материала из G-code metadata")
    name: str | None = Field(None, description="Имя / settings id материала")
    settings_id: str | None = Field(
        None,
        description="Отображаемое имя выбранного профиля из контейнера; может меняться при переименовании",
    )
    vendor: str | None = Field(None, description="Вендор материала")
    color: str | None = Field(None, description="Цвет материала")
    weight_g: float | None = Field(None, ge=0, description="Вес материала в граммах")
    length_mm: float | None = Field(None, ge=0, description="Длина материала в миллиметрах")
    volume_cm3: float | None = Field(None, ge=0, description="Использованный объём в кубических сантиметрах")
    density_g_cm3: float | None = Field(None, gt=0, description="Плотность из профиля слайсера")
    diameter_mm: float | None = Field(None, gt=0, description="Диаметр прутка из профиля слайсера")
    slicer_filament_id: str | None = Field(None, description="Идентификатор филамента из профиля слайсера")
    identity_resolution: CalculatorMaterialIdentityResolution | None = Field(
        None,
        description="Результат серверного сопоставления стабильного filament_id с каталогом FilamentHub",
    )
    slicer_usage_cost: float | None = Field(
        None,
        ge=0,
        description="Справочная стоимость фактически израсходованного материала по расчёту слайсера",
    )
    slicer_profile_price_per_kg: float | None = Field(
        None,
        ge=0,
        description="Цена за кг из профиля слайсера; резервная рекомендация, не источник валюты",
    )
    flow_ratio: float | None = Field(None, gt=0, description="Коэффициент потока из профиля слайсера")
    max_volumetric_speed_mm3_s: float | None = Field(
        None,
        ge=0,
        description="Максимальная объёмная скорость из профиля слайсера",
    )
    prime_volume_mm3: float | None = Field(None, ge=0, description="Объём прочистки/прайма из профиля слайсера")
    is_support_material: bool | None = Field(None, description="Профиль помечен как материал поддержек")
    used_for_model: bool | None = Field(None, description="Материал использован для модели")
    used_for_support: bool | None = Field(None, description="Материал использован для поддержек")
    infill_weight_g: float | None = Field(
        None,
        ge=0,
        description="Расход материала на G-code роли infill, нормализованный к весу tool",
    )
    support_weight_g: float | None = Field(
        None,
        ge=0,
        description="Расход материала на G-code роли support, нормализованный к весу tool",
    )
    brim_weight_g: float | None = Field(
        None,
        ge=0,
        description="Расход материала на G-code роль brim, нормализованный к весу tool",
    )
    prime_tower_weight_g: float | None = Field(
        None,
        ge=0,
        description="Расход материала на G-code роль prime/wipe tower, нормализованный к весу tool",
    )


class CalculatorFhubIdentity(BaseModel):
    """Versioned FilamentHub identity embedded in G-code by the Orca plugin."""

    kind: Literal["material_preset", "print_profile", "printer_profile"]
    entity_id: int = Field(..., ge=1, le=2**63 - 1)
    tool_index: int | None = Field(None, ge=0, le=255)


class CalculatorParsedObjectGroup(BaseModel):
    """Instances of one model name found in EXCLUDE_OBJECT metadata."""

    name: str = Field(..., min_length=1, max_length=255)
    count: int = Field(..., ge=1)
    extrusion_share: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Доля экструзии именованных объектов, используемая для распределения задания",
    )
    material_weights_g: dict[int, float] = Field(
        default_factory=dict,
        description="Вес каждого Tn внутри именованных объектов; общие skirt/purge/support не распределяются",
    )


class CalculatorGcodeParseResponse(BaseModel):
    """Schema for parsed G-code metadata used by Calculator Pro."""

    file_name: str = Field(..., description="Имя загруженного файла")
    file_size_bytes: int = Field(..., ge=0, description="Размер исходного файла в байтах")
    slicer_name: str | None = Field(None, description="Определённый слайсер")
    slicer_version: str | None = Field(None, description="Версия слайсера")
    printer_settings_id: str | None = Field(None, description="Machine preset из G-code")
    print_settings_id: str | None = Field(None, description="Process preset из G-code")
    printer_model: str | None = Field(None, description="Модель принтера из G-code")
    fhub_identities: list[CalculatorFhubIdentity] = Field(
        default_factory=list,
        description="Доступные текущему пользователю стабильные FH identities из G-code",
    )
    print_time_seconds: int | None = Field(None, ge=0, description="Оценка времени печати в секундах")
    first_layer_print_time_seconds: int | None = Field(
        None,
        ge=0,
        description="Время первого слоя как подмножество общего времени",
    )
    total_filament_weight_g: float | None = Field(None, ge=0, description="Суммарный вес филамента в граммах")
    total_filament_length_mm: float | None = Field(None, ge=0, description="Суммарная длина филамента в миллиметрах")
    total_filament_volume_cm3: float | None = Field(None, ge=0, description="Суммарный объём филамента в см³")
    infill_filament_weight_g: float | None = Field(
        None,
        ge=0,
        description="Суммарный фактический расход на роли infill",
    )
    support_filament_weight_g: float | None = Field(
        None,
        ge=0,
        description="Суммарный фактический расход на роли support",
    )
    brim_filament_weight_g: float | None = Field(
        None,
        ge=0,
        description="Суммарный фактический расход на роль brim",
    )
    prime_tower_filament_weight_g: float | None = Field(
        None,
        ge=0,
        description="Суммарный фактический расход на роль prime/wipe tower",
    )
    object_filament_weight_g: float | None = Field(
        None,
        ge=0,
        description="Экструзия внутри именованных EXCLUDE_OBJECT scopes",
    )
    shared_filament_weight_g: float | None = Field(
        None,
        ge=0,
        description="Экструзия вне именованных объектов: общие и служебные структуры",
    )
    layer_height_mm: float | None = Field(None, ge=0, description="Высота слоя")
    initial_layer_height_mm: float | None = Field(None, ge=0, description="Высота первого слоя")
    sparse_infill_density_percent: float | None = Field(None, ge=0, description="Плотность заполнения в процентах")
    sparse_infill_pattern: str | None = Field(None, description="Паттерн заполнения")
    wall_loops: int | None = Field(None, ge=0, description="Количество периметров / стенок")
    outer_wall_line_width_mm: float | None = Field(None, ge=0, description="Ширина линии внешней стенки")
    inner_wall_line_width_mm: float | None = Field(None, ge=0, description="Ширина линии внутренней стенки")
    outer_wall_speed_mm_s: float | None = Field(None, ge=0, description="Скорость внешней стенки")
    inner_wall_speed_mm_s: float | None = Field(None, ge=0, description="Скорость внутренней стенки")
    sparse_infill_speed_mm_s: float | None = Field(None, ge=0, description="Скорость разреженного заполнения")
    support_speed_mm_s: float | None = Field(None, ge=0, description="Скорость печати поддержек")
    initial_layer_speed_mm_s: float | None = Field(None, ge=0, description="Скорость первого слоя")
    prime_volume_mm3: float | None = Field(None, ge=0, description="Общий объём прайма из настроек процесса")
    nozzle_diameter_mm: float | None = Field(None, ge=0, description="Диаметр сопла")
    nozzle_temperature_first_layer_c: float | None = Field(None, ge=0, description="Температура сопла первого слоя")
    nozzle_temperature_other_layers_c: float | None = Field(None, ge=0, description="Температура сопла остальных слоёв")
    bed_temperature_first_layer_c: float | None = Field(None, ge=0, description="Температура стола первого слоя")
    bed_temperature_other_layers_c: float | None = Field(None, ge=0, description="Температура стола остальных слоёв")
    object_count: int | None = Field(None, ge=0, description="Количество объектов в задании")
    object_groups: list[CalculatorParsedObjectGroup] = Field(
        default_factory=list,
        description="Группы экземпляров по имени из EXCLUDE_OBJECT_DEFINE",
    )
    total_layers: int | None = Field(None, ge=0, description="Общее количество слоёв")
    max_z_height_mm: float | None = Field(None, ge=0, description="Максимальная высота модели по Z")
    support_type: str | None = Field(None, description="Тип поддержек")
    support_threshold_angle_deg: float | None = Field(None, ge=0, description="Угол поддержек")
    support_used: bool | None = Field(None, description="Поддержки реально присутствуют в sliced job")
    support_filament_config_index: int | None = Field(None, ge=0, description="Raw support_filament setting (0 = auto/current)")
    support_interface_filament_config_index: int | None = Field(None, ge=0, description="Raw support_interface_filament setting")
    support_roles_detected: list[str] = Field(default_factory=list, description="Роли support, обнаруженные в toolpath comments")
    brim_width_mm: float | None = Field(None, ge=0, description="Ширина brim")
    raft_layers: int | None = Field(None, ge=0, description="Количество raft-слоёв")
    active_material_count: int | None = Field(None, ge=0, description="Количество реально используемых материалов")
    is_multi_material: bool | None = Field(None, description="Мульти-материальная ли печать")
    toolchange_count: int | None = Field(None, ge=0, description="Количество смен инструмента / материала")
    thumbnail_data_url: str | None = Field(None, description="Data URL превью G-code, если найден")
    container_format: str = Field("plain_gcode", description="plain_gcode или gcode_3mf")
    plate_index: int | None = Field(None, ge=1, description="Выбранная plate внутри gcode.3mf")
    available_plate_indices: list[int] = Field(default_factory=list, description="Доступные sliced plates внутри gcode.3mf")
    materials: list[CalculatorParsedMaterial] = Field(default_factory=list, description="Материалы, извлечённые из G-code")


class CalculatorHistoryFilamentSnapshot(BaseModel):
    """Lightweight filament snapshot stored with a calculator history entry."""

    id: int | None = Field(None, description="ID филамента в каталоге, если был выбран")
    name: str = Field(..., description="Имя филамента")
    brand_name: str | None = Field(None, description="Название бренда")
    material_type: str | None = Field(None, description="Тип материала")
    color_name: str | None = Field(None, description="Цвет")


class CalculatorHistoryParsedJob(BaseModel):
    """One parsed file/plate preserved as part of a calculator batch."""

    job_key: str = Field(..., min_length=1, max_length=160)
    parsed_gcode: CalculatorGcodeParseResponse


class CalculatorHistoryEntryCreate(BaseModel):
    """Persisted Calculator Pro estimate payload."""

    title: str | None = Field(None, max_length=255, description="Пользовательский или вычисленный заголовок расчёта")
    request_data: CalculatorEstimateRequest
    result_data: CalculatorEstimateResponse
    parsed_gcode: CalculatorGcodeParseResponse | None = None
    parsed_jobs: list[CalculatorHistoryParsedJob] = Field(default_factory=list, max_length=128)
    filament_snapshot: CalculatorHistoryFilamentSnapshot | None = None


class CalculatorHistoryEntryResponse(BaseModel):
    """Stored Calculator Pro history entry."""

    id: int
    user_id: int
    title: str
    pricing_method: PricingMethod
    request_data: CalculatorEstimateRequest
    result_data: CalculatorEstimateResponse
    parsed_gcode: CalculatorGcodeParseResponse | None = None
    parsed_jobs: list[CalculatorHistoryParsedJob] = Field(default_factory=list)
    filament_snapshot: CalculatorHistoryFilamentSnapshot | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalculatorHistoryEntryListResponse(BaseModel):
    """Paginated list of calculator history entries."""

    items: list[CalculatorHistoryEntryResponse]
    total: int


# ── Calculator profile (server-persisted settings) ──────────────────────


class CalculatorProfileUpdate(BaseModel):
    """PUT body — all fields optional, only supplied fields are updated."""

    # Economics
    electricity_cost_per_kwh: float | None = Field(None, ge=0)
    printer_power_w: float | None = Field(None, gt=0)
    modeling_rate_per_hour: float | None = Field(None, ge=0)
    postprocessing_rate_per_hour: float | None = Field(None, ge=0)
    printing_rate_per_hour: float | None = Field(None, ge=0)
    amortization_rate_per_hour: float | None = Field(None, ge=0)
    overhead_percent: float | None = Field(None, ge=0, le=100)
    markup_percent: float | None = Field(None, ge=0, le=200)
    tax_rate_percent: float | None = Field(None, ge=0, le=100)
    fixed_costs: float | None = Field(None, ge=0)
    bed_prep_cost_per_print: float | None = Field(None, ge=0)
    min_order_price: float | None = Field(None, ge=0)
    round_to_nearest: int | None = Field(None, ge=0)
    rounding_mode: RoundingMode | None = None
    printer_purchase_price: float | None = Field(None, ge=0)
    printer_useful_hours: int | None = Field(None, ge=0)
    maintenance_cost_per_hour: float | None = Field(None, ge=0)
    power_hotend_w: float | None = Field(None, ge=0)
    power_bed_w: float | None = Field(None, ge=0)
    power_steppers_w: float | None = Field(None, ge=0)
    power_electronics_w: float | None = Field(None, ge=0)

    # Quote
    seller_name: str | None = Field(None, max_length=255)
    seller_inn: str | None = Field(None, max_length=32)
    seller_phone: str | None = Field(None, max_length=64)
    payment_terms: str | None = Field(None, max_length=512)
    seller_registration_id: str | None = Field(None, max_length=64)
    seller_tax_code: str | None = Field(None, max_length=32)
    seller_address: str | None = Field(None, max_length=512)
    seller_bank_details: str | None = Field(None, max_length=512)
    quote_market: str | None = Field(None, pattern=r"^(ru|intl|cn)?$")
    validity_days: int | None = Field(None, ge=1, le=365)
    disclaimer_mode: str | None = Field(None, pattern=r"^(offer|not_offer)$")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    quote_number_prefix: str | None = Field(None, max_length=32)


class CalculatorProfileDefaults(BaseModel):
    """Platform starting economics, never an implicit overwrite of a user profile."""

    # The money below is meaningless without the currency it was entered in: 170 rub/h
    # handed to someone billing in euro is not a starting point, it is a wrong number.
    currency: str = Field("RUB", min_length=3, max_length=4)
    electricity_cost_per_kwh: float = Field(6.0, ge=0)
    printer_power_w: float = Field(350.0, gt=0)
    modeling_rate_per_hour: float = Field(934.0, ge=0)
    postprocessing_rate_per_hour: float = Field(100.0, ge=0)
    printing_rate_per_hour: float = Field(170.0, ge=0)
    amortization_rate_per_hour: float = Field(16.0, ge=0)
    overhead_percent: float = Field(20.0, ge=0, le=100)
    markup_percent: float = Field(30.0, ge=0, le=200)
    tax_rate_percent: float = Field(0.0, ge=0, le=100)
    fixed_costs: float = Field(0.0, ge=0)
    bed_prep_cost_per_print: float = Field(0.0, ge=0)
    min_order_price: float = Field(0.0, ge=0)
    round_to_nearest: int = Field(10, ge=0)
    rounding_mode: RoundingMode = RoundingMode.UP
    printer_purchase_price: float = Field(0.0, ge=0)
    printer_useful_hours: int = Field(0, ge=0)
    maintenance_cost_per_hour: float = Field(0.0, ge=0)
    power_hotend_w: float = Field(0.0, ge=0)
    power_bed_w: float = Field(0.0, ge=0)
    power_steppers_w: float = Field(0.0, ge=0)
    power_electronics_w: float = Field(0.0, ge=0)


# ── Shared quote (public link) ───────────────────────────────────────


class SharedQuoteCreate(BaseModel):
    """POST body to create a shareable quote link."""

    title: str = Field("", max_length=255)
    html_content: str = Field(..., min_length=1, max_length=500_000)


class SharedQuoteResponse(BaseModel):
    """Response with share URL."""

    uuid: str
    share_url: str
    expires_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CalculatorProfileResponse(BaseModel):
    """GET response — full profile."""

    # Economics
    electricity_cost_per_kwh: float
    printer_power_w: float
    modeling_rate_per_hour: float
    postprocessing_rate_per_hour: float
    printing_rate_per_hour: float
    amortization_rate_per_hour: float
    overhead_percent: float
    markup_percent: float
    tax_rate_percent: float
    fixed_costs: float
    bed_prep_cost_per_print: float
    min_order_price: float
    round_to_nearest: int
    rounding_mode: str
    printer_purchase_price: float
    printer_useful_hours: int
    maintenance_cost_per_hour: float
    power_hotend_w: float
    power_bed_w: float
    power_steppers_w: float
    power_electronics_w: float

    # Quote
    seller_name: str
    seller_inn: str
    seller_phone: str
    payment_terms: str
    seller_registration_id: str
    seller_tax_code: str
    seller_address: str
    seller_bank_details: str
    quote_market: str
    validity_days: int
    disclaimer_mode: str
    currency: str
    quote_number_prefix: str

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

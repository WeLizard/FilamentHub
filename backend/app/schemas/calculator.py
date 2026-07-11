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


class CalculatorPrintJobRequest(BaseModel):
    """Execution and commercial quantity of one uploaded G-code plate."""

    job_key: str = Field(..., min_length=1, max_length=160)
    repeats: int = Field(1, ge=1, le=1000)
    output_quantity_per_run: int = Field(1, ge=1, le=100_000)
    print_time_seconds: float = Field(..., ge=0, le=31_536_000)
    quote_mode: Literal["set", "groups"] = "set"


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


class CalculatorParsedMaterial(BaseModel):
    """Parsed material row extracted from G-code metadata."""

    tool_index: int | None = Field(None, ge=0, description="Индекс инструмента T0..TN")
    type: str | None = Field(None, description="Тип материала из G-code metadata")
    name: str | None = Field(None, description="Имя / settings id материала")
    settings_id: str | None = Field(None, description="Стабильный идентификатор профиля из контейнера, если доступен")
    vendor: str | None = Field(None, description="Вендор материала")
    color: str | None = Field(None, description="Цвет материала")
    weight_g: float | None = Field(None, ge=0, description="Вес материала в граммах")
    length_mm: float | None = Field(None, ge=0, description="Длина материала в миллиметрах")
    volume_cm3: float | None = Field(None, ge=0, description="Использованный объём в кубических сантиметрах")
    density_g_cm3: float | None = Field(None, gt=0, description="Плотность из профиля слайсера")
    diameter_mm: float | None = Field(None, gt=0, description="Диаметр прутка из профиля слайсера")
    slicer_filament_id: str | None = Field(None, description="Идентификатор филамента из профиля слайсера")
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

    # Quote
    seller_name: str | None = Field(None, max_length=255)
    seller_inn: str | None = Field(None, max_length=32)
    seller_phone: str | None = Field(None, max_length=64)
    payment_terms: str | None = Field(None, max_length=512)
    validity_days: int | None = Field(None, ge=1, le=365)
    disclaimer_mode: str | None = Field(None, pattern=r"^(offer|not_offer)$")
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    quote_number_prefix: str | None = Field(None, max_length=32)


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

    # Quote
    seller_name: str
    seller_inn: str
    seller_phone: str
    payment_terms: str
    validity_days: int
    disclaimer_mode: str
    currency: str
    quote_number_prefix: str

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

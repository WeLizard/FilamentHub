"""Pydantic schemas for Calculator."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


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
        None, ge=1.0, le=2.0, description="Коэффициент потерь на поддержки (1.0-2.0, обычно 1.2-1.3)"
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
    
    # ========== Накладные расходы и наценка ==========
    overhead_percent: float | None = Field(
        None, ge=0, le=100, description="Процент накладных расходов (20-30% по умолчанию)"
    )
    markup_percent: float | None = Field(
        None, ge=0, le=200, description="Процент наценки (20-70% в зависимости от сегмента)"
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
    
    # ========== Округление ==========
    round_to_nearest: int | None = Field(
        None, ge=0, description="Округлять итоговую сумму до ближайшего N (например, 10 для округления до десятков)"
    )
    rounding_mode: RoundingMode = Field(
        default=RoundingMode.UP,
        description="Стратегия округления итоговой суммы: up, down или nearest"
    )


class CalculatorEstimateResponse(BaseModel):
    """Schema for calculator estimate response."""

    # Компоненты стоимости
    cost_material: float = Field(0, ge=0, description="Стоимость материала")
    cost_electricity: float = Field(0, ge=0, description="Стоимость электроэнергии")
    cost_modeling: float = Field(0, ge=0, description="Стоимость моделирования")
    cost_printing: float = Field(0, ge=0, description="Стоимость печати (почасовая)")
    cost_postprocessing: float = Field(0, ge=0, description="Стоимость постобработки")
    cost_amortization: float = Field(0, ge=0, description="Стоимость амортизации")
    
    # Промежуточные расчеты
    cost_direct: float = Field(0, ge=0, description="Прямые затраты (материалы + время + труд)")
    cost_overhead: float = Field(0, ge=0, description="Накладные расходы")
    cost_before_markup: float = Field(0, ge=0, description="Стоимость до наценки")
    cost_markup: float = Field(0, ge=0, description="Наценка")
    
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
    
    # Финансовые показатели (только для combined)
    cost_of_goods_sold: float | None = Field(None, ge=0, description="Себестоимость (прямые затраты + накладные + фиксированные)")
    profit_margin: float | None = Field(None, description="Маржа (прибыль) = Финальная цена - Себестоимость")
    profit_margin_percent: float | None = Field(None, description="Маржа в процентах от финальной цены")
    
    # Метод расчета
    pricing_method: PricingMethod = Field(..., description="Использованный метод расчета")
    
    # Примененные коэффициенты
    applied_urgency_coefficient: float | None = Field(None, description="Примененный коэффициент срочности")
    applied_complexity_coefficient: float | None = Field(None, description="Примененный коэффициент сложности")
    applied_volume_discount: float | None = Field(None, description="Примененный коэффициент скидки за объем")


class CalculatorParsedMaterial(BaseModel):
    """Parsed material row extracted from G-code metadata."""

    type: str | None = Field(None, description="Тип материала из G-code metadata")
    name: str | None = Field(None, description="Имя / settings id материала")
    vendor: str | None = Field(None, description="Вендор материала")
    color: str | None = Field(None, description="Цвет материала")
    weight_g: float | None = Field(None, ge=0, description="Вес материала в граммах")
    length_mm: float | None = Field(None, ge=0, description="Длина материала в миллиметрах")


class CalculatorGcodeParseResponse(BaseModel):
    """Schema for parsed G-code metadata used by Calculator Pro."""

    file_name: str = Field(..., description="Имя загруженного файла")
    file_size_bytes: int = Field(..., ge=0, description="Размер исходного файла в байтах")
    slicer_name: str | None = Field(None, description="Определённый слайсер")
    slicer_version: str | None = Field(None, description="Версия слайсера")
    print_time_seconds: int | None = Field(None, ge=0, description="Оценка времени печати в секундах")
    total_filament_weight_g: float | None = Field(None, ge=0, description="Суммарный вес филамента в граммах")
    total_filament_length_mm: float | None = Field(None, ge=0, description="Суммарная длина филамента в миллиметрах")
    layer_height_mm: float | None = Field(None, ge=0, description="Высота слоя")
    initial_layer_height_mm: float | None = Field(None, ge=0, description="Высота первого слоя")
    sparse_infill_density_percent: float | None = Field(None, ge=0, description="Плотность заполнения в процентах")
    sparse_infill_pattern: str | None = Field(None, description="Паттерн заполнения")
    wall_loops: int | None = Field(None, ge=0, description="Количество периметров / стенок")
    thumbnail_data_url: str | None = Field(None, description="Data URL превью G-code, если найден")
    materials: list[CalculatorParsedMaterial] = Field(default_factory=list, description="Материалы, извлечённые из G-code")


class CalculatorHistoryFilamentSnapshot(BaseModel):
    """Lightweight filament snapshot stored with a calculator history entry."""

    id: int | None = Field(None, description="ID филамента в каталоге, если был выбран")
    name: str = Field(..., description="Имя филамента")
    brand_name: str | None = Field(None, description="Название бренда")
    material_type: str | None = Field(None, description="Тип материала")
    color_name: str | None = Field(None, description="Цвет")


class CalculatorHistoryEntryCreate(BaseModel):
    """Persisted Calculator Pro estimate payload."""

    title: str | None = Field(None, max_length=255, description="Пользовательский или вычисленный заголовок расчёта")
    request_data: CalculatorEstimateRequest
    result_data: CalculatorEstimateResponse
    parsed_gcode: CalculatorGcodeParseResponse | None = None
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
    filament_snapshot: CalculatorHistoryFilamentSnapshot | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalculatorHistoryEntryListResponse(BaseModel):
    """Paginated list of calculator history entries."""

    items: list[CalculatorHistoryEntryResponse]
    total: int

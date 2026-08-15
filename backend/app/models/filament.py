"""Filament (материал) model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.filament_country_cell import FilamentCountryCell
    from app.models.filament_line import FilamentLine
    from app.models.filament_review import FilamentReview
    from app.models.preset import Preset
    from app.models.print_profile_filament import PrintProfileFilament


class FilamentAvailability(str, enum.Enum):
    """Доступность филамента для покупки у бренда."""

    available = "available"
    out_of_stock = "out_of_stock"
    discontinued = "discontinued"
    coming_soon = "coming_soon"


class Filament(Base):
    """
    Материал для 3D-печати.

    Примеры: ThermPlast PLA Red, ThermPlast PETG Black
    """

    __tablename__ = "filaments"
    __table_args__ = (
        UniqueConstraint("brand_id", "slug", name="uq_filaments_brand_slug"),
        CheckConstraint(
            "color_group IS NULL OR color_group IN "
            "('black','white','gray','red','orange','yellow','green','blue',"
            "'purple','pink','brown','gold','silver')",
            name="ck_filaments_color_group",
        ),
        CheckConstraint(
            "color_group_source IN ('auto','manual')",
            name="ck_filaments_color_group_source",
        ),
    )

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Brand relationship
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"), index=True)
    # Чей это вклад: организации либо, если пусто, сообщества. Не сотрудника —
    # человек уходит, вклад остаётся за компанией.
    contributed_by_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    line_id: Mapped[int | None] = mapped_column(
        ForeignKey("filament_lines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # line_id: линейка (группирует варианты-цвета). NULL = филамент вне линейки.

    # Basic info
    name: Mapped[str] = mapped_column(String(200), index=True)
    slug: Mapped[str] = mapped_column(String(200), index=True)
    # slug: stable URL identifier scoped to the brand (e.g., "abs-black")
    material_type: Mapped[str] = mapped_column(String(50), index=True)
    # material_type: PLA, ABS, PETG, TPU, Nylon, ASA, PC, etc.

    # Visual
    color_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # color_hex: #FF0000 (базовый цвет, используется в OrcaSlicer)
    color_group: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # color_group: переводимая поисковая категория; не заменяет фирменное имя.
    color_group_source: Mapped[str] = mapped_column(
        String(10), default="auto", server_default="auto", nullable=False
    )
    ral_code: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    # ral_code: необязательный четырёхзначный код RAL Classic; не заменяет HEX

    # Extended visual settings (JSON) - только для сайта
    visual_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # visual_settings: {
    #   "color_type": "single" | "two" | "three" | "gradient" | "transition" | "thermochromic",
    #   "colors": ["#FF0000", "#00FF00", ...], // до 5 цветов
    #   "finish": "matte" | "glossy",
    #   "filler": "none" | ... (legacy primary visual effect),
    #   "effects": ["metallic", "glitter", ...],
    #   "transparency": true | false
    # }

    # Physical composition and declared functional properties are separate from
    # visual rendering. A material may combine several additives and claims.
    additives: Mapped[list[dict]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    property_claims: Mapped[list[dict]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )

    # Physical properties
    diameter: Mapped[float] = mapped_column(Float, default=1.75)
    # diameter: 1.75 или 2.85 мм

    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    # density: г/см³ (для расчета веса)

    # Product-specific handling guidance. These facts belong to the exact
    # catalogue variant: additives and formulations can make two filaments of
    # the same broad material type behave differently.
    drying_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drying_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    drying_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    enclosure_requirement: Mapped[str | None] = mapped_column(String(16), nullable=True)
    chamber_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    bed_adhesives: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    post_processing_chemicals: Mapped[list[dict]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )

    # Рекомендованные производителем диапазоны печати (спека материала).
    # Это ДИАПАЗОН-рекомендация вендора, НЕ конкретные значения профиля — Preset
    # подтягивает их как дефолт при создании. Пусто у community-материалов без спеки.
    recommended_nozzle_temp_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_nozzle_temp_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_bed_temp_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_bed_temp_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Требуемая твёрдость сопла (HRC) — свойство материала: абразивные (карбон/стекло)
    # требуют закалённого сопла. Экспортируется в профиль как required_nozzle_HRC.
    required_nozzle_hrc: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Pricing (для калькулятора)
    price_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # price_per_kg: рекомендованная цена за кг (вендор заполняет)
    spool_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    # spool_weight: вес нетто филамента в граммах (обычно 1000г)
    empty_spool_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    # empty_spool_weight_g: вес пустой катушки (тара) в граммах, для взвешивания
    price_display_unit: Mapped[str] = mapped_column(
        String(10), default="per_kg", server_default="per_kg", nullable=False
    )
    # price_display_unit: в каком виде бренд назначил цену и хочет её показывать —
    # "per_kg" или "per_spool". price_per_kg всегда канонический; вторая единица
    # выводится как доп-инфо.

    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Statistics
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    # views_count: сколько раз посмотрели страницу филамента

    scans_count: Mapped[int] = mapped_column(Integer, default=0)
    # scans_count: сколько раз отсканировали QR-код

    # QR Code
    qr_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    # qr_code: короткий код для QR-кода (например: "FHUB-ABC123")
    # Автоматически генерируется для верифицированных брендов

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # active управляет видимостью; availability — статус продажи у бренда
    availability: Mapped[FilamentAvailability] = mapped_column(
        Enum(FilamentAvailability, name="filament_availability", native_enum=False),
        default=FilamentAvailability.available,
        server_default=FilamentAvailability.available.value,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="filaments")
    line: Mapped["FilamentLine | None"] = relationship("FilamentLine", back_populates="filaments")
    country_cells: Mapped[list["FilamentCountryCell"]] = relationship(
        "FilamentCountryCell", back_populates="filament", cascade="all, delete-orphan"
    )
    presets: Mapped[list["Preset"]] = relationship(
        "Preset", back_populates="filament", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["FilamentReview"]] = relationship(
        "FilamentReview", back_populates="filament", cascade="all, delete-orphan"
    )
    print_profile_links: Mapped[list["PrintProfileFilament"]] = relationship(
        "PrintProfileFilament", back_populates="filament", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Filament(id={self.id}, name='{self.name}', type='{self.material_type}')>"

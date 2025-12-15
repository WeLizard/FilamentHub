"""Material Properties model for structured material data."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class MaterialProperty(Base):
    """Структурированные свойства материала для 3D печати."""

    __tablename__ = "material_properties"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Material identification
    material_type: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    # material_type: PLA, PETG, ABS, ASA, TPU, Nylon, PC, PP, etc.
    
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # display_name: Отображаемое имя (например, "PLA (Polylactic Acid)")
    
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # description: Краткое описание материала

    # ============================================================================
    # ФИЗИЧЕСКИЕ СВОЙСТВА
    # ============================================================================
    
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    # density: Плотность (г/см³), например 1.24 для PLA
    
    melting_temp_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # melting_temp_min: Минимальная температура плавления (°C)
    
    melting_temp_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # melting_temp_max: Максимальная температура плавления (°C)
    
    glass_transition_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # glass_transition_temp: Температура стеклования Tg (°C)
    
    shrinkage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # shrinkage_percent: Усадка при охлаждении (%), например 0.3-0.5 для PLA
    
    tensile_strength_mpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    # tensile_strength_mpa: Прочность на разрыв (МПа)
    
    flexural_strength_mpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    # flexural_strength_mpa: Прочность на изгиб (МПа)
    
    elongation_at_break_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    # elongation_at_break_percent: Относительное удлинение при разрыве (%)
    
    elastic_modulus_mpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    # elastic_modulus_mpa: Модуль упругости (МПа)
    
    hardness_shore: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # hardness_shore: Твёрдость по Шору (например, "Shore D 80" или "Shore A 95")

    # ============================================================================
    # ХИМИЧЕСКИЕ СВОЙСТВА
    # ============================================================================
    
    chemical_formula: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # chemical_formula: Химическая формула (например, "(C3H4O2)n" для PLA)
    
    chemical_resistance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # chemical_resistance: {"water": "excellent", "acetone": "poor", "alcohol": "good"}
    
    solvents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # solvents: ["dichloromethane", "chloroform"] - что растворяет материал
    
    toxicity_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # toxicity_rating: low, medium, high
    
    fumes_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    # fumes_info: Информация о выделениях при печати
    
    biodegradable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # biodegradable: Биоразлагаемый ли материал
    
    food_safe: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # food_safe: Пищевая безопасность (после постобработки)

    # ============================================================================
    # ОБРАБОТКА И ПОСТОБРАБОТКА
    # ============================================================================
    
    adhesives: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # adhesives: [{"type": "cyanoacrylate", "effectiveness": "excellent", "notes": "..."}]
    
    post_processing: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # post_processing: {"sanding": "easy", "acetone_smoothing": "no", "annealing": "yes"}
    
    paint_compatibility: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # paint_compatibility: [{"type": "acrylic", "primer_needed": false}]
    
    heat_treatment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # heat_treatment: {"annealing_temp": 80, "annealing_time_hours": 2}

    # ============================================================================
    # ПРИМЕНЕНИЕ
    # ============================================================================
    
    recommended_uses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # recommended_uses: ["Prototypes", "Functional parts", "Decorative items"]
    
    not_recommended_uses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # not_recommended_uses: ["Outdoor use without coating", "High-temp applications"]
    
    typical_applications: Mapped[str | None] = mapped_column(Text, nullable=True)
    # typical_applications: Примеры использования (текст)

    # ============================================================================
    # ПЕЧАТЬ
    # ============================================================================
    
    print_temp_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # print_temp_range: "190-220°C" - типичный диапазон для экструдера
    
    bed_temp_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # bed_temp_range: "50-60°C" - типичный диапазон для стола
    
    print_speed_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # print_speed_range: "40-60 mm/s" - типичные скорости
    
    requires_enclosure: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # requires_enclosure: Нужен ли закрытый корпус принтера
    
    warping_tendency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # warping_tendency: low, medium, high
    
    stringing_tendency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # stringing_tendency: low, medium, high
    
    layer_adhesion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # layer_adhesion: poor, good, excellent
    
    support_difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # support_difficulty: easy, medium, hard

    # ============================================================================
    # МЕТАДАННЫЕ И ВЕРИФИКАЦИЯ
    # ============================================================================
    
    data_sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # data_sources: [{"type": "datasheet", "url": "...", "title": "..."}]
    
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # verified: Проверены ли данные модератором
    
    verified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # verified_by_id: Кто верифицировал данные
    
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # verified_at: Когда были верифицированы
    
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # created_by_id: Кто создал запись
    
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # updated_by_id: Кто последним обновлял

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    verified_by: Mapped["User"] = relationship("User", foreign_keys=[verified_by_id])
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped["User"] = relationship("User", foreign_keys=[updated_by_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<MaterialProperty(id={self.id}, material_type={self.material_type}, verified={self.verified})>"


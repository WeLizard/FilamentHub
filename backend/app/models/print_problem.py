"""Print Problem model for troubleshooting guide."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PrintProblemSeverity(str, Enum):
    """Серьёзность проблемы печати."""

    MINOR = "minor"  # Незначительная (косметический дефект)
    MODERATE = "moderate"  # Умеренная (влияет на качество)
    MAJOR = "major"  # Серьёзная (деталь непригодна)
    CRITICAL = "critical"  # Критическая (риск повреждения принтера)


class PrintProblem(Base):
    """Проблема 3D печати с решениями (Troubleshooting Guide)."""

    __tablename__ = "print_problems"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Problem identification
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # name: Название проблемы (например, "Warping", "Stringing", "Layer Shifting")

    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    # slug: URL-friendly версия (например, "warping", "stringing")

    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # aliases: ["отклеивание", "коробление", "деформация"] - альтернативные названия

    severity: Mapped[PrintProblemSeverity] = mapped_column(
        SQLEnum(PrintProblemSeverity, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PrintProblemSeverity.MODERATE,
        index=True,
    )
    # severity: Серьёзность проблемы

    description: Mapped[str] = mapped_column(Text, nullable=False)
    # description: Подробное описание проблемы и как её распознать

    # ============================================================================
    # ВИЗУАЛЬНАЯ ИДЕНТИФИКАЦИЯ
    # ============================================================================

    example_images: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # example_images: [{"url": "/uploads/problems/warping.jpg", "description": "..."}]

    visual_symptoms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # visual_symptoms: ["Углы детали подняты", "Деталь отклеилась от стола"]

    # ============================================================================
    # ПРИЧИНЫ
    # ============================================================================

    causes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # causes: [
    #   {
    #     "title": "Недостаточная адгезия к столу",
    #     "description": "...",
    #     "likelihood": "high"
    #   }
    # ]

    common_materials: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # common_materials: ["ABS", "ASA", "Nylon"] - материалы где чаще встречается

    # ============================================================================
    # РЕШЕНИЯ
    # ============================================================================

    solutions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # solutions: [
    #   {
    #     "title": "Увеличить температуру стола",
    #     "description": "...",
    #     "difficulty": "easy",
    #     "effectiveness": "high",
    #     "steps": ["Шаг 1", "Шаг 2"]
    #   }
    # ]

    quick_fixes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # quick_fixes: ["Протереть стол изопропиловым спиртом", "Использовать брим"]

    prevention_tips: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # prevention_tips: ["Калибруйте стол регулярно", "Используйте клей-карандаш"]

    # ============================================================================
    # НАСТРОЙКИ СЛАЙСЕРА
    # ============================================================================

    slicer_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # slicer_settings: {
    #   "bed_temp": {"adjust": "+5-10°C", "reason": "..."},
    #   "first_layer_speed": {"adjust": "-50%", "reason": "..."}
    # }

    # ============================================================================
    # СВЯЗИ И МЕТАДАННЫЕ
    # ============================================================================

    related_problems: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # related_problems: [{"id": 2, "slug": "layer-adhesion", "relation": "often_occurs_with"}]

    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # tags: "адгезия,стол,первый слой,ABS" - для поиска

    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # views: Количество просмотров

    helpful_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # helpful_votes: Сколько пользователей отметили "Помогло"

    # ============================================================================
    # МОДЕРАЦИЯ
    # ============================================================================

    published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # published: Опубликовано ли

    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # verified: Проверено экспертом

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # created_by_id: Кто создал

    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # updated_by_id: Кто последним обновлял

    verified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # verified_by_id: Кто верифицировал

    # Display order
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # order: Порядок отображения (по популярности/важности)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])
    updated_by: Mapped["User"] = relationship("User", foreign_keys=[updated_by_id])
    verified_by: Mapped["User"] = relationship("User", foreign_keys=[verified_by_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<PrintProblem(id={self.id}, name={self.name}, severity={self.severity.value}, verified={self.verified})>"



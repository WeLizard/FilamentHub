"""FilamentReview schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class FilamentReviewBase(BaseModel):
    """Базовая схема отзыва."""

    success: bool = Field(..., description="Успешна ли печать")
    rating: float = Field(..., ge=1.0, le=5.0, description="Рейтинг от 1.0 до 5.0")
    comment: str | None = Field(None, max_length=2000, description="Текст отзыва")
    printer_model: str | None = Field(None, max_length=200, description="Модель принтера")

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: float) -> float:
        """Валидация рейтинга: округление до 0.5."""
        # Округляем до ближайшего 0.5 (1.0, 1.5, 2.0, ..., 5.0)
        return round(v * 2) / 2


class FilamentReviewCreate(FilamentReviewBase):
    """Схема создания отзыва."""

    filament_id: int = Field(..., description="ID материала")
    preset_id: int | None = Field(None, description="ID пресета (опционально, если не указан - используется официальный)")


class FilamentReviewUpdate(BaseModel):
    """Схема обновления отзыва."""

    success: bool | None = None
    rating: float | None = Field(None, ge=1.0, le=5.0)
    comment: str | None = Field(None, max_length=2000)
    printer_model: str | None = Field(None, max_length=200)
    active: bool | None = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: float | None) -> float | None:
        """Валидация рейтинга: округление до 0.5."""
        if v is None:
            return None
        return round(v * 2) / 2


class FilamentReviewResponse(FilamentReviewBase):
    """Схема ответа с отзывом."""

    id: int
    filament_id: int
    user_id: int
    preset_id: int | None = Field(None, description="ID пресета, к которому относится отзыв")
    preset_name: str | None = Field(None, description="Название пресета")
    username: str | None = Field(None, description="Имя пользователя")
    user_badges: list[str] | None = Field(None, description="Бейджи пользователя")
    active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class FilamentReviewListResponse(BaseModel):
    """Схема списка отзывов."""

    items: list[FilamentReviewResponse]
    total: int
    page: int
    size: int
    pages: int


class FilamentRatingStats(BaseModel):
    """Статистика рейтингов материала."""

    avg_rating: float | None = Field(None, description="Средний рейтинг")
    total_reviews: int = Field(0, description="Всего отзывов")
    success_rate: float | None = Field(None, ge=0.0, le=100.0, description="Процент успешных печатей")
    rating_distribution: dict[int, int] = Field(
        default_factory=dict, description="Распределение рейтингов: {1: count, 2: count, ...}"
    )





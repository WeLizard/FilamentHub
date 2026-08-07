"""Схемы страновых ячеек бренда и филамента."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.filament_country_cell import CountryAvailability


def _upper_country(value: str) -> str:
    """Код страны приводится при записи: иначе ru и RU дадут две ячейки."""
    return value.upper()


class BrandCountryCellBase(BaseModel):
    """Присутствие бренда в стране. Товарных данных и цен здесь не бывает."""

    country: str = Field(..., pattern=r"^[A-Za-z]{2}$")
    website: str | None = Field(None, max_length=255)
    shop_links: list[dict[str, str]] | None = None
    published: bool = False

    _normalize_country = field_validator("country")(_upper_country)


class BrandCountryCellCreate(BrandCountryCellBase):
    """Схема создания ячейки бренда."""


class BrandCountryCellUpdate(BaseModel):
    """Схема обновления. Страну у существующей ячейки не меняют."""

    website: str | None = Field(None, max_length=255)
    shop_links: list[dict[str, str]] | None = None
    published: bool | None = None


class BrandCountryCellResponse(BrandCountryCellBase):
    """Ячейка бренда в ответе."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    created_at: datetime
    updated_at: datetime


class FilamentCountryCellBase(BaseModel):
    """Рыночные сведения о филаменте в стране."""

    country: str = Field(..., pattern=r"^[A-Za-z]{2}$")
    availability: CountryAvailability = CountryAvailability.unknown
    price: float | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=8)
    price_display_unit: Literal["per_kg", "per_spool"] | None = None
    product_url: str | None = Field(None, max_length=500)
    purchase_links: list[dict[str, str]] | None = None
    market_note: str | None = None
    # Заполняется, только если тот же товар официально продаётся на этом рынке
    # под другим коммерческим названием. Перевод — это локализация, не ячейка.
    market_display_name: str | None = Field(None, max_length=200)
    published: bool = False

    _normalize_country = field_validator("country")(_upper_country)

    @model_validator(mode="after")
    def price_and_currency_come_together(self) -> "FilamentCountryCellBase":
        """Цена без валюты унаследует чужую и окажется не в тех деньгах."""
        if (self.price is None) != (self.currency is None):
            raise ValueError("price and currency must be set together")
        return self


class FilamentCountryCellCreate(FilamentCountryCellBase):
    """Схема создания ячейки филамента."""


class FilamentCountryCellUpdate(BaseModel):
    """Схема обновления. Страну у существующей ячейки не меняют."""

    availability: CountryAvailability | None = None
    price: float | None = Field(None, ge=0)
    currency: str | None = Field(None, max_length=8)
    price_display_unit: Literal["per_kg", "per_spool"] | None = None
    product_url: str | None = Field(None, max_length=500)
    purchase_links: list[dict[str, str]] | None = None
    market_note: str | None = None
    market_display_name: str | None = Field(None, max_length=200)
    published: bool | None = None


class FilamentCountryCellResponse(FilamentCountryCellBase):
    """Ячейка филамента в ответе."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filament_id: int
    price_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

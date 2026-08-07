"""Рыночные сведения о филаменте в отдельной стране."""

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
    from app.models.filament import Filament
    from app.models.user import User


class CountryAvailability(str, enum.Enum):
    """Продаётся ли товар в стране.

    `unknown` существует наравне с остальными: ячейку могли завести ради цены, не
    утверждая ничего о наличии. Отсутствие ячейки означает то же самое, и ни то
    ни другое не выводится как «не продаётся».
    """

    available = "available"
    unavailable = "unavailable"
    unknown = "unknown"


class FilamentCountryCell(Base):
    """Один и тот же товар, местные условия продажи.

    Свойства материала — диаметр, плотность, температуры, усадка — сюда не
    попадают никогда: это один и тот же пластик. Здесь только то, что зависит от
    рынка.
    """

    __tablename__ = "filament_country_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    availability: Mapped[CountryAvailability] = mapped_column(
        Enum(CountryAvailability, name="country_availability"),
        default=CountryAvailability.unknown,
        nullable=False,
    )

    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Рынок, торгующий катушками, не должен видеть цену за килограмм.
    price_display_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)

    product_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    purchase_links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Региональная коммерческая заметка: условия поставки, фасовка на этом рынке.
    # Переведённое описание товара сюда не попадает — это локализация, и страна
    # никогда не используется вместо языка.
    market_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Только настоящее региональное коммерческое имя того же товара, не перевод.
    market_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Цена — коммерческая величина, и правят её несколько организаций: нужно
    # видеть, кто и когда её поменял.
    price_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    price_updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    filament: Mapped["Filament"] = relationship("Filament", back_populates="country_cells")
    price_updated_by: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("filament_id", "country", name="uq_filament_country_cell"),
        # Цена без валюты унаследовала бы валюту бренда, и сербская цена
        # оказалась бы в рублях.
        CheckConstraint(
            "(price IS NULL) = (currency IS NULL)", name="ck_filament_cell_price_currency_pair"
        ),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<FilamentCountryCell filament={self.filament_id} country={self.country}>"

"""Присутствие бренда в отдельной стране."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand


class BrandCountryCell(Base):
    """Региональная витрина бренда: одна страна — одна ячейка.

    Зона ячейки — присутствие бренда: где его региональный сайт и официальные
    магазины. Данных конкретного товара здесь нет, цен в том числе: у бренда цен
    не бывает. Бренд остаётся одной канонической записью во всех странах и в
    ячейке не переименовывается: другое имя — это локализация. Права
    представителей тоже не здесь: витрина и право её менять разные сущности.

    Пустое поле значит «как у всех»: глобальный бренд с одним сайтом не заполняет
    ничего и везде выглядит одинаково.
    """

    __tablename__ = "brand_country_cells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Ровно две буквы в верхнем регистре: иначе ru и RU дадут две ячейки.
    country: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shop_links: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Как бренд говорит о себе на этом рынке и где его там читают.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_media_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Валюта цен на этом рынке. Не копия валюты страны: бренд бывает назначает
    # цены в чужой валюте. У самой цены валюта своя и она главнее.
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Наполовину заполненная ячейка не уезжает в витрину при первом сохранении.
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    brand: Mapped["Brand"] = relationship("Brand", back_populates="country_cells")

    __table_args__ = (
        UniqueConstraint("brand_id", "country", name="uq_brand_country_cell"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<BrandCountryCell brand={self.brand_id} country={self.country}>"

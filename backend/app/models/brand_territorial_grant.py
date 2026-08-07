"""Право организации вести бренд в своей стране."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.organization import Organization


class GrantSource(str, enum.Enum):
    """Откуда взялось право. Различается только для аудита."""

    invitation = "invitation"
    application = "application"


class GrantStatus(str, enum.Enum):
    """Состояние права."""

    pending = "pending"
    active = "active"
    revoked = "revoked"


class BrandTerritorialGrant(Base):
    """Одна организация ведёт один бренд в одной стране.

    Ради этого вся затея и была: Creality существует один, а Creality Russia и
    Creality Germany входят в него, каждый со своей областью. Приглашение
    администратора и самостоятельно поданная заявка после одобрения дают одну и
    ту же сущность — источник различается только для аудита.

    `country = NULL` означает глобальную область. Сама она не появляется никогда
    и выдаётся только решением администратора.

    `Brand.organization_id` описывает один workspace за брендом и поэтому не
    может быть источником прав для независимых представителей нескольких стран.
    `OrganizationBrandAccess` решает другую задачу: доступ сотрудника внутри
    одной организации.
    """

    __tablename__ = "brand_territorial_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL — глобальная область; две буквы в верхнем регистре — страна.
    country: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)

    status: Mapped[GrantStatus] = mapped_column(
        Enum(GrantStatus, name="grant_status"), default=GrantStatus.pending, nullable=False
    )
    source: Mapped[GrantSource] = mapped_column(
        Enum(GrantSource, name="grant_source"), nullable=False
    )

    # Начальный набор, а не жёсткая роль «дистрибьютор»: конкретному праву можно
    # выдать больше, не заводя новую разновидность аккаунта.
    manage_brand_country: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manage_filament_country: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    create_filaments: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    edit_own_created_filaments: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Общий слой по умолчанию закрыт: региональный представитель не переписывает
    # ни бренд, ни свойства чужих товаров.
    edit_brand_common: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edit_all_filaments_common: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    brand: Mapped["Brand"] = relationship("Brand", back_populates="territorial_grants")
    organization: Mapped["Organization"] = relationship("Organization")

    __table_args__ = (
        # Одной организации незачем два права на один и тот же бренд и страну.
        # Несколько независимых организаций на одну страну не запрещены: это
        # решение администратора, а не устройство таблицы.
        Index(
            "uq_grant_org_brand_country",
            "brand_id",
            "organization_id",
            "country",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        """String representation."""
        scope = self.country or "global"
        return f"<BrandTerritorialGrant brand={self.brand_id} org={self.organization_id} {scope}>"

"""UserSpool model — physical filament spool owned by a user."""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression, func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.spool_compat_resource import SpoolCompatResource
    from app.models.user import User


class UserSpoolState(str, enum.Enum):
    """Physical state of a spool."""

    active = "active"
    shelf = "shelf"
    archived = "archived"
    empty = "empty"


class UserSpool(Base):
    """A physical filament spool in a user's inventory."""

    __tablename__ = "user_spools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filament_id: Mapped[int | None] = mapped_column(
        ForeignKey("filaments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    compat_filament_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("spool_compat_resources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    initial_weight_g: Mapped[float] = mapped_column(Float, nullable=False)
    used_weight_g: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    state: Mapped[UserSpoolState] = mapped_column(
        Enum(UserSpoolState, name="user_spool_state", native_enum=False),
        default=UserSpoolState.shelf,
        nullable=False,
        index=True,
    )
    # True from the moment a low-stock alert fired until the spool is refilled or
    # replaced; it keeps one alert per crossing, however many readings follow.
    low_stock_fired: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=expression.false()
    )
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    empty_spool_weight_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    # price: фактическая цена покупки этой катушки (пользователь заполняет)
    source: Mapped[str] = mapped_column(
        String(30), default="manual", nullable=False
    )
    lot_nr: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purchased_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    first_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="spools")
    filament: Mapped["Filament | None"] = relationship("Filament")
    compat_filament_ref: Mapped["SpoolCompatResource | None"] = relationship(
        "SpoolCompatResource", lazy="selectin"
    )

    @property
    def compat_import_id(self) -> int | None:
        ref = self.compat_filament_ref
        return ref.id if ref is not None and ref.source_kind == "import" else None

    @property
    def remaining_weight_g(self) -> float:
        return max(0.0, self.initial_weight_g - self.used_weight_g)

    @property
    def remaining_pct(self) -> float:
        if self.initial_weight_g <= 0:
            return 0.0
        return round(self.remaining_weight_g / self.initial_weight_g * 100, 1)

    def __repr__(self) -> str:
        return (
            f"<UserSpool(id={self.id}, user_id={self.user_id}, "
            f"filament_id={self.filament_id}, state={self.state.value}, "
            f"remaining={self.remaining_weight_g}g)>"
        )

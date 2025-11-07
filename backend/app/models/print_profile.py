"""PrintProfile model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PrintProfile(Base):
    """Настройки печати (Print Settings) для OrcaSlicer."""

    __tablename__ = "print_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_official: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    compatible_printers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    compatible_filaments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    orcaslicer_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship("User", back_populates="print_profiles")

    def __repr__(self) -> str:
        status = "official" if self.is_official else "user"
        return f"<PrintProfile(id={self.id}, name='{self.name}', status={status})>"



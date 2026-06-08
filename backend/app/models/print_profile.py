"""PrintProfile model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.print_profile_filament import PrintProfileFilament
    from app.models.print_profile_printer import PrintProfilePrinter
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
    source: Mapped[str] = mapped_column(String(50), default="user", server_default="user", index=True)
    vendor: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    setting_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    quality_tier: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    default_nozzle: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    layer_height_mm: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    compatible_printers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    compatible_filaments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    orcaslicer_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_from_bundle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bundles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship("User", back_populates="print_profiles")
    printer_links: Mapped[list["PrintProfilePrinter"]] = relationship(
        "PrintProfilePrinter",
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    filament_links: Mapped[list["PrintProfileFilament"]] = relationship(
        "PrintProfileFilament",
        back_populates="profile",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        status = "official" if self.is_official else "user"
        return f"<PrintProfile(id={self.id}, name='{self.name}', status={status})>"



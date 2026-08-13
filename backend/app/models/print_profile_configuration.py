"""Exact links between process profiles and slicer machine configurations."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.print_profile import PrintProfile
    from app.models.printer_profile import PrinterProfile


class PrintProfileConfigurationLink(Base):
    """One process recipe explicitly assigned to one machine configuration."""

    __tablename__ = "print_profile_configuration_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    print_profile_id: Mapped[int] = mapped_column(
        ForeignKey("print_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    printer_profile_id: Mapped[int] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="explicit",
        server_default="explicit",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "print_profile_id",
            "printer_profile_id",
            name="uq_print_profile_config_link",
        ),
        Index("ix_pp_config_print_profile", "print_profile_id"),
        Index("ix_pp_config_printer_profile", "printer_profile_id"),
    )

    print_profile: Mapped["PrintProfile"] = relationship(
        "PrintProfile", back_populates="configuration_links"
    )
    printer_profile: Mapped["PrinterProfile"] = relationship(
        "PrinterProfile", back_populates="print_profile_configuration_links"
    )

"""Links user-owned physical printers to Orca machine configurations."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.printer_profile import PrinterProfile
    from app.models.user_printer_device import UserPrinterDevice


class UserPrinterProfileLink(Base):
    """One Orca machine configuration assigned to one physical printer."""

    __tablename__ = "user_printer_profile_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    physical_printer_id: Mapped[int] = mapped_column(
        ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    printer_profile_id: Mapped[int] = mapped_column(
        ForeignKey("printer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "physical_printer_id",
            "printer_profile_id",
            name="uq_user_printer_profile_link",
        ),
    )

    physical_printer: Mapped["UserPrinterDevice"] = relationship(
        "UserPrinterDevice", back_populates="profile_links"
    )
    printer_profile: Mapped["PrinterProfile"] = relationship(
        "PrinterProfile", back_populates="physical_printer_links"
    )

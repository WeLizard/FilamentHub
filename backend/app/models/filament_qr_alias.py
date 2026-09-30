"""Permanent product QR aliases for merged catalog filaments."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament


class FilamentQrAlias(Base):
    """A printed product code that still resolves after its filament is merged."""

    __tablename__ = "filament_qr_aliases"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    filament: Mapped["Filament"] = relationship()

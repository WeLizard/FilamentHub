"""SyncDevice model — отслеживание устройств для синхронизации."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class SyncDevice(Base):
    """Устройство пользователя для отслеживания состояния синхронизации."""

    __tablename__ = "sync_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    orcaslicer_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sync_devices")

    # Unique constraint: one device per user
    __table_args__ = (
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<SyncDevice(id={self.id}, user_id={self.user_id}, fingerprint={self.device_fingerprint})>"

"""Bounded latest-state projection for device preset sync observations."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.sync_history import SyncOperation, SyncPresetType, SyncStatus


class SyncPresetState(Base):
    """Latest known state of one preset on one sync device.

    ``SyncHistory`` remains the append-only audit trail. This projection is the
    bounded read model used by status and deletion detection, so those paths do
    not scan the complete history on every request.
    """

    __tablename__ = "sync_preset_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("sync_devices.id", ondelete="CASCADE"), nullable=False
    )
    preset_type: Mapped[SyncPresetType] = mapped_column(
        SQLEnum(SyncPresetType, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    preset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[SyncOperation] = mapped_column(
        SQLEnum(SyncOperation, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_sync_preset_states_device_type_preset",
            "device_id",
            "preset_type",
            "preset_id",
            unique=True,
        ),
        Index(
            "ix_sync_preset_states_user_device_type_preset",
            "user_id",
            "device_id",
            "preset_type",
            "preset_id",
        ),
    )

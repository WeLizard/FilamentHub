"""SyncHistory model — история синхронизаций."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SyncPresetType(str, Enum):
    """Тип пресета для синхронизации."""
    FILAMENT = "filament"
    PRINTER = "printer"
    PRINT = "print"


class SyncOperation(str, Enum):
    """Тип операции синхронизации."""
    DOWNLOAD = "download"
    UPLOAD = "upload"
    DELETE = "delete"


class SyncStatus(str, Enum):
    """Статус операции синхронизации."""
    SUCCESS = "success"
    ERROR = "error"
    CONFLICT = "conflict"


class SyncHistory(Base):
    """Запись истории синхронизации."""

    __tablename__ = "sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("sync_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False)
    preset_type: Mapped[SyncPresetType] = mapped_column(
        SQLEnum(SyncPresetType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    operation: Mapped[SyncOperation] = mapped_column(
        SQLEnum(SyncOperation, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    preset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SyncStatus] = mapped_column(
        SQLEnum(SyncStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<SyncHistory(id={self.id}, user={self.user_id}, "
            f"op={self.operation.value}, status={self.status.value})>"
        )

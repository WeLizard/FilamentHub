"""Notification model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType(str, Enum):
    """Типы уведомлений."""

    PRESET_UPDATED = "preset_updated"  # Пресет изменен
    PRESET_DELETED = "preset_deleted"  # Пресет удален
    PRESET_LOCALLY_DELETED = "preset_locally_deleted"  # Пресет удалён локально в OrcaSlicer
    BRAND_VERIFIED = "brand_verified"  # Бренд верифицирован
    BRAND_REQUEST_APPROVED = "brand_request_approved"  # Заявка на бренд одобрена
    BRAND_REQUEST_REJECTED = "brand_request_rejected"  # Заявка на бренд отклонена
    ADMIN_MESSAGE = "admin_message"  # Сообщение от админа (массовая рассылка)


class Notification(Base):
    """Модель уведомления для пользователя."""

    __tablename__ = "notifications"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign keys
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    # user_id: кому адресовано уведомление

    # Type and content
    type: Mapped[NotificationType] = mapped_column(
        SQLEnum(NotificationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Link to related entity (optional)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # link: ссылка на связанную сущность (например, /filaments/123 или /presets/456)
    
    # Metadata (используем extra_data вместо metadata, так как metadata зарезервировано в SQLAlchemy)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # extra_data: JSON с дополнительными данными (например, preset_id, brand_id, filament_id)

    # Status
    read: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type.value}, read={self.read})>"


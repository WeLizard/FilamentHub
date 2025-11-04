"""Printer request model for adding new printers."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.printer import Printer
    from app.models.user import User


class PrinterRequestStatus(str, Enum):
    """Статус заявки на добавление принтера."""

    PENDING = "pending"  # Ожидает рассмотрения
    APPROVED = "approved"  # Одобрена
    REJECTED = "rejected"  # Отклонена


class PrinterRequest(Base):
    """
    Заявка на добавление нового принтера в базу.
    
    Пользователи могут предложить добавить редкий принтер,
    который отсутствует в базе.
    """

    __tablename__ = "printer_requests"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # User who submitted the request
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    # New printer data
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Optional printer specs
    build_volume_x: Mapped[float | None] = mapped_column(nullable=True)
    build_volume_y: Mapped[float | None] = mapped_column(nullable=True)
    build_volume_z: Mapped[float | None] = mapped_column(nullable=True)
    nozzle_diameter: Mapped[float | None] = mapped_column(nullable=True)
    max_extruder_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_bed_temp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Request message (optional)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # message: дополнительная информация о принтере или почему он нужен

    # Proof files (для загрузки скриншотов, изображений принтера)
    proof_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # proof_files: JSON массив путей к загруженным файлам (например, ["printer_requests/123/screen1.jpg"])

    # Status
    status: Mapped[PrinterRequestStatus] = mapped_column(
        String(20), default=PrinterRequestStatus.PENDING, index=True, nullable=False
    )

    # Admin who processed the request (optional)
    processed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Rejection reason (if rejected)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    processed_by: Mapped["User | None"] = relationship("User", foreign_keys=[processed_by_id])

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<PrinterRequest(id={self.id}, name='{self.name}', "
            f"status='{self.status}', user_id={self.user_id})>"
        )


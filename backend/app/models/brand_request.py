"""Brand request model for join/create requests."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.user import User


class BrandRequestType(str, Enum):
    """Тип заявки на бренд."""

    JOIN = "join"  # Заявка на вступление в существующий бренд
    CREATE = "create"  # Заявка на создание нового бренда


class BrandRequestStatus(str, Enum):
    """Статус заявки на бренд."""

    PENDING = "pending"  # Ожидает рассмотрения
    APPROVED = "approved"  # Одобрена
    REJECTED = "rejected"  # Отклонена


class BrandRequest(Base):
    """
    Заявка на вступление в бренд или создание нового бренда.

    - JOIN: пользователь просит вступить в существующий верифицированный бренд
    - CREATE: пользователь просит создать новый бренд
    """

    __tablename__ = "brand_requests"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # User who submitted the request
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    # Type of request
    request_type: Mapped[BrandRequestType] = mapped_column(String(20), index=True, nullable=False)

    # For JOIN requests: target brand
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id"), index=True, nullable=True
    )

    # For CREATE requests: new brand data
    new_brand_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_brand_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_brand_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_brand_website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Request message (optional)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Подтверждающие документы для заявки (структурированные поля для подтверждающих документов)
    # Базовое текстовое описание
    proof_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # proof_text: описание подтверждающих документов (общее описание, дополнительные детали)

    # Структурированные поля для подтверждающих документов
    company_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # company_email: email от компании (например: info@company.ru, manager@company.ru)

    company_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # company_website: сайт компании/бренда (для проверки email на сайте)

    social_media_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    # social_media_urls: JSON массив ссылок на соцсети бренда (Instagram, VK, Facebook и т.д.)

    # Proof files (для загрузки PDF, изображений и других документов)
    proof_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # proof_files: JSON массив путей к загруженным файлам (например, ["brand_requests/123/file1.pdf"])

    # Status
    status: Mapped[BrandRequestStatus] = mapped_column(
        String(20), default=BrandRequestStatus.PENDING, index=True, nullable=False
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
    brand: Mapped["Brand | None"] = relationship("Brand", foreign_keys=[brand_id])
    processed_by: Mapped["User | None"] = relationship("User", foreign_keys=[processed_by_id])

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<BrandRequest(id={self.id}, type='{self.request_type}', "
            f"status='{self.status}', user_id={self.user_id})>"
        )


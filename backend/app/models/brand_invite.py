"""Brand invite model — admin pre-verified invitations to manufacturers."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class BrandInvite(Base):
    """Приглашение бренда с пред-верификацией.

    Админ выпускает single-use токен на корпоративную почту бренда. Переход по
    ссылке и принятие авторизованным пользователем = верификация: бренд
    создаётся с verified=True, минуя загрузку документов.
    """

    __tablename__ = "brand_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pre_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    invited_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    created_at: Mapped[datetime] = mapped_column(default=func.now(), server_default=func.now())

    invited_by: Mapped["User | None"] = relationship("User", foreign_keys=[invited_by_id])
    accepted_by: Mapped["User | None"] = relationship("User", foreign_keys=[accepted_by_id])

    def __repr__(self) -> str:
        """String representation."""
        return f"<BrandInvite(id={self.id}, email='{self.email}', accepted={self.accepted_at is not None})>"

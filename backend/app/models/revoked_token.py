"""RevokedToken model — серверный blacklist для инвалидации JWT токенов."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class RevokedToken(Base):
    """
    Отозванные JWT токены (blacklist).

    При logout access и refresh токены добавляются сюда.
    При каждом запросе проверяется: если jti найден — токен отклоняется (401).
    Записи с истёкшим expires_at можно периодически удалять.
    """

    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_revoked_tokens_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<RevokedToken(jti='{self.jti}', expires_at={self.expires_at})>"

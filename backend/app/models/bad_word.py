"""Bad word model for user text moderation."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class BadWord(Base):
    """Запрещённое слово для модерации пользовательского текста."""

    __tablename__ = "bad_words"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="ru", index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<BadWord(id={self.id}, word={self.word!r}, language={self.language})>"

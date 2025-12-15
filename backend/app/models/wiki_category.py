"""Wiki Category model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.wiki_article import WikiArticle


class WikiCategory(Base):
    """Категория статей Wiki."""

    __tablename__ = "wiki_categories"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Content
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    # slug: URL-friendly версия имени (например, "materials", "problems")
    
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # icon: название Lucide иконки (например, "Package", "Wrench", "Settings")
    
    # Display order
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # order: порядок отображения на главной странице (меньше = выше)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    articles: Mapped[list["WikiArticle"]] = relationship(
        "WikiArticle", back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<WikiCategory(id={self.id}, name={self.name}, slug={self.slug})>"



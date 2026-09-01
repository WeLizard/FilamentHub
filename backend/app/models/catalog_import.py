"""Audit record for a confirmed administrative catalog import."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class CatalogImportBatch(Base):
    """One atomic master-import that reached the database after confirmation."""

    __tablename__ = "catalog_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    applied_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    plan_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    applied_by: Mapped["User | None"] = relationship("User")

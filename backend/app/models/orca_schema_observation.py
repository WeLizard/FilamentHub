"""Aggregated observations of OrcaSlicer preset fields outside our baseline."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class OrcaSchemaObservation(Base):
    """One current aggregate row per preset scope and field name."""

    __tablename__ = "orca_schema_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    field_name: Mapped[str] = mapped_column(String(200), nullable=False)
    value_shape: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="new", server_default="new", nullable=False
    )
    occurrences: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    registry_version: Mapped[str] = mapped_column(String(100), nullable=False)
    first_source: Mapped[str] = mapped_column(String(50), nullable=False)
    last_source: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("scope", "field_name", name="uq_orca_schema_obs_field"),
        Index("ix_orca_schema_obs_status_seen", "status", "last_seen_at"),
        Index("ix_orca_schema_obs_scope", "scope"),
    )

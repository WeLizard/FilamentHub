"""Short-lived private G-code uploads used by Calculator Pro."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CalculatorGcodeArtifact(Base):
    """Owner-bound metadata for one immutable, temporary G-code blob."""

    __tablename__ = "calculator_gcode_artifacts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('uploading', 'ready', 'failed', 'cancelled')",
            name="ck_calc_gcode_artifact_state",
        ),
        CheckConstraint(
            "expected_size_bytes > 0",
            name="ck_calc_gcode_artifact_size",
        ),
        Index("ix_calc_gcode_owner_expiry", "owner_user_id", "expires_at"),
        Index("ix_calc_gcode_state_expiry", "state", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="uploading")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

"""Current desired preset/spool assignment for a provider-neutral material slot."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.material_system import MaterialSlot
    from app.models.preset import Preset
    from app.models.user_spool import UserSpool


class MaterialSlotAssignment(Base):
    """User-desired current assignment, separate from provider observation."""

    __tablename__ = "material_slot_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_slot_id: Mapped[int] = mapped_column(
        ForeignKey("material_slots.id", ondelete="CASCADE"),
        nullable=False,
    )
    preset_id: Mapped[int | None] = mapped_column(
        ForeignKey("presets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_spools.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "material_slot_id", name="uq_material_slot_assignment_slot"
        ),
        Index(
            "uq_material_slot_assignment_spool",
            "spool_id",
            unique=True,
            postgresql_where=text("spool_id IS NOT NULL"),
            sqlite_where=text("spool_id IS NOT NULL"),
        ),
    )

    material_slot: Mapped["MaterialSlot"] = relationship(
        "MaterialSlot", back_populates="assignment"
    )
    preset: Mapped["Preset | None"] = relationship("Preset")
    spool: Mapped["UserSpool | None"] = relationship("UserSpool")

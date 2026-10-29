"""A user's own named folders over their spools (a spool may sit in several)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SpoolCollection(Base):
    """Personal organisation only: it never changes stock, price or alert rules."""

    __tablename__ = "spool_collections"
    __table_args__ = (UniqueConstraint("user_id", "name_key", name="uq_spool_collection_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Case-folded name, so "Blue" and "blue" cannot both exist for one person.
    name_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SpoolCollectionMember(Base):
    __tablename__ = "spool_collection_members"

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("spool_collections.id", ondelete="CASCADE"), primary_key=True
    )
    spool_id: Mapped[int] = mapped_column(
        ForeignKey("user_spools.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

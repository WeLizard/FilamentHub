"""Durable transport identities and private Spoolman-compatible metadata."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SpoolCompatWireCounter(Base):
    __tablename__ = "spool_compat_wire_counters"

    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    next_wire_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SpoolCompatResource(Base):
    """A stable wire reference, distinct from both catalog PK and physical spool PK."""

    __tablename__ = "spool_compat_resources"
    __table_args__ = (
        UniqueConstraint("kind", "wire_id", name="uq_spool_compat_kind_wire"),
        Index("uq_spool_compat_catalog_brand", "brand_id", unique=True,
              postgresql_where=text("source_kind = 'catalog'"),
              sqlite_where=text("source_kind = 'catalog'")),
        Index("uq_spool_compat_catalog_filament", "filament_id", unique=True,
              postgresql_where=text("source_kind = 'catalog'"),
              sqlite_where=text("source_kind = 'catalog'")),
        CheckConstraint("kind IN ('vendor','filament')", name="ck_spool_compat_kind"),
        CheckConstraint("source_kind IN ('catalog','import','alias')", name="ck_spool_compat_source"),
        CheckConstraint(
            "(kind = 'vendor' AND filament_id IS NULL) OR "
            "(kind = 'filament' AND brand_id IS NULL)",
            name="ck_spool_compat_target_kind",
        ),
        CheckConstraint(
            "(source_kind = 'import' AND user_id IS NOT NULL AND "
            "original_payload IS NOT NULL AND latest_payload IS NOT NULL) OR "
            "(source_kind IN ('catalog','alias') AND user_id IS NULL AND "
            "original_payload IS NULL AND latest_payload IS NULL)",
            name="ck_spool_compat_owner_payload",
        ),
        CheckConstraint("revision >= 1", name="ck_spool_compat_revision"),
        Index("ix_spool_compat_owner_kind", "user_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    wire_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), nullable=True)
    filament_id: Mapped[int | None] = mapped_column(ForeignKey("filaments.id", ondelete="SET NULL"), nullable=True)
    original_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latest_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    source_namespace: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SpoolCompatResourceExtra(Base):
    __tablename__ = "spool_compat_resource_extras"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", name="uq_spool_compat_extra_owner_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("spool_compat_resources.id", ondelete="CASCADE"), nullable=False, index=True)
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SpoolCompatFieldDefinition(Base):
    __tablename__ = "spool_compat_field_defs"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "key", name="uq_spool_compat_field_owner_key"),
        CheckConstraint("kind IN ('spool','vendor','filament')", name="ck_spool_compat_field_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

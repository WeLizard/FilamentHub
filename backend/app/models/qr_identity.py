"""Durable QR instance identities and sparse manufacturer batch state."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.filament import Filament
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.user_spool import UserSpool


class QrUserBindingState:
    """Lifecycle values for a user-issued spool binding."""

    ACTIVE = "active"
    PENDING_RETIREMENT = "pending_retirement"
    ALL = (ACTIVE, PENDING_RETIREMENT)


class QrManufacturerBatchMode:
    """Whether a batch repeats the SKU code or derives one serial per label."""

    SKU = "sku"
    SERIALIZED = "serialized"
    ALL = (SKU, SERIALIZED)


class QrManufacturerBatchStatus:
    """Manufacturer batch lifecycle."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    ALL = (ACTIVE, CANCELLED)


class QrManufacturerInstanceStatus:
    """Sparse state recorded only after an issued serial has a real event."""

    CLAIMED = "claimed"
    REVOKED = "revoked"
    SCRAPPED = "scrapped"
    ALL = (CLAIMED, REVOKED, SCRAPPED)


class QrUserSpoolBinding(Base):
    """One immediately-bound, reprintable QR identity for an owned spool."""

    __tablename__ = "qr_user_spool_bindings"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'pending_retirement')",
            name="ck_qr_user_binding_state",
        ),
        UniqueConstraint("user_spool_id", name="uq_qr_user_binding_spool"),
        UniqueConstraint("token_digest", name="uq_qr_user_binding_token"),
        Index("ix_qr_user_binding_filament", "filament_id"),
        Index("ix_qr_user_binding_user", "user_id"),
        Index("ix_qr_user_binding_purge", "purge_after"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_spool_id: Mapped[int] = mapped_column(
        ForeignKey("user_spools.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False
    )
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=QrUserBindingState.ACTIVE, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_rotation_key_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retirement_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    spool: Mapped["UserSpool"] = relationship("UserSpool")
    user: Mapped["User"] = relationship("User")
    filament: Mapped["Filament"] = relationship("Filament")


class QrManufacturerBatch(Base):
    """One compact manifest and secret for a potentially very large label run."""

    __tablename__ = "qr_manufacturer_batches"
    __table_args__ = (
        CheckConstraint("mode IN ('sku', 'serialized')", name="ck_qr_batch_mode"),
        CheckConstraint("status IN ('active', 'cancelled')", name="ck_qr_batch_status"),
        CheckConstraint("total_quantity > 0", name="ck_qr_batch_quantity"),
        UniqueConstraint("public_id", name="uq_qr_batch_public_id"),
        UniqueConstraint("token_ref", name="uq_qr_batch_token_ref"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key_digest",
            name="uq_qr_batch_org_idempotency",
        ),
        Index("ix_qr_batch_org_created", "organization_id", "created_at"),
        Index("ix_qr_batch_brand_created", "brand_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token_ref: Mapped[str] = mapped_column(String(14), nullable=False)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=QrManufacturerBatchStatus.ACTIVE, nullable=False
    )
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    created_by: Mapped["User | None"] = relationship("User")
    items: Mapped[list["QrManufacturerBatchItem"]] = relationship(
        "QrManufacturerBatchItem",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="QrManufacturerBatchItem.ordinal_start",
    )


class QrManufacturerBatchItem(Base):
    """A compact SKU range inside a manufacturer batch."""

    __tablename__ = "qr_manufacturer_batch_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_qr_batch_item_quantity"),
        CheckConstraint("ordinal_start >= 0", name="ck_qr_batch_item_ordinal"),
        UniqueConstraint("batch_id", "filament_id", name="uq_qr_batch_item_filament"),
        UniqueConstraint("batch_id", "ordinal_start", name="uq_qr_batch_item_ordinal"),
        Index("ix_qr_batch_item_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("qr_manufacturer_batches.id", ondelete="CASCADE"), nullable=False
    )
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal_start: Mapped[int] = mapped_column(Integer, nullable=False)
    product_qr_code: Mapped[str] = mapped_column(String(50), nullable=False)

    batch: Mapped["QrManufacturerBatch"] = relationship(
        "QrManufacturerBatch", back_populates="items"
    )
    filament: Mapped["Filament"] = relationship("Filament")


class QrManufacturerInstanceState(Base):
    """Sparse state for claimed, revoked, or scrapped manufacturer serials."""

    __tablename__ = "qr_manufacturer_instance_states"
    __table_args__ = (
        CheckConstraint(
            "status IN ('claimed', 'revoked', 'scrapped')",
            name="ck_qr_instance_state",
        ),
        CheckConstraint(
            "(status = 'claimed' AND user_id IS NOT NULL AND user_spool_id IS NOT NULL) "
            "OR (status IN ('revoked', 'scrapped') AND user_id IS NULL "
            "AND user_spool_id IS NULL)",
            name="ck_qr_instance_binding_shape",
        ),
        CheckConstraint("ordinal >= 0", name="ck_qr_instance_ordinal"),
        UniqueConstraint("batch_id", "ordinal", name="uq_qr_instance_batch_ordinal"),
        UniqueConstraint("user_spool_id", name="uq_qr_instance_user_spool"),
        Index("ix_qr_instance_filament", "filament_id"),
        Index("ix_qr_instance_user", "user_id"),
        Index("ix_qr_instance_spool", "user_spool_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("qr_manufacturer_batches.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    filament_id: Mapped[int] = mapped_column(
        ForeignKey("filaments.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    user_spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_spools.id", ondelete="CASCADE"), nullable=True
    )
    last_operation_key_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    batch: Mapped["QrManufacturerBatch"] = relationship("QrManufacturerBatch")
    filament: Mapped["Filament"] = relationship("Filament")
    user: Mapped["User | None"] = relationship("User")
    spool: Mapped["UserSpool | None"] = relationship("UserSpool")

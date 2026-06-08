"""Bundle and BundleImport models — admin-only seed of catalog from external slicer bundles."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class BundleSource:
    """Allowed source slicers for a catalog bundle."""

    ORCA = "orca"
    PRUSA = "prusa"
    CURA = "cura"
    BAMBU = "bambu"

    ALL = (ORCA, PRUSA, CURA, BAMBU)


class BundleStatus:
    """Lifecycle states of a Bundle row."""

    PENDING = "pending"
    VALIDATED = "validated"
    IMPORTED = "imported"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class BundleImportStatus:
    """Lifecycle states of a BundleImport audit row."""

    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Bundle(Base):
    """Загруженный архив каталога принтеров (например OrcaSlicer system bundle)."""

    __tablename__ = "bundles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    uuid: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), unique=True, nullable=False, default=uuid4
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BundleStatus.PENDING,
        server_default=BundleStatus.PENDING, index=True,
    )
    validation_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_user_id])
    imports: Mapped[list["BundleImport"]] = relationship(
        "BundleImport",
        back_populates="bundle",
        cascade="all, delete-orphan",
        foreign_keys="BundleImport.bundle_id",
    )

    def __repr__(self) -> str:
        return f"<Bundle(id={self.id}, source={self.source}, status={self.status})>"


class BundleImport(Base):
    """Audit-запись каждой попытки импорта bundle."""

    __tablename__ = "bundle_imports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    bundle_id: Mapped[int] = mapped_column(
        ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    bundle: Mapped["Bundle"] = relationship(
        "Bundle", back_populates="imports", foreign_keys=[bundle_id]
    )
    started_by: Mapped["User"] = relationship("User", foreign_keys=[started_by_user_id])
    rolled_back_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[rolled_back_by_user_id]
    )

    def __repr__(self) -> str:
        return f"<BundleImport(id={self.id}, bundle_id={self.bundle_id}, status={self.status})>"

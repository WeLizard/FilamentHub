"""Persistent drafts for explicitly reviewed catalog curation."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CatalogCurationProposal(Base):
    __tablename__ = "catalog_curation_proposals"
    __table_args__ = (Index("ix_cat_cur_proposal_svc_id", "created_by_service_account_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    draft: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False)
    unmapped_facts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_facts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    coverage_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_service_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_curation_service_accounts.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_service_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_curation_service_accounts.id", ondelete="SET NULL"), nullable=True
    )
    applied_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_import_batches.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

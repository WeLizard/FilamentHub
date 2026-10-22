"""Server-side verification of quotes cited by catalog curation proposals.

Only verdicts are stored. Page text is read in memory and never persisted; the
page hash identifies which version of the page a verdict was reached on.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CatalogQuoteCheck(Base):
    __tablename__ = "catalog_curation_quote_checks"
    __table_args__ = (
        UniqueConstraint(
            "proposal_id", "scope", "sheet", "key", "field", name="uq_cc_quote_checks_fact"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_curation_proposals.id", ondelete="CASCADE"), nullable=False
    )
    # evidence | source_fact | unmapped_fact. ``sheet`` is empty for facts, whose
    # ``key`` is the filament key and ``field`` the case-folded property name.
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    sheet: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str] = mapped_column(String(120), nullable=False)
    # Hash of everything the verdict depends on (URLs, quote, claimed value). An
    # edited claim no longer matches it, so a stale verdict can never be trusted.
    claim_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    page_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CatalogImageConfirmation(Base):
    """An administrator's "checked by eye" for a claim whose proof is an image.

    Bound to the claim hash, so editing the claim withdraws the confirmation.
    """

    __tablename__ = "catalog_curation_image_confirmations"
    __table_args__ = (
        UniqueConstraint(
            "proposal_id", "scope", "sheet", "key", "field", name="uq_cc_image_confirm_fact"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_curation_proposals.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    sheet: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CatalogQuoteCheckJob(Base):
    """One coalesced pending verification per proposal (the proposal id is the key)."""

    __tablename__ = "catalog_curation_quote_jobs"

    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_curation_proposals.id", ondelete="CASCADE"), primary_key=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        index=True,
    )
    # Lease: a worker sets it before fetching, with no transaction held open.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)

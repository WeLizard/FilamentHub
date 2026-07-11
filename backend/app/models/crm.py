"""CRM-lite models for customers, versioned quotes, and accepted orders."""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.calculator_history_entry import CalculatorHistoryEntry
    from app.models.shared_quote import SharedQuote
    from app.models.user import User


class CrmQuoteStatus(str, Enum):
    """Commercial proposal lifecycle."""

    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CrmOrderStatus(str, Enum):
    """Production order lifecycle after quote acceptance."""

    NEW = "new"
    PLANNED = "planned"
    IN_PRODUCTION = "in_production"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CrmQuoteEventType(str, Enum):
    """Audit event types for a quote."""

    CREATED = "created"
    VERSION_CREATED = "version_created"
    STATUS_CHANGED = "status_changed"
    CUSTOMER_CHANGED = "customer_changed"
    SHARED = "shared"


class CrmCustomer(Base):
    """A customer owned by one FilamentHub user."""

    __tablename__ = "crm_customers"
    __table_args__ = (
        Index("ix_crm_customers_user_name", "user_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    quotes: Mapped[list["CrmQuote"]] = relationship(back_populates="customer")
    orders: Mapped[list["CrmOrder"]] = relationship(back_populates="customer")


class CrmQuote(Base):
    """A commercial proposal whose content lives in immutable versions."""

    __tablename__ = "crm_quotes"
    __table_args__ = (
        UniqueConstraint("user_id", "number", name="uq_crm_quote_user_number"),
        Index("ix_crm_quotes_user_status_updated", "user_id", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("crm_customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CrmQuoteStatus] = mapped_column(
        SQLEnum(CrmQuoteStatus, values_callable=lambda enum: [item.value for item in enum], name="crmquotestatus"),
        nullable=False,
        default=CrmQuoteStatus.DRAFT,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    customer: Mapped[CrmCustomer | None] = relationship(back_populates="quotes")
    versions: Mapped[list["CrmQuoteVersion"]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="CrmQuoteVersion.version_number",
    )
    events: Mapped[list["CrmQuoteEvent"]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="CrmQuoteEvent.created_at",
    )
    order: Mapped["CrmOrder | None"] = relationship(back_populates="quote", uselist=False)


class CrmQuoteVersion(Base):
    """Immutable snapshot of one quote revision."""

    __tablename__ = "crm_quote_versions"
    __table_args__ = (
        UniqueConstraint("quote_id", "version_number", name="uq_crm_quote_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("crm_quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_history_id: Mapped[int | None] = mapped_column(
        ForeignKey("calculator_history_entries.id", ondelete="SET NULL"), nullable=True
    )
    shared_quote_id: Mapped[int | None] = mapped_column(
        ForeignKey("shared_quotes.id", ondelete="SET NULL"), nullable=True
    )
    seller_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    customer_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calculation_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    disclaimer_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="not_offer")
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    tax_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    grand_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    quote: Mapped[CrmQuote] = relationship(back_populates="versions")
    lines: Mapped[list["CrmQuoteLine"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="CrmQuoteLine.position",
    )
    source_history: Mapped["CalculatorHistoryEntry | None"] = relationship()
    shared_quote: Mapped["SharedQuote | None"] = relationship()


class CrmQuoteLine(Base):
    """One priced line in an immutable quote version."""

    __tablename__ = "crm_quote_lines"
    __table_args__ = (
        UniqueConstraint("version_id", "position", name="uq_crm_quote_line_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("crm_quote_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="pcs")
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    source_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    version: Mapped[CrmQuoteVersion] = relationship(back_populates="lines")


class CrmQuoteEvent(Base):
    """Append-only quote audit trail."""

    __tablename__ = "crm_quote_events"
    __table_args__ = (
        Index("ix_crm_quote_events_quote_created", "quote_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("crm_quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[CrmQuoteEventType] = mapped_column(
        SQLEnum(
            CrmQuoteEventType,
            values_callable=lambda enum: [item.value for item in enum],
            name="crmquoteeventtype",
        ),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    quote: Mapped[CrmQuote] = relationship(back_populates="events")
    actor: Mapped["User | None"] = relationship()


class CrmOrder(Base):
    """A production order created from an accepted quote."""

    __tablename__ = "crm_orders"
    __table_args__ = (
        UniqueConstraint("quote_id", name="uq_crm_order_quote"),
        UniqueConstraint("user_id", "number", name="uq_crm_order_user_number"),
        Index("ix_crm_orders_user_status_updated", "user_id", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quote_id: Mapped[int] = mapped_column(
        ForeignKey("crm_quotes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("crm_customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CrmOrderStatus] = mapped_column(
        SQLEnum(CrmOrderStatus, values_callable=lambda enum: [item.value for item in enum], name="crmorderstatus"),
        nullable=False,
        default=CrmOrderStatus.NEW,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    quote: Mapped[CrmQuote] = relationship(back_populates="order")
    customer: Mapped[CrmCustomer | None] = relationship(back_populates="orders")

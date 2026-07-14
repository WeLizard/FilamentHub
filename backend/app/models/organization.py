"""Organization ownership and membership models for multi-brand companies."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.user import User


class OrganizationMemberRole(str, Enum):
    """Permission level inside a manufacturer organization."""

    OWNER = "owner"
    EDITOR = "editor"


class Organization(Base):
    """A legal/company workspace that can own multiple public brands."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), onupdate=func.now(), server_default=func.now()
    )

    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    brands: Mapped[list["Brand"]] = relationship(back_populates="organization")


class OrganizationMembership(Base):
    """A user's role and brand scope inside an organization."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_membership_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[OrganizationMemberRole] = mapped_column(
        SQLEnum(
            OrganizationMemberRole,
            values_callable=lambda values: [value.value for value in values],
            name="organizationmemberrole",
        ),
        default=OrganizationMemberRole.EDITOR,
        server_default=OrganizationMemberRole.EDITOR.value,
        nullable=False,
    )
    all_brands: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    invited_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now()
    )

    organization: Mapped["Organization"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(
        back_populates="organization_memberships", foreign_keys=[user_id]
    )
    invited_by: Mapped["User | None"] = relationship(foreign_keys=[invited_by_id])
    brand_access: Mapped[list["OrganizationBrandAccess"]] = relationship(
        back_populates="membership", cascade="all, delete-orphan"
    )


class OrganizationBrandAccess(Base):
    """Selected-brand grants for members whose all_brands flag is false."""

    __tablename__ = "organization_brand_access"
    __table_args__ = (
        UniqueConstraint("membership_id", "brand_id", name="uq_membership_brand_access"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("organization_memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )

    membership: Mapped["OrganizationMembership"] = relationship(back_populates="brand_access")
    brand: Mapped["Brand"] = relationship()

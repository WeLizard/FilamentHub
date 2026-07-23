"""User model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.brand import Brand
    from app.models.feedback import Feedback
    from app.models.filament_review import FilamentReview
    from app.models.notification import Notification
    from app.models.organization import OrganizationMembership
    from app.models.preset import Preset
    from app.models.print_profile import PrintProfile
    from app.models.printer_profile import PrinterProfile
    from app.models.subscription import Subscription
    from app.models.sync_device import SyncDevice
    from app.models.user_printer_device import UserPrinterDevice
    from app.models.user_saved_preset import UserSavedPreset
    from app.models.user_spool import UserSpool
    from app.models.wiki_feedback import WikiArticleFeedback


class UserRole(str, Enum):
    """User roles."""

    USER = "user"
    BRAND = "brand"
    MODERATOR = "moderator"
    ADMIN = "admin"


class User(Base):
    """User model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    oauth_provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.USER,
        nullable=False,
    )

    # API key for OrcaSlicer integration
    api_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)

    # Profile info
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Sync settings (разрешения на импорт/экспорт профилей)
    allow_printer_profiles_import: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_printer_profiles_export: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_print_profiles_import: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_print_profiles_export: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_filament_presets_import: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_filament_presets_export: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # allow_filament_presets_import: Разрешение на импорт filament presets из OrcaSlicer на сайт
    # allow_filament_presets_export: Разрешение на экспорт filament presets с сайта в OrcaSlicer

    # Deleted preset rule (правило обработки удалённых пресетов)
    deleted_preset_rule: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # deleted_preset_rule: "always_restore", "always_delete", "always_ask",
    # "restore_created_delete_saved", "restore_created_ask_saved"

    # Status
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Wiki editing permission
    can_edit_wiki: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Badges (список строк: ["founder", "beta_tester", "contributor", "verified"])
    badges: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # badges:
    # - "founder" - основатель (первые пользователи)
    # - "beta_tester" - бета-тестер
    # - "contributor" - контрибьютор (помог с разработкой)
    # - "verified" - верифицированный (производитель)
    # - "early_adopter" - ранний последователь
    # - "supporter" - поддержал проект

    # Brand relationship (if user is a brand)
    brand_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("brands.id"), nullable=True, index=True
    )

    # Printer relationship (user's preferred printer, optional)
    printer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("printers.id"), nullable=True, index=True
    )
    # printer_id: выбранный принтер пользователя (для фильтрации релевантных пресетов)

    # Catalog "recommend for my printer" selection (per-user, follows the account
    # across devices). FK SET NULL so deleting the printer/config auto-clears the
    # stale choice.
    recommend_physical_printer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("user_printer_devices.id", ondelete="SET NULL"), nullable=True
    )
    recommend_printer_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("printer_profiles.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # last_sync_at: время последней синхронизации с OrcaSlicer (для инкрементальной синхронизации)

    # Relationships
    brand: Mapped["Brand | None"] = relationship("Brand", foreign_keys=[brand_id])
    presets: Mapped[list["Preset"]] = relationship("Preset", back_populates="user")
    filament_reviews: Mapped[list["FilamentReview"]] = relationship(
        "FilamentReview", back_populates="user", cascade="all, delete-orphan"
    )
    saved_presets: Mapped[list["UserSavedPreset"]] = relationship(
        "UserSavedPreset", back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan", order_by="Notification.created_at.desc()"
    )
    printer_profiles: Mapped[list["PrinterProfile"]] = relationship(
        "PrinterProfile",
        foreign_keys="PrinterProfile.owner_user_id",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    print_profiles: Mapped[list["PrintProfile"]] = relationship(
        "PrintProfile", back_populates="owner", cascade="all, delete-orphan"
    )
    feedback_messages: Mapped[list["Feedback"]] = relationship(
        "Feedback", foreign_keys="Feedback.user_id", back_populates="user", cascade="all, delete-orphan"
    )
    wiki_feedback: Mapped[list["WikiArticleFeedback"]] = relationship(
        "WikiArticleFeedback", back_populates="user", cascade="all, delete-orphan"
    )
    sync_devices: Mapped[list["SyncDevice"]] = relationship(
        "SyncDevice", back_populates="user", cascade="all, delete-orphan"
    )
    printer_devices: Mapped[list["UserPrinterDevice"]] = relationship(
        "UserPrinterDevice",
        foreign_keys="UserPrinterDevice.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    spools: Mapped[list["UserSpool"]] = relationship(
        "UserSpool", back_populates="user", cascade="all, delete-orphan"
    )
    subscription: Mapped["Subscription | None"] = relationship(
        "Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    organization_memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="user",
        foreign_keys="OrganizationMembership.user_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role.value})>"

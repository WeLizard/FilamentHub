"""Pydantic schemas for User."""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.organization import OrganizationMemberRole
from app.models.user import UserRole


def validate_password_strength(password: str) -> str:
    """Validate password has at least one letter and one digit."""
    if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', password):
        raise ValueError('Пароль должен содержать хотя бы одну букву')
    if not re.search(r'\d', password):
        raise ValueError('Пароль должен содержать хотя бы одну цифру')
    return password


class UserBase(BaseModel):
    """Base schema for User."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)


class UserCreate(UserBase):
    """Schema for creating User."""

    password: str = Field(..., min_length=8, max_length=100)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)
    # Роль всегда "user" при создании - роль "brand" присваивается только через процесс верификации
    role: Literal["user"] = Field(default="user")


class UserUpdate(BaseModel):
    """Schema for updating User."""

    email: EmailStr | None = None
    username: str | None = Field(None, min_length=3, max_length=100)
    full_name: str | None = Field(None, max_length=255)
    country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    password: str | None = Field(None, min_length=8, max_length=100)

    @field_validator('password')
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_password_strength(v)
        return v
    printer_id: int | None = Field(None, gt=0, description="ID выбранного принтера из каталога. Передайте null чтобы сбросить выбор.")
    recommend_physical_printer_id: int | None = Field(None, gt=0, description="Выбранный физический принтер для рекомендаций каталога. null — сброс.")
    recommend_printer_profile_id: int | None = Field(None, gt=0, description="Выбранная конфигурация для рекомендаций каталога. null — сброс.")
    # Sync settings
    allow_filament_presets_import: bool | None = None
    allow_filament_presets_export: bool | None = None
    allow_printer_profiles_import: bool | None = None
    allow_printer_profiles_export: bool | None = None
    allow_print_profiles_import: bool | None = None
    allow_print_profiles_export: bool | None = None
    auto_import_local_presets: bool | None = None
    sync_printer_endpoints: bool | None = None


class UserSettingsUpdate(BaseModel):
    """Schema for updating user sync settings."""

    allow_filament_presets_import: bool | None = None
    allow_filament_presets_export: bool | None = None
    allow_printer_profiles_import: bool | None = None
    allow_printer_profiles_export: bool | None = None
    allow_print_profiles_import: bool | None = None
    allow_print_profiles_export: bool | None = None
    auto_import_local_presets: bool | None = None
    sync_printer_endpoints: bool | None = None


class UserPreferencesResponse(BaseModel):
    """Account-wide preferences shared by free and paid product areas."""

    currency: str | None = None


class UserPreferencesUpdate(BaseModel):
    """Update account-wide preferences."""

    currency: str = Field(..., pattern=r"^[A-Z]{3}$")


class UserPasswordUpdate(BaseModel):
    """Schema for updating user password."""

    current_password: str | None = Field(None, min_length=1, description="Текущий пароль (не нужен для OAuth-аккаунтов без пароля)")
    new_password: str = Field(..., min_length=8, max_length=100, description="Новый пароль")

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class UserEmailUpdate(BaseModel):
    """Schema for updating user email."""

    new_email: EmailStr = Field(..., description="Новый email")
    language: str | None = Field(
        default=None,
        pattern=r"^[a-z]{2}$",
        description="Interface language of the request, used for the confirmation email",
    )


class UserUsernameUpdate(BaseModel):
    """Schema for updating user username."""

    new_username: str = Field(..., min_length=3, max_length=100, description="Новый username")


class UserResponse(UserBase):
    """Schema for User response."""

    # Output schema: don't re-validate stored emails (legacy/seed rows may use
    # reserved TLDs like .local). Input validation stays strict via UserCreate.
    email: str
    id: int
    role: UserRole
    api_key: str | None = None
    active: bool
    email_verified: bool
    avatar_url: str | None = None  # Загруженный аватар пользователя
    country: str | None = None
    brand_id: int | None = None
    active_organization_id: int | None = None
    brand_name: str | None = None  # Название бренда (для админки)
    printer_id: int | None = None  # ID выбранного принтера из каталога
    recommend_physical_printer_id: int | None = None
    recommend_printer_profile_id: int | None = None
    # Sync settings
    allow_filament_presets_import: bool = True
    allow_filament_presets_export: bool = True
    allow_printer_profiles_import: bool = True
    allow_printer_profiles_export: bool = True
    allow_print_profiles_import: bool = True
    allow_print_profiles_export: bool = True
    auto_import_local_presets: bool | None = None
    sync_printer_endpoints: bool | None = None
    oauth_provider: str | None = None
    has_password: bool = False
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None
    legal_onboarding_required: bool = False
    required_legal_acceptances: list[
        Literal["terms", "personal_data_consent"]
    ] = Field(default_factory=list)
    legal_document_pack: Literal["ru", "eu", "intl"] | None = None
    # True when the account accepted some earlier version, so the mandatory
    # screen is a re-ask rather than a first-time one.
    legal_previously_accepted: bool = False
    # Calculator Pro entitlement (effective flag + subscription summary).
    # Named to avoid colliding with the ORM `subscription` relationship (from_attributes);
    # serialized to the client as `subscription`.
    has_calculator_access: bool = False
    subscription_info: dict | None = Field(default=None, serialization_alias="subscription")

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        instance = super().model_validate(obj, **kwargs)
        # Вычисляем has_password из password_hash (не передаём сам hash клиенту)
        if hasattr(obj, "password_hash"):
            instance.has_password = bool(obj.password_hash)
        # Effective calculator (Pro) access + subscription summary (see subscription_service).
        if hasattr(obj, "role"):
            from app.services.subscription_service import pro_active, subscription_summary
            instance.has_calculator_access = pro_active(obj)
            instance.subscription_info = subscription_summary(obj)
        if hasattr(obj, "terms_version_accepted"):
            from app.services.legal_acceptance_service import (
                required_current_legal_acceptances,
            )

            required_acceptances = required_current_legal_acceptances(obj)
            instance.legal_onboarding_required = bool(required_acceptances)
            instance.required_legal_acceptances = [
                document_type.value
                for document_type in required_acceptances
            ]
            instance.legal_previously_accepted = bool(obj.terms_version_accepted)
        return instance


class UserListResponse(BaseModel):
    """Paginated admin user list."""

    items: list[UserResponse]
    total: int
    page: int
    size: int
    total_pages: int


class ActiveBrandUpdate(BaseModel):
    """Select or clear the user's active workspace."""

    organization_id: int | None = None
    brand_id: int | None = Field(
        None,
        gt=0,
        description="Accessible brand ID, or null to clear the active workspace",
    )


class AccessibleBrandResponse(BaseModel):
    """A brand workspace available to the current user."""

    brand_id: int
    brand_name: str
    brand_slug: str
    organization_id: int
    organization_name: str
    membership_role: OrganizationMemberRole | None = None
    is_active: bool


class Token(BaseModel):
    """Schema for JWT token."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    legal_onboarding_required: bool = False


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Schema for logout request."""

    refresh_token: str | None = None


class RefreshTokenResponse(BaseModel):
    """Schema for refresh token response."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class PluginSessionTokenResponse(BaseModel):
    """Short-lived capability used by the OrcaSlicer plugin bridge."""

    plugin_token: str
    expires_in: int
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Schema for token payload."""

    sub: str | None = None  # user email
    user_id: int | None = None
    role: UserRole | None = None


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: str  # email или username (без учёта регистра)
    password: str


class RegisterRequest(UserCreate):
    """Schema for register request."""

    recaptcha_token: str | None = Field(None, description="reCAPTCHA v3 token")
    terms_accepted: Literal[True]
    personal_data_consent: Literal[True]
    terms_version: str = Field(..., max_length=32)
    personal_data_consent_version: str = Field(..., max_length=32)
    privacy_policy_version: str = Field(..., max_length=32)
    legal_language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    legal_pack: Literal["ru", "eu", "intl"] | None = None


class LegalRequirementsResponse(BaseModel):
    """Current public legal document versions and routes."""

    legal_pack: Literal["ru", "eu", "intl"]
    edition_id: str
    terms_version: str
    personal_data_consent_version: str
    privacy_policy_version: str
    terms_url: str
    personal_data_consent_url: str
    privacy_policy_url: str
    legal_update_effective_date: date
    legal_update_note: str = ""


class AuthMethodsResponse(BaseModel):
    """Authentication capabilities enabled for the current request region."""

    access_region: Literal["ru", "intl", "unknown"]
    local_login: bool = True
    local_registration: bool = True
    oauth_providers: list[Literal["google", "yandex"]]
    registration_captcha: Literal["recaptcha"] | None = None


class LegalAcceptanceRequest(BaseModel):
    """Separate affirmative choices for the current mandatory documents."""

    terms_accepted: Literal[True] | None = None
    personal_data_consent: Literal[True] | None = None
    terms_version: str = Field(..., max_length=32)
    personal_data_consent_version: str = Field(..., max_length=32)
    privacy_policy_version: str = Field(..., max_length=32)
    legal_language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    legal_pack: Literal["ru", "eu", "intl"] | None = None


class LegalDocumentResponse(BaseModel):
    """One immutable legal-document translation from a published edition."""

    legal_pack: Literal["ru", "eu", "intl"]
    edition_id: str
    document_type: Literal["terms", "personal_data_consent", "privacy_policy"]
    language: Literal["ru", "en", "zh"]
    title: str
    revision_label: str
    markdown: str


class OAuthUrlResponse(BaseModel):
    """Schema for OAuth authorization URL response."""

    url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """Schema for OAuth callback request."""

    code: str
    state: str


class APIKeyResponse(BaseModel):
    """Schema for API key response."""

    api_key: str
    message: str = "API key generated. Use it for OrcaSlicer integration."


class AccountDeleteRequest(BaseModel):
    """Schema for account deletion request with options."""

    delete_reviews: bool = Field(
        default=False,
        description="Полностью удалить отзывы (True) или анонимизировать (False)"
    )
    release_brand_representation: bool = Field(
        default=False,
        description="Снять официальное представительство, сохранив бренд, каталог и QR"
    )
    delete_brand_if_sole_representative: bool | None = Field(
        default=None,
        description="Deprecated compatibility alias for release_brand_representation",
        deprecated=True,
    )
    password_confirm: str = Field(
        ...,
        description="Подтверждение пароля для удаления аккаунта"
    )


class AccountDeletionStats(BaseModel):
    """Schema for account deletion statistics."""

    presets_count: int = Field(description="Количество созданных пресетов")
    official_presets_count: int = Field(description="Количество официальных пресетов")
    approved_presets_count: int = Field(description="Количество одобренных пресетов")
    presets_used_by_others_count: int = Field(description="Количество пресетов, сохраненных другими пользователями")
    reviews_count: int = Field(description="Количество отзывов")
    saved_presets_count: int = Field(description="Количество сохраненных пресетов")
    brand_requests_count: int = Field(description="Количество заявок на верификацию бренда")
    is_brand_representative: bool = Field(description="Является ли пользователь представителем бренда")
    brand_other_representatives_count: int = Field(description="Количество других представителей бренда (если есть)")
    organization_memberships_count: int = 0
    owned_organizations_count: int = 0
    sole_owner_organizations_count: int = 0
    ownership_transfer_required: bool = False
    representation_release_available: bool = False
    spools_count: int = Field(default=0, description="Количество катушек в личной библиотеке")
    printers_count: int = Field(default=0, description="Количество заведённых принтеров")
    printer_profiles_count: int = Field(default=0, description="Количество конфигураций принтеров")
    print_profiles_count: int = Field(default=0, description="Количество профилей печати")
    calculations_count: int = Field(default=0, description="Количество сохранённых расчётов")
    quotes_count: int = Field(default=0, description="Количество коммерческих предложений")
    customers_count: int = Field(default=0, description="Количество клиентов в записной книжке")
    slice_reports_count: int = Field(default=0, description="Количество сведений о нарезках")


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password request."""

    email: EmailStr = Field(..., description="Email пользователя для восстановления пароля")
    language: str | None = Field(
        default=None,
        pattern=r"^[a-z]{2}$",
        description="Interface language of the request, used for the reset email",
    )


class ForgotPasswordResponse(BaseModel):
    """Schema for forgot password response."""

    message: str = Field(
        default="Если указанный email существует в системе, на него будет отправлена инструкция по восстановлению пароля.",
        description="Сообщение о результате запроса"
    )


class ResetPasswordRequest(BaseModel):
    """Schema for reset password request."""

    token: str = Field(..., description="Токен восстановления пароля")
    new_password: str = Field(..., min_length=8, max_length=100, description="Новый пароль")

    @field_validator('new_password')
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class ResetPasswordResponse(BaseModel):
    """Schema for reset password response."""

    message: str = Field(default="Пароль успешно изменён", description="Сообщение о результате")


class EmailChangeResponse(BaseModel):
    """Response after requesting email change — email is NOT changed yet."""

    message: str = Field(
        default="На новый email отправлено письмо с подтверждением.",
        description="Сообщение о результате",
    )


class ConfirmEmailChangeResponse(BaseModel):
    """Response after confirming email change."""

    message: str = Field(default="Email успешно изменён", description="Сообщение о результате")

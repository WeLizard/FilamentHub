"""Editable catalog proposals and reviewable source evidence."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.catalog_import import CatalogImportDraft, CatalogImportPreview
from app.schemas.catalog_raw_fact import validate_public_http_url, validate_subject


def _clean_quote(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Quote must not be blank")
    return value


class _QuotedSource(BaseModel):
    """Optional verbatim quote and image reference; absent on legacy proposals."""

    quote: str | None = Field(default=None, max_length=500)
    image_url: AnyHttpUrl | None = None

    @field_validator("quote")
    @classmethod
    def require_non_blank_quote(cls, value: str | None) -> str | None:
        return _clean_quote(value)

    @field_validator("image_url")
    @classmethod
    def reject_image_credentials(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        return validate_public_http_url(value) if value is not None else None


class _QuotedFact(_QuotedSource):
    unit: str | None = Field(default=None, max_length=50)
    conditions: str | None = Field(default=None, max_length=300)
    subject: str | None = Field(default=None, max_length=130)

    @field_validator("unit", "conditions")
    @classmethod
    def blank_means_absent(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("subject")
    @classmethod
    def check_subject(cls, value: str | None) -> str | None:
        return validate_subject(value) if value is not None else None


class CatalogFieldEvidence(_QuotedSource):
    model_config = ConfigDict(extra="forbid")

    sheet: Literal["Brands", "Filaments", "BrandMarkets", "FilamentMarkets", "Presets"]
    key: str = Field(min_length=1, max_length=255)
    field: str = Field(min_length=1, max_length=100)
    kind: Literal["direct", "inferred"]
    source_urls: list[AnyHttpUrl] = Field(min_length=1, max_length=10)
    explanation: str | None = Field(default=None, max_length=2000)

    @field_validator("source_urls")
    @classmethod
    def reject_credentials(cls, value: list[AnyHttpUrl]) -> list[AnyHttpUrl]:
        if any(url.username is not None or url.password is not None for url in value):
            raise ValueError("Source URLs must not contain credentials")
        return value

    @model_validator(mode="after")
    def explain_inference(self) -> "CatalogFieldEvidence":
        if self.kind == "inferred" and not (self.explanation or "").strip():
            raise ValueError("Inferred values require an explanation")
        return self


class CatalogUnmappedFact(_QuotedFact):
    """A manufacturer fact that the current filament card cannot represent."""

    model_config = ConfigDict(extra="forbid")

    filament_key: str = Field(min_length=1, max_length=255)
    property_name: str = Field(min_length=1, max_length=120)
    value_summary: str = Field(min_length=1, max_length=500)
    explanation: str | None = Field(default=None, max_length=1000)
    source_urls: list[AnyHttpUrl] = Field(min_length=1, max_length=10)
    # Facts stay private until an administrator explicitly chooses to publish
    # them. ``kind`` is optional so proposals created before this contract load.
    public_action: Literal["none", "publish", "remove"] = "none"
    kind: Literal["direct", "inferred"] | None = None

    @field_validator("filament_key", "property_name", "value_summary")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("explanation")
    @classmethod
    def normalize_explanation(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("source_urls")
    @classmethod
    def reject_credentials(cls, value: list[AnyHttpUrl]) -> list[AnyHttpUrl]:
        if any(url.username is not None or url.password is not None for url in value):
            raise ValueError("Source URLs must not contain credentials")
        return value

    @model_validator(mode="after")
    def validate_public_action(self) -> "CatalogUnmappedFact":
        if self.public_action == "publish":
            if self.kind is None:
                raise ValueError("Published facts must identify direct or inferred evidence")
            if self.kind == "inferred" and not (self.explanation or "").strip():
                raise ValueError("Inferred published facts require an explanation")
        return self


class CatalogSourceFact(_QuotedFact):
    """A source-supported manufacturer fact and its review disposition."""

    model_config = ConfigDict(extra="forbid")

    filament_key: str = Field(min_length=1, max_length=255)
    property_name: str = Field(min_length=1, max_length=120)
    value_summary: str = Field(min_length=1, max_length=500)
    source_urls: list[AnyHttpUrl] = Field(min_length=1, max_length=10)
    disposition: Literal["mapped", "unsupported", "unresolved"]
    mapped_fields: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("filament_key", "property_name", "value_summary")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("mapped_fields")
    @classmethod
    def normalize_mapped_fields(cls, value: list[str]) -> list[str]:
        normalized = [field.strip() for field in value]
        if any(not field for field in normalized):
            raise ValueError("Mapped field names must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Mapped field names must be unique")
        return normalized

    @field_validator("source_urls")
    @classmethod
    def reject_credentials(cls, value: list[AnyHttpUrl]) -> list[AnyHttpUrl]:
        if any(url.username is not None or url.password is not None for url in value):
            raise ValueError("Source URLs must not contain credentials")
        return value

    @model_validator(mode="after")
    def match_disposition_to_fields(self) -> "CatalogSourceFact":
        if self.disposition == "mapped" and not self.mapped_fields:
            raise ValueError("Mapped facts must name at least one catalog field")
        if self.disposition != "mapped" and self.mapped_fields:
            raise ValueError("Unsupported or unresolved facts cannot name mapped fields")
        return self


class CatalogSourceFactReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filament_key: str
    total: int = Field(ge=0)
    mapped: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    captured: int = Field(ge=0)
    coverage_percent: int = Field(ge=0, le=100)


class CatalogCurationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    draft: CatalogImportDraft
    evidence: list[CatalogFieldEvidence] = Field(default_factory=list, max_length=50000)
    unmapped_facts: list[CatalogUnmappedFact] = Field(default_factory=list, max_length=2000)
    source_facts: list[CatalogSourceFact] = Field(default_factory=list, max_length=20000)
    coverage_note: str = Field(min_length=1, max_length=10000)


class CatalogCurationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    draft: CatalogImportDraft | None = None
    evidence: list[CatalogFieldEvidence] | None = Field(default=None, max_length=50000)
    unmapped_facts: list[CatalogUnmappedFact] | None = Field(default=None, max_length=2000)
    source_facts: list[CatalogSourceFact] | None = Field(default=None, max_length=20000)
    coverage_note: str | None = Field(default=None, min_length=1, max_length=10000)


class CatalogCurationRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)


class CatalogCurationApply(CatalogCurationRevision):
    confirmation_token: str = Field(min_length=1, max_length=4096)


class CatalogCurationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: Literal["draft", "applied"]
    revision: int
    created_by_user_id: int | None
    created_by_service_account_id: int | None = None
    updated_by_user_id: int | None = None
    updated_by_service_account_id: int | None = None
    created_at: datetime
    updated_at: datetime
    applied_batch_id: int | None


class CatalogCurationDetail(CatalogCurationSummary):
    draft: CatalogImportDraft
    evidence: list[CatalogFieldEvidence]
    unmapped_facts: list[CatalogUnmappedFact]
    source_facts: list[CatalogSourceFact]
    coverage_note: str


class CatalogCurationListItem(CatalogCurationSummary):
    """A proposal row with what a reviewer needs to tell proposals apart."""

    brand_name: str | None = None
    filament_count: int = 0
    author_name: str | None = None


class CatalogCurationList(BaseModel):
    items: list[CatalogCurationListItem]
    total: int


class CatalogCurationPreview(CatalogImportPreview):
    proposal_id: int
    revision: int
    unmapped_facts: list[CatalogUnmappedFact]
    source_facts: list[CatalogSourceFact]
    source_facts_review: list[CatalogSourceFactReview]


QuoteCheckStatus = Literal[
    "verified",
    "quote_not_found",
    "value_not_in_quote",
    "source_unavailable",
    "image_only",
    "not_official_domain",
    "quote_too_short",
    "pending",
]


class CatalogQuoteCheckItem(BaseModel):
    scope: Literal["evidence", "source_fact", "unmapped_fact"]
    # Identity of the claim: sheet/key/field for evidence; for facts the sheet is
    # empty, ``key`` is the filament key and ``field`` the case-folded property name.
    sheet: str
    key: str
    field: str
    status: QuoteCheckStatus
    reason: str | None = None
    url: str | None = None
    checked_at: datetime | None = None
    # An administrator has looked at the image and accepted this claim.
    confirmed: bool = False
    # False for a quote found only in a legacy ``explanation``: shown, never blocking.
    gating: bool


class CatalogQuoteCheckSummary(BaseModel):
    total: int = Field(ge=0)
    verified: int = Field(ge=0)
    quote_not_found: int = Field(ge=0)
    value_not_in_quote: int = Field(ge=0)
    source_unavailable: int = Field(ge=0)
    image_only: int = Field(ge=0)
    not_official_domain: int = Field(ge=0)
    quote_too_short: int = Field(ge=0)
    pending: int = Field(ge=0)
    verified_percent: int = Field(ge=0, le=100)


class CatalogQuoteImageConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["evidence", "source_fact", "unmapped_fact"]
    sheet: str = Field(default="", max_length=32)
    key: str = Field(min_length=1, max_length=255)
    field: str = Field(min_length=1, max_length=120)
    confirmed: bool


class CatalogQuoteCheckReport(BaseModel):
    # Verified claims are counted in the summary but not listed, which keeps the
    # report small on large proposals.
    items: list[CatalogQuoteCheckItem]
    summary: CatalogQuoteCheckSummary
    job_pending: bool


class CatalogCurationServiceAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=90)
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Expiration must include a timezone")
        normalized = value.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if normalized <= now or normalized > now + timedelta(days=365):
            raise ValueError("Expiration must be within the next 365 days")
        return normalized


class CatalogCurationServiceAccountSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by_user_id: int | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class CatalogCurationServiceAccountCreated(BaseModel):
    account: CatalogCurationServiceAccountSummary
    # The cleartext credential is intentionally available only in this response.
    token: str


class CatalogCurationServiceAccountList(BaseModel):
    items: list[CatalogCurationServiceAccountSummary]
    total: int

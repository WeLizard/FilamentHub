"""Raw manufacturer fact: one quoted statement from one source page.

Raw facts are collected freely and kept outside the database, in the git-ignored
``backend/curation_staging/``. The format is deliberately open: property and
material type names are recorded exactly as the source writes them.
"""

import re
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

SUBJECT_PATTERN = re.compile(r"^(?:brand|(?:line|variant):\S[^\n]{0,118})$")


def validate_subject(value: str) -> str:
    """Accept ``brand``, ``line:<name>`` or ``variant:<key>``."""
    value = value.strip()
    if not SUBJECT_PATTERN.fullmatch(value):
        raise ValueError("Subject must be 'brand', 'line:<name>' or 'variant:<key>'")
    return value


def validate_public_http_url(value: AnyHttpUrl) -> AnyHttpUrl:
    if value.username is not None or value.password is not None:
        raise ValueError("URLs must not contain credentials")
    return value


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class CatalogRawFact(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brand: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=130)
    page_url: AnyHttpUrl
    image_url: AnyHttpUrl | None = None
    quote: str = Field(min_length=1, max_length=500)
    property_source_name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=500)
    unit: str | None = Field(default=None, max_length=50)
    conditions: str | None = Field(default=None, max_length=300)
    material_type_source_name: str | None = Field(default=None, max_length=200)
    collected_at: datetime | None = None

    @field_validator("subject")
    @classmethod
    def check_subject(cls, value: str) -> str:
        return validate_subject(value)

    @field_validator("page_url", "image_url")
    @classmethod
    def check_url(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        return validate_public_http_url(value) if value is not None else None

    @field_validator("quote", "property_source_name", "value")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value

    @field_validator("unit", "conditions", "material_type_source_name")
    @classmethod
    def blank_means_absent(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("collected_at must include a timezone")
        return value
